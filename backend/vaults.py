import shutil
import sqlite3
from pathlib import Path

import yaml

from db.sqlite_operator import allocate_storage_id, init_database
from runtime_context import WorkspaceContext, get_runtime_context
from utils import atomic_write_text


VAULT_LOCAL_DIRS = (
    "vault/assets",
    "vault/notes",
    "db",
    "review",
    "wd-tags",
    "ui_cache/thumbnails",
    "logs/raw",
    "logs/structured",
    "queues",
    "batches",
    "input",
    "local_ingest",
    "online_ingest",
)


def vault_id_slug(value: str) -> str:
    cleaned = "".join(ch.casefold() if ch.isalnum() else "-" for ch in str(value or "").strip())
    return "-".join(part for part in cleaned.split("-") if part) or "vault"


def _ctx(ctx: WorkspaceContext | None = None) -> WorkspaceContext:
    return ctx or get_runtime_context()


def _config_path(ctx: WorkspaceContext | None = None) -> Path:
    return _ctx(ctx).config_path


def _config_root(ctx: WorkspaceContext | None = None) -> Path:
    return _ctx(ctx).root


def _read_config(ctx: WorkspaceContext | None = None) -> dict:
    config_path = _config_path(ctx)
    if not config_path.exists():
        return {}
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _write_config(config: dict, ctx: WorkspaceContext | None = None):
    atomic_write_text(_config_path(ctx), yaml.safe_dump(config, sort_keys=False, allow_unicode=True))


def _resolve_config_path(path: str | Path, ctx: WorkspaceContext | None = None) -> Path:
    value = Path(path)
    return value.resolve() if value.is_absolute() else (_config_root(ctx) / value).resolve()


def _default_vault_entry() -> dict:
    return {"name": "Default", "root": "data/vaults/default"}


def _ensure_vault_registry(config: dict) -> dict:
    vaults = config.get("vaults")
    if not isinstance(vaults, dict) or not vaults:
        config["vaults"] = {"default": _default_vault_entry()}
        config["active_vault"] = "default"
    elif "active_vault" not in config or str(config.get("active_vault") or "") not in vaults:
        config["active_vault"] = "default" if "default" in vaults else sorted(vaults.keys())[0]
    return config


def _has_vault_registry(config: dict) -> bool:
    return isinstance(config.get("vaults"), dict) and bool(config.get("vaults"))


def vault_root(entry: dict, ctx: WorkspaceContext | None = None) -> Path:
    return _resolve_config_path(entry.get("root") or "data/vaults/default", ctx)


def vault_db_path(root: Path) -> Path:
    return root / "db" / "lmz_main.db"


def create_vault_layout(root: Path, initialize_db: bool = True):
    for relative in VAULT_LOCAL_DIRS:
        (root / relative).mkdir(parents=True, exist_ok=True)
    if initialize_db:
        conn = init_database(vault_db_path(root))
        conn.close()


def vault_list(ctx: WorkspaceContext | None = None) -> list[dict]:
    config = _ensure_vault_registry(_read_config(ctx))
    active = str(config.get("active_vault") or "default")
    items = []
    for vault_id, entry in sorted(config.get("vaults", {}).items()):
        root = vault_root(entry, ctx)
        db_path = vault_db_path(root)
        item_count = 0
        if db_path.exists():
            try:
                conn = sqlite3.connect(db_path)
                item_count = int(conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] or 0)
                conn.close()
            except sqlite3.Error:
                item_count = 0
        items.append({
            "id": vault_id,
            "name": str(entry.get("name") or vault_id),
            "root": str(root),
            "config_root": str(_config_root(ctx)),
            "active": vault_id == active,
            "exists": root.exists(),
            "db_path": str(db_path),
            "item_count": item_count,
        })
    return items


def active_vault_id(ctx: WorkspaceContext | None = None) -> str:
    config = _ensure_vault_registry(_read_config(ctx))
    return str(config.get("active_vault") or "default")


def create_vault(name: str, vault_id: str | None = None, ctx: WorkspaceContext | None = None) -> dict:
    config = _ensure_vault_registry(_read_config(ctx))
    vaults = config["vaults"]
    clean_id = vault_id_slug(vault_id or name)
    if clean_id in vaults:
        raise ValueError(f"vault already exists: {clean_id}")
    entry = {"name": str(name or clean_id).strip() or clean_id, "root": f"data/vaults/{clean_id}"}
    root = vault_root(entry, ctx)
    create_vault_layout(root, initialize_db=True)
    vaults[clean_id] = entry
    _write_config(config, ctx)
    return {"status": "success", "vault": clean_id, "items": vault_list(ctx)}


