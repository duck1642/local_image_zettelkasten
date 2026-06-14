import hashlib
import json
import shutil
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from db.sqlite_operator import allocate_storage_id, init_database
from path_policy import vault_root_is_inside_workspace, vault_root_is_usable
from runtime_context import VaultContext, WorkspaceContext, get_runtime_context
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


def _vault_entry(vault_id: str, ctx: WorkspaceContext | None = None) -> tuple[str, dict, Path]:
    config = _ensure_vault_registry(_read_config(ctx))
    clean_id = vault_id_slug(vault_id)
    if clean_id not in config["vaults"]:
        raise KeyError(f"vault not found: {clean_id}")
    entry = config["vaults"][clean_id]
    return clean_id, entry, vault_root(entry, ctx)


def _ctx_for_vault(vault_id: str, ctx: WorkspaceContext | None = None) -> WorkspaceContext:
    runtime = _ctx(ctx)
    clean_id, entry, root = _vault_entry(vault_id, runtime)
    vault_dir = root / "vault"
    vault_context = VaultContext(
        id=clean_id,
        name=str(entry.get("name") or clean_id),
        root=root,
        vault_dir=vault_dir,
        assets_dir=vault_dir / "assets",
        notes_dir=vault_dir / "notes",
        db_path=root / "db" / "lmz_main.db",
        review_dir=root / "review",
        queues_dir=root / "queues",
        local_ingest_dir=root / "local_ingest",
        online_ingest_dir=root / "online_ingest",
        batches_dir=root / "batches",
        input_dir=root / "input",
        wd_tags_dir=root / "wd-tags",
        thumbnails_dir=root / "ui_cache" / "thumbnails",
        logs_dir=root / "logs",
    )
    return WorkspaceContext(
        config_path=runtime.config_path,
        root=runtime.root,
        topics_dir=runtime.topics_dir,
        secrets_dir=runtime.secrets_dir,
        models_dir=runtime.models_dir,
        workspace_db_path=runtime.workspace_db_path,
        active_vault=vault_context,
        vaults_configured=runtime.vaults_configured,
    )


def _safe_package_name(value: str) -> str:
    return vault_id_slug(value).replace("-", "_")


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
    runtime = _ctx(ctx)
    config = _ensure_vault_registry(_read_config(ctx))
    vault_id = vault_id_slug(vault_id)
    if vault_id not in config["vaults"]:
        raise KeyError(f"vault not found: {vault_id}")
    root = vault_root(config["vaults"][vault_id], ctx)
    if not vault_root_is_usable(root, runtime.root):
        raise ValueError(f"vault root is missing or outside workspace: {root}")
    config["active_vault"] = vault_id
    _write_config(config, ctx)

    # Dynamic dynamic-vault switching runtime updates
    from runtime_context import reload_runtime_context
    from runtime_activation import activate_runtime_context

    new_ctx = reload_runtime_context(runtime.config_path)
    activate_runtime_context(new_ctx)

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
    if not vault_root_is_inside_workspace(root, _config_root(ctx)):
        raise ValueError(f"vault root is outside workspace: {root}")
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


def _normalize_merge_sources(source_ids: list[str]) -> list[str]:
    sources: list[str] = []
    for value in source_ids:
        source_id = vault_id_slug(value)
        if source_id and source_id not in sources:
            sources.append(source_id)
    if len(sources) < 2:
        raise ValueError("at least two source vault ids are required")
    return sources


def _validate_new_merged_vault(name: str, config: dict) -> tuple[str, str]:
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("merged vault name is required")
    clean_id = vault_id_slug(clean_name)
    vaults = config.get("vaults", {})
    if clean_id in vaults:
        raise ValueError(f"vault already exists: {clean_id}")
    name_key = clean_name.casefold()
    for entry in vaults.values():
        if str(entry.get("name") or "").strip().casefold() == name_key:
            raise ValueError(f"vault name already exists: {clean_name}")
    return clean_name, clean_id


