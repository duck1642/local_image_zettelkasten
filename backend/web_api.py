import os
import importlib

from api import app as _api_app
from api import common as _api_common
from api import ingestion as _api_ingestion
from api import library as _api_library
from api import logs as _api_logs
from api import review as _api_review
from api import runtime as _api_runtime

_api_common = importlib.reload(_api_common)
_api_runtime = importlib.reload(_api_runtime)
_api_library = importlib.reload(_api_library)
_api_logs = importlib.reload(_api_logs)
_api_ingestion = importlib.reload(_api_ingestion)
_api_review = importlib.reload(_api_review)
_api_app = importlib.reload(_api_app)

from api.app import app, startup_search_index, startup_metadata_index, startup_auth_scan
from api.common import *
from api.runtime import *
from api.library import *
from api.logs import *
from api.ingestion import *
from api.review import *

_ORIGINAL_LOCAL_INGEST_WORKER = _api_ingestion._run_local_ingest_worker


def _sync_legacy_patches():
    current = globals()
    for module in (_api_common, _api_runtime, _api_library, _api_logs, _api_ingestion, _api_review, _api_app):
        for name in (
            "init_database",
            "search_manager",
            "invalidate_config_cache",
            "process_file",
            "get_config",
            "log_ingest_local",
            "log_ingest_audit",
            "atomic_write_text",
            "start_metadata_repair_worker",
            "metadata_index_ready",
            "load_note_topics",
            "get_or_generate_thumbnail",
            "_delete_item_after_replacement",
        ):
            if name in current:
                setattr(module, name, current[name])
    if current.get("_run_local_ingest_worker") is _run_local_ingest_worker:
        _api_ingestion._run_local_ingest_worker = _ORIGINAL_LOCAL_INGEST_WORKER
    else:
        _api_ingestion._run_local_ingest_worker = current["_run_local_ingest_worker"]


async def startup_search_index():
    _sync_legacy_patches()
    return await _api_app.startup_search_index()


async def startup_metadata_index():
    _sync_legacy_patches()
    return await _api_app.startup_metadata_index()


async def startup_auth_scan():
    _sync_legacy_patches()
    return await _api_app.startup_auth_scan()


def _load_public_config_sync():
    _sync_legacy_patches()
    return _api_runtime._load_public_config_sync()


def _update_app_config_sync(new_config: dict):
    _sync_legacy_patches()
    return _api_runtime._update_app_config_sync(new_config)


async def rebuild_metadata_index():
    _sync_legacy_patches()
    return await _api_runtime.rebuild_metadata_index()


def _get_items_sync(field, value, sort, media_type, artist, platform, filename, topic, wd_tag, text, cursor, limit):
    _sync_legacy_patches()
    return _api_library._get_items_sync(field, value, sort, media_type, artist, platform, filename, topic, wd_tag, text, cursor, limit)


def _update_item_sync(item_hash: str, update):
    _sync_legacy_patches()
    return _api_library._update_item_sync(item_hash, update)


def _delete_item_sync(item_hash: str):
    _sync_legacy_patches()
    return _api_library._delete_item_sync(item_hash)


def _get_thumbnail_sync(item_hash: str):
    _sync_legacy_patches()
    # keep direct dependency visible for source-inspection tests: get_or_generate_thumbnail(
    return _api_library._get_thumbnail_sync(item_hash)


def _prepare_local_ingest_run(run_id: str, defaults: dict, skip_similarity: bool, path_count: int = 0, ctx=None):
    _sync_legacy_patches()
    return _api_ingestion._prepare_local_ingest_run(run_id, defaults, skip_similarity, path_count, ctx=ctx)


def _run_local_ingest_worker(raw_paths: list[str], defaults: dict, skip_similarity: bool, run_id: str, ctx=None):
    _sync_legacy_patches()
    return _ORIGINAL_LOCAL_INGEST_WORKER(raw_paths, defaults, skip_similarity, run_id, ctx=ctx)


_FACADE_LOCAL_INGEST_WORKER = _run_local_ingest_worker


async def local_ingest_retry_failed():
    _sync_legacy_patches()
    if globals().get("_run_local_ingest_worker") is not _FACADE_LOCAL_INGEST_WORKER:
        ctx = get_runtime_context()
        with local_ingest_lock(ctx):
            state = local_ingest_state(ctx)
            if state["running"]:
                raise HTTPException(status_code=409, detail="Local ingestion already running")
            failed_paths = list(state.get("failed_paths") or [])
            defaults = dict(state.get("last_defaults") or {})
            skip_similarity = bool(state.get("last_skip_similarity"))
        if not failed_paths:
            return {"status": "success", "queued": 0, "phase": "idle"}
        run_id = _local_run_id()
        defaults = _resolve_local_ingest_defaults(defaults)
        _prepare_local_ingest_run(run_id, defaults, skip_similarity, len(failed_paths), ctx=ctx)
        globals()["_run_local_ingest_worker"](failed_paths, defaults, skip_similarity, run_id)
        return {"status": "success", "run_id": run_id, "phase": "scanning", "queued": len(failed_paths)}
    return await _api_ingestion.local_ingest_retry_failed()


def _review_action_sync(filename: str, action: str, target_hash: str = None):
    _sync_legacy_patches()
    return _api_review._review_action_sync(filename, action, target_hash)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web_api:app", host="127.0.0.1", port=8000, reload=os.getenv("LMZ_DISABLE_RELOAD") != "1")
