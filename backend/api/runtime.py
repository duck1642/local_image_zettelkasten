from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.common import *
from runtime_context import (
    RuntimeNotLoadedError,
    build_runtime_context,
    clear_runtime_context,
    has_runtime_context,
    try_get_runtime_context,
)
from path_policy import validate_workspace_config_paths, workspace_relative_path
from utils import validate_config_schema
from runtime_activation import activate_runtime_context, active_vault_is_usable
from api.guards import (
    require_workspace_context,
    require_usable_vault_context,
    require_usable_target_vault_context,
)

router = APIRouter()


@router.get("/api/session-key")
async def get_session_key(request: Request):
    _validate_origin(request.headers.get("origin"))
    return {"key": _api_key()}


@router.get("/api/metadata-index/status")
async def get_metadata_index_status():
    require_usable_vault_context()
    return await asyncio.to_thread(_get_metadata_index_status_sync)

def _get_metadata_index_status_sync():
    conn = connect_database()
    try:
        return metadata_index_status(conn)
    finally:
        conn.close()

@router.post("/api/metadata-index/rebuild")
async def rebuild_metadata_index():
    require_usable_vault_context()
    return await asyncio.to_thread(start_metadata_repair_worker, True, True)

@router.post("/api/workspace-metadata/rebuild")
async def rebuild_workspace_metadata_route():
    require_workspace_context()
    return await asyncio.to_thread(rebuild_workspace_metadata)

@router.post("/api/workspace-metadata/prune")
async def prune_workspace_metadata_route():
    require_workspace_context()
    return await asyncio.to_thread(prune_unused_workspace_metadata)


@router.get("/api/system/memory")
async def get_system_memory():
    require_workspace_context()
    return await asyncio.to_thread(_get_system_memory_sync)