def preview_merged_vault(name: str, source_ids: list[str], ctx: WorkspaceContext | None = None) -> dict:
    config = _ensure_vault_registry(_read_config(ctx))
    vaults = config["vaults"]
    clean_name, clean_id = _validate_new_merged_vault(name, config)
    sources = _normalize_merge_sources(source_ids)
    workspace_root = _config_root(ctx)

    payload = {
        "status": "preview",
        "name": clean_name,
        "vault": clean_id,
        "source_vault_ids": sources,
        "sources": [],
        "total_items": 0,
        "duplicates": 0,
        "importable": 0,
        "possible_similar": 0,
        "similarity": "unsupported",
    }
    seen_hashes: set[str] = set()
    for source_id in sources:
        if source_id not in vaults:
            raise KeyError(f"vault not found: {source_id}")
        source_root = vault_root(vaults[source_id], ctx)
        if not vault_root_is_usable(source_root, workspace_root):
            raise ValueError(f"source vault is offline or missing: {source_id}")
        source_db = vault_db_path(source_root)
        if not source_db.exists():
            raise ValueError(f"source database is missing: {source_id}")

        conn = sqlite3.connect(source_db)
        try:
            rows = conn.execute("SELECT hash FROM items").fetchall()
        finally:
            conn.close()
        total = len(rows)
        duplicates = 0
        importable = 0
        for (item_hash,) in rows:
            if item_hash in seen_hashes:
                duplicates += 1
            else:
                seen_hashes.add(item_hash)
                importable += 1
        payload["sources"].append({
            "id": source_id,
            "items": total,
            "duplicates": duplicates,
            "importable": importable,
        })
        payload["total_items"] += total
        payload["duplicates"] += duplicates
        payload["importable"] += importable
    return payload


def _item_columns(conn: sqlite3.Connection) -> list[str]:
    return [row[1] for row in conn.execute("PRAGMA table_info(items)").fetchall()]


def _copy_item_tiles(source_conn: sqlite3.Connection, target_conn: sqlite3.Connection, item_hash: str):
    try:
        rows = source_conn.execute(
            "SELECT tile_index, tile_phash FROM item_tiles WHERE parent_hash = ?",
            (item_hash,),
        ).fetchall()
    except sqlite3.Error:
        return
    if rows:
        target_conn.executemany(
            """
            INSERT OR REPLACE INTO item_tiles(parent_hash, tile_index, tile_phash)
            VALUES (?, ?, ?)
            """,
            [(item_hash, tile_index, tile_phash) for tile_index, tile_phash in rows],
        )