def rename_vault(vault_id: str, name: str, ctx: WorkspaceContext | None = None) -> dict:
    config = _ensure_vault_registry(_read_config(ctx))
    vault_id = vault_id_slug(vault_id)
    if vault_id not in config["vaults"]:
        raise KeyError(f"vault not found: {vault_id}")
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("vault name is required")
    config["vaults"][vault_id]["name"] = clean_name
    _write_config(config, ctx)
    return {"status": "success", "items": vault_list(ctx)}


def set_active_vault(vault_id: str, ctx: WorkspaceContext | None = None) -> dict:
    config = _ensure_vault_registry(_read_config(ctx))
    vault_id = vault_id_slug(vault_id)
    if vault_id not in config["vaults"]:
        raise KeyError(f"vault not found: {vault_id}")
    root = vault_root(config["vaults"][vault_id], ctx)
    if not root.exists():
        raise ValueError(f"vault root does not exist: {root}")
    config["active_vault"] = vault_id
    _write_config(config, ctx)

    # Dynamic dynamic-vault switching runtime updates
    from runtime_context import reload_runtime_context
    from db.search_manager import search_manager
    from metadata_index import restart_metadata_watchdog

    new_ctx = reload_runtime_context()
    search_manager.reset_all()
    restart_metadata_watchdog(new_ctx)

    return {"status": "success", "active": vault_id, "restart_required": False, "items": vault_list()}


def _vault_non_empty(root: Path) -> bool:
    for path in root.rglob("*"):
        if path.is_file():
            return True
    return False


def delete_vault(vault_id: str, confirm: bool = False, ctx: WorkspaceContext | None = None) -> dict:
    config = _ensure_vault_registry(_read_config(ctx))
    vault_id = vault_id_slug(vault_id)
    if vault_id == str(config.get("active_vault") or "default"):
        raise ValueError("cannot delete active vault")
    if vault_id not in config["vaults"]:
        raise KeyError(f"vault not found: {vault_id}")
    root = vault_root(config["vaults"][vault_id], ctx)
    if root.exists() and _vault_non_empty(root) and not confirm:
        raise ValueError("vault is not empty; pass confirm=true")
    if root.exists():
        shutil.rmtree(root)
    del config["vaults"][vault_id]
    _write_config(config, ctx)
    return {"status": "success", "items": vault_list(ctx)}


def _copy_if_exists(source: Path, target: Path) -> bool:
    if not source.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


def _item_paths(root: Path, item_hash: str, storage_id: str, ext: str, mime_type: str) -> dict[str, Path]:
    shard = str(item_hash)[:2] or "00"
    video_suffix = "_video" if str(mime_type or "").startswith("video/") else ""
    return {
        "asset": root / "vault" / "assets" / shard / f"{storage_id}{ext}",
        "note": root / "vault" / "notes" / shard / f"{storage_id}.md",
        "wd": root / "wd-tags" / shard / f"{storage_id}.json",
        "thumb": root / "ui_cache" / "thumbnails" / shard / f"{storage_id}{video_suffix}.jpg",
    }


def preview_vault_merge(target_id: str, source_ids: list[str], ctx: WorkspaceContext | None = None) -> dict:
    config = _ensure_vault_registry(_read_config(ctx))
    vaults = config["vaults"]
    target_id = vault_id_slug(target_id)
    sources = [vault_id_slug(value) for value in source_ids]
    if not sources:
        raise ValueError("source vault ids are required")
    if target_id in sources:
        raise ValueError("target cannot be a source")
    if target_id not in vaults:
        raise KeyError(f"vault not found: {target_id}")
    target_db = vault_db_path(vault_root(vaults[target_id], ctx))
    target_hashes = set()
    if target_db.exists():
        conn = sqlite3.connect(target_db)
        target_hashes = {row[0] for row in conn.execute("SELECT hash FROM items").fetchall()}
        conn.close()
    payload = {"target": target_id, "sources": [], "total_items": 0, "duplicates": 0, "importable": 0}
    for source_id in sources:
        if source_id not in vaults:
            raise KeyError(f"vault not found: {source_id}")
        source_db = vault_db_path(vault_root(vaults[source_id], ctx))
        rows = []
        if source_db.exists():
            conn = sqlite3.connect(source_db)
            rows = conn.execute("SELECT hash FROM items").fetchall()
            conn.close()
        total = len(rows)
        duplicates = sum(1 for (item_hash,) in rows if item_hash in target_hashes)
        payload["sources"].append({"id": source_id, "items": total, "duplicates": duplicates, "importable": total - duplicates})
        payload["total_items"] += total
        payload["duplicates"] += duplicates
        payload["importable"] += total - duplicates
    return payload


