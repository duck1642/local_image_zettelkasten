import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from db.sqlite_operator import init_database
from db.search_manager import search_manager
from logger import log_system
from metadata_index import start_metadata_repair_worker, start_metadata_watchdog
from runtime_context import RuntimeNotLoadedError, has_runtime_context, reload_runtime_context

from api.common import (
    ALLOWED_ORIGINS,
    EXTENSION_ORIGIN_REGEX,
    MUTATING_METHODS,
    _assets_dir,
    _file_response_under,
    _require_api_key,
    _review_dir,
    _scan_auth_status_sync,
    _validate_origin,
    configure_terminal_logging,
)
from api import capture, ingestion, library, logs, review, runtime

LAUNCHER_SAFE_EXACT_PATHS = {
    "/",
    "/api/session-key",
    "/api/workspaces",
    "/api/workspaces/active",
    "/api/workspaces/relocate",
}
LAUNCHER_SAFE_PREFIXES = (
    "/api/workspaces/",
)


def _is_launcher_safe_path(path: str) -> bool:
    if path in LAUNCHER_SAFE_EXACT_PATHS:
        return True
    return any(path.startswith(prefix) and path.endswith("/load") for prefix in LAUNCHER_SAFE_PREFIXES)


def _load_env_workspace_if_requested():
    env_path = os.environ.get("LMZ_CONFIG_PATH")
    if not env_path or has_runtime_context():
        return
    from logger import reconfigure_logging

    try:
        ctx = reload_runtime_context(env_path)
        reconfigure_logging(ctx)
        configure_terminal_logging()
    except Exception as exc:
        log_system("WARNING", "LMZ_CONFIG_PATH workspace load failed; staying in launcher mode", error=str(exc))


async def startup_auth_scan():
    if not has_runtime_context():
        return
    await asyncio.to_thread(_scan_auth_status_sync, "startup")


async def startup_env_workspace():
    await asyncio.to_thread(_load_env_workspace_if_requested)


async def startup_metadata_index():
    if not has_runtime_context():
        return
    def start_services():
        try:
            start_metadata_watchdog()
        except Exception as exc:
            log_system("WARNING", "Metadata watchdog startup failed", error=str(exc))
        try:
            start_metadata_repair_worker(full=False)
        except Exception as exc:
            log_system("WARNING", "Metadata index repair startup failed", error=str(exc))
    await asyncio.to_thread(start_services)


async def startup_search_index():
    if not has_runtime_context():
        return
    def hydrate_search_index():
        conn = init_database()
        try:
            search_manager.hydrate(conn)
        finally:
            conn.close()
    await asyncio.to_thread(hydrate_search_index)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await startup_env_workspace()
    await startup_auth_scan()
    yield


app = FastAPI(title="LMZ API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(ALLOWED_ORIGINS),
    allow_origin_regex=EXTENSION_ORIGIN_REGEX,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def local_api_guard(request: Request, call_next):
    configure_terminal_logging()
    if not has_runtime_context() and os.environ.get("LMZ_CONFIG_PATH"):
        await asyncio.to_thread(_load_env_workspace_if_requested)
    if request.method in MUTATING_METHODS:
        try:
            _validate_origin(request.headers.get("origin"))
            _require_api_key(request)
        except Exception as exc:
            status_code = getattr(exc, "status_code", 500)
            detail = getattr(exc, "detail", str(exc))
            return JSONResponse(status_code=status_code, content={"detail": detail})
    if request.method != "OPTIONS" and not has_runtime_context() and not _is_launcher_safe_path(request.url.path):
        return JSONResponse(status_code=503, content={"detail": "Workspace not loaded"})
    try:
        return await call_next(request)
    except RuntimeNotLoadedError:
        return JSONResponse(status_code=503, content={"detail": "Workspace not loaded"})


@app.get("/vault/{asset_path:path}")
async def serve_vault_asset(asset_path: str):
    return await asyncio.to_thread(_file_response_under, _assets_dir(), asset_path)


@app.get("/review-assets/{asset_path:path}")
async def serve_review_asset(asset_path: str):
    return await asyncio.to_thread(_file_response_under, _review_dir(), asset_path)


app.include_router(runtime.router)
app.include_router(library.router)
app.include_router(logs.router)
app.include_router(ingestion.router)
app.include_router(review.router)
app.include_router(capture.router)


@app.get("/")
async def root():
    return {"status": "LMZ API Running"}