def merge_vaults_to_new(name: str, source_ids: list[str], ctx: WorkspaceContext | None = None) -> dict:
    import re
    preview = preview_merged_vault(name, source_ids, ctx)
    clean_id = str(preview["vault"])
    config = _ensure_vault_registry(_read_config(ctx))
    vaults = config["vaults"]
    created = False
    target_conn: sqlite3.Connection | None = None
    try:
        create_vault(str(preview["name"]), clean_id, ctx)
        created = True
        target_root = vault_root(_ensure_vault_registry(_read_config(ctx))["vaults"][clean_id], ctx)
        target_db = vault_db_path(target_root)
        target_conn = init_database(target_db)
        target_columns = _item_columns(target_conn)
        copied_paths: list[Path] = []
        imported = 0
        skipped = 0
        seen_hashes: set[str] = set()

        def safe_copy(src: Path, dst: Path) -> bool:
            if _copy_if_exists(src, dst):
                copied_paths.append(dst)
                return True
            return False

        for source_id in preview["source_vault_ids"]:
            source_root = vault_root(vaults[source_id], ctx)
            source_db = vault_db_path(source_root)
            source_conn = sqlite3.connect(source_db)
            try:
                source_columns = _item_columns(source_conn)
                copy_columns = [column for column in target_columns if column in source_columns]
                if "hash" not in copy_columns or "storage_id" not in copy_columns:
                    raise ValueError(f"source item schema is unsupported: {source_id}")
                select_sql = f"SELECT {', '.join(copy_columns)} FROM items"
                insert_sql = (
                    f"INSERT INTO items({', '.join(copy_columns)}) "
                    f"VALUES ({', '.join('?' for _ in copy_columns)})"
                )
                for row in source_conn.execute(select_sql).fetchall():
                    item = dict(zip(copy_columns, row))
                    item_hash = item.get("hash")
                    if not item_hash:
                        skipped += 1
                        continue
                    if item_hash in seen_hashes:
                        skipped += 1
                        continue
                    seen_hashes.add(item_hash)
                    old_storage_id = str(item.get("storage_id") or "")
                    new_storage_id = allocate_storage_id(target_conn)
                    item["storage_id"] = new_storage_id
                    target_conn.execute(insert_sql, [item.get(column) for column in copy_columns])
                    _copy_item_tiles(source_conn, target_conn, str(item_hash))

                    if old_storage_id:
                        ext = str(item.get("file_extension") or "")
                        mime_type = str(item.get("mime_type") or "")
                        old_paths = _item_paths(source_root, str(item_hash), old_storage_id, ext, mime_type)
                        new_paths = _item_paths(target_root, str(item_hash), new_storage_id, ext, mime_type)
                        safe_copy(old_paths["asset"], new_paths["asset"])
                        safe_copy(old_paths["wd"], new_paths["wd"])
                        safe_copy(old_paths["thumb"], new_paths["thumb"])
                        if safe_copy(old_paths["note"], new_paths["note"]):
                            text = new_paths["note"].read_text(encoding="utf-8", errors="ignore")
                            pattern = re.compile(r"\b" + re.escape(old_storage_id) + r"\b")
                            text = pattern.sub(new_storage_id, text)
                            new_paths["note"].write_text(text, encoding="utf-8")
                    imported += 1
            finally:
                source_conn.close()
        target_conn.commit()
        preview.update({
            "status": "success",
            "imported": imported,
            "skipped": skipped,
            "items": vault_list(ctx),
        })
        return preview
    except Exception:
        if target_conn is not None:
            target_conn.rollback()
            target_conn.close()
            target_conn = None
        if created:
            try:
                delete_vault(clean_id, confirm=True, ctx=ctx)
            except Exception:
                root = _config_root(ctx) / "data" / "vaults" / clean_id
                shutil.rmtree(root, ignore_errors=True)
        raise
    finally:
        if target_conn is not None:
            target_conn.close()


def _fetch_vault_items(db_path: Path) -> list[dict]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(items)")
        columns = [row[1] for row in cursor.fetchall()]
        has_thumb_status = "thumbnail_status" in columns
        has_thumb_error = "thumbnail_error" in columns
        
        select_cols = ["hash", "storage_id", "file_extension", "mime_type"]
        if has_thumb_status:
            select_cols.append("thumbnail_status")
        if has_thumb_error:
            select_cols.append("thumbnail_error")
            
        cols_str = ", ".join(select_cols)
        rows = conn.execute(f"""
            SELECT {cols_str}
            FROM items
            WHERE storage_id IS NOT NULL AND storage_id != ''
        """).fetchall()
        
        items = []
        for row in rows:
            item = {
                "hash": row[0],
                "storage_id": row[1],
                "ext": row[2] or "",
                "mime_type": row[3] or "",
            }
            idx = 4
            if has_thumb_status:
                item["thumbnail_status"] = row[idx] or "pending"
                idx += 1
            else:
                item["thumbnail_status"] = "pending"
                
            if has_thumb_error:
                item["thumbnail_error"] = row[idx]
            else:
                item["thumbnail_error"] = None
            items.append(item)
        return items
    finally:
        conn.close()


