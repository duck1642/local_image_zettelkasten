from fastapi import APIRouter

from api.common import *

router = APIRouter()


@router.get("/api/session-key")
async def get_session_key(request: Request):
    _validate_origin(request.headers.get("origin"))
    return {"key": _api_key()}


@router.get("/api/metadata-index/status")
async def get_metadata_index_status():
    return await asyncio.to_thread(_get_metadata_index_status_sync)

def _get_metadata_index_status_sync():
    conn = connect_database()
    try:
        return metadata_index_status(conn)
    finally:
        conn.close()

@router.post("/api/metadata-index/rebuild")
async def rebuild_metadata_index():
    return await asyncio.to_thread(start_metadata_repair_worker, True, True)

@router.post("/api/workspace-metadata/rebuild")
async def rebuild_workspace_metadata_route():
    return await asyncio.to_thread(rebuild_workspace_metadata)

@router.post("/api/workspace-metadata/prune")
async def prune_workspace_metadata_route():
    return await asyncio.to_thread(prune_unused_workspace_metadata)


@router.get("/api/system/memory")
async def get_system_memory():
    return await asyncio.to_thread(_get_system_memory_sync)

def _get_system_memory_sync():
    try:
        try:
            import psutil
            backend_mb = psutil.Process().memory_info().rss / 1024 / 1024
        except ModuleNotFoundError:
            backend_mb = _get_process_memory_mb_fallback()
        return {"backend_mb": round(backend_mb, 2)}
    except Exception as exc:
        log_system("ERROR", "Failed to read backend memory", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to read backend memory") from exc

def _get_process_memory_mb_fallback():
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessMemoryCounters), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        handle = kernel32.GetCurrentProcess()
        ok = psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())
        return counters.WorkingSetSize / 1024 / 1024

    import resource
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return value / divisor


CONFIG_SECRET_KEYS = {"pixiv_token"}


def _strip_config_secrets(config: dict) -> dict:
    safe_config = copy.deepcopy(config or {})
    external_tools = safe_config.get("external_tools")
    if isinstance(external_tools, dict):
        for key in CONFIG_SECRET_KEYS:
            external_tools.pop(key, None)
    return safe_config


def _config_runtime_info() -> dict:
    from workspaces import REGISTRY_PATH

    ctx = get_runtime_context()
    active_vault = ctx.active_vault
    mode = "obsidian" if ctx.root.name.casefold() == "lmz" and ctx.root.parent != ctx.root else "default"
    return {
        "config_path": str(ctx.config_path),
        "config_root": str(ctx.root),
        "topic_root": str(ctx.topics_dir),
        "workspace_mode": mode,
        "workspace_label": "Obsidian workspace" if mode == "obsidian" else "Default workspace",
        "workspace_registry": str(REGISTRY_PATH),
        "active_vault": active_vault.id,
        "active_vault_name": active_vault.name,
        "active_vault_root": str(active_vault.root) if active_vault.root else "",
        "vaults_configured": bool(ctx.vaults_configured),
        "db_path": str(active_vault.db_path),
        "env_override": bool(os.environ.get("LMZ_CONFIG_PATH")),
    }


