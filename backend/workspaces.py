import json
import os
import shutil
import uuid
from pathlib import Path

from app_paths import get_app_paths
from config_repository import WorkspaceConfigRepository, WorkspaceRegistryRepository
from config_schema import WorkspaceRegistry, default_workspace_registry


import sys

SRC_DIR = Path(__file__).resolve().parent
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).parent
else:
    PROJECT_ROOT = SRC_DIR.parent
REGISTRY_PATH = get_app_paths().registry_path
DEFAULT_WORKSPACE_ID = "default"
WORKSPACE_MARKER_NAME = ".lmz-workspace"
WORKSPACE_MARKER_PAYLOAD = {"type": "lmz-workspace", "version": 1}
DELETE_MODES = {"unregister", "generated", "all"}
GENERATED_VAULT_DIRS = ("db", "logs", "queues", "batches", "wd-tags", "ui_cache")


class WorkspaceDeletionError(RuntimeError):
    pass


def _resolve(path: str | Path, base: Path = PROJECT_ROOT) -> Path:
    if base == PROJECT_ROOT:
        base = get_app_paths().data_root
    value = Path(path).expanduser()
    return value.resolve() if value.is_absolute() else (base / value).resolve()


def _default_registry() -> dict:
    return default_workspace_registry().model_dump(mode="json")


def load_workspace_registry() -> dict:
    return WorkspaceRegistryRepository(REGISTRY_PATH).read().value.model_dump(mode="json")


def save_workspace_registry(registry: dict):
    value = WorkspaceRegistry.model_validate(registry)
    repository = WorkspaceRegistryRepository(REGISTRY_PATH)
    if not REGISTRY_PATH.exists():
        repository.create(value)
        return
    current = repository.read()
    repository.replace(value, expected_etag=current.etag)


def _has_valid_marker(workspace_root: Path) -> bool:
    marker = workspace_root / WORKSPACE_MARKER_NAME
    try:
        return json.loads(marker.read_text(encoding="utf-8")) == WORKSPACE_MARKER_PAYLOAD
    except (OSError, ValueError, TypeError):
        return False

def workspace_list() -> list[dict]:
    registry = load_workspace_registry()
    active = registry["active_workspace"]
    items = []
    for workspace_id, entry in sorted(registry["workspaces"].items()):
        config_path = _resolve(entry.get("config_path") or "")
        managed = workspace_id != DEFAULT_WORKSPACE_ID and _has_valid_marker(config_path.parent)
        items.append({
            "id": workspace_id,
            "name": str(entry.get("name") or workspace_id),
            "config_path": str(config_path),
            "active": workspace_id == active,
            "exists": config_path.exists(),
            "managed": managed,
            "can_delete_all": managed and workspace_id != active,
        })
    return items


def active_workspace_config_path() -> Path:
    registry = load_workspace_registry()
    entry = registry["workspaces"][registry["active_workspace"]]
    return _resolve(entry["config_path"])


def set_active_workspace(workspace_id: str) -> dict:
    registry = load_workspace_registry()
    workspace_id = str(workspace_id or "").strip()
    if not workspace_id or workspace_id not in registry["workspaces"]:
        raise ValueError(f"unknown workspace: {workspace_id}")
    config_path = _resolve(registry["workspaces"][workspace_id].get("config_path") or "")
    if not config_path.exists():
        raise ValueError(f"workspace config does not exist: {config_path}")
    registry["active_workspace"] = workspace_id
    save_workspace_registry(registry)
    return registry


def _slug_workspace_id(name: str) -> str:
    cleaned = "".join(ch.casefold() if ch.isalnum() else "-" for ch in str(name or "").strip())
    return "-".join(part for part in cleaned.split("-") if part) or "workspace"


def register_workspace(name: str, config_path: str | Path, workspace_id: str | None = None, set_active: bool = False) -> dict:
    registry = load_workspace_registry()
    resolved = _resolve(config_path)
    if not resolved.exists():
        raise ValueError(f"workspace config does not exist: {resolved}")
    WorkspaceConfigRepository(resolved).read()
    workspace_id = _slug_workspace_id(workspace_id or name or resolved.parent.name)
    stored_path = str(resolved)
    try:
        resolved_abs = resolved.resolve()
        data_root = get_app_paths().data_root
        if resolved_abs.is_relative_to(data_root):
            stored_path = str(resolved_abs.relative_to(data_root)).replace("\\", "/")
    except Exception:
        pass

    registry["workspaces"][workspace_id] = {
        "name": str(name or workspace_id),
        "config_path": stored_path,
    }
    if set_active:
        registry["active_workspace"] = workspace_id
    save_workspace_registry(registry)
    return registry


def _validate_workspace_root(workspace_root: Path):
    root = workspace_root.resolve()
    project = PROJECT_ROOT.resolve()
    if root == project or root.is_relative_to(project) or project.is_relative_to(root):
        raise ValueError(f"refusing deletion for unsafe workspace root: {root}")


def _validate_owned_path(path: Path, workspace_root: Path) -> Path:
    root = workspace_root.resolve()
    resolved = path.resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise ValueError(f"workspace-owned path escapes workspace root: {path}")
    return path