def audit_vault_health(vault_id: str, ctx: WorkspaceContext | None = None) -> dict:
    clean_id, _entry, root = _vault_entry(vault_id, ctx)
    db_path = vault_db_path(root)
    items = _fetch_vault_items(db_path)
    expected = {"asset": set(), "note": set(), "wd": set(), "thumb": set()}
    failed_thumbs = []
    
    for item in items:
        paths = _item_paths(root, item["hash"], item["storage_id"], item["ext"], item["mime_type"])
        expected["asset"].add(paths["asset"].resolve())
        expected["note"].add(paths["note"].resolve())
        mime = str(item.get("mime_type") or "").lower()
        if mime.startswith("image/") or mime.startswith("video/"):
            expected["wd"].add(paths["wd"].resolve())
            if item.get("thumbnail_status") == "failed":
                failed_thumbs.append({
                    "hash": item["hash"],
                    "path": str(paths["thumb"]),
                    "error": item.get("thumbnail_error") or "Unknown thumbnail generation failure"
                })
            else:
                expected["thumb"].add(paths["thumb"].resolve())

    missing = {key: [] for key in expected}
    for key, paths in expected.items():
        for path in sorted(paths):
            if not path.exists():
                missing[key].append(str(path))

    def existing_files(folder: Path, suffix: str | None = None) -> set[Path]:
        if not folder.exists():
            return set()
        files = {path.resolve() for path in folder.rglob("*") if path.is_file()}
        if suffix:
            files = {path for path in files if path.name.endswith(suffix)}
        return files

    actual_assets = existing_files(root / "vault" / "assets")
    actual_notes = existing_files(root / "vault" / "notes", ".md")
    actual_wd = existing_files(root / "wd-tags", ".json")
    actual_thumbs = existing_files(root / "ui_cache" / "thumbnails", ".jpg")
    orphan_assets = sorted(str(path) for path in actual_assets - expected["asset"])
    orphan_notes = sorted(str(path) for path in actual_notes - expected["note"])
    orphan_wd = sorted(str(path) for path in actual_wd - expected["wd"])
    orphan_thumbs = sorted(str(path) for path in actual_thumbs - expected["thumb"])

    stale_index_rows = {"topics": 0, "wd_tags": 0, "metadata_files": 0}
    bad_storage_ids = []
    hash_mismatches = []
    facet_drift = []
    broken_topic_links = []
    unused_topic_files = []
    workspace_dictionary_drift = {"missing_in_dictionary": 0, "unused_in_vault": 0}
    if db_path.exists():
        conn = sqlite3.connect(db_path)
        try:
            bad_storage_ids = [
                row[0]
                for row in conn.execute("SELECT hash FROM items WHERE storage_id IS NULL OR TRIM(storage_id) = ''").fetchall()
            ]
            stale_index_rows["topics"] = conn.execute(
                "SELECT COUNT(*) FROM item_topics t LEFT JOIN items i ON i.hash = t.item_hash WHERE i.hash IS NULL"
            ).fetchone()[0]
            stale_index_rows["wd_tags"] = conn.execute(
                "SELECT COUNT(*) FROM item_wd_tags w LEFT JOIN items i ON i.hash = w.item_hash WHERE i.hash IS NULL"
            ).fetchone()[0]
            stale_index_rows["metadata_files"] = conn.execute(
                "SELECT COUNT(*) FROM item_metadata_files m LEFT JOIN items i ON i.hash = m.item_hash WHERE i.hash IS NULL"
            ).fetchone()[0]
            for kind, table, column, count_sql in (
                ("topic", "item_topics", "topic_norm", "COUNT(*)"),
                ("wd_tag", "item_wd_tags", "tag_norm", "COUNT(DISTINCT item_hash)"),
            ):
                indexed = dict(conn.execute(f"SELECT {column}, {count_sql} FROM {table} GROUP BY {column}").fetchall())
                faceted = dict(conn.execute("SELECT value_norm, count FROM metadata_facet_counts WHERE kind = ?", (kind,)).fetchall())
                if indexed != faceted:
                    facet_drift.append(kind)
            topics_dir = _ctx(ctx).topics_dir.resolve()
            topic_rows = conn.execute("SELECT DISTINCT topic_rel FROM item_topics WHERE topic_rel != ''").fetchall()
            used_topic_rels = {str(row[0]).replace("\\", "/") for row in topic_rows}
            broken_topic_links = sorted(rel for rel in used_topic_rels if not (topics_dir / rel).exists())
            if topics_dir.exists():
                all_topic_rels = {str(path.relative_to(topics_dir)).replace("\\", "/") for path in topics_dir.rglob("*.md")}
                unused_topic_files = sorted(all_topic_rels - used_topic_rels)
            used_wd = {row[0] for row in conn.execute("SELECT DISTINCT tag_norm FROM item_wd_tags").fetchall()}
        finally:
            conn.close()
        try:
            from workspace_db import connect_workspace_database
            workspace_conn = connect_workspace_database(ctx)
            try:
                dictionary_wd = {row[0] for row in workspace_conn.execute("SELECT tag_norm FROM wd_tag_dictionary").fetchall()}
                workspace_dictionary_drift = {
                    "missing_in_dictionary": len(used_wd - dictionary_wd),
                    "unused_in_vault": len(dictionary_wd - used_wd),
                }
            finally:
                workspace_conn.close()
        except sqlite3.Error:
            workspace_dictionary_drift["error"] = "workspace dictionary unavailable"

    for item in items:
        asset_path = _item_paths(root, item["hash"], item["storage_id"], item["ext"], item["mime_type"])["asset"]
        if not asset_path.exists():
            continue
        digest = hashlib.sha256()
        try:
            with asset_path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest().casefold() != str(item["hash"]).casefold():
                hash_mismatches.append(str(asset_path))
        except OSError:
            hash_mismatches.append(str(asset_path))

    review_dir = root / "review"
    review_mismatches = {"media_without_sidecar": [], "sidecar_without_media": []}
    if review_dir.exists():
        sidecars = {path for path in review_dir.glob("*.json") if path.is_file()}
        media = {path for path in review_dir.iterdir() if path.is_file() and path.suffix.casefold() != ".json"}
        review_mismatches["media_without_sidecar"] = sorted(str(path) for path in media if not Path(str(path) + ".json").exists())
        review_mismatches["sidecar_without_media"] = sorted(str(path) for path in sidecars if not Path(str(path)[:-5]).exists())

    issue_count = (
        sum(len(paths) for paths in missing.values())
        + len(orphan_assets) + len(orphan_notes) + len(orphan_wd) + len(orphan_thumbs)
        + sum(stale_index_rows.values())
        + len(bad_storage_ids) + len(hash_mismatches)
        + len(facet_drift) + len(broken_topic_links)
        + len(review_mismatches["media_without_sidecar"]) + len(review_mismatches["sidecar_without_media"])
        + int(workspace_dictionary_drift.get("missing_in_dictionary", 0))
        + int(workspace_dictionary_drift.get("unused_in_vault", 0))
    )
    return {
        "status": "success",
        "vault": clean_id,
        "root": str(root),
        "item_count": len(items),
        "issue_count": issue_count,
        "missing_files": missing,
        "failed_thumbnails": failed_thumbs,
        "details": {
            "missing_files": {
                "asset": [{"path": path, "reason": "DB item points to an asset file that does not exist"} for path in missing.get("asset", [])],
                "note": [{"path": path, "reason": "DB item points to a note file that does not exist"} for path in missing.get("note", [])],
                "wd": [{"path": path, "reason": "WD cache is missing; old or manually untagged items may need tagging, not repair"} for path in missing.get("wd", [])],
                "thumb": [{"path": path, "reason": "thumbnail can be regenerated"} for path in missing.get("thumb", [])],
            },
            "failed_thumbnails": failed_thumbs,
        },
        "orphans": {
            "assets": orphan_assets,
            "notes": orphan_notes,
            "wd_cache": orphan_wd,
            "thumbnails": orphan_thumbs,
        },
        "stale_index_rows": stale_index_rows,
        "bad_storage_ids": bad_storage_ids,
        "hash_mismatches": hash_mismatches,
        "facet_drift": facet_drift,
        "broken_topic_links": broken_topic_links,
        "unused_topic_files": unused_topic_files,
        "review_mismatches": review_mismatches,
        "workspace_dictionary_drift": workspace_dictionary_drift,
    }


