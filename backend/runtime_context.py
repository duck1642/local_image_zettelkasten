import os
import threading
from dataclasses import dataclass
from pathlib import Path

import yaml

from config_migrations import migrate_workspace_config


import sys

SRC_DIR = Path(__file__).resolve().parent
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).parent
else:
    PROJECT_ROOT = SRC_DIR.parent


@dataclass(frozen=True)
class VaultContext:
    id: str
    name: str
    root: Path
    vault_dir: Path
    assets_dir: Path
    notes_dir: Path
    db_path: Path
    review_dir: Path
    queues_dir: Path
    local_ingest_dir: Path
    online_ingest_dir: Path
    batches_dir: Path
    input_dir: Path
    wd_tags_dir: Path
    thumbnails_dir: Path
    logs_dir: Path


@dataclass(frozen=True)
class WorkspaceContext:
    config_path: Path
    root: Path
    topics_dir: Path
    models_dir: Path
    workspace_db_path: Path
    active_vault: VaultContext
    vaults_configured: bool


_CONTEXT_LOCK = threading.RLock()
_RUNTIME_CONTEXT: WorkspaceContext | None = None


class RuntimeNotLoadedError(RuntimeError):
    pass


def _slug_vault_id(value: str) -> str:
    cleaned = "".join(ch.casefold() if ch.isalnum() else "-" for ch in str(value or "").strip())
    return "-".join(part for part in cleaned.split("-") if part) or "default"


def _resolve_config_path(config_path: str | Path | None = None) -> Path:
    if config_path is not None:
        candidate = Path(config_path).expanduser()
        return (candidate if candidate.is_absolute() else PROJECT_ROOT / candidate).resolve()

    env_path = os.environ.get("LMZ_CONFIG_PATH")
    if env_path:
        candidate = Path(env_path).expanduser()
        return (candidate if candidate.is_absolute() else PROJECT_ROOT / candidate).resolve()

    try:
        from workspaces import active_workspace_config_path

        return active_workspace_config_path()
    except Exception:
        return PROJECT_ROOT / "config" / "config.yaml"


def _config_root_for(config_path: Path) -> Path:
    if config_path.parent == PROJECT_ROOT / "config":
        return PROJECT_ROOT
    return config_path.parent


def _load_config(config_path: Path) -> dict:
    if not config_path.exists():
        return {}
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _resolve_from_root(root: Path, path_str: str | Path) -> Path:
    value = Path(path_str)
    return value.resolve() if value.is_absolute() else (root / value).resolve()


def _vault_context(root: Path, vault_id: str, entry: dict) -> VaultContext:
    name = str(entry.get("name") or vault_id)
    vault_root = _resolve_from_root(root, str(entry.get("root") or f"data/vaults/{vault_id}"))
    vault_dir = vault_root / "vault"
    return VaultContext(
        id=vault_id,
        name=name,
        root=vault_root,
        vault_dir=vault_dir,
        assets_dir=vault_dir / "assets",
        notes_dir=vault_dir / "notes",
        db_path=vault_root / "db" / "lmz_main.db",
        review_dir=vault_root / "review",
        queues_dir=vault_root / "queues",
        local_ingest_dir=vault_root / "local_ingest",
        online_ingest_dir=vault_root / "online_ingest",
        batches_dir=vault_root / "batches",
        input_dir=vault_root / "input",
        wd_tags_dir=vault_root / "wd-tags",
        thumbnails_dir=vault_root / "ui_cache" / "thumbnails",
        logs_dir=vault_root / "logs",
    )


def build_runtime_context(config_path: str | Path | None = None, active_vault_id: str | None = None) -> WorkspaceContext:
    resolved_config_path = _resolve_config_path(config_path)
    root = _config_root_for(resolved_config_path)
    migrate_workspace_config(resolved_config_path)
    config = _load_config(resolved_config_path)
    paths = config.get("paths", {}) if isinstance(config.get("paths"), dict) else {}
    if "models" in paths:
        raise ValueError("paths.models is no longer supported; models are stored in app data/models")
    vaults = config.get("vaults", {}) if isinstance(config.get("vaults"), dict) else {}
    if not vaults:
        raise RuntimeError("config.yaml must define vaults")

    active_id = _slug_vault_id(str(active_vault_id or config.get("active_vault") or "default"))
    if active_id not in vaults:
        active_id = "default" if "default" in vaults else sorted(vaults.keys())[0]
    active_vault = _vault_context(root, active_id, vaults.get(active_id) or {})

    return WorkspaceContext(
        config_path=resolved_config_path,
        root=root,
        topics_dir=(root / "data" / "topics").resolve(),
        models_dir=(PROJECT_ROOT / "data" / "models").resolve(),
        workspace_db_path=root / "data" / "workspace.db",
        active_vault=active_vault,
        vaults_configured=bool(vaults),
    )


def has_runtime_context() -> bool:
    with _CONTEXT_LOCK:
        return _RUNTIME_CONTEXT is not None


def try_get_runtime_context() -> WorkspaceContext | None:
    with _CONTEXT_LOCK:
        return _RUNTIME_CONTEXT


def clear_runtime_context():
    global _RUNTIME_CONTEXT
    with _CONTEXT_LOCK:
        _RUNTIME_CONTEXT = None


def set_runtime_context(ctx: WorkspaceContext) -> WorkspaceContext:
    global _RUNTIME_CONTEXT
    with _CONTEXT_LOCK:
        _RUNTIME_CONTEXT = ctx
        return _RUNTIME_CONTEXT


def get_runtime_context() -> WorkspaceContext:
    global _RUNTIME_CONTEXT
    with _CONTEXT_LOCK:
        if _RUNTIME_CONTEXT is None:
            env_path = os.environ.get("LMZ_CONFIG_PATH")
            if env_path:
                _RUNTIME_CONTEXT = build_runtime_context(env_path)
                return _RUNTIME_CONTEXT
            raise RuntimeNotLoadedError("Workspace not loaded")
        return _RUNTIME_CONTEXT


def reload_runtime_context(config_path: str | Path | None = None, active_vault_id: str | None = None) -> WorkspaceContext:
    global _RUNTIME_CONTEXT
    with _CONTEXT_LOCK:
        _RUNTIME_CONTEXT = build_runtime_context(config_path, active_vault_id=active_vault_id)
        return _RUNTIME_CONTEXT


def get_active_vault_context() -> VaultContext:
    return get_runtime_context().active_vault