def merge_vaults(target_id: str, source_ids: list[str], ctx: WorkspaceContext | None = None) -> dict:
    import re
    preview = preview_vault_merge(target_id, source_ids, ctx)
    config = _ensure_vault_registry(_read_config(ctx))
    vaults = config["vaults"]
    target_root = vault_root(vaults[vault_id_slug(target_id)], ctx)
    target_conn = init_database(vault_db_path(target_root))
    try:
        imported = 0
        skipped = 0
        columns = [
            "hash", "original_filename", "file_extension", "mime_type", "size_bytes",
            "date_added", "source_url", "source_url_norm", "platform", "source_artist",
            "phash", "audio_hash", "visual_embedding", "width", "height", "storage_id",
        ]
        select_sql = f"SELECT {', '.join(columns)} FROM items"
        insert_sql = f"INSERT INTO items({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})"
        for source_id in [vault_id_slug(value) for value in source_ids]:
            source_root = vault_root(vaults[source_id], ctx)
            source_db = vault_db_path(source_root)
            if not source_db.exists():
                continue
            source_conn = sqlite3.connect(source_db)
            try:
                for row in source_conn.execute(select_sql).fetchall():
                    row = list(row)
                    item_hash = row[0]
                    if target_conn.execute("SELECT 1 FROM items WHERE hash = ?", (item_hash,)).fetchone():
                        skipped += 1
                        continue
                    old_storage_id = row[15]
                    new_storage_id = allocate_storage_id(target_conn)
                    row[15] = new_storage_id
                    target_conn.execute(insert_sql, row)
                    ext = row[2] or ""
                    mime_type = row[3] or ""
                    old_paths = _item_paths(source_root, item_hash, old_storage_id, ext, mime_type)
                    new_paths = _item_paths(target_root, item_hash, new_storage_id, ext, mime_type)
                    _copy_if_exists(old_paths["asset"], new_paths["asset"])
                    _copy_if_exists(old_paths["wd"], new_paths["wd"])
                    _copy_if_exists(old_paths["thumb"], new_paths["thumb"])
                    if _copy_if_exists(old_paths["note"], new_paths["note"]):
                        text = new_paths["note"].read_text(encoding="utf-8", errors="ignore")
                        pattern = re.compile(r"\b" + re.escape(str(old_storage_id)) + r"\b")
                        text = pattern.sub(str(new_storage_id), text)
                        new_paths["note"].write_text(text, encoding="utf-8")
                    imported += 1
            finally:
                source_conn.close()
        target_conn.commit()
    except Exception:
        target_conn.rollback()
        raise
    finally:
        target_conn.close()
    preview.update({"status": "success", "imported": imported, "skipped": skipped})
    return preview


def migrate_legacy_layout(copy: bool = True, overwrite: bool = False, ctx: WorkspaceContext | None = None) -> dict:
    raw_config = _read_config(ctx)
    paths = raw_config.get("paths", {}) if isinstance(raw_config.get("paths"), dict) else {}
    config = _ensure_vault_registry(raw_config)
    target_root = vault_root(config["vaults"]["default"], ctx)
    if target_root.exists() and any(target_root.iterdir()) and not overwrite:
        raise ValueError(f"default vault already exists: {target_root}")
    create_vault_layout(target_root, initialize_db=False)

    def source_dir_for(key: str, fallback: str, parent_of_file: bool = False) -> Path:
        source = _resolve_config_path(paths.get(key) or fallback, ctx)
        return source.parent if parent_of_file else source

    mappings = {
        source_dir_for("vault", "data/vault"): target_root / "vault",
        source_dir_for("db", "data/db/lmz_main.db", parent_of_file=True): target_root / "db",
        source_dir_for("review", "data/review"): target_root / "review",
        source_dir_for("wd_tags", "data/wd-tags"): target_root / "wd-tags",
        source_dir_for("thumbnails", "data/ui_cache/thumbnails"): target_root / "ui_cache" / "thumbnails",
        source_dir_for("logs", "logs"): target_root / "logs",
        source_dir_for("queues", "data/queues"): target_root / "queues",
        source_dir_for("batches", "data/batches"): target_root / "batches",
        source_dir_for("input", "data/input"): target_root / "input",
        source_dir_for("local_ingest", "data/local_ingest"): target_root / "local_ingest",
        source_dir_for("online_ingest", "data/online_ingest"): target_root / "online_ingest",
    }
    copied = []
    for source, target in mappings.items():
        if not source.exists():
            continue
        if target.exists() and overwrite:
            shutil.rmtree(target)
        if copy:
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.move(str(source), str(target))
        copied.append({"from": str(source), "to": str(target)})
    create_vault_layout(target_root, initialize_db=True)
    _write_config(config, ctx)
    return {"status": "success", "target": str(target_root), "copied": copied}