def _health_category_counts(report: dict) -> dict:
    missing = report.get("missing_files") or {}
    orphans = report.get("orphans") or {}
    stale = report.get("stale_index_rows") or {}
    review = report.get("review_mismatches") or {}
    dictionary = report.get("workspace_dictionary_drift") or {}
    return {
        "missing_files": sum(len(paths or []) for paths in missing.values()),
        "missing_required_files": len(missing.get("asset") or []) + len(missing.get("note") or []),
        "missing_wd_cache": len(missing.get("wd") or []),
        "missing_thumbnails": len(missing.get("thumb") or []),
        "orphan_assets_notes": len(orphans.get("assets") or []) + len(orphans.get("notes") or []),
        "orphan_derived_cache": len(orphans.get("wd_cache") or []) + len(orphans.get("thumbnails") or []),
        "stale_index_rows": sum(int(value or 0) for value in stale.values()),
        "facet_drift": len(report.get("facet_drift") or []),
        "bad_storage_ids": len(report.get("bad_storage_ids") or []),
        "hash_mismatches": len(report.get("hash_mismatches") or []),
        "broken_topic_links": len(report.get("broken_topic_links") or []),
        "unused_topic_files": len(report.get("unused_topic_files") or []),  # informational only, not a health issue
        "review_mismatches": len(review.get("media_without_sidecar") or []) + len(review.get("sidecar_without_media") or []),
        "workspace_dictionary_drift": int(dictionary.get("missing_in_dictionary") or 0) + int(dictionary.get("unused_in_vault") or 0),
    }


