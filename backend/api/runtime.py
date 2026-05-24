from fastapi import APIRouter
from fastapi.responses import JSONResponse

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
        return str(get_runtime_context().project_root).casefold()
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
    blocked = await asyncio.to_thread(_runtime_switch_blocker)
    if blocked:
        return blocked
    return await asyncio.to_thread(_set_workspace_active_sync, body)


def _runtime_switch_blocker():
    from api.ingestion import runtime_switch_preflight

    preflight = runtime_switch_preflight()
    if preflight.get("allowed"):
        return None
    return JSONResponse(
        status_code=409,
        content={"detail": "Runtime switch blocked", "blockers": list(preflight.get("blockers") or [])},
    )


def _ensure_runtime_switch_allowed():
    from api.ingestion import runtime_switch_preflight

    preflight = runtime_switch_preflight()
    if not preflight.get("allowed"):
        raise HTTPException(
            status_code=409,
            detail={"detail": "Runtime switch blocked", "blockers": list(preflight.get("blockers") or [])},
        )


def _set_workspace_active_sync(body: dict):
    from workspaces import set_active_workspace, workspace_list
    from runtime_context import reload_runtime_context
    from db.search_manager import search_manager
    from metadata_index import restart_metadata_watchdog

    _ensure_runtime_switch_allowed()
    workspace_id = str((body or {}).get("id") or "").strip()
    if not workspace_id:
        raise HTTPException(status_code=400, detail="workspace id is required")
    try:
        registry = set_active_workspace(workspace_id)

        # Dynamic workspace switching runtime updates
        import os
        os.environ.pop("LMZ_CONFIG_PATH", None)

        new_ctx = reload_runtime_context()
        search_manager.reset_all()
        restart_metadata_watchdog(new_ctx)

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success", "active": registry["active"], "restart_required": False, "items": workspace_list()}


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
    delete_sources = bool((body or {}).get("delete_sources", True))
    try:
        return merge_vaults(target_id, sources, delete_sources=delete_sources)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/vaults/{vault_id}/health")
async def get_vault_health(vault_id: str):
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
    return await asyncio.to_thread(_repair_vault_sync, vault_id, body)


def _repair_vault_sync(vault_id: str, body: dict):
    from vaults import repair_vault

    try:
        return repair_vault(
            vault_id,
            actions=list((body or {}).get("actions") or []),
            confirm_destructive=bool((body or {}).get("confirm_destructive")),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/vaults/{vault_id}/backup")
async def backup_vault(vault_id: str):
    return await asyncio.to_thread(_backup_vault_sync, vault_id)


def _backup_vault_sync(vault_id: str):
    from vaults import backup_vault

    try:
        return backup_vault(vault_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/vaults/{vault_id}/export")
async def export_vault(vault_id: str):
    return await asyncio.to_thread(_export_vault_sync, vault_id)


def _export_vault_sync(vault_id: str):
    from vaults import export_vault

    try:
        return export_vault(vault_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/vaults/import")
async def import_vault(body: dict):
    return await asyncio.to_thread(_import_vault_sync, body)


def _import_vault_sync(body: dict):
    from vaults import import_vault_package

    try:
        return import_vault_package(
            str((body or {}).get("package_path") or "").strip(),
            name=str((body or {}).get("name") or "").strip() or None,
            vault_id=str((body or {}).get("id") or "").strip() or None,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


__all__ = [name for name in globals() if not name.startswith("__")]

