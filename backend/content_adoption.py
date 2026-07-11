from __future__ import annotations

import hashlib
import argparse
import json
import os
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from app_paths import AppPaths, get_app_paths
from config_repository import WorkspaceConfigRepository, bootstrap_data_home
from config_schema import VaultEntry, WorkspaceConfig


class ContentAdoptionError(RuntimeError):
    pass


def detect_legacy_source(candidates: list[str | Path] | None = None) -> Path | None:
    roots = candidates or [Path.cwd()]
    for candidate in roots:
        root = Path(candidate).expanduser().resolve()
        if (root / "config" / "config.yaml").is_file() and (root / "data").is_dir():
            return root
    return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_symlink(path: Path) -> None:
    if path.is_symlink():
        raise ContentAdoptionError(f"symbolic links are not supported during adoption: {path}")


def _copy_sqlite(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_uri = f"file:{source.resolve().as_posix()}?mode=ro"
    source_db = sqlite3.connect(source_uri, uri=True)
    destination_db = sqlite3.connect(destination)
    try:
        source_db.backup(destination_db)
        result = destination_db.execute("PRAGMA integrity_check").fetchone()
        if not result or str(result[0]).casefold() != "ok":
            raise ContentAdoptionError(f"SQLite integrity check failed for {source}")
    except sqlite3.Error as exc:
        raise ContentAdoptionError(f"SQLite copy failed for {source}: {exc}") from exc
    finally:
        destination_db.close()
        source_db.close()


def _copy_file(source: Path, destination: Path) -> None:
    _reject_symlink(source)
    if source.suffix.casefold() in {".db", ".sqlite", ".sqlite3"}:
        _copy_sqlite(source, destination)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _copy_tree(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    _reject_symlink(source)
    if source.is_file():
        _copy_file(source, destination)
        return
    for item in sorted(source.rglob("*")):
        _reject_symlink(item)
        relative = item.relative_to(source)
        target = destination / relative
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            _copy_file(item, target)


def _legacy_topology_from_config(config_path: Path, source_root: Path) -> tuple[WorkspaceConfig, dict[str, Path]]:
    if not config_path.is_file():
        raise ContentAdoptionError(f"legacy workspace config not found: {config_path}")
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ContentAdoptionError(f"legacy workspace config is unreadable: {exc}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("vaults"), dict) or not raw["vaults"]:
        raise ContentAdoptionError("legacy workspace config does not define vault topology")

    vaults: dict[str, VaultEntry] = {}
    source_vaults: dict[str, Path] = {}
    for vault_id, value in raw["vaults"].items():
        if not isinstance(value, dict):
            raise ContentAdoptionError(f"invalid legacy vault entry: {vault_id}")
        clean_id = str(vault_id).strip()
        if not clean_id or "/" in clean_id or "\\" in clean_id or clean_id in {".", ".."}:
            raise ContentAdoptionError(f"unsafe legacy vault id: {vault_id}")
        root_value = Path(str(value.get("root") or f"data/vaults/{clean_id}")).expanduser()
        source_vault = root_value.resolve() if root_value.is_absolute() else (source_root / root_value).resolve()
        vaults[clean_id] = VaultEntry(
            name=str(value.get("name") or clean_id),
            root=f"data/vaults/{clean_id}",
        )
        source_vaults[clean_id] = source_vault

    active = str(raw.get("active_vault") or "default")
    if active not in vaults:
        raise ContentAdoptionError(f"legacy active vault is not defined: {active}")
    return WorkspaceConfig(active_vault=active, vaults=vaults), source_vaults


def _legacy_topology(source_root: Path) -> tuple[WorkspaceConfig, dict[str, Path]]:
    return _legacy_topology_from_config(source_root / "config" / "config.yaml", source_root)


def convert_legacy_workspace_config(config_path: str | Path) -> dict:
    """Convert one external legacy workspace config, preserving a byte backup."""
    path = Path(config_path).expanduser().resolve()
    if not path.is_file():
        raise ContentAdoptionError(f"legacy workspace config not found: {path}")
    topology, _ = _legacy_topology_from_config(path, path.parent)
    legacy_payload = path.read_bytes()
    backup = path.with_name(f"{path.name}.legacy-{uuid.uuid4().hex}")
    temp = path.with_name(f".{path.name}.migrating-{uuid.uuid4().hex}.tmp")
    shutil.copy2(path, backup)
    payload = yaml.safe_dump(
        topology.model_dump(mode="json"), sort_keys=False, allow_unicode=True
    ).encode("utf-8")
    try:
        with temp.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        WorkspaceConfigRepository(path).read()
    except Exception:
        temp.unlink(missing_ok=True)
        path.write_bytes(legacy_payload)
        raise
    return {"config_path": str(path), "legacy_backup": str(backup), "vault_count": len(topology.vaults)}


def _manifest(root: Path) -> list[dict]:
    entries = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if path.name.endswith(".lock"):
            continue
        if relative in {"app/migration-manifest.json", "app/migration-receipt.json"}:
            continue
        entries.append({"path": relative, "size": path.stat().st_size, "sha256": _sha256(path)})
    return entries


def _verify_manifest(root: Path, entries: list[dict]) -> None:
    for entry in entries:
        path = root / entry["path"]
        if not path.is_file() or path.stat().st_size != entry["size"] or _sha256(path) != entry["sha256"]:
            raise ContentAdoptionError(f"copied file verification failed: {entry['path']}")


def adopt_legacy_content(source_root: str | Path, paths: AppPaths | None = None) -> dict:
    paths = paths or get_app_paths()
    source = Path(source_root).expanduser().resolve()
    target = paths.data_root.resolve()
    if not source.is_dir():
        raise ContentAdoptionError(f"legacy source does not exist: {source}")
    if target.exists():
        raise ContentAdoptionError(f"target data root already exists; refusing to merge: {target}")
    if target == source or target.is_relative_to(source) or source.is_relative_to(target):
        raise ContentAdoptionError("legacy source and target data root cannot contain one another")

    topology, source_vaults = _legacy_topology(source)
    legacy_workspace_db = source / "data" / "workspace.db"
    if not legacy_workspace_db.is_file():
        raise ContentAdoptionError(f"legacy workspace database not found: {legacy_workspace_db}")
    stage = target.parent / f"{target.name}-migrating-{uuid.uuid4().hex}"
    ambiguous = []
    try:
        stage_paths = AppPaths(
            data_root=stage,
            app_dir=stage / "app",
            settings_path=stage / "app" / "settings.yaml",
            registry_path=stage / "app" / "workspaces.yaml",
            secrets_dir=stage / "app" / "secrets",
            logs_dir=stage / "app" / "logs",
            models_dir=stage / "app" / "models",
            cache_dir=stage / "app" / "cache",
            default_workspace_dir=stage / "default",
            default_workspace_config=stage / "default" / "config.yaml",
        )
        bootstrap_data_home(stage_paths)

        from config_repository import WorkspaceConfigRepository

        repository = WorkspaceConfigRepository(stage_paths.default_workspace_config)
        current = repository.read()
        repository.replace(topology, expected_etag=current.etag)

        _copy_tree(source / "data" / "workspace.db", stage / "default" / "data" / "workspace.db")
        _copy_tree(source / "data" / "topics", stage / "default" / "data" / "topics")
        for vault_id, source_vault in source_vaults.items():
            _copy_tree(source_vault, stage / "default" / "data" / "vaults" / vault_id)
        _copy_tree(source / "backups", stage / "default" / "backups")
        _copy_tree(source / "exports", stage / "default" / "exports")
        _copy_tree(source / "secrets", stage / "app" / "secrets")
        _copy_tree(source / "data" / "models", stage / "app" / "models")

        ambiguous_root = source / "config" / "data"
        if ambiguous_root.exists():
            ambiguous.append(str(ambiguous_root))

        entries = _manifest(stage)
        _verify_manifest(stage, entries)
        manifest_path = stage / "app" / "migration-manifest.json"
        manifest_path.write_text(json.dumps({"algorithm": "sha256", "files": entries}, indent=2), encoding="utf-8")
        manifest_hash = _sha256(manifest_path)
        receipt = {
            "version": 1,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "source": str(source),
            "target": str(target),
            "file_count": len(entries),
            "manifest_sha256": manifest_hash,
            "ambiguous_paths": ambiguous,
            "source_deleted": False,
        }
        (stage / "app" / "migration-receipt.json").write_text(
            json.dumps(receipt, indent=2), encoding="utf-8"
        )
        os.replace(stage, target)
        return receipt
    except Exception:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        raise


def adopt_legacy_content_into_existing(source_root: str | Path, paths: AppPaths | None = None) -> dict:
    """Adopt project-root content into an already bootstrapped data home.

    This mode intentionally does not read or copy the legacy ``secrets`` tree,
    and leaves the target app settings, registry, logs, and cache untouched.
    Only the default workspace payload and downloaded models are staged and
    swapped. The previous target payload is retained in a sibling backup root.
    """
    paths = paths or get_app_paths()
    source = Path(source_root).expanduser().resolve()
    target = paths.data_root.resolve()
    if not source.is_dir():
        raise ContentAdoptionError(f"legacy source does not exist: {source}")
    if not target.is_dir():
        raise ContentAdoptionError(f"existing target data root does not exist: {target}")
    if target == source or target.is_relative_to(source) or source.is_relative_to(target):
        raise ContentAdoptionError("legacy source and target data root cannot contain one another")

    # Validate the already-created target without replacing any app-owned files.
    bootstrap_data_home(paths)
    topology, source_vaults = _legacy_topology(source)
    legacy_workspace_db = source / "data" / "workspace.db"
    if not legacy_workspace_db.is_file():
        raise ContentAdoptionError(f"legacy workspace database not found: {legacy_workspace_db}")
    migration_id = uuid.uuid4().hex
    stage = target.parent / f"{target.name}-content-migrating-{migration_id}"
    backup = target.parent / f"{target.name}-migration-backup-{migration_id}"
    stage_default = stage / "default"
    stage_models = stage / "app" / "models"
    manifest_path = target / "app" / "migration-manifest.json"
    receipt_path = target / "app" / "migration-receipt.json"
    old_manifest = manifest_path.read_bytes() if manifest_path.exists() else None
    old_receipt = receipt_path.read_bytes() if receipt_path.exists() else None
    moved_default = False
    installed_default = False
    moved_models = False
    installed_models = False
    ambiguous = []
    try:
        stage_default.mkdir(parents=True, exist_ok=True)
        WorkspaceConfigRepository(stage_default / "config.yaml").create(topology)
        _copy_tree(legacy_workspace_db, stage_default / "data" / "workspace.db")
        _copy_tree(source / "data" / "topics", stage_default / "data" / "topics")
        for vault_id, source_vault in source_vaults.items():
            _copy_tree(source_vault, stage_default / "data" / "vaults" / vault_id)
        _copy_tree(source / "backups", stage_default / "backups")
        _copy_tree(source / "exports", stage_default / "exports")

        source_models = source / "data" / "models"
        has_models = source_models.exists()
        if has_models:
            stage_models.mkdir(parents=True, exist_ok=True)
            _copy_tree(source_models, stage_models)

        ambiguous_root = source / "config" / "data"
        if ambiguous_root.exists():
            ambiguous.append(str(ambiguous_root))

        entries = _manifest(stage)
        _verify_manifest(stage, entries)
        backup.mkdir(parents=True, exist_ok=False)

        backup_default = backup / "default"
        backup_models = backup / "app" / "models"
        if (target / "default").exists():
            backup_default.parent.mkdir(parents=True, exist_ok=True)
            os.replace(target / "default", backup_default)
            moved_default = True
        os.replace(stage_default, target / "default")
        installed_default = True

        if has_models:
            if paths.models_dir.exists():
                backup_models.parent.mkdir(parents=True, exist_ok=True)
                os.replace(paths.models_dir, backup_models)
                moved_models = True
            os.replace(stage_models, paths.models_dir)
            installed_models = True

        manifest_path.write_text(
            json.dumps({"algorithm": "sha256", "files": entries}, indent=2),
            encoding="utf-8",
        )
        receipt = {
            "version": 2,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "source": str(source),
            "target": str(target),
            "file_count": len(entries),
            "manifest_sha256": _sha256(manifest_path),
            "ambiguous_paths": ambiguous,
            "source_deleted": False,
            "legacy_secrets_touched": False,
            "target_settings_preserved": True,
            "target_registry_preserved": True,
            "reindex": "not-run",
            "rollback_backup": str(backup),
        }
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        return receipt
    except Exception:
        if installed_models and paths.models_dir.exists():
            shutil.rmtree(paths.models_dir, ignore_errors=True)
        if moved_models and (backup / "app" / "models").exists():
            os.replace(backup / "app" / "models", paths.models_dir)
        if installed_default and (target / "default").exists():
            shutil.rmtree(target / "default", ignore_errors=True)
        if moved_default and (backup / "default").exists():
            os.replace(backup / "default", target / "default")
        if old_manifest is None:
            manifest_path.unlink(missing_ok=True)
        else:
            manifest_path.write_bytes(old_manifest)
        if old_receipt is None:
            receipt_path.unlink(missing_ok=True)
        else:
            receipt_path.write_bytes(old_receipt)
        raise
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Adopt durable content into a new LMZ data home")
    parser.add_argument("source", nargs="?", help="Legacy LMZ project root (auto-detects the current directory)")
    parser.add_argument("--target", help="New data root (defaults to LMZ_DATA_ROOT or ~/.lmz)")
    parser.add_argument("--yes", action="store_true", help="Confirm the explicit content-only adoption")
    parser.add_argument(
        "--into-existing",
        action="store_true",
        help="Adopt into an existing .lmz root while preserving app settings, registry, logs, cache, and secrets",
    )
    args = parser.parse_args()
    if args.target:
        os.environ["LMZ_DATA_ROOT"] = str(Path(args.target).expanduser().resolve())
    source = Path(args.source).expanduser().resolve() if args.source else detect_legacy_source()
    if source is None:
        print("No legacy LMZ project-root data was detected.", file=sys.stderr)
        return 2
    target = get_app_paths().data_root
    if not args.yes:
        print(f"Legacy LMZ content detected: {source}")
        print(f"Proposed new data home: {target}")
        if args.into_existing:
            print("This replaces only the default workspace and app models, preserves app settings/registry/secrets, and never deletes the source.")
        else:
            print("This creates fresh configs, copies durable content, and never deletes the source.")
        if not sys.stdin.isatty() or input("Proceed with content-only adoption? [y/N] ").strip().casefold() not in {"y", "yes"}:
            print("No changes made. Re-run with --yes to confirm non-interactively.")
            return 2
    receipt = adopt_legacy_content_into_existing(source) if args.into_existing else adopt_legacy_content(source)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