def _repairable_issue_count(counts: dict) -> int:
    return (
        int(counts.get("missing_wd_cache") or 0)
        + int(counts.get("missing_thumbnails") or 0)
        + int(counts.get("orphan_assets_notes") or 0)
        + int(counts.get("orphan_derived_cache") or 0)
        + int(counts.get("stale_index_rows") or 0)
        + int(counts.get("facet_drift") or 0)
        + int(counts.get("review_mismatches") or 0)
    )


def _repair_missing_wd_cache(conn: sqlite3.Connection, ctx: WorkspaceContext, limit: int = 100000) -> dict:
    from md_generator import generate_markdown
    from metadata_index import safe_reindex_item_metadata
    from tagging.service import tag_media
    from utils import asset_path_for, atomic_write_text, get_config, note_path_for, wd_tag_cache_path_for

    checked = 0
    tagged = 0
    skipped_existing = 0
    skipped_missing_asset = 0
    skipped_status = 0
    failed = 0
    errors = []
    rows = conn.execute("""
        SELECT hash, file_extension, mime_type, storage_id
        FROM items
        WHERE storage_id IS NOT NULL AND storage_id != ''
        ORDER BY date_added DESC
    """).fetchall()
    for item_hash, extension, mime_type, storage_id in rows:
        if checked >= limit:
            break
        checked += 1
        cache_path = wd_tag_cache_path_for(item_hash, storage_id=storage_id, ctx=ctx)
        if cache_path.exists():
            skipped_existing += 1
            continue
        asset_path = asset_path_for(item_hash, extension or "", mime_type or "", storage_id=storage_id, ctx=ctx)
        if not asset_path.exists():
            skipped_missing_asset += 1
            continue
        try:
            result = tag_media(asset_path, item_hash=item_hash, config=get_config(), storage_id=storage_id)
            # Explicitly write to the ctx-aware path. tag_media calls _write_result internally
            # which has no ctx parameter and falls back to get_runtime_context(), so if the
            # repair_ctx path differs in any way the file lands in the wrong location.
            # Writing here with cache_path (already computed with ctx) guarantees correctness.
            atomic_write_text(cache_path, json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
            if result.status == "ok":
                tagged += 1
            else:
                skipped_status += 1
                if len(errors) < 10:
                    errors.append({
                        "hash": item_hash,
                        "storage_id": storage_id,
                        "status": result.status,
                        "error": result.error or f"tagging returned status={result.status!r}",
                    })
            md_content = generate_markdown(conn, item_hash, force_wd_from_cache=True)
            if md_content:
                note_path = note_path_for(item_hash, storage_id=storage_id, ctx=ctx)
                note_path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_text(note_path, md_content)
                safe_reindex_item_metadata(conn, item_hash, "vault_repair_wd_tagging")
                conn.commit()
        except Exception as exc:
            failed += 1
            conn.rollback()
            if len(errors) < 10:
                errors.append({"hash": item_hash, "storage_id": storage_id, "status": "exception", "error": str(exc)})
    try:
        from logger import log_system
        log_system(
            "INFO",
            "WD cache repair batch finished",
            checked=checked,
            tagged=tagged,
            skipped_existing=skipped_existing,
            skipped_missing_asset=skipped_missing_asset,
            skipped_status=skipped_status,
            failed=failed,
        )
    except Exception:
        pass
    return {
        "checked": checked,
        "tagged": tagged,
        "skipped_existing": skipped_existing,
        "skipped_missing_asset": skipped_missing_asset,
        "skipped_status": skipped_status,
        "failed": failed,
        "errors": errors,
    }


def repair_vault(vault_id: str, actions: list[str] | None = None, confirm_destructive: bool = False, ctx: WorkspaceContext | None = None) -> dict:
    repair_ctx = _ctx_for_vault(vault_id, ctx)
    clean_id, _entry, root = _vault_entry(vault_id, repair_ctx)
    selected = {str(action or "").strip() for action in (actions or []) if str(action or "").strip()}
    if not selected:
        selected = {"metadata", "thumbnails", "wd_tagging", "derived_cache", "review_sidecars", "quarantine_orphans"}
    allowed = {"metadata", "thumbnails", "wd_tagging", "derived_cache", "review_sidecars", "quarantine_orphans"}
    unknown = sorted(selected - allowed)
    if unknown:
        raise ValueError(f"unknown repair actions: {', '.join(unknown)}")
    destructive_actions = {"derived_cache", "review_sidecars", "quarantine_orphans"}
    requested_destructive = selected.intersection(destructive_actions)
    if requested_destructive and not confirm_destructive:
        raise ValueError(f"destructive actions require confirmation: {', '.join(sorted(requested_destructive))}")
    if "metadata" in selected and repair_ctx.active_vault.id != get_runtime_context().active_vault.id:
        raise ValueError("metadata repair is only supported for the active vault")
    if "wd_tagging" in selected and repair_ctx.active_vault.id != get_runtime_context().active_vault.id:
        raise ValueError("WD tagging repair is only supported for the active vault")
    before = audit_vault_health(clean_id, repair_ctx)
    before_counts = _health_category_counts(before)
    try:
        from logger import log_system
        log_system(
            "INFO",
            "Vault repair started",
            vault=clean_id,
            actions=sorted(selected),
            issues_before=before.get("issue_count", 0),
            repairable_before=_repairable_issue_count(before_counts),
            counts=before_counts,
        )
    except Exception:
        pass
    result = {
        "status": "success",
        "vault": clean_id,
        "actions": sorted(selected),
        "before_issue_count": int(before.get("issue_count") or 0),
        "before_counts": before_counts,
    }
    db_path = vault_db_path(root)

    if "metadata" in selected and db_path.exists():
        from metadata_index import rebuild_all_metadata
        conn = init_database(db_path)
        try:
            result["metadata"] = rebuild_all_metadata(conn, context="vault_repair")
        finally:
            conn.close()

    if "thumbnails" in selected and db_path.exists():
        from thumbnails import repair_missing_thumbnails
        conn = init_database(db_path)
        try:
            result["thumbnails"] = repair_missing_thumbnails(conn, limit=100000, ctx=repair_ctx)
        finally:
            conn.close()

    if "wd_tagging" in selected and db_path.exists():
        conn = init_database(db_path)
        try:
            result["wd_tagging"] = _repair_missing_wd_cache(conn, repair_ctx)
        finally:
            conn.close()

    if "derived_cache" in selected:
        removed = 0
        for key in ("wd_cache", "thumbnails"):
            for path_text in before["orphans"].get(key, []):
                path = Path(path_text)
                if path.exists():
                    path.unlink()
                    removed += 1
        result["derived_cache"] = {"removed": removed}

    if "review_sidecars" in selected:
        removed = 0
        for path_text in before["review_mismatches"].get("sidecar_without_media", []):
            path = Path(path_text)
            if path.exists():
                path.unlink()
                removed += 1
        result["review_sidecars"] = {"removed_orphan_sidecars": removed}

    if "quarantine_orphans" in selected:
        quarantine_dir = root / "quarantine"
        moved = 0
        for key in ("assets", "notes"):
            for path_text in before["orphans"].get(key, []):
                path = Path(path_text)
                if not path.exists():
                    continue
                target = quarantine_dir / key / path.name
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    target = target.with_name(f"{target.stem}-{moved}{target.suffix}")
                shutil.move(str(path), str(target))
                moved += 1
        result["quarantine_orphans"] = {"moved": moved}

    if confirm_destructive:
        result["destructive_confirmed"] = True
    after = audit_vault_health(clean_id, repair_ctx)
    after_counts = _health_category_counts(after)
    result["after"] = after
    result["after_issue_count"] = int(after.get("issue_count") or 0)
    result["after_counts"] = after_counts
    result["fixed_issue_count"] = max(0, result["before_issue_count"] - result["after_issue_count"])
    result["repairable_before"] = _repairable_issue_count(before_counts)
    result["repairable_after"] = _repairable_issue_count(after_counts)
    manual_keys = ("missing_required_files", "bad_storage_ids", "hash_mismatches", "broken_topic_links", "workspace_dictionary_drift")
    result["manual_remaining"] = {key: after_counts.get(key, 0) for key in manual_keys if after_counts.get(key, 0)}
    if result["fixed_issue_count"] == 0:
        result["message"] = "No repairable issues changed"
    elif result["after_issue_count"] > 0:
        result["message"] = f"Fixed {result['fixed_issue_count']} issues; {result['after_issue_count']} remain"
    else:
        result["message"] = f"Fixed {result['fixed_issue_count']} issues"
    try:
        from logger import log_system
        log_system(
            "INFO",
            "Vault repair finished",
            vault=clean_id,
            issues_before=result["before_issue_count"],
            issues_after=result["after_issue_count"],
            fixed=result["fixed_issue_count"],
            manual_remaining=result["manual_remaining"],
            counts_after=after_counts,
        )
    except Exception:
        pass
    return result


def backup_vault(vault_id: str, ctx: WorkspaceContext | None = None, package_dir: Path | None = None) -> dict:
    clean_id, _entry, root = _vault_entry(vault_id, ctx)
    if not root.exists():
        raise ValueError(f"vault root does not exist: {root}")
    destination_dir = package_dir or (_ctx(ctx).root / "backups")
    destination_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    package_path = destination_dir / f"{_safe_package_name(clean_id)}-{stamp}.lmzvault.zip"
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("lmz-vault-package.yaml", yaml.safe_dump({"vault_id": clean_id, "name": _vault_entry(clean_id, ctx)[1].get("name") or clean_id}, sort_keys=False))
        for path in root.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(root).as_posix())
    return {"status": "success", "vault": clean_id, "package_path": str(package_path), "bytes": package_path.stat().st_size}


