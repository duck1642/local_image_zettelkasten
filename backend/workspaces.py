from pathlib import Path

import yaml


SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent
REGISTRY_PATH = PROJECT_ROOT / "config" / "workspaces.yaml"
DEFAULT_WORKSPACE_ID = "default"


def _resolve(path: str | Path, base: Path = PROJECT_ROOT) -> Path:
    value = Path(path).expanduser()
    return value.resolve() if value.is_absolute() else (base / value).resolve()


def _default_registry() -> dict:
    return {
        "active": DEFAULT_WORKSPACE_ID,
        "workspaces": {
            DEFAULT_WORKSPACE_ID: {
                "name": "Default",
                "config_path": "config/config.yaml",
            }
        },
    }


def load_workspace_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return _default_registry()
    try:
        data = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return _default_registry()
    if not isinstance(data, dict):
        return _default_registry()
    workspaces = data.get("workspaces")
    if not isinstance(workspaces, dict):
        workspaces = {}
    if DEFAULT_WORKSPACE_ID not in workspaces:
        workspaces[DEFAULT_WORKSPACE_ID] = _default_registry()["workspaces"][DEFAULT_WORKSPACE_ID]
    active = str(data.get("active") or DEFAULT_WORKSPACE_ID)
    if active not in workspaces:
        active = DEFAULT_WORKSPACE_ID
    return {"active": active, "workspaces": workspaces}


def save_workspace_registry(registry: dict):
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(yaml.safe_dump(registry, sort_keys=False, allow_unicode=True), encoding="utf-8")


def workspace_list() -> list[dict]:
    registry = load_workspace_registry()
    active = registry["active"]
    items = []
    for workspace_id, entry in sorted(registry["workspaces"].items()):
        config_path = _resolve(entry.get("config_path") or "")
        items.append({
            "id": workspace_id,
            "name": str(entry.get("name") or workspace_id),
            "config_path": str(config_path),
            "active": workspace_id == active,
            "exists": config_path.exists(),
        })
    return items


def active_workspace_config_path() -> Path:
    registry = load_workspace_registry()
    entry = registry["workspaces"].get(registry["active"]) or registry["workspaces"][DEFAULT_WORKSPACE_ID]
    return _resolve(entry.get("config_path") or "config/config.yaml")


def set_active_workspace(workspace_id: str) -> dict:
    registry = load_workspace_registry()
    workspace_id = str(workspace_id or "").strip()
    if not workspace_id or workspace_id not in registry["workspaces"]:
        raise ValueError(f"unknown workspace: {workspace_id}")
    config_path = _resolve(registry["workspaces"][workspace_id].get("config_path") or "")
    if not config_path.exists():
        raise ValueError(f"workspace config does not exist: {config_path}")
    registry["active"] = workspace_id
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
    workspace_id = _slug_workspace_id(workspace_id or name or resolved.parent.name)
    registry["workspaces"][workspace_id] = {
        "name": str(name or workspace_id),
        "config_path": str(resolved),
    }
    if set_active:
        registry["active"] = workspace_id
    save_workspace_registry(registry)
    return registry