def _get_system_memory_sync():
    try:
        try:
            import psutil
            payload = _get_psutil_app_memory(psutil)
        except ModuleNotFoundError:
            backend_mb = _get_process_memory_mb_fallback()
            payload = {
                "backend_mb": round(backend_mb, 2),
                "app_mb": round(backend_mb, 2),
                "runtime_mb": round(backend_mb, 2),
                "roles": _empty_memory_roles(backend_mb=backend_mb),
                "process_count": 1,
                "mode": "fallback",
                "warnings": ["psutil unavailable; reporting backend process only"],
                "processes": [],
            }
        return payload
    except Exception as exc:
        log_system("ERROR", "Failed to read backend memory", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to read backend memory") from exc

def _empty_memory_roles(backend_mb: float = 0.0) -> dict:
    return {
        "backend_mb": round(float(backend_mb or 0.0), 2),
        "tauri_mb": 0.0,
        "webview_mb": 0.0,
        "subprocess_mb": 0.0,
        "dev_tool_mb": 0.0,
        "other_mb": 0.0,
    }

def _process_name(proc) -> str:
    try:
        return str(proc.name() or "")
    except Exception:
        return ""

def _process_exe(proc) -> str:
    try:
        return str(proc.exe() or "")
    except Exception:
        return ""

def _process_cmdline(proc) -> list[str]:
    try:
        return [str(part or "") for part in (proc.cmdline() or [])]
    except Exception:
        return []

def _process_rss_mb(proc) -> float | None:
    try:
        return float(proc.memory_info().rss) / 1024 / 1024
    except Exception:
        return None

def _process_children(proc, recursive: bool = True) -> list:
    try:
        return list(proc.children(recursive=recursive))
    except Exception:
        return []

def _process_parent(proc):
    try:
        return proc.parent()
    except Exception:
        return None

def _looks_like_tauri_host(proc) -> bool:
    name = _process_name(proc).casefold()
    exe = _process_exe(proc).casefold()
    haystack = " ".join([name, exe])
    return any(token in haystack for token in ("lmz", "local_media_zettelkasten", "tauri"))

def _looks_like_dev_launcher(proc) -> bool:
    cmdline = " ".join(_process_cmdline(proc)).casefold()
    return "dev.py" in cmdline and "local_media_zettelkasten" in cmdline

def _project_path_token() -> str:
    try:
        return str(get_runtime_context().root).casefold()
    except Exception:
        try:
            return str(Path(__file__).resolve().parents[2]).casefold()
        except Exception:
            return "local_media_zettelkasten"

def _process_matches_project(proc, project_token: str) -> bool:
    if not project_token:
        return False
    haystack = " ".join([_process_exe(proc), *_process_cmdline(proc)]).casefold()
    return project_token in haystack or "local_media_zettelkasten" in haystack

def _scan_project_processes(psutil_module, project_token: str) -> list:
    matches = []
    try:
        iterator = psutil_module.process_iter(["pid", "name", "exe", "cmdline"])
    except Exception:
        return matches
    for proc in iterator:
        if _process_matches_project(proc, project_token):
            matches.append(proc)
            matches.extend(_process_children(proc, recursive=True))
    return matches

def _role_for_process(proc, backend_pid: int) -> str:
    try:
        if int(proc.pid) == int(backend_pid):
            return "backend"
    except Exception:
        pass
    name = _process_name(proc).casefold()
    exe = _process_exe(proc).casefold()
    cmdline = " ".join(_process_cmdline(proc)).casefold()
    haystack = " ".join([name, exe, cmdline])
    if "msedgewebview2" in haystack:
        return "webview"
    if any(token in haystack for token in ("ffmpeg", "gallery-dl", "gallery_dl", "yt-dlp", "yt_dlp")):
        return "subprocess"
    if _looks_like_tauri_host(proc):
        return "tauri"
    if any(token in haystack for token in ("node", "npm", "cargo", "vite", "tauri-cli")):
        return "dev_tool"
    return "other"

def _collect_process_group(backend_proc, psutil_module=None) -> tuple[list, str, list[str]]:
    warnings: list[str] = []
    backend_children = _process_children(backend_proc, recursive=True)
    parent = _process_parent(backend_proc)
    processes = [backend_proc, *backend_children]
    mode = "backend_tree"
    if parent and _looks_like_tauri_host(parent):
        processes = [parent, *_process_children(parent, recursive=True)]
        mode = "packaged_sidecar"
    elif parent and _looks_like_dev_launcher(parent):
        processes = [parent, *_process_children(parent, recursive=True)]
        mode = "dev_launcher"
    elif psutil_module is not None:
        project_matches = _scan_project_processes(psutil_module, _project_path_token())
        if project_matches:
            processes = [backend_proc, *backend_children, *project_matches]
            mode = "dev_scan"
            warnings.append("app root not detected; included readable project-matched process trees")
        else:
            warnings.append("app root not detected; reporting backend process tree only")
    else:
        warnings.append("app root not detected; reporting backend process tree only")

    by_pid = {}
    for proc in processes:
        try:
            by_pid[int(proc.pid)] = proc
        except Exception:
            continue
    return list(by_pid.values()), mode, warnings

def _aggregate_memory_processes(processes: list, backend_pid: int, mode: str, warnings: list[str]) -> dict:
    roles = _empty_memory_roles()
    process_rows = []
    app_mb = 0.0
    for proc in processes:
        rss_mb = _process_rss_mb(proc)
        if rss_mb is None:
            warnings.append(f"process {getattr(proc, 'pid', '?')} memory unavailable")
            continue
        role = _role_for_process(proc, backend_pid)
        key = f"{role}_mb"
        if key not in roles:
            key = "other_mb"
        rounded = round(rss_mb, 2)
        roles[key] = round(float(roles.get(key, 0.0)) + rounded, 2)
        app_mb += rss_mb
        process_rows.append({
            "pid": int(getattr(proc, "pid", 0) or 0),
            "name": _process_name(proc),
            "role": role,
            "rss_mb": rounded,
        })
    runtime_mb = (
        roles["backend_mb"]
        + roles["tauri_mb"]
        + roles["webview_mb"]
        + roles["subprocess_mb"]
    )
    return {
        "backend_mb": roles["backend_mb"],
        "app_mb": round(app_mb, 2),
        "runtime_mb": round(runtime_mb, 2),
        "roles": roles,
        "process_count": len(process_rows),
        "mode": mode,
        "warnings": warnings,
        "processes": sorted(process_rows, key=lambda row: (row["role"], row["pid"])),
    }

def _get_psutil_app_memory(psutil_module) -> dict:
    backend_proc = psutil_module.Process()
    processes, mode, warnings = _collect_process_group(backend_proc, psutil_module)
    return _aggregate_memory_processes(processes, int(backend_proc.pid), mode, warnings)

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
    mode = "lmz" if ctx.root.name.casefold() == "lmz" and ctx.root.parent != ctx.root else "default"
    return {
        "config_path": str(ctx.config_path),
        "config_root": str(ctx.root),
        "topic_root": str(ctx.topics_dir),
        "workspace_mode": mode,
        "workspace_label": "LMZ workspace" if mode == "lmz" else "Default workspace",
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
    require_workspace_context()
    return await asyncio.to_thread(_load_public_config_sync)

@router.post("/api/config")
async def update_app_config(new_config: dict):
    require_workspace_context()
    return await asyncio.to_thread(_update_app_config_sync, new_config)

def _update_app_config_sync(new_config: dict):
    safe_config = copy.deepcopy(new_config or {})
    safe_config.pop("_runtime", None)
    try:
        validate_workspace_config_paths(safe_config, get_runtime_context().root)
        validate_config_schema(safe_config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
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
    blocked = await asyncio.to_thread(_runtime_switch_blocker)
    if blocked:
        return blocked
    return await asyncio.to_thread(_set_workspace_active_sync, body)


def _runtime_switch_blocker():
    if not has_runtime_context():
        return None
    from api.ingestion import runtime_switch_preflight

    preflight = runtime_switch_preflight()
    if preflight.get("allowed"):
        return None
    return JSONResponse(
        status_code=409,
        content={"detail": "Runtime switch blocked", "blockers": list(preflight.get("blockers") or [])},
    )


def _ensure_runtime_switch_allowed():
    if not has_runtime_context():
        return
    from api.ingestion import runtime_switch_preflight

    preflight = runtime_switch_preflight()
    if not preflight.get("allowed"):
        raise HTTPException(
            status_code=409,
            detail={"detail": "Runtime switch blocked", "blockers": list(preflight.get("blockers") or [])},
        )


def _set_workspace_active_sync(body: dict):
    _ensure_runtime_switch_allowed()
    workspace_id = str((body or {}).get("id") or "").strip()
    if not workspace_id:
        raise HTTPException(status_code=400, detail="workspace id is required")
    payload = _load_workspace_sync(workspace_id)
    if payload.get("status") != "success":
        return payload
    from workspaces import load_workspace_registry, workspace_list

    return {
        "status": "success",
        "active": load_workspace_registry()["active"],
        "restart_required": False,
        "items": workspace_list(),
    }


@router.post("/api/workspaces")
async def create_workspace(body: dict):
    return await asyncio.to_thread(_create_workspace_sync, body)


def _create_workspace_sync(body: dict):
    from workspace_setup import setup_lmz_workspace
    from workspaces import register_workspace, workspace_list

    parent_path = str((body or {}).get("path") or "").strip()
    name = str((body or {}).get("name") or "LMZ Workspace").strip() or "LMZ Workspace"
    set_active = bool((body or {}).get("set_active"))
    if not parent_path:
        raise HTTPException(status_code=400, detail="Workspace parent folder is required")
    try:
        payload = setup_lmz_workspace(parent_path)
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




@router.delete("/api/workspaces/{workspace_id}")
async def delete_workspace(
    workspace_id: str,
    mode: Literal["unregister", "generated", "all"] = Query("unregister"),
):
    blocked = await asyncio.to_thread(_runtime_switch_blocker)
    if blocked:
        return blocked
    return await asyncio.to_thread(_delete_workspace_sync, workspace_id, mode)


def _delete_workspace_sync(workspace_id: str, mode: str = "unregister"):
    from workspaces import WorkspaceDeletionError, delete_workspace, workspace_list
    from fastapi import HTTPException

    try:
        result = delete_workspace(workspace_id, mode=mode)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except WorkspaceDeletionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return {
        "status": "success",
        "active": result["active"],
        "mode": result["mode"],
        "cleanup_status": result["cleanup_status"],
        "cleanup_path": result["cleanup_path"],
        "items": workspace_list(),
    }


@router.get("/api/vaults")
async def get_vaults():
    require_workspace_context()
    return await asyncio.to_thread(_get_vaults_sync)


def _get_vaults_sync():
    from vaults import active_vault_id, vault_list

    return {"active": active_vault_id(), "items": vault_list()}


@router.post("/api/vaults")
async def create_vault(body: dict):
    require_workspace_context()
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
    require_workspace_context()
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
    require_workspace_context()
    blocked = await asyncio.to_thread(_runtime_switch_blocker)
    if blocked:
        return blocked
    return await asyncio.to_thread(_set_vault_active_sync, body)


def _set_vault_active_sync(body: dict):
    from vaults import set_active_vault

    _ensure_runtime_switch_allowed()
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
    require_workspace_context()
    return await asyncio.to_thread(_delete_vault_sync, vault_id, confirm)


def _delete_vault_sync(vault_id: str, confirm: bool = False):
    from vaults import delete_vault

    try:
        return delete_vault(vault_id, confirm=confirm)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/vaults/merge-preview")
async def preview_merged_vault(body: dict):
    require_workspace_context()
    return await asyncio.to_thread(_preview_merged_vault_sync, body)


def _preview_merged_vault_sync(body: dict):
    from vaults import preview_merged_vault

    name = str((body or {}).get("name") or "").strip()
    sources = list((body or {}).get("source_vault_ids") or [])
    try:
        return preview_merged_vault(name, sources)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/vaults/merge")
async def create_merged_vault(body: dict):
    require_workspace_context()
    return await asyncio.to_thread(_create_merged_vault_sync, body)


def _create_merged_vault_sync(body: dict):
    from vaults import merge_vaults_to_new

    name = str((body or {}).get("name") or "").strip()
    sources = list((body or {}).get("source_vault_ids") or [])
    try:
        payload = merge_vaults_to_new(name, sources)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    payload["restart_required"] = False
    return payload


@router.get("/api/vaults/{vault_id}/health")
async def get_vault_health(vault_id: str):
    require_usable_target_vault_context(vault_id)
    return await asyncio.to_thread(_get_vault_health_sync, vault_id)


def _get_vault_health_sync(vault_id: str):
    from vaults import audit_vault_health

    try:
        return audit_vault_health(vault_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/vaults/{vault_id}/repair")
async def repair_vault(vault_id: str, body: dict):
    require_usable_target_vault_context(vault_id)
    return await asyncio.to_thread(_repair_vault_sync, vault_id, body)


def _repair_vault_sync(vault_id: str, body: dict):
    from vaults import repair_vault

    try:
        return repair_vault(
            vault_id,
            actions=list((body or {}).get("actions") or []),
            confirm_destructive=(body or {}).get("confirm_destructive") is True,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/vaults/{vault_id}/backup")
async def backup_vault(vault_id: str, body: dict | None = None):
    require_usable_target_vault_context(vault_id)
    return await asyncio.to_thread(_backup_vault_sync, vault_id, body or {})


def _backup_vault_sync(vault_id: str, body: dict | None = None):
    from vaults import backup_vault

    try:
        return backup_vault(vault_id, confirm=(body or {}).get("confirm") is True)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/vaults/{vault_id}/export")
async def export_vault(vault_id: str, body: dict | None = None):
    require_usable_target_vault_context(vault_id)
    return await asyncio.to_thread(_export_vault_sync, vault_id, body or {})


def _export_vault_sync(vault_id: str, body: dict | None = None):
    from vaults import export_vault

    try:
        return export_vault(
            vault_id,
            confirm=(body or {}).get("confirm") is True,
            include_review=(body or {}).get("include_review") is True,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class RelocateWorkspaceRequest(BaseModel):
    workspace_id: str
    new_config_path: str

class RelocateVaultRequest(BaseModel):
    vault_id: str
    new_vault_root: str

@router.post("/api/workspaces/{workspace_id}/load")
async def load_workspace(workspace_id: str):
    return await asyncio.to_thread(_load_workspace_sync, workspace_id)

def _load_workspace_sync(workspace_id: str):
    from workspaces import load_workspace_registry, set_active_workspace, _resolve
    
    registry = load_workspace_registry()
    if workspace_id not in registry["workspaces"]:
        raise HTTPException(status_code=404, detail="Workspace not found")
        
    entry = registry["workspaces"][workspace_id]
    config_path = _resolve(entry.get("config_path") or "")
    if not config_path.exists():
        return {
            "status": "relocate_workspace",
            "message": f"Workspace configuration file not found at {config_path}",
            "config_path": str(config_path)
        }

    previous_ctx = try_get_runtime_context()
    try:
        import os
        os.environ.pop("LMZ_CONFIG_PATH", None)
        new_ctx = build_runtime_context(config_path)
        
        active_vault = new_ctx.active_vault
        if active_vault and active_vault.root and not active_vault_is_usable(new_ctx):
            vault_root = Path(active_vault.root)
            activate_runtime_context(new_ctx, hydrate=False)
            configure_terminal_logging()
            return {
                "status": "relocate_vault",
                "message": f"Vault directory is missing or outside the workspace at {vault_root}",
                "vault_id": active_vault.id,
                "vault_name": active_vault.name,
                "vault_root": str(vault_root)
            }
        
        activate_runtime_context(new_ctx)
        configure_terminal_logging()

        set_active_workspace(workspace_id)
            
        return {
            "status": "success",
            "active_workspace": workspace_id,
            "active_vault": active_vault.id if active_vault else None
        }
    except ValueError as e:
        if previous_ctx is not None:
            activate_runtime_context(previous_ctx, hydrate=False)
            configure_terminal_logging()
        else:
            clear_runtime_context()
            from logger import reconfigure_logging
            reconfigure_logging(None)
            configure_terminal_logging()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if previous_ctx is not None:
            activate_runtime_context(previous_ctx, hydrate=False)
            configure_terminal_logging()
        else:
            clear_runtime_context()
            from logger import reconfigure_logging
            reconfigure_logging(None)
            configure_terminal_logging()
        log_system("ERROR", "Failed to load workspace", workspace_id=workspace_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to load workspace: {e}")

@router.post("/api/workspaces/relocate")
async def relocate_workspace(body: RelocateWorkspaceRequest):
    return await asyncio.to_thread(_relocate_workspace_sync, body.workspace_id, body.new_config_path)

def _relocate_workspace_sync(workspace_id: str, new_config_path: str):
    from workspaces import load_workspace_registry, save_workspace_registry, _resolve, PROJECT_ROOT
    registry = load_workspace_registry()
    if workspace_id not in registry["workspaces"]:
        raise HTTPException(status_code=404, detail="Workspace not found")
        
    resolved = _resolve(new_config_path)
    if not resolved.exists():
        raise HTTPException(status_code=400, detail=f"File does not exist: {resolved}")
        
    stored_path = str(resolved)
    try:
        resolved_abs = resolved.resolve()
        project_root_abs = PROJECT_ROOT.resolve()
        if resolved_abs.is_relative_to(project_root_abs):
            stored_path = str(resolved_abs.relative_to(project_root_abs)).replace("\\", "/")
    except Exception:
        pass
        
    registry["workspaces"][workspace_id]["config_path"] = stored_path
    save_workspace_registry(registry)
    return {"status": "success", "config_path": str(resolved)}

@router.post("/api/vaults/relocate")
async def relocate_vault(body: RelocateVaultRequest):
    require_workspace_context()
    return await asyncio.to_thread(_relocate_vault_sync, body.vault_id, body.new_vault_root)

def _relocate_vault_sync(vault_id: str, new_vault_root: str):
    from vaults import _read_config, _write_config, vault_id_slug
    from runtime_context import reload_runtime_context
    from workspaces import load_workspace_registry, set_active_workspace, _resolve

    ctx = get_runtime_context()
    config = _read_config()
    clean_id = vault_id_slug(vault_id)
    if "vaults" not in config or clean_id not in config["vaults"]:
        raise HTTPException(status_code=404, detail="Vault not found")
        
    resolved_root = Path(new_vault_root).expanduser().resolve()
    if not resolved_root.exists():
        raise HTTPException(status_code=400, detail=f"Directory does not exist: {resolved_root}")

    try:
        stored_root = workspace_relative_path(resolved_root, ctx.root, label="vault root")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    config["vaults"][clean_id]["root"] = stored_root
    _write_config(config)
    
    new_ctx = reload_runtime_context(ctx.config_path)
    activate_runtime_context(new_ctx)
    configure_terminal_logging()

    registry = load_workspace_registry()
    for candidate_id, entry in registry.get("workspaces", {}).items():
        if _resolve(entry.get("config_path") or "") == new_ctx.config_path:
            set_active_workspace(candidate_id)
            break
    return {"status": "success", "vault_root": str(resolved_root)}


@router.post("/api/vaults/import")
async def import_vault(body: dict):
    require_workspace_context()
    return await asyncio.to_thread(_import_vault_sync, body)


@router.post("/api/vaults/import-preview")
async def import_vault_preview(body: dict):
    require_workspace_context()
    return await asyncio.to_thread(_import_vault_preview_sync, body)


@router.post("/api/vaults/restore-preview")
async def restore_backup_preview(body: dict):
    require_workspace_context()
    return await asyncio.to_thread(_restore_backup_preview_sync, body)


@router.post("/api/vaults/restore")
async def restore_backup(body: dict):
    require_workspace_context()
    return await asyncio.to_thread(_restore_backup_sync, body)


def _import_vault_preview_sync(body: dict):
    from vaults import preview_import_vault_package

    try:
        return preview_import_vault_package(
            str((body or {}).get("package_path") or "").strip(),
            target_name=str((body or {}).get("target_name") or (body or {}).get("name") or "").strip() or None,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _restore_backup_preview_sync(body: dict):
    from vaults import preview_restore_backup_package

    try:
        return preview_restore_backup_package(
            str((body or {}).get("package_path") or "").strip(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _restore_backup_sync(body: dict):
    from vaults import restore_backup_package

    try:
        return restore_backup_package(
            str((body or {}).get("package_path") or "").strip(),
            package_fingerprint_value=str((body or {}).get("package_fingerprint") or "").strip(),
            confirm=(body or {}).get("confirm") is True,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _import_vault_sync(body: dict):
    from vaults import import_vault_package

    try:
        return import_vault_package(
            str((body or {}).get("package_path") or "").strip(),
            target_name=str((body or {}).get("target_name") or (body or {}).get("name") or "").strip() or None,
            package_fingerprint_value=str((body or {}).get("package_fingerprint") or "").strip(),
            confirm=(body or {}).get("confirm") is True,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


__all__ = [name for name in globals() if not name.startswith("__")]