def export_vault(vault_id: str, ctx: WorkspaceContext | None = None) -> dict:
    return backup_vault(vault_id, ctx, package_dir=_ctx(ctx).root / "exports")


def import_vault_package(package_path: str | Path, name: str | None = None, vault_id: str | None = None, ctx: WorkspaceContext | None = None) -> dict:
    source = Path(package_path).expanduser().resolve()
    if not source.exists():
        raise ValueError(f"vault package not found: {source}")
    config = _ensure_vault_registry(_read_config(ctx))
    with zipfile.ZipFile(source, "r") as archive:
        manifest = {}
        try:
            manifest = yaml.safe_load(archive.read("lmz-vault-package.yaml").decode("utf-8")) or {}
        except KeyError:
            manifest = {}
        clean_id = vault_id_slug(vault_id or name or manifest.get("vault_id") or source.stem)
        if clean_id in config["vaults"]:
            raise ValueError(f"vault already exists: {clean_id}")
        entry = {"name": str(name or manifest.get("name") or clean_id), "root": f"data/vaults/{clean_id}"}
        root = vault_root(entry, ctx)
        if root.exists() and _vault_non_empty(root):
            raise ValueError(f"target vault root is not empty: {root}")
        root_existed_before = root.exists()
        try:
            root.mkdir(parents=True, exist_ok=True)
            for member in archive.infolist():
                if member.is_dir() or member.filename == "lmz-vault-package.yaml":
                    continue
                target = (root / member.filename).resolve()
                if root.resolve() not in target.parents and target != root.resolve():
                    raise ValueError(f"unsafe package path: {member.filename}")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
            create_vault_layout(root, initialize_db=not vault_db_path(root).exists())
            config["vaults"][clean_id] = entry
            _write_config(config, ctx)
        except Exception:
            if not root_existed_before and root.exists():
                shutil.rmtree(root, ignore_errors=True)
            raise
    return {"status": "success", "vault": clean_id, "items": vault_list(ctx)}


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