def _generated_paths(config_path: Path, workspace_root: Path) -> list[Path]:
    if not config_path.exists():
        raise ValueError("workspace config is required to delete LMZ-generated data")
    config = WorkspaceConfigRepository(config_path).read().value

    candidates = [
        config_path,
        workspace_root / "data" / "workspace.db",
        workspace_root / "data" / "topics",
    ]
    marker = workspace_root / WORKSPACE_MARKER_NAME
    if _has_valid_marker(workspace_root):
        candidates.append(marker)

    for entry in config.vaults.values():
        root_value = Path(entry.root)
        vault_root = root_value.resolve() if root_value.is_absolute() else (workspace_root / root_value).resolve()
        if vault_root == workspace_root or not vault_root.is_relative_to(workspace_root):
            raise ValueError(f"vault root escapes workspace root: {vault_root}")
        candidates.extend(vault_root / relative for relative in GENERATED_VAULT_DIRS)

    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        safe = _validate_owned_path(candidate, workspace_root)
        if safe not in seen:
            seen.add(safe)
            unique.append(safe)
    return unique


def _move_path(source: Path, destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, destination)


def _purge_staging_dir(path: Path):
    shutil.rmtree(path)


def _restore_staged_paths(moved: list[tuple[Path, Path]]) -> list[str]:
    errors = []
    for source, destination in reversed(moved):
        if not destination.exists():
            continue
        try:
            _move_path(destination, source)
        except OSError as exc:
            errors.append(f"{source}: {exc}")
    return errors


def _discard_empty_staging(staging_root: Path, restore_errors: list[str]):
    if restore_errors or not staging_root.exists():
        return
    try:
        _purge_staging_dir(staging_root)
    except OSError:
        pass


def _stage_paths(paths: list[Path], workspace_root: Path, staging_root: Path) -> list[tuple[Path, Path]]:
    moved: list[tuple[Path, Path]] = []
    try:
        for source in paths:
            if not source.exists():
                continue
            relative = source.relative_to(workspace_root)
            destination = staging_root / relative
            _move_path(source, destination)
            moved.append((source, destination))
    except OSError as exc:
        restore_errors = _restore_staged_paths(moved)
        _discard_empty_staging(staging_root, restore_errors)
        detail = f"workspace deletion staging failed: {exc}"
        if restore_errors:
            detail += f"; rollback errors: {'; '.join(restore_errors)}"
        raise WorkspaceDeletionError(detail) from exc
    return moved


def delete_workspace(workspace_id: str, mode: str = "unregister") -> dict:
    registry = load_workspace_registry()
    workspace_id = str(workspace_id or "").strip()
    mode = str(mode or "unregister").strip().casefold()
    if mode not in DELETE_MODES:
        raise ValueError(f"unknown workspace deletion mode: {mode}")
    if workspace_id == DEFAULT_WORKSPACE_ID:
        raise ValueError("Cannot delete the default workspace")
    if workspace_id not in registry["workspaces"]:
        raise KeyError(f"Workspace not found: {workspace_id}")
    if workspace_id == registry["active_workspace"]:
        raise ValueError("Cannot delete the active workspace")

    entry = registry["workspaces"][workspace_id]
    config_path = _resolve(entry.get("config_path") or "")
    workspace_root = config_path.parent.resolve()
    _validate_workspace_root(workspace_root)

    if mode == "all" and not _has_valid_marker(workspace_root):
        raise ValueError("Full deletion requires a valid LMZ workspace ownership marker")

    if mode == "unregister":
        del registry["workspaces"][workspace_id]
        save_workspace_registry(registry)
        return {**registry, "mode": mode, "cleanup_status": "not_requested", "cleanup_path": ""}

    staging_root = workspace_root.parent / f".lmz-delete-{uuid.uuid4().hex}"
    paths = [workspace_root] if mode == "all" else _generated_paths(config_path, workspace_root)
    moved: list[tuple[Path, Path]] = []
    try:
        if mode == "all":
            staging_root.mkdir(parents=True, exist_ok=False)
            destination = staging_root / workspace_root.name
            _move_path(workspace_root, destination)
            moved.append((workspace_root, destination))
        else:
            moved = _stage_paths(paths, workspace_root, staging_root)

        del registry["workspaces"][workspace_id]
        save_workspace_registry(registry)
    except WorkspaceDeletionError:
        raise
    except (OSError, ValueError) as exc:
        restore_errors = _restore_staged_paths(moved)
        _discard_empty_staging(staging_root, restore_errors)
        detail = f"workspace deletion failed: {exc}"
        if restore_errors:
            detail += f"; rollback errors: {'; '.join(restore_errors)}"
        raise WorkspaceDeletionError(detail) from exc

    if not staging_root.exists():
        return {**registry, "mode": mode, "cleanup_status": "complete", "cleanup_path": ""}
    try:
        _purge_staging_dir(staging_root)
        cleanup_status = "complete"
        cleanup_path = ""
    except OSError:
        cleanup_status = "pending"
        cleanup_path = str(staging_root)
    return {**registry, "mode": mode, "cleanup_status": cleanup_status, "cleanup_path": cleanup_path}