def _load_public_config_sync() -> dict:
    config_path = get_runtime_context().config_path
    if not config_path.exists():
        config = _strip_config_secrets(get_config())
        config["_runtime"] = _config_runtime_info()
        return config
    with open(config_path, "r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    config = _strip_config_secrets(config)
    config["_runtime"] = _config_runtime_info()
    return config


@router.get("/api/config")
async def get_app_config():
    return await asyncio.to_thread(_load_public_config_sync)

@router.post("/api/config")
async def update_app_config(new_config: dict):
    return await asyncio.to_thread(_update_app_config_sync, new_config)

def _update_app_config_sync(new_config: dict):
    safe_config = _strip_config_secrets(new_config)
    safe_config.pop("_runtime", None)
    atomic_write_text(get_runtime_context().config_path, yaml.dump(safe_config, default_flow_style=False, allow_unicode=True))
    invalidate_config_cache()
    return {"status": "success"}


@router.get("/api/workspaces")
async def get_workspaces():
    return await asyncio.to_thread(_get_workspaces_sync)


def _get_workspaces_sync():
    from workspaces import load_workspace_registry, workspace_list

    return {"active": load_workspace_registry()["active"], "items": workspace_list()}


@router.post("/api/workspaces/active")
async def set_workspace_active(body: dict):
    return await asyncio.to_thread(_set_workspace_active_sync, body)


def _set_workspace_active_sync(body: dict):
    from workspaces import set_active_workspace, workspace_list

    workspace_id = str((body or {}).get("id") or "").strip()
    if not workspace_id:
        raise HTTPException(status_code=400, detail="workspace id is required")
    try:
        registry = set_active_workspace(workspace_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success", "active": registry["active"], "restart_required": True, "items": workspace_list()}


@router.post("/api/workspaces/obsidian")
async def add_obsidian_workspace(body: dict):
    return await asyncio.to_thread(_add_obsidian_workspace_sync, body)


def _add_obsidian_workspace_sync(body: dict):
    from tools.maintenance.setup_obsidian_workspace import setup_obsidian_workspace
    from workspaces import register_workspace, workspace_list

    vault_path = str((body or {}).get("path") or "").strip()
    name = str((body or {}).get("name") or "Obsidian Workspace").strip() or "Obsidian Workspace"
    set_active = bool((body or {}).get("set_active"))
    if not vault_path:
        raise HTTPException(status_code=400, detail="Obsidian vault path is required")
    try:
        payload = setup_obsidian_workspace(vault_path)
        registry = register_workspace(name, payload["config_path"], set_active=set_active)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "status": "success",
        "workspace": payload,
        "active": registry["active"],
        "restart_required": set_active,
        "items": workspace_list(),
    }


@router.get("/api/vaults")
async def get_vaults():
    return await asyncio.to_thread(_get_vaults_sync)


def _get_vaults_sync():
    from vaults import active_vault_id, vault_list

    return {"active": active_vault_id(), "items": vault_list()}


@router.post("/api/vaults")
async def create_vault(body: dict):
    return await asyncio.to_thread(_create_vault_sync, body)


def _create_vault_sync(body: dict):
    from vaults import create_vault

    name = str((body or {}).get("name") or "").strip()
    vault_id = str((body or {}).get("id") or "").strip() or None
    if not name:
        raise HTTPException(status_code=400, detail="vault name is required")
    try:
        payload = create_vault(name, vault_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    payload["restart_required"] = False
    return payload


@router.patch("/api/vaults/{vault_id}")
async def rename_vault(vault_id: str, body: dict):
    return await asyncio.to_thread(_rename_vault_sync, vault_id, body)


def _rename_vault_sync(vault_id: str, body: dict):
    from vaults import rename_vault

    name = str((body or {}).get("name") or "").strip()
    try:
        return rename_vault(vault_id, name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/vaults/active")
async def set_vault_active(body: dict):
    return await asyncio.to_thread(_set_vault_active_sync, body)


def _set_vault_active_sync(body: dict):
    from vaults import set_active_vault

    vault_id = str((body or {}).get("id") or "").strip()
    if not vault_id:
        raise HTTPException(status_code=400, detail="vault id is required")
    try:
        return set_active_vault(vault_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/api/vaults/{vault_id}")
async def delete_vault(vault_id: str, confirm: bool = Query(False)):
    return await asyncio.to_thread(_delete_vault_sync, vault_id, confirm)


def _delete_vault_sync(vault_id: str, confirm: bool = False):
    from vaults import delete_vault

    try:
        return delete_vault(vault_id, confirm=confirm)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/vaults/{target_id}/merge-preview")
async def preview_vault_merge(target_id: str, body: dict):
    return await asyncio.to_thread(_preview_vault_merge_sync, target_id, body)


def _preview_vault_merge_sync(target_id: str, body: dict):
    from vaults import preview_vault_merge

    sources = list((body or {}).get("source_vault_ids") or [])
    try:
        return preview_vault_merge(target_id, sources)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/vaults/{target_id}/merge")
async def merge_vaults(target_id: str, body: dict):
    return await asyncio.to_thread(_merge_vaults_sync, target_id, body)


def _merge_vaults_sync(target_id: str, body: dict):
    from vaults import merge_vaults

    sources = list((body or {}).get("source_vault_ids") or [])
    try:
        return merge_vaults(target_id, sources)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


__all__ = [name for name in globals() if not name.startswith("__")]

