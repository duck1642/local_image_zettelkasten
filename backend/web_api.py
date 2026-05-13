import os
import sys
import json
import base64
import mimetypes
import asyncio
import time
import traceback
import secrets
import threading
import copy
import shutil
from datetime import datetime
from collections import Counter
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from db.sqlite_operator import init_database, normalize_source_url
from utils import (
    get_config, ASSETS_DIR, REVIEW_DIR, LOCAL_INGEST_DIR, note_path_for,
    asset_path_for, calculate_file_hash, asset_url_for, wd_tag_cache_path_for
)
from processor import process_file
from logger import log_auth, log_ingest_audit, log_ingest_local, log_review, log_svelte, log_system, RAW_LOGS_DIR, STRUCTURED_LOGS_DIR
from md_generator import MANUAL_FRONTMATTER_FIELDS, load_note_frontmatter, load_note_topics, load_note_wd_tags, generate_markdown
from metadata_index import (
    indexed_item_metadata,
    metadata_facets,
    metadata_index_ready,
    metadata_index_status,
    safe_reindex_item_metadata,
    start_metadata_repair_worker,
    start_metadata_watchdog,
)
from tagging import load_tag_cache, tag_media
from thumbnails import ThumbnailBusyError, get_or_generate_thumbnail
from utils import SECRETS_DIR, WD_TAGS_DIR, atomic_write_text, get_cookie_auth_status
from ingest_control import ONLINE_STOP_AFTER_CURRENT, LOCAL_STOP_AFTER_CURRENT

class TerminalLogger:
    def __init__(self, filename, original_stream):
        self.terminal = original_stream
        self.log_path = RAW_LOGS_DIR / filename
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._handle = open(self.log_path, "a", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        with self._lock:
            self._handle.write(message)
            self._handle.flush()

    def flush(self):
        self.terminal.flush()
        with self._lock:
            self._handle.flush()

    def isatty(self):
        return hasattr(self.terminal, 'isatty') and self.terminal.isatty()

    def __getattr__(self, attr):
        return getattr(self.terminal, attr)

_terminal_logging_configured = False

def configure_terminal_logging():
    global _terminal_logging_configured
    if _terminal_logging_configured:
        return
    if not isinstance(sys.stdout, TerminalLogger):
        sys.stdout = TerminalLogger("terminal.log", sys.stdout)
    if not isinstance(sys.stderr, TerminalLogger):
        sys.stderr = TerminalLogger("terminal.log", sys.stderr)
    _terminal_logging_configured = True

configure_terminal_logging()

app = FastAPI(title="LMZ API")

ALLOWED_ORIGINS = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
}

MUTATING_METHODS = {"POST", "PATCH", "DELETE"}
LOG_FILES = {
    "system.jsonl": STRUCTURED_LOGS_DIR / "system.jsonl",
    "svelte.jsonl": STRUCTURED_LOGS_DIR / "svelte.jsonl",
    "ingest_local.jsonl": STRUCTURED_LOGS_DIR / "ingest_local.jsonl",
    "ingest_online.jsonl": STRUCTURED_LOGS_DIR / "ingest_online.jsonl",
    "review.jsonl": STRUCTURED_LOGS_DIR / "review.jsonl",
    "auth.jsonl": STRUCTURED_LOGS_DIR / "auth.jsonl",
    "ingestion_audit.jsonl": STRUCTURED_LOGS_DIR / "ingestion_audit.jsonl",
    "terminal.log": RAW_LOGS_DIR / "terminal.log",
}

REVIEW_RESOLVED_STATES = {
    "resolved_variant",
    "resolved_delete",
    "resolved_replace",
}
REVIEW_PENDING_STATES = {"pending", "deferred"}
REVIEW_CLEANUP_STATES = {"pending_cleanup", "cleanup_failed"}
REVIEW_VISIBLE_STATES = REVIEW_PENDING_STATES | REVIEW_CLEANUP_STATES
LOCAL_INGEST_LOCK = threading.Lock()
LOCAL_RESULTS_LIMIT = 500
LOCAL_INGEST_STATE = {
    "running": False,
    "phase": "idle",
    "run_id": None,
    "scanned": 0,
    "staged": 0,
    "queued": 0,
    "processed": 0,
    "summary": {"ingested": 0, "review": 0, "failed": 0, "duplicate": 0},
    "results": [],
    "failed_paths": [],
    "last_defaults": {},
    "last_skip_similarity": False,
    "started_at": None,
    "finished_at": None,
    "stop_requested": False,
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(ALLOWED_ORIGINS),
    allow_methods=["*"],
    allow_headers=["*"],
)

def _scan_auth_status_sync(reason: str = "manual") -> dict:
    config = get_config()
    ext_tools = config.get("external_tools", {})
    cookie_status = get_cookie_auth_status()
    pixiv_token = "available" if ext_tools.get("pixiv_token") else "missing"
    statuses = {
        "cookies": cookie_status.get("cookies"),
        "cookies_path": cookie_status.get("path", ""),
        "platforms": {
            "X": {"cookies": cookie_status.get("x", "missing"), "token": "not_required"},
            "Instagram": {"cookies": cookie_status.get("instagram", "missing"), "token": "not_required"},
            "Pinterest": {"cookies": cookie_status.get("pinterest", "missing"), "token": "not_required"},
            "YouTube": {"cookies": cookie_status.get("youtube", "missing"), "token": "not_required"},
            "Pixiv": {"cookies": "not_required", "token": pixiv_token},
        },
    }

    log_auth(
        "INFO",
        "Auth scan summary",
        reason=reason,
        cookies=statuses["cookies"],
        cookies_path=statuses["cookies_path"],
    )
    for platform, status in statuses["platforms"].items():
        log_auth(
            "INFO",
            "Auth platform status",
            reason=reason,
            platform=platform,
            cookies=status["cookies"],
            token=status["token"],
        )
    return statuses


@app.on_event("startup")
async def startup_auth_scan():
    await asyncio.to_thread(_scan_auth_status_sync, "startup")

@app.on_event("startup")
async def startup_metadata_index():
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

def _api_key_path() -> Path:
    return SECRETS_DIR / ".api_key"

def _api_key() -> str:
    path = _api_key_path()
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = secrets.token_urlsafe(32)
    atomic_write_text(path, value)
    return value

def _validate_origin(origin: str | None):
    if origin and origin not in ALLOWED_ORIGINS:
        raise HTTPException(status_code=403, detail="Origin not allowed")

def _require_api_key(request: Request):
    provided = request.headers.get("X-LMZ-API-KEY", "")
    expected = _api_key()
    if not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=403, detail="Invalid API key")

def _log_file_for(filename: str) -> Path:
    if filename not in LOG_FILES:
        raise HTTPException(status_code=400, detail="Invalid log file")
    return LOG_FILES[filename]

def _queue_name(queue_name: str, allow_failed: bool = True) -> str:
    allowed = {"normal", "force", "failed"} if allow_failed else {"normal", "force"}
    if queue_name not in allowed:
        raise HTTPException(status_code=400, detail="Invalid queue")
    return queue_name

def _review_path(filename: str) -> Path:
    if Path(filename).name != filename:
        raise HTTPException(status_code=400, detail="Invalid review filename")
    path = (REVIEW_DIR / filename).resolve()
    review_root = REVIEW_DIR.resolve()
    if path.parent != review_root:
        raise HTTPException(status_code=400, detail="Invalid review filename")
    return path

def _review_sidecar_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".json")

def _read_review_sidecar(path: Path) -> dict:
    sidecar_path = _review_sidecar_path(path)
    if not sidecar_path.exists():
        return {}
    try:
        data = json.loads(sidecar_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def _write_review_sidecar(path: Path, sidecar: dict):
    sidecar_path = _review_sidecar_path(path)
    atomic_write_text(sidecar_path, json.dumps(sidecar, indent=2, ensure_ascii=False))

def _stat_signature(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return int(stat.st_size), int(stat.st_mtime_ns)

def _ensure_review_hash(path: Path, sidecar: dict) -> dict:
    size, mtime_ns = _stat_signature(path)
    cached_hash = str(sidecar.get("file_hash") or "").strip()
    cached_size = int(sidecar.get("file_size") or -1)
    cached_mtime = int(sidecar.get("file_mtime") or -1)
    if not cached_hash or cached_size != size or cached_mtime != mtime_ns:
        sidecar["file_hash"] = calculate_file_hash(path)
        sidecar["file_size"] = size
        sidecar["file_mtime"] = mtime_ns
    return sidecar

def _review_display_name(path: Path, sidecar: dict) -> str:
    original_name = str(sidecar.get("original_name") or "").strip()
    if original_name:
        return Path(original_name).name
    metadata = sidecar.get("metadata") if isinstance(sidecar, dict) else {}
    if isinstance(metadata, dict):
        for key in ("original_name", "original_path", "source_path"):
            value = str(metadata.get(key) or "").strip()
            if value:
                return Path(value).name
    return path.name

def _ensure_review_sidecar_defaults(path: Path, sidecar: dict) -> tuple[dict, bool]:
    changed = False
    if not isinstance(sidecar, dict):
        sidecar = {}
        changed = True
    if not sidecar.get("storage_name"):
        sidecar["storage_name"] = path.name
        changed = True
    if not sidecar.get("original_name"):
        sidecar["original_name"] = _review_display_name(path, sidecar)
        changed = True
    if not sidecar.get("review_id"):
        sidecar["review_id"] = f"review_{path.stem}"
        changed = True
    if not sidecar.get("state"):
        sidecar["state"] = "pending"
        changed = True
    if not sidecar.get("source_path"):
        metadata = sidecar.get("metadata") if isinstance(sidecar.get("metadata"), dict) else {}
        source_path = str(metadata.get("original_path") or metadata.get("source_path") or "").strip()
        if source_path:
            sidecar["source_path"] = source_path
            changed = True
    if not sidecar.get("staged_from"):
        metadata = sidecar.get("metadata") if isinstance(sidecar.get("metadata"), dict) else {}
        staged_from = str(metadata.get("staged_from") or "").strip()
        if staged_from:
            sidecar["staged_from"] = staged_from
            changed = True
    return sidecar, changed

def _normalize_review_state(state: str | None) -> str:
    clean = str(state or "").strip()
    if clean == "cleanup_failed":
        return "pending_cleanup"
    if clean in REVIEW_RESOLVED_STATES or clean in REVIEW_PENDING_STATES or clean == "pending_cleanup":
        return clean
    return "pending"

def _review_section_for_state(state: str | None) -> str:
    return "cleanup" if _normalize_review_state(state) == "pending_cleanup" else "pending"

def _is_cleanup_review_state(state: str | None) -> bool:
    return _normalize_review_state(state) == "pending_cleanup"

def _set_review_state(
    sidecar: dict,
    state: str,
    cleanup_error: str | None = None,
    action: str | None = None,
    target_hash: str | None = None,
) -> dict:
    state = _normalize_review_state(state)
    sidecar["state"] = state
    if state in REVIEW_RESOLVED_STATES:
        sidecar["resolved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if action:
        sidecar["last_action"] = action
    if target_hash:
        sidecar["target_hash"] = target_hash
    if cleanup_error:
        sidecar["last_cleanup_error"] = cleanup_error
    elif "last_cleanup_error" in sidecar:
        sidecar.pop("last_cleanup_error", None)
    return sidecar

def _guess_review_mime_type(filename: str) -> str:
    guessed, _ = mimetypes.guess_type(filename)
    if guessed:
        return guessed
    ext = Path(filename).suffix.lower()
    fallback_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".jfif": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".ogv": "video/ogg",
    }
    return fallback_map.get(ext, "application/octet-stream")

def _review_failure_status(message: str) -> int:
    text = (message or "").strip().lower()
    if text.startswith("duplicate ignored"):
        return 409
    if text.startswith("invalid"):
        return 400
    if text.startswith("system error"):
        return 500
    return 400

def _review_cleanup_path(path: Path, retries: int = 5, delay_seconds: float = 0.2) -> tuple[bool, str]:
    if not path.exists():
        return True, ""
    last_error = ""
    for _ in range(retries):
        try:
            path.unlink()
            return True, ""
        except OSError as exc:
            last_error = str(exc)
            time.sleep(delay_seconds)
    return False, last_error

def _review_db_has_hashes(hashes: list[str]) -> set[str]:
    clean = sorted({str(h or "").strip() for h in hashes if str(h or "").strip()})
    if not clean:
        return set()
    conn = init_database()
    try:
        placeholders = ",".join("?" for _ in clean)
        cursor = conn.cursor()
        cursor.execute(f"SELECT hash FROM items WHERE hash IN ({placeholders})", clean)
        return {row[0] for row in cursor.fetchall() if row and row[0]}
    finally:
        conn.close()

def _manual_frontmatter_for_hash(item_hash: str) -> dict:
    conn = init_database()
    try:
        row = conn.execute("SELECT storage_id FROM items WHERE hash = ?", (item_hash,)).fetchone()
        if not row or not row[0]:
            return {}
        frontmatter = load_note_frontmatter(item_hash, row[0])
    finally:
        conn.close()
    return {
        field: frontmatter[field]
        for field in MANUAL_FRONTMATTER_FIELDS
        if field in frontmatter
    }

def _apply_manual_frontmatter_to_item(item_hash: str, manual_fields: dict):
    if not manual_fields:
        return
    conn = init_database()
    try:
        md_content = generate_markdown(conn, item_hash, manual_overrides=manual_fields)
        if not md_content:
            raise RuntimeError("replacement note generation returned empty content")
        row = conn.execute("SELECT storage_id FROM items WHERE hash = ?", (item_hash,)).fetchone()
        if not row or not row[0]:
            raise RuntimeError(f"item {item_hash} is missing storage_id")
        note_path = note_path_for(item_hash, row[0])
        note_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(note_path, md_content)
        safe_reindex_item_metadata(conn, item_hash, "review_replace_preserve")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def _item_file_paths(item_hash: str, extension: str, mime_type: str, storage_id: str | None, conn=None) -> list[Path]:
    if not storage_id:
        raise RuntimeError(f"item {item_hash} is missing storage_id")
    return [
        asset_path_for(item_hash, extension, mime_type, storage_id=storage_id),
        note_path_for(item_hash, storage_id=storage_id),
        wd_tag_cache_path_for(item_hash, storage_id=storage_id),
    ]

def _tail_lines(path: Path, count: int = 150) -> list[str]:
    if not path.exists():
        return []
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        end = handle.tell()
        block_size = 8192
        data = b""
        position = end
        while position > 0 and data.count(b"\n") <= count:
            read_size = min(block_size, position)
            position -= read_size
            handle.seek(position)
            data = handle.read(read_size) + data
        return data.decode("utf-8", errors="replace").splitlines()[-count:]

@app.middleware("http")
async def local_api_guard(request: Request, call_next):
    configure_terminal_logging()
    if request.method in MUTATING_METHODS:
        try:
            _validate_origin(request.headers.get("origin"))
            _require_api_key(request)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return await call_next(request)

@app.get("/api/session-key")
async def get_session_key(request: Request):
    _validate_origin(request.headers.get("origin"))
    return {"key": _api_key()}

if ASSETS_DIR.exists():
    app.mount("/vault", StaticFiles(directory=str(ASSETS_DIR)), name="vault")
REVIEW_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/review-assets", StaticFiles(directory=str(REVIEW_DIR)), name="review-assets")

@app.get("/api/stats")
async def get_stats():
    return await asyncio.to_thread(_get_stats_sync)

@app.get("/api/metadata-index/status")
async def get_metadata_index_status():
    return await asyncio.to_thread(_get_metadata_index_status_sync)

def _get_metadata_index_status_sync():
    conn = init_database()
    try:
        return metadata_index_status(conn)
    finally:
        conn.close()

@app.post("/api/metadata-index/rebuild")
async def rebuild_metadata_index():
    return await asyncio.to_thread(start_metadata_repair_worker, True)

def _get_stats_sync():
    conn = init_database()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM items")
        count = cursor.fetchone()[0]
        return {"total_items": count}
    finally:
        conn.close()

@app.get("/api/system/memory")
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

@app.get("/api/search/suggestions")
async def get_search_suggestions(kind: str, q: str = "", limit: int = 20):
    return await asyncio.to_thread(_get_search_suggestions_sync, kind, q, limit)

@app.get("/api/facets")
async def get_facets(kind: str, q: str = "", limit: int = 100):
    return await asyncio.to_thread(_get_facets_sync, kind, q, limit)

def _get_search_suggestions_sync(kind: str, q: str = "", limit: int = 20):
    kind = (kind or "").strip().lower()
    needle = (q or "").strip().lower()
    limit = max(1, min(int(limit or 20), 50))

    if kind == "command":
        commands = [
            "/masonry",
            "/grid",
            "/zoom-in",
            "/zoom-out",
            ">toggle-inspector",
            "/ram-track",
            "/scan-auth",
            "/cleanup-review",
            "/sort-newest",
            "/sort-oldest",
            "/sort-artist",
            "/media-all",
            "/media-image",
            "/media-video",
        ]
        items = [
            {"value": cmd, "count": 0}
            for cmd in commands
            if cmd.lower().startswith(f">{needle}") or cmd.lower().lstrip(">").startswith(needle)
        ][:limit]
        return {"suggestions": [item["value"] for item in items], "items": items}

    if kind not in {"artist", "platform", "topic", "wd_tag"}:
        raise HTTPException(status_code=400, detail="Invalid suggestion kind")

    result = _get_facets_sync(kind, q, limit)
    return {"suggestions": [item["value"] for item in result["items"]], "items": result["items"]}

def _sort_facets(items, needle, limit):
    needle = needle.lower()
    filtered = [
        item for item in items
        if not needle or needle in item["value"].lower()
    ]
    filtered.sort(
        key=lambda item: (
            0 if needle and item["value"].lower().startswith(needle) else 1,
            -item["count"],
            item["value"].lower()
        )
    )
    return filtered[:limit]

def _count_python_facets(rows, value_loader, needle, limit):
    counts = Counter()
    display_values = {}
    for row in rows:
        seen = set()
        for value in value_loader(row[0]):
            text = str(value or "").strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            counts[key] += 1
            display_values.setdefault(key, text)
    items = [{"value": display_values[key], "count": count} for key, count in counts.items()]
    return _sort_facets(items, needle, limit)

def _get_facets_sync(kind: str, q: str = "", limit: int = 100):
    kind = (kind or "").strip().lower()
    needle = (q or "").strip().lower()
    limit = max(1, min(int(limit or 100), 500))

    if kind not in {"artist", "platform", "topic", "wd_tag"}:
        raise HTTPException(status_code=400, detail="Invalid facet kind")

    conn = init_database()
    cursor = conn.cursor()
    try:
        if kind in {"artist", "platform"}:
            column = "source_artist" if kind == "artist" else "platform"
            conditions = [f"{column} IS NOT NULL", f"TRIM({column}) != ''"]
            params = []
            if needle:
                conditions.append(f"{column} LIKE ?")
                params.append(f"%{needle}%")
            where_clause = " AND ".join(conditions)
            cursor.execute(
                f"SELECT {column}, COUNT(*) FROM items WHERE {where_clause} GROUP BY {column}",
                tuple(params)
            )
            items = [{"value": row[0], "count": row[1]} for row in cursor.fetchall() if row[0]]
            return {"kind": kind, "items": _sort_facets(items, needle, limit)}

        if metadata_index_ready(conn):
            return {"kind": kind, "items": metadata_facets(conn, kind, needle.casefold(), limit)}

        start_metadata_repair_worker(full=False)
        log_system("WARNING", "Metadata index not ready; skipping facet scan and starting repair", kind=kind)
        return {"kind": kind, "items": []}
    finally:
        conn.close()

@app.get("/api/thumbnails/{item_hash}")
async def get_thumbnail(item_hash: str):
    return await asyncio.to_thread(_get_thumbnail_sync, item_hash)

def _get_thumbnail_sync(item_hash: str):
    conn = init_database()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT file_extension, mime_type, storage_id FROM items WHERE hash = ?", (item_hash,))
        row = cursor.fetchone()
        if not row: raise HTTPException(status_code=404)
        try:
            thumb_path = get_or_generate_thumbnail(item_hash, row[0], row[1], storage_id=row[2])
        except ThumbnailBusyError:
            raise HTTPException(status_code=503, detail="Thumbnail generation busy")
        if not thumb_path: raise HTTPException(status_code=500, detail="Thumbnail generation failed")
        return FileResponse(
            thumb_path, media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=31536000, immutable"}
        )
    finally:
        conn.close()

@app.get("/api/items")
async def get_items(
    field: str = None, value: str = None,
    sort: str = 'newest', media_type: str = 'all',
    artist: list[str] = Query(default=[]), platform: list[str] = Query(default=[]),
    filename: list[str] = Query(default=[]), topic: list[str] = Query(default=[]),
    wd_tag: list[str] = Query(default=[]), text: list[str] = Query(default=[]),
    cursor: str = None, limit: int = 50
):
    return await asyncio.to_thread(
        _get_items_sync,
        field, value, sort, media_type, artist, platform, filename, topic, wd_tag, text, cursor, limit
    )

def _encode_cursor(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "v2:" + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

def _decode_cursor(cursor: str | None) -> dict:
    if not cursor:
        return {}
    if cursor.startswith("v2:"):
        try:
            raw = cursor[3:]
            raw += "=" * (-len(raw) % 4)
            payload = json.loads(base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}
    try:
        cursor_date, cursor_hash = cursor.rsplit("_", 1)
    except ValueError:
        cursor_date, cursor_hash = cursor, ""
    return {"date": cursor_date, "hash": cursor_hash}

def _cursor_for_item(item: dict, sort: str) -> str:
    payload = {
        "sort": sort,
        "date": str(item.get("date_added") or ""),
        "hash": str(item.get("hash") or ""),
    }
    if sort == "artist":
        payload["artist"] = str(item.get("artist") or "")
    return _encode_cursor(payload)

def _item_after_cursor(item: dict, cursor: str, sort: str) -> bool:
    if not cursor:
        return True
    payload = _decode_cursor(cursor)
    cursor_date = str(payload.get("date") or "")
    cursor_hash = str(payload.get("hash") or "")
    item_key = (str(item.get("date_added") or ""), str(item.get("hash") or ""))
    cursor_key = (cursor_date, cursor_hash)
    if sort == "artist":
        item_key = (
            str(item.get("artist") or "").casefold(),
            str(item.get("date_added") or ""),
            str(item.get("hash") or ""),
        )
        cursor_key = (
            str(payload.get("artist") or "").casefold(),
            cursor_date,
            cursor_hash,
        )
        return item_key > cursor_key
    if sort == "oldest":
        return item_key > cursor_key
    return item_key < cursor_key

def _clean_filter_values(values):
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    cleaned = []
    for value in values:
        text = str(value or "").strip()
        if text:
            cleaned.append(text)
    return cleaned

def _append_or_like(conditions, params, column, values):
    values = _clean_filter_values(values)
    if not values:
        return
    conditions.append("(" + " OR ".join([f"{column} LIKE ?"] * len(values)) + ")")
    params.extend([f"%{value}%" for value in values])

def _append_text_terms(conditions, params, terms):
    for term in _clean_filter_values(terms):
        conditions.append("(original_filename LIKE ? OR hash LIKE ? OR source_url LIKE ? OR source_artist LIKE ? OR platform LIKE ?)")
        params.extend([f"%{term}%"] * 5)

def _get_items_sync(field, value, sort, media_type, artist, platform, filename, topic, wd_tag, text, cursor, limit):
    limit = max(1, min(limit, 100))
    topic_filters = _clean_filter_values(topic)
    wd_tag_filters = _clean_filter_values(wd_tag)
    conn = init_database()
    cursor_obj = conn.cursor()
    try:
        base_query = "SELECT hash, file_extension, mime_type, original_filename, source_url, date_added, platform, source_artist, width, height, storage_id FROM items"
        conditions = []
        params = []
        use_metadata_index = bool(topic_filters or wd_tag_filters) and metadata_index_ready(conn)

        if field and value:
            allowed = {"source_artist", "platform", "original_filename"}
            if field in allowed:
                conditions.append(f"{field} LIKE ?")
                params.append(f"%{value}%")

        _append_or_like(conditions, params, "source_artist", artist)
        _append_or_like(conditions, params, "platform", platform)
        _append_or_like(conditions, params, "original_filename", filename)
        _append_text_terms(conditions, params, text)

        if media_type == 'image':
            conditions.append("mime_type LIKE 'image/%'")
        elif media_type == 'video':
            conditions.append("mime_type LIKE 'video/%'")

        if use_metadata_index:
            for topic_value in topic_filters:
                conditions.append("EXISTS (SELECT 1 FROM item_topics mt WHERE mt.item_hash = items.hash AND mt.topic_norm LIKE ?)")
                params.append(f"%{topic_value.casefold()}%")
            for wd_value in wd_tag_filters:
                conditions.append("EXISTS (SELECT 1 FROM item_wd_tags mw WHERE mw.item_hash = items.hash AND mw.tag_norm LIKE ?)")
                params.append(f"%{wd_value.casefold()}%")

        has_frontmatter_filter = bool(topic_filters or wd_tag_filters)
        if has_frontmatter_filter and not use_metadata_index:
            start_metadata_repair_worker(full=False)
            log_system("WARNING", "Metadata index not ready; skipping topic/WD filter scan and starting repair")
            return {"items": [], "has_more": False, "next_cursor": None}

        if cursor:
            cursor_payload = _decode_cursor(cursor)
            cursor_date = str(cursor_payload.get("date") or "")
            cursor_hash = str(cursor_payload.get("hash") or "")
            if sort == 'artist':
                cursor_artist = str(cursor_payload.get("artist") or "")
                conditions.append(
                    "("
                    "COALESCE(source_artist, '') COLLATE NOCASE > ? COLLATE NOCASE "
                    "OR (COALESCE(source_artist, '') COLLATE NOCASE = ? COLLATE NOCASE "
                    "AND (date_added < ? OR (date_added = ? AND hash < ?)))"
                    ")"
                )
                params.extend([cursor_artist, cursor_artist, cursor_date, cursor_date, cursor_hash])
            elif sort == 'oldest':
                conditions.append("(date_added > ? OR (date_added = ? AND hash > ?))")
                params.extend([cursor_date, cursor_date, cursor_hash])
            else:
                conditions.append("(date_added < ? OR (date_added = ? AND hash < ?))")
                params.extend([cursor_date, cursor_date, cursor_hash])

        where_clause = ""
        if conditions:
            where_clause = " WHERE " + " AND ".join(conditions)

        order_clause = " ORDER BY date_added DESC, hash DESC"
        if sort == 'oldest': order_clause = " ORDER BY date_added ASC, hash ASC"
        elif sort == 'artist': order_clause = " ORDER BY COALESCE(source_artist, '') COLLATE NOCASE ASC, date_added DESC, hash DESC"

        cursor_obj.execute(f"{base_query}{where_clause}{order_clause} LIMIT {limit + 1}", tuple(params))
        rows = cursor_obj.fetchall()

        items = []

        for row in rows:
            h, ext = row[0], (row[1] or "")

            items.append({
                "hash": h, "extension": ext, "mime_type": row[2],
                "original_filename": row[3], "source_url": row[4],
                "date_added": row[5], "platform": row[6], "artist": row[7],
                "url": asset_url_for(h, ext, row[2], storage_id=row[10]),
                "thumbnail_url": f"/api/thumbnails/{h}",
                "width": row[8], "height": row[9]
            })

        has_more = len(items) > limit
        if has_more:
            items = items[:limit]

        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = _cursor_for_item(last, sort)

        return {"items": items, "next_cursor": next_cursor, "has_more": has_more}
    finally:
        conn.close()

def _get_item_details(h, row, conn=None):
    ext = row[1] or ""
    storage_id = row[10] if len(row) > 10 else None
    try:
        if conn is not None:
            metadata = indexed_item_metadata(conn, h)
            topics = metadata.get("topics", [])
            wd_data = metadata.get("wd_data", {"status": "missing"})
        else:
            raise RuntimeError("metadata index connection unavailable")
    except Exception as exc:
        log_system("WARNING", "Metadata index detail fallback", hash=h, error=str(exc))
        if not storage_id:
            raise RuntimeError(f"item {h} is missing storage_id")
        topics = load_note_topics(h, storage_id)
        wd_data = load_note_wd_tags(h, storage_id)
        if wd_data.get("status") != "ok":
            cache_data = load_tag_cache(h, storage_id)
            if cache_data.get("status") == "ok":
                wd_data = {
                    "status": "ok",
                    "source": "cache",
                    "rating": cache_data.get("rating") or {},
                    "character_tags": cache_data.get("character_tags") or [],
                    "tags": cache_data.get("tags") or []
                }
    
    def get_names(tag_list):
        names = []
        for t in tag_list:
            if isinstance(t, str): names.append(t)
            elif isinstance(t, dict): names.append(t.get("display_name") or t.get("name") or "")
        return [n for n in names if n]

    formatted_wd = {
        "rating": wd_data.get("rating", {}).get("label") or wd_data.get("rating", {}).get("name") or "None",
        "characters": get_names(wd_data.get("character_tags", [])),
        "general": get_names(wd_data.get("tags", []))
    }
    
    return {
        "hash": h, "extension": ext, "mime_type": row[2] or "",
        "original_filename": row[3], "source_url": row[4],
        "date_added": row[5], "platform": row[6], "artist": row[7],
        "url": asset_url_for(h, ext, row[2] or "", storage_id=storage_id),
        "thumbnail_url": f"/api/thumbnails/{h}",
        "width": row[8], "height": row[9],
        "topics": topics,
        "wd_tags": formatted_wd
    }

@app.get("/api/items/{item_hash}")
async def get_item(item_hash: str):
    return await asyncio.to_thread(_get_item_sync, item_hash)

def _get_item_sync(item_hash: str):
    conn = init_database()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT hash, file_extension, mime_type, original_filename, source_url, date_added, platform, source_artist, width, height, storage_id FROM items WHERE hash = ?", (item_hash,))
        row = cursor.fetchone()
        if not row: raise HTTPException(status_code=404)
        return _get_item_details(item_hash, row, conn)
    finally:
        conn.close()

@app.get("/api/items/{item_hash}/path")
async def get_item_path(item_hash: str):
    return await asyncio.to_thread(_get_item_path_sync, item_hash)

def _get_item_path_sync(item_hash: str):
    conn = init_database()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT file_extension, mime_type, storage_id FROM items WHERE hash = ?", (item_hash,))
        row = cursor.fetchone()
        if not row: raise HTTPException(status_code=404)
        path = asset_path_for(item_hash, row[0] or "", row[1] or "", storage_id=row[2])
        return {"absolute_path": str(path.resolve())}
    finally:
        conn.close()

@app.get("/api/items/{item_hash}/note_path")
async def get_item_note_path(item_hash: str):
    return await asyncio.to_thread(_get_item_note_path_sync, item_hash)

def _get_item_note_path_sync(item_hash: str):
    conn = init_database()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT storage_id FROM items WHERE hash = ?", (item_hash,))
        row = cursor.fetchone()
        if not row: raise HTTPException(status_code=404)
        path = note_path_for(item_hash, row[0])
        return {"absolute_path": str(path.resolve())}
    finally:
        conn.close()

@app.post("/api/items/{item_hash}/open_folder")
async def open_item_folder(item_hash: str):
    return await asyncio.to_thread(_open_item_folder_sync, item_hash)

def _open_item_folder_sync(item_hash: str):
    conn = init_database()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT file_extension, mime_type, storage_id FROM items WHERE hash = ?", (item_hash,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404)
        path = asset_path_for(item_hash, row[0] or "", row[1] or "", storage_id=row[2])
        if not path.exists():
            raise HTTPException(status_code=404, detail="Asset missing")
        if sys.platform == "win32":
            import subprocess
            subprocess.Popen(["explorer", "/select,", str(path.resolve())])
        else:
            _open_path_external(path.parent)
        return {"status": "success"}
    finally:
        conn.close()

@app.post("/api/items/{item_hash}/open_note")
async def open_item_note(item_hash: str):
    return await asyncio.to_thread(_open_item_note_sync, item_hash)

def _open_item_note_sync(item_hash: str):
    conn = init_database()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT storage_id FROM items WHERE hash = ?", (item_hash,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404)
        path = note_path_for(item_hash, row[0])
        if not path.exists():
            raise HTTPException(status_code=404, detail="Note missing")
        _open_path_external(path)
        return {"status": "success"}
    finally:
        conn.close()

class ItemUpdate(BaseModel):
    artist: str = None
    source_url: str = None
    platform: str = None
    topics: list[str] = None

class BulkDeleteRequest(BaseModel):
    hashes: list[str]

@app.patch("/api/items/{item_hash}")
async def update_item(item_hash: str, update: ItemUpdate):
    return await asyncio.to_thread(_update_item_sync, item_hash, update)

def _update_item_sync(item_hash: str, update: ItemUpdate):
    conn = init_database()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM items WHERE hash = ?", (item_hash,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404)
        manual_overrides = {}
        if update.artist is not None:
            cursor.execute("UPDATE items SET source_artist = ? WHERE hash = ?", (update.artist, item_hash))
            manual_overrides["artist"] = update.artist
        if update.source_url is not None:
            cursor.execute("UPDATE items SET source_url = ?, source_url_norm = ? WHERE hash = ?", (update.source_url, normalize_source_url(update.source_url), item_hash))
        if update.platform is not None:
            cursor.execute("UPDATE items SET platform = ? WHERE hash = ?", (update.platform, item_hash))
        if update.topics is not None:
            manual_overrides["topics"] = update.topics
        
        md_content = generate_markdown(conn, item_hash, topics_override=update.topics, manual_overrides=manual_overrides)
        if md_content:
            row = cursor.execute("SELECT storage_id FROM items WHERE hash = ?", (item_hash,)).fetchone()
            if not row or not row[0]:
                raise RuntimeError(f"item {item_hash} is missing storage_id")
            note_path = note_path_for(item_hash, row[0])
            note_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(note_path, md_content)
            safe_reindex_item_metadata(conn, item_hash, "item_patch")
            conn.commit()
            
        return {"status": "success"}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

@app.delete("/api/items/{item_hash}")
async def delete_item(item_hash: str):
    return await asyncio.to_thread(_delete_item_sync, item_hash)

@app.post("/api/items/bulk_delete")
async def bulk_delete_items(request: BulkDeleteRequest):
    return await asyncio.to_thread(_bulk_delete_items_sync, request.hashes)

def _delete_item_row(cursor, conn, item_hash: str):
    cursor.execute("SELECT file_extension, mime_type, storage_id FROM items WHERE hash = ?", (item_hash,))
    row = cursor.fetchone()
    if not row:
        return {"hash": item_hash, "status": "missing", "cleanup_errors": []}

    cleanup_paths = _item_file_paths(item_hash, row[0] or "", row[1] or "", row[2], conn)

    cursor.execute("DELETE FROM items WHERE hash = ?", (item_hash,))
    conn.commit()

    cleanup_errors = []
    for path in cleanup_paths:
        try:
            if path.exists():
                path.unlink()
        except OSError as exc:
            error = {"hash": item_hash, "path": str(path), "error": str(exc)}
            cleanup_errors.append(error)
            log_system("WARNING", "Deleted DB row but file cleanup failed", hash=item_hash, path=str(path), error=str(exc))

    log_system("INFO", f"Deleted item {item_hash}")
    return {"hash": item_hash, "status": "deleted", "cleanup_errors": cleanup_errors}

def _delete_item_after_replacement(item_hash: str):
    conn = init_database()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT file_extension, mime_type, storage_id FROM items WHERE hash = ?", (item_hash,))
        row = cursor.fetchone()
        if not row:
            return {"hash": item_hash, "status": "missing", "cleanup_errors": []}

        cleanup_paths = _item_file_paths(item_hash, row[0] or "", row[1] or "", row[2], conn)
        existing_paths = [path for path in cleanup_paths if path.exists()]
        trash_dir = REVIEW_DIR / ".replace-trash"
        trash_dir.mkdir(parents=True, exist_ok=True)
        moved_paths = []

        def restore_moved():
            restore_errors = []
            for temp_path, original_path in reversed(moved_paths):
                try:
                    if temp_path.exists() and not original_path.exists():
                        original_path.parent.mkdir(parents=True, exist_ok=True)
                        temp_path.replace(original_path)
                except OSError as exc:
                    restore_errors.append({"hash": item_hash, "path": str(original_path), "error": str(exc)})
            return restore_errors

        for index, path in enumerate(existing_paths):
            try:
                temp_path = trash_dir / f"{item_hash}_{index}_{path.name}"
                path.replace(temp_path)
                moved_paths.append((temp_path, path))
            except OSError as exc:
                cleanup_errors = [{"hash": item_hash, "path": str(path), "error": str(exc)}]
                cleanup_errors.extend(restore_moved())
                return {"hash": item_hash, "status": "cleanup_failed", "cleanup_errors": cleanup_errors}

        try:
            cursor.execute("DELETE FROM items WHERE hash = ?", (item_hash,))
            conn.commit()
        except Exception as exc:
            conn.rollback()
            cleanup_errors = [{"hash": item_hash, "path": "database", "error": str(exc)}]
            cleanup_errors.extend(restore_moved())
            return {"hash": item_hash, "status": "cleanup_failed", "cleanup_errors": cleanup_errors}

        for temp_path, _ in moved_paths:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError as exc:
                log_review("WARNING", "Review replace staged file cleanup failed", target_hash=item_hash, path=str(temp_path), error=str(exc))
        return {"hash": item_hash, "status": "deleted", "cleanup_errors": []}
    finally:
        conn.close()

def _delete_item_sync(item_hash: str):
    conn = init_database()
    cursor = conn.cursor()
    try:
        result = _delete_item_row(cursor, conn, item_hash)
        if result["status"] == "missing":
            raise HTTPException(status_code=404)
        return {"status": "success", "cleanup_errors": result["cleanup_errors"]}
    finally:
        conn.close()

def _bulk_delete_items_sync(hashes: list[str]):
    unique_hashes = []
    seen = set()
    for value in hashes or []:
        item_hash = str(value or "").strip()
        if item_hash and item_hash not in seen:
            unique_hashes.append(item_hash)
            seen.add(item_hash)

    conn = init_database()
    cursor = conn.cursor()
    deleted = []
    missing = []
    failed_cleanup = []
    try:
        for item_hash in unique_hashes:
            result = _delete_item_row(cursor, conn, item_hash)
            if result["status"] == "missing":
                missing.append(item_hash)
            else:
                deleted.append(item_hash)
                failed_cleanup.extend(result["cleanup_errors"])
        return {
            "status": "success",
            "requested_count": len(unique_hashes),
            "deleted_count": len(deleted),
            "missing_count": len(missing),
            "failed_cleanup_count": len(failed_cleanup),
            "deleted": deleted,
            "missing": missing,
            "failed_cleanup": failed_cleanup,
        }
    finally:
        conn.close()

@app.post("/api/items/{item_hash}/tag")
async def trigger_tagging(item_hash: str):
    def sync_tagging():
        conn = init_database()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT file_extension, mime_type, storage_id FROM items WHERE hash = ?", (item_hash,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404)
            
            asset_path = asset_path_for(item_hash, row[0] or "", row[1] or "", storage_id=row[2])
            if not asset_path.exists():
                raise HTTPException(status_code=404, detail="Asset missing")

            log_system("INFO", f"Triggering AI tagging for {item_hash}")
            tag_media(asset_path, item_hash=item_hash, config=get_config(), storage_id=row[2])
            
            md_content = generate_markdown(conn, item_hash)
            if md_content:
                note_path = note_path_for(item_hash, storage_id=row[2])
                note_path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_text(note_path, md_content)
                safe_reindex_item_metadata(conn, item_hash, "manual_tag")
                conn.commit()
            
            cursor.execute("SELECT hash, file_extension, mime_type, original_filename, source_url, date_added, platform, source_artist, width, height, storage_id FROM items WHERE hash = ?", (item_hash,))
            updated_row = cursor.fetchone()
            return _get_item_details(item_hash, updated_row, conn)
        finally:
            conn.close()

    try:
        return await asyncio.to_thread(sync_tagging)
    except HTTPException:
        raise
    except Exception as e:
        print(f"!!! TAGGING CRASH !!!\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/logs")
async def stream_logs(filename: str = Query("system.jsonl")):
    log_file = _log_file_for(filename)

    if not log_file.exists():
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.touch()
    
    async def log_generator():
        for line in _tail_lines(log_file, 150):
            yield f"data: {line}\n\n"

        try:
            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                f.seek(0, os.SEEK_END)
                while True:
                    line = f.readline()
                    if not line:
                        await asyncio.sleep(0.5)
                        continue
                    yield f"data: {line}\n\n"
        except Exception:
            pass
    return StreamingResponse(log_generator(), media_type="text/event-stream")

@app.post("/api/auth/scan")
async def scan_auth_status():
    statuses = await asyncio.to_thread(_scan_auth_status_sync, "manual")
    return {"status": "ok", "auth": statuses}

class UILogEntry(BaseModel):
    level: str
    message: str
    extra: dict = None

@app.post("/api/logs/ui")
async def post_ui_log(entry: UILogEntry):
    log_svelte(entry.level, entry.message, **(entry.extra or {}))
    return {"status": "ok"}

@app.post("/api/logs/open")
async def open_log_external(filename: str = Query(...)):
    return await asyncio.to_thread(_open_log_external_sync, filename)

def _open_path_external(path: Path):
    if os.name == 'nt':
        os.startfile(str(path))
    else:
        import subprocess
        opener = "open" if os.uname().sysname == "Darwin" else "xdg-open"
        subprocess.call([opener, str(path)])

def _open_log_external_sync(filename: str):
    log_file = _log_file_for(filename)
        
    if not log_file.exists(): raise HTTPException(status_code=404)
    try:
        _open_path_external(log_file)
        return {"status": "opened"}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/logs/clear")
async def clear_all_logs():
    return await asyncio.to_thread(_clear_all_logs_sync)

def _clear_all_logs_sync():
    try:
        for folder in [RAW_LOGS_DIR, STRUCTURED_LOGS_DIR]:
            if folder.exists():
                for f in folder.iterdir():
                    if f.is_file() and (f.suffix == '.log' or f.suffix == '.jsonl'):
                        with open(f, 'w', encoding='utf-8') as out:
                            out.write('')
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class QueueUpdate(BaseModel):
    content: str
from queue_service import read_queue, write_queue, queue_counts, INGESTION_LOCK, run_queue, clear_failed, move_failed_urls, parse_urls, queue_path

@app.get("/api/queue/{queue_name}")
async def get_queue(queue_name: str):
    return await asyncio.to_thread(_get_queue_sync, queue_name)

def _get_queue_sync(queue_name: str):
    queue_name = _queue_name(queue_name)
    return {"content": read_queue(queue_name), "count": queue_counts().get(queue_name, 0)}

@app.post("/api/queue/{queue_name}")
async def save_queue(queue_name: str, update: QueueUpdate):
    return await asyncio.to_thread(_save_queue_sync, queue_name, update)

def _save_queue_sync(queue_name: str, update: QueueUpdate):
    queue_name = _queue_name(queue_name)
    write_queue(queue_name, update.content)
    return {"status": "success", "count": queue_counts().get(queue_name, 0)}

@app.post("/api/queue/{queue_name}/parse")
async def parse_queue_content(queue_name: str, update: QueueUpdate):
    return await asyncio.to_thread(_parse_queue_content_sync, queue_name, update)

def _parse_queue_content_sync(queue_name: str, update: QueueUpdate):
    _queue_name(queue_name)
    return {"count": len(parse_urls(update.content))}

@app.post("/api/queue/actions/clear-failed")
async def api_clear_failed():
    return await asyncio.to_thread(_api_clear_failed_sync)

def _api_clear_failed_sync():
    clear_failed()
    return {"status": "success", "counts": queue_counts()}

class RetryFailedBody(BaseModel):
    target: str

@app.post("/api/queue/actions/retry-failed")
async def api_retry_failed(body: RetryFailedBody):
    return await asyncio.to_thread(_api_retry_failed_sync, body)

def _api_retry_failed_sync(body: RetryFailedBody):
    if body.target not in ["normal", "force"]: raise HTTPException(400, "Invalid target")
    moved = move_failed_urls(body.target)
    return {"status": "success", "moved": moved, "counts": queue_counts()}

@app.post("/api/queue/{queue_name}/open")
async def open_queue_external(queue_name: str):
    return await asyncio.to_thread(_open_queue_external_sync, queue_name)

def _open_queue_external_sync(queue_name: str):
    queue_name = _queue_name(queue_name)
    path = queue_path(queue_name)
    if not path.exists():
        read_queue(queue_name)
    try:
        _open_path_external(path)
        return {"status": "opened"}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ingest/{queue_name}")
async def start_ingestion(queue_name: str):
    queue_name = _queue_name(queue_name, allow_failed=False)
    if not INGESTION_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Already running")
    ONLINE_STOP_AFTER_CURRENT.clear()
    def run_in_background():
        try:
            run_queue(queue_name)
        except Exception as e:
            log_system("ERROR", "Ingestion worker crashed", error=str(e), traceback=traceback.format_exc())
        finally:
            INGESTION_LOCK.release()
    asyncio.get_running_loop().run_in_executor(None, run_in_background)
    return {"status": "success"}

@app.get("/api/ingest/runtime-status")
async def ingest_runtime_status():
    with LOCAL_INGEST_LOCK:
        local_running = bool(LOCAL_INGEST_STATE.get("running"))
        local_stop_requested = bool(LOCAL_INGEST_STATE.get("stop_requested"))
    online_running = bool(INGESTION_LOCK.locked())
    return {
        "online_running": online_running,
        "online_stop_requested": bool(ONLINE_STOP_AFTER_CURRENT.is_set()),
        "local_running": local_running,
        "local_stop_requested": local_stop_requested,
        "any_running": bool(online_running or local_running),
    }

@app.post("/api/ingest/stop-after-current")
async def ingest_stop_after_current():
    online_running = bool(INGESTION_LOCK.locked())
    with LOCAL_INGEST_LOCK:
        local_running = bool(LOCAL_INGEST_STATE.get("running"))
        if local_running:
            LOCAL_INGEST_STATE["stop_requested"] = True
            LOCAL_INGEST_STATE["phase"] = "stopping"
    if online_running:
        ONLINE_STOP_AFTER_CURRENT.set()
    if local_running:
        LOCAL_STOP_AFTER_CURRENT.set()
    if not online_running and not local_running:
        return {"status": "idle", "message": "No ingestion is running."}
    return {
        "status": "success",
        "online_stop_requested": online_running,
        "local_stop_requested": local_running,
    }

@app.get("/api/queue-stats")
async def get_queue_stats(): return await asyncio.to_thread(queue_counts)

class LocalIngestDefaults(BaseModel):
    artist: str | None = None
    platform: str | None = None
    source_url: str | None = None

class LocalIngestStartRequest(BaseModel):
    paths: list[str]
    defaults: LocalIngestDefaults | None = None
    skip_similarity: bool = False

class LocalIngestDropIntakeRequest(BaseModel):
    session_id: str | None = None
    source_tab: str | None = None
    paths: list[str]

def _iter_local_ingest_paths(paths: list[str], stop_event: threading.Event | None = None):
    allowed_exts = {ext.lstrip(".").lower() for ext in get_config().get("firewall", {}).get("allowed_extensions", [])}
    seen = set()
    for raw in paths or []:
        if stop_event and stop_event.is_set():
            break
        text = str(raw or "").strip()
        if not text:
            continue
        path = Path(text).expanduser()
        if not path.is_absolute():
            path = (LOCAL_INGEST_DIR / path).resolve()
        else:
            path = path.resolve()
        if path.is_file():
            key = str(path)
            if key not in seen:
                seen.add(key)
                yield path
            continue
        if path.is_dir():
            for child in path.rglob("*"):
                if stop_event and stop_event.is_set():
                    break
                if not child.is_file():
                    continue
                ext = child.suffix.lstrip(".").lower()
                if allowed_exts and ext not in allowed_exts:
                    continue
                key = str(child.resolve())
                if key not in seen:
                    seen.add(key)
                    yield child.resolve()

def _local_drop_intake_sync(body: LocalIngestDropIntakeRequest):
    with LOCAL_INGEST_LOCK:
        local_running = bool(LOCAL_INGEST_STATE.get("running"))
    online_running = bool(INGESTION_LOCK.locked())
    if local_running or online_running:
        raise HTTPException(status_code=409, detail="Ingestion is already running")

    raw_paths = [str(path or "").strip() for path in (body.paths or []) if str(path or "").strip()]
    allowed_exts = {ext.lstrip(".").lower() for ext in get_config().get("firewall", {}).get("allowed_extensions", [])}
    accepted: list[str] = []
    skipped: list[dict] = []
    seen: set[str] = set()

    for raw in raw_paths:
        try:
            candidate = Path(raw).expanduser()
            resolved = candidate.resolve() if candidate.is_absolute() else (LOCAL_INGEST_DIR / candidate).resolve()
        except Exception:
            skipped.append({"path": raw, "reason": "invalid_path"})
            continue

        if not resolved.exists():
            skipped.append({"path": str(resolved), "reason": "missing_path"})
            continue

        if resolved.is_dir():
            key = str(resolved)
            if key in seen:
                skipped.append({"path": key, "reason": "duplicate_path"})
                continue
            seen.add(key)
            accepted.append(key)
            continue

        if not resolved.is_file():
            skipped.append({"path": str(resolved), "reason": "unsupported_type"})
            continue

        ext = resolved.suffix.lstrip(".").lower()
        if allowed_exts and ext not in allowed_exts:
            skipped.append({"path": str(resolved), "reason": "unsupported_extension"})
            continue

        key = str(resolved)
        if key in seen:
            skipped.append({"path": key, "reason": "duplicate_path"})
            continue
        seen.add(key)
        accepted.append(key)

    reason_counts = dict(Counter(str(item.get("reason") or "unknown") for item in skipped))
    session_id = str(body.session_id or "").strip() or _local_run_id()
    source_tab = str(body.source_tab or "").strip() or "unknown"
    summary = {
        "received": len(raw_paths),
        "accepted": len(accepted),
        "skipped": len(skipped),
    }

    log_ingest_local(
        "INFO",
        "Local drop intake processed",
        session_id=session_id,
        source_tab=source_tab,
        received=summary["received"],
        accepted=summary["accepted"],
        skipped=summary["skipped"],
        skipped_reasons=reason_counts,
    )
    return {
        "session_id": session_id,
        "accepted_paths": accepted,
        "skipped": skipped,
        "summary": summary,
    }

def _snapshot_local_ingest_state() -> dict:
    with LOCAL_INGEST_LOCK:
        return {
            "running": bool(LOCAL_INGEST_STATE["running"]),
            "phase": LOCAL_INGEST_STATE.get("phase") or "idle",
            "run_id": LOCAL_INGEST_STATE.get("run_id"),
            "scanned": int(LOCAL_INGEST_STATE.get("scanned") or 0),
            "staged": int(LOCAL_INGEST_STATE.get("staged") or 0),
            "queued": int(LOCAL_INGEST_STATE["queued"]),
            "processed": int(LOCAL_INGEST_STATE["processed"]),
            "summary": dict(LOCAL_INGEST_STATE["summary"]),
            "results": list(LOCAL_INGEST_STATE["results"]),
            "failed_paths": list(LOCAL_INGEST_STATE["failed_paths"]),
            "last_defaults": dict(LOCAL_INGEST_STATE.get("last_defaults") or {}),
            "last_skip_similarity": bool(LOCAL_INGEST_STATE.get("last_skip_similarity")),
            "started_at": LOCAL_INGEST_STATE["started_at"],
            "finished_at": LOCAL_INGEST_STATE["finished_at"],
            "stop_requested": bool(LOCAL_INGEST_STATE.get("stop_requested")),
        }

def _set_local_ingest_state(**kwargs):
    with LOCAL_INGEST_LOCK:
        for key, value in kwargs.items():
            LOCAL_INGEST_STATE[key] = value

def _local_run_id() -> str:
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(4)}"

def _safe_staged_filename(index: int, source_path: Path) -> str:
    invalid = '<>:"/\\|?*'
    safe = "".join("_" if char in invalid or ord(char) < 32 else char for char in source_path.name).strip(" .")
    if not safe:
        safe = "local_file"
    if len(safe) > 180:
        stem = Path(safe).stem[:140]
        suffix = Path(safe).suffix[:20]
        safe = f"{stem}{suffix}"
    return f"{index:06d}_{safe}"

def _append_local_ingest_result(result: dict):
    LOCAL_INGEST_STATE["results"].append(result)
    overflow = len(LOCAL_INGEST_STATE["results"]) - LOCAL_RESULTS_LIMIT
    if overflow > 0:
        del LOCAL_INGEST_STATE["results"][:overflow]

def _prepare_local_ingest_run(run_id: str, defaults: dict, skip_similarity: bool, path_count: int = 0):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOCAL_INGEST_LOCK:
        if LOCAL_INGEST_STATE["running"]:
            raise HTTPException(status_code=409, detail="Local ingestion already running")
        LOCAL_STOP_AFTER_CURRENT.clear()
        LOCAL_INGEST_STATE["running"] = True
        LOCAL_INGEST_STATE["phase"] = "scanning"
        LOCAL_INGEST_STATE["run_id"] = run_id
        LOCAL_INGEST_STATE["scanned"] = 0
        LOCAL_INGEST_STATE["staged"] = 0
        LOCAL_INGEST_STATE["queued"] = 0
        LOCAL_INGEST_STATE["processed"] = 0
        LOCAL_INGEST_STATE["summary"] = {"ingested": 0, "review": 0, "failed": 0, "duplicate": 0}
        LOCAL_INGEST_STATE["results"] = []
        LOCAL_INGEST_STATE["failed_paths"] = []
        LOCAL_INGEST_STATE["last_defaults"] = dict(defaults or {})
        LOCAL_INGEST_STATE["last_skip_similarity"] = bool(skip_similarity)
        LOCAL_INGEST_STATE["started_at"] = now
        LOCAL_INGEST_STATE["finished_at"] = None
        LOCAL_INGEST_STATE["stop_requested"] = False
    log_ingest_local(
        "INFO",
        "Local ingest run started",
        run_id=run_id,
        path_count=path_count,
        artist=defaults.get("artist") or "Local",
        platform=defaults.get("platform") or "Local",
        skip_similarity=bool(skip_similarity),
    )

def _cleanup_local_run_dir(run_dir: Path):
    try:
        if run_dir.exists():
            shutil.rmtree(run_dir)
    except OSError as exc:
        log_ingest_local("WARNING", "Failed to clean local ingest staging directory", run_id=run_dir.name, path=str(run_dir), error=str(exc))

def _run_local_ingest_worker(raw_paths: list[str], defaults: dict, skip_similarity: bool, run_id: str):
    cfg = get_config()
    run_dir = LOCAL_INGEST_DIR / run_id
    discovered = 0
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        for source_path in _iter_local_ingest_paths(raw_paths, LOCAL_STOP_AFTER_CURRENT):
            if LOCAL_STOP_AFTER_CURRENT.is_set():
                break
            discovered += 1
            with LOCAL_INGEST_LOCK:
                LOCAL_INGEST_STATE["scanned"] = discovered
                LOCAL_INGEST_STATE["phase"] = "staging"
            staged_path = run_dir / _safe_staged_filename(discovered, source_path)
            try:
                shutil.copy2(source_path, staged_path)
                with LOCAL_INGEST_LOCK:
                    LOCAL_INGEST_STATE["staged"] = int(LOCAL_INGEST_STATE.get("staged") or 0) + 1
                    LOCAL_INGEST_STATE["queued"] = int(LOCAL_INGEST_STATE.get("queued") or 0) + 1
            except Exception as exc:
                message = f"Local staging failed: {exc}"
                log_ingest_local(
                    "ERROR",
                    "Local ingest staging failed",
                    run_id=run_id,
                    source_path=str(source_path),
                    name=source_path.name,
                    error=str(exc),
                )
                with LOCAL_INGEST_LOCK:
                    LOCAL_INGEST_STATE["summary"]["failed"] = int(LOCAL_INGEST_STATE["summary"].get("failed", 0)) + 1
                    LOCAL_INGEST_STATE["failed_paths"].append(str(source_path))
                    _append_local_ingest_result(
                        {
                            "path": str(source_path),
                            "source_path": str(source_path),
                            "staged_path": "",
                            "name": source_path.name,
                            "status": "failed",
                            "message": message,
                        }
                    )
                continue

            metadata = {
                "artist": defaults.get("artist") or "Local",
                "platform": defaults.get("platform") or "Local",
                "source_url": defaults.get("source_url") or "",
                "original_path": str(source_path),
                "staged_from": "local",
                "ingest_type": "local",
                "run_id": run_id,
            }
            with LOCAL_INGEST_LOCK:
                LOCAL_INGEST_STATE["phase"] = "running"
            try:
                ok, message, _ = process_file(staged_path, cfg, metadata=metadata, delete_source=True, skip_similarity=skip_similarity)
                if ok:
                    status = "ingested"
                elif "moved to review" in message.lower():
                    status = "review"
                elif message.lower().startswith("duplicate ignored"):
                    status = "duplicate"
                else:
                    status = "failed"
            except Exception as exc:
                status = "failed"
                message = f"Local ingest crash: {exc}"
            log_ingest_local(
                "INFO" if status in {"ingested", "duplicate", "review"} else "ERROR",
                "Local ingest item processed",
                run_id=run_id,
                status=status,
                source_path=str(source_path),
                name=source_path.name,
                result_message=message,
            )

            with LOCAL_INGEST_LOCK:
                LOCAL_INGEST_STATE["processed"] += 1
                LOCAL_INGEST_STATE["queued"] = max(0, int(LOCAL_INGEST_STATE.get("queued") or 0) - 1)
                LOCAL_INGEST_STATE["summary"][status] = int(LOCAL_INGEST_STATE["summary"].get(status, 0)) + 1
                _append_local_ingest_result(
                    {
                        "path": str(source_path),
                        "source_path": str(source_path),
                        "staged_path": str(staged_path),
                        "name": source_path.name,
                        "status": status,
                        "message": message,
                    }
                )
                if status == "failed":
                    LOCAL_INGEST_STATE["failed_paths"].append(str(source_path))
                if not LOCAL_STOP_AFTER_CURRENT.is_set():
                    LOCAL_INGEST_STATE["phase"] = "scanning"

        if discovered == 0:
            with LOCAL_INGEST_LOCK:
                LOCAL_INGEST_STATE["phase"] = "finished" if LOCAL_STOP_AFTER_CURRENT.is_set() else "failed"
                if not LOCAL_STOP_AFTER_CURRENT.is_set():
                    log_ingest_local("WARNING", "Local ingest found no valid files", run_id=run_id)
                    _append_local_ingest_result(
                        {
                            "path": "",
                            "source_path": "",
                            "staged_path": "",
                            "name": "",
                            "status": "failed",
                            "message": "No valid local files found",
                        }
                    )
                    LOCAL_INGEST_STATE["summary"]["failed"] = 1
        elif LOCAL_STOP_AFTER_CURRENT.is_set():
            log_ingest_local("INFO", "Local ingest stop-after-current acknowledged", run_id=run_id)
            with LOCAL_INGEST_LOCK:
                LOCAL_INGEST_STATE["phase"] = "stopping"
    except Exception as exc:
        log_ingest_local("ERROR", "Local ingest worker crashed", run_id=run_id, error=str(exc), traceback=traceback.format_exc())
        with LOCAL_INGEST_LOCK:
            LOCAL_INGEST_STATE["phase"] = "failed"
            LOCAL_INGEST_STATE["summary"]["failed"] = int(LOCAL_INGEST_STATE["summary"].get("failed", 0)) + 1
            _append_local_ingest_result(
                {
                    "path": "",
                    "source_path": "",
                    "staged_path": "",
                    "name": "",
                    "status": "failed",
                    "message": f"Local ingest worker crashed: {exc}",
                }
            )
    finally:
        _cleanup_local_run_dir(run_dir)
        with LOCAL_INGEST_LOCK:
            if LOCAL_INGEST_STATE.get("phase") not in {"failed", "stopping"}:
                LOCAL_INGEST_STATE["phase"] = "finished"
            elif LOCAL_INGEST_STATE.get("phase") == "stopping":
                LOCAL_INGEST_STATE["phase"] = "finished"
            LOCAL_INGEST_STATE["running"] = False
            LOCAL_INGEST_STATE["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            LOCAL_INGEST_STATE["stop_requested"] = False
            summary = dict(LOCAL_INGEST_STATE.get("summary") or {})
            phase = str(LOCAL_INGEST_STATE.get("phase") or "")
        LOCAL_STOP_AFTER_CURRENT.clear()
        log_ingest_local(
            "INFO" if phase == "finished" else "ERROR",
            "Local ingest run finished",
            run_id=run_id,
            phase=phase,
            summary_ingested=summary.get("ingested", 0),
            summary_review=summary.get("review", 0),
            summary_failed=summary.get("failed", 0),
            summary_duplicate=summary.get("duplicate", 0),
        )
        log_ingest_audit(
            "INFO" if phase == "finished" else "ERROR",
            "Local ingestion run summary",
            ingest_type="local",
            run_id=run_id,
            phase=phase,
            summary_ingested=summary.get("ingested", 0),
            summary_review=summary.get("review", 0),
            summary_failed=summary.get("failed", 0),
            summary_duplicate=summary.get("duplicate", 0),
        )

@app.post("/api/local-ingest/start")
async def local_ingest_start(body: LocalIngestStartRequest):
    raw_paths = [str(path or "").strip() for path in (body.paths or []) if str(path or "").strip()]
    if not raw_paths:
        raise HTTPException(status_code=400, detail="No local paths provided")
    defaults = body.defaults.model_dump() if body.defaults else {}
    run_id = _local_run_id()
    _prepare_local_ingest_run(run_id, defaults, bool(body.skip_similarity), len(raw_paths))
    asyncio.get_running_loop().run_in_executor(None, _run_local_ingest_worker, raw_paths, defaults, bool(body.skip_similarity), run_id)
    return {"status": "success", "run_id": run_id, "phase": "scanning"}

@app.post("/api/local-ingest/drop-intake")
async def local_ingest_drop_intake(body: LocalIngestDropIntakeRequest):
    return await asyncio.to_thread(_local_drop_intake_sync, body)

@app.get("/api/local-ingest/status")
async def local_ingest_status():
    return await asyncio.to_thread(_snapshot_local_ingest_state)

@app.post("/api/local-ingest/retry-failed")
async def local_ingest_retry_failed():
    with LOCAL_INGEST_LOCK:
        if LOCAL_INGEST_STATE["running"]:
            raise HTTPException(status_code=409, detail="Local ingestion already running")
        failed_paths = list(LOCAL_INGEST_STATE.get("failed_paths") or [])
        defaults = dict(LOCAL_INGEST_STATE.get("last_defaults") or {})
        skip_similarity = bool(LOCAL_INGEST_STATE.get("last_skip_similarity"))
    if not failed_paths:
        return {"status": "success", "queued": 0, "phase": "idle"}
    run_id = _local_run_id()
    _prepare_local_ingest_run(run_id, defaults, skip_similarity, len(failed_paths))
    asyncio.get_running_loop().run_in_executor(None, _run_local_ingest_worker, failed_paths, defaults, skip_similarity, run_id)
    return {"status": "success", "run_id": run_id, "phase": "scanning", "queued": len(failed_paths)}

@app.get("/api/review/count")
async def get_review_count(include_resolved: bool = False):
    return await asyncio.to_thread(_get_review_count_sync, include_resolved)

def _iter_review_media_files() -> list[Path]:
    if not REVIEW_DIR.exists():
        return []
    allowed = {
        f".{ext.lstrip('.').lower()}"
        for ext in get_config().get("firewall", {}).get("allowed_extensions", [])
    }
    return sorted(
        [
            p
            for p in REVIEW_DIR.iterdir()
            if p.is_file()
            and p.suffix.lower() not in [".json", ".md"]
            and (not allowed or p.suffix.lower() in allowed)
        ]
    )

def _resolve_review_entries() -> list[dict]:
    files = _iter_review_media_files()
    entries: list[dict] = []
    for media_path in files:
        sidecar = _read_review_sidecar(media_path)
        changed = False
        sidecar, defaults_changed = _ensure_review_sidecar_defaults(media_path, sidecar)
        changed = changed or defaults_changed
        before_hash = str(sidecar.get("file_hash") or "")
        sidecar = _ensure_review_hash(media_path, sidecar)
        if str(sidecar.get("file_hash") or "") != before_hash:
            changed = True
        raw_state = str(sidecar.get("state") or "pending")
        state = _normalize_review_state(raw_state)
        if raw_state != state or not raw_state:
            sidecar["state"] = state
            changed = True
        entries.append(
            {
                "path": media_path,
                "sidecar": sidecar,
                "state": state,
                "changed": changed,
                "mime_type": _guess_review_mime_type(media_path.name),
                "extension": media_path.suffix.lower(),
            }
        )

    present_hashes = _review_db_has_hashes(
        [str(entry["sidecar"].get("file_hash") or "") for entry in entries]
    )

    for entry in entries:
        sidecar = entry["sidecar"]
        file_hash = str(sidecar.get("file_hash") or "")
        if file_hash and file_hash in present_hashes and entry["state"] in REVIEW_PENDING_STATES:
            _set_review_state(sidecar, "resolved_variant", action=sidecar.get("last_action") or "reconciled")
            entry["state"] = "resolved_variant"
            entry["changed"] = True
        if entry["changed"]:
            try:
                _write_review_sidecar(entry["path"], sidecar)
            except Exception as exc:
                log_system("WARNING", "Failed to persist review sidecar reconciliation", filename=entry["path"].name, error=str(exc))
    return entries

def _is_pending_review_state(state: str) -> bool:
    if not state:
        return True
    return _normalize_review_state(state) in REVIEW_PENDING_STATES

def _get_review_count_sync(include_resolved: bool = False):
    entries = _resolve_review_entries()
    pending = sum(1 for entry in entries if _is_pending_review_state(entry["state"]))
    cleanup = sum(1 for entry in entries if _is_cleanup_review_state(entry["state"]))
    if include_resolved:
        return {"count": pending, "pending": pending, "cleanup": cleanup, "total": len(entries)}
    return {"count": pending, "pending": pending, "cleanup": cleanup}

@app.get("/api/review")
async def get_review_items(include_resolved: bool = False):
    return await asyncio.to_thread(_get_review_items_sync, include_resolved)

def _get_review_items_sync(include_resolved: bool = False):
    entries = _resolve_review_entries()
    if not include_resolved:
        entries = [entry for entry in entries if _normalize_review_state(entry["state"]) in REVIEW_VISIBLE_STATES]

    items = []
    best_hashes = sorted(
        {
            str(entry["sidecar"].get("best_match") or "").strip()
            for entry in entries
            if str(entry["sidecar"].get("best_match") or "").strip()
        }
    )
    match_map = {}
    if best_hashes:
        conn = init_database()
        try:
            placeholders = ",".join("?" for _ in best_hashes)
            cursor = conn.cursor()
            cursor.execute(f"SELECT hash, file_extension, mime_type, source_artist, storage_id FROM items WHERE hash IN ({placeholders})", best_hashes)
            for row in cursor.fetchall():
                match_map[row[0]] = {
                    "hash": row[0],
                    "url": asset_url_for(row[0], row[1] or "", row[2] or "", storage_id=row[4]),
                    "artist": row[3],
                    "mime_type": row[2] or "",
                    "extension": row[1] or "",
                }
        finally:
            conn.close()

    for entry in entries:
        p = entry["path"]
        sidecar = entry["sidecar"]
        best_match = str(sidecar.get("best_match") or "").strip()
        display_name = _review_display_name(p, sidecar)
        items.append({
            "filename": p.name,
            "display_name": display_name,
            "url": f"/review-assets/{p.name}",
            "metadata": sidecar,
            "best_match": match_map.get(best_match) if best_match else None,
            "mime_type": entry["mime_type"],
            "extension": entry["extension"],
            "state": entry["state"],
            "section": _review_section_for_state(entry["state"]),
            "last_action": sidecar.get("last_action") or "",
            "last_cleanup_error": sidecar.get("last_cleanup_error") or "",
        })
    return items

@app.post("/api/review/{filename}/action")
async def review_action(filename: str, action: str):
    return await asyncio.to_thread(_review_action_sync, filename, action)

def _review_action_sync(filename: str, action: str):
    if action not in {"delete", "keep", "variant", "replace"}:
        raise HTTPException(status_code=400, detail="Invalid review action")
    file_path = _review_path(filename)
    if not file_path.exists(): raise HTTPException(status_code=404)
    sidecar = _read_review_sidecar(file_path)
    sidecar, _ = _ensure_review_sidecar_defaults(file_path, sidecar)
    display_name = _review_display_name(file_path, sidecar)
    meta_path = _review_sidecar_path(file_path)
    current_state = _normalize_review_state(sidecar.get("state"))
    if current_state == "pending_cleanup":
        message = "Review item is pending cleanup; retry cleanup instead of applying review actions."
        log_review("WARNING", "Review action rejected for cleanup item", action=action, filename=filename, display_name=display_name, state=current_state)
        raise HTTPException(status_code=409, detail=message)
    metadata = sidecar.get("metadata", {}) if isinstance(sidecar, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}
    sidecar = _ensure_review_hash(file_path, sidecar)
    _write_review_sidecar(file_path, sidecar)

    if action == "delete":
        file_deleted, file_err = _review_cleanup_path(file_path)
        sidecar_deleted = True
        sidecar_err = ""
        if meta_path.exists():
            sidecar_deleted, sidecar_err = _review_cleanup_path(meta_path)
        if file_deleted and sidecar_deleted:
            message = "Review item deleted."
            log_review("INFO", "Review action succeeded", action=action, filename=filename, display_name=display_name, state="resolved_delete", detail=message)
            return {"status": "success", "action": action, "message": message}

        sidecar = _set_review_state(
            _read_review_sidecar(file_path) if file_path.exists() else sidecar,
            "pending_cleanup",
            cleanup_error=file_err or sidecar_err,
            action=action,
        )
        if file_path.exists():
            _write_review_sidecar(file_path, sidecar)
        message = "Review delete requested, but cleanup is pending."
        log_review("WARNING", "Review delete cleanup pending", action=action, filename=filename, display_name=display_name, state="pending_cleanup", error=file_err or sidecar_err)
        return {"status": "warning", "action": action, "message": message}

    if action == "keep":
        sidecar = _set_review_state(sidecar, "deferred", action=action)
        _write_review_sidecar(file_path, sidecar)
        message = "Review item kept in review queue."
        log_review("INFO", "Review action succeeded", action=action, filename=filename, display_name=display_name, state="deferred", detail=message)
        return {"status": "success", "action": action, "message": message}

    target_hash = ""
    replacement_manual_fields = {}
    if action == "replace":
        target_hash = str(sidecar.get("best_match") or "").strip()
        if not target_hash:
            message = "Replace target is missing. Item kept pending."
            log_review("WARNING", "Review replace warning", action=action, filename=filename, display_name=display_name, detail=message)
            return {"status": "warning", "action": action, "message": message}
        conn = init_database()
        try:
            target_exists = bool(conn.execute("SELECT 1 FROM items WHERE hash = ?", (target_hash,)).fetchone())
        finally:
            conn.close()
        if not target_exists:
            message = "Replace target no longer exists in DB. Item kept pending."
            log_review("WARNING", "Review replace warning", action=action, filename=filename, display_name=display_name, target_hash=target_hash, detail=message)
            return {"status": "warning", "action": action, "message": message}
        replacement_manual_fields = _manual_frontmatter_for_hash(target_hash)

    try:
        ok, process_message, idx_data = process_file(
            file_path,
            get_config(),
            metadata=metadata,
            delete_source=True,
            skip_similarity=True,
        )
    except Exception as exc:
        log_review("ERROR", "Review action failed", action=action, filename=filename, display_name=display_name, target_hash=target_hash, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Review action failed: {exc}") from exc

    if not ok:
        status_code = _review_failure_status(process_message)
        log_review("ERROR", "Review action failed", action=action, filename=filename, display_name=display_name, target_hash=target_hash, error=process_message)
        raise HTTPException(status_code=status_code, detail=process_message)

    preserve_error = ""
    if action == "replace":
        new_hash = str((idx_data or {}).get("file_hash") or "").strip()
        if not new_hash:
            preserve_error = "replacement hash was not returned by processor"
        else:
            try:
                _apply_manual_frontmatter_to_item(new_hash, replacement_manual_fields)
            except Exception as exc:
                preserve_error = str(exc)
                log_review("ERROR", "Review replace metadata preservation failed", action=action, filename=filename, display_name=display_name, target_hash=target_hash, new_hash=new_hash, error=preserve_error)

    resolved_state = "resolved_replace" if action == "replace" else "resolved_variant"
    sidecar = _set_review_state(sidecar, resolved_state, action=action, target_hash=target_hash)
    file_deleted, file_err = _review_cleanup_path(file_path)
    sidecar_deleted = True
    sidecar_err = ""
    if meta_path.exists():
        sidecar_deleted, sidecar_err = _review_cleanup_path(meta_path)
    if not file_deleted:
        sidecar = _set_review_state(sidecar, "pending_cleanup", cleanup_error=file_err, action=action, target_hash=target_hash)
        _write_review_sidecar(file_path, sidecar)
        log_review("WARNING", "Review cleanup pending after successful ingest", action=action, filename=filename, display_name=display_name, state="pending_cleanup", target_hash=target_hash, error=file_err)
        return {
            "status": "warning",
            "action": action,
            "message": "Ingested to DB, but failed to delete review file. Item kept pending for cleanup.",
        }
    elif not sidecar_deleted:
        log_review("WARNING", "Review sidecar cleanup pending after successful ingest", action=action, filename=filename, display_name=display_name, state=resolved_state, target_hash=target_hash, error=sidecar_err)

    if preserve_error:
        message = "Replacement ingested, but old target was kept because manual metadata preservation failed."
        return {"status": "warning", "action": action, "message": message, "error": preserve_error}

    if action == "replace":
        replace_result = _delete_item_after_replacement(target_hash)
        if replace_result["status"] != "deleted":
            error_text = "; ".join(str(item.get("error", "")) for item in replace_result.get("cleanup_errors", []) if item.get("error"))
            message = "Replacement ingested, but old target cleanup failed. Both vault items are kept."
            log_review(
                "WARNING",
                "Review replace target cleanup failed",
                action=action,
                filename=filename,
                display_name=display_name,
                state=resolved_state,
                target_hash=target_hash,
                error=error_text or replace_result["status"],
            )
            return {"status": "warning", "action": action, "message": message}

    message = "Review item replaced and ingested." if action == "replace" else "Review item ingested as variant."
    log_review("INFO", "Review action succeeded", action=action, filename=filename, display_name=display_name, state=resolved_state, target_hash=target_hash, detail=message)
    return {"status": "success", "action": action, "message": message}

@app.post("/api/review/cleanup")
async def cleanup_review_resolved():
    return await asyncio.to_thread(_cleanup_review_resolved_sync)

def _cleanup_review_resolved_sync():
    entries = _resolve_review_entries()
    cleaned = 0
    failed = 0
    cleaned_orphans = 0
    failed_orphans = 0
    seen_sidecars = set()
    for entry in entries:
        state = entry["state"]
        if state not in REVIEW_RESOLVED_STATES and not _is_cleanup_review_state(state):
            continue
        file_path = entry["path"]
        display_name = _review_display_name(file_path, entry["sidecar"])
        sidecar_path = _review_sidecar_path(file_path)
        seen_sidecars.add(sidecar_path.resolve())
        ok_file, err_file = _review_cleanup_path(file_path)
        ok_sidecar, err_sidecar = _review_cleanup_path(sidecar_path)
        if ok_file and ok_sidecar:
            cleaned += 1
            log_review("INFO", "Review cleanup succeeded", filename=file_path.name, display_name=display_name, state=state)
            continue
        failed += 1
        if file_path.exists():
            sidecar = _read_review_sidecar(file_path)
            sidecar = _set_review_state(sidecar, "pending_cleanup", cleanup_error=err_file or err_sidecar, action=sidecar.get("last_action") or "cleanup")
            _write_review_sidecar(file_path, sidecar)
        log_review("WARNING", "Review cleanup failed", filename=file_path.name, display_name=display_name, state="pending_cleanup", error=err_file or err_sidecar)

    if REVIEW_DIR.exists():
        for sidecar_path in REVIEW_DIR.glob("*.json"):
            resolved_sidecar = sidecar_path.resolve()
            if resolved_sidecar in seen_sidecars:
                continue
            media_path = sidecar_path.with_suffix("")
            if media_path.exists():
                continue
            ok_sidecar, err_sidecar = _review_cleanup_path(sidecar_path)
            if ok_sidecar:
                cleaned_orphans += 1
                log_review("INFO", "Review orphan sidecar cleaned", sidecar=str(sidecar_path.name))
            else:
                failed_orphans += 1
                log_review("WARNING", "Review orphan sidecar cleanup failed", sidecar=str(sidecar_path.name), error=err_sidecar)
    return {
        "status": "success",
        "cleaned": cleaned,
        "failed": failed,
        "cleaned_orphans": cleaned_orphans,
        "failed_orphans": failed_orphans,
    }

CONFIG_SECRET_KEYS = {"pixiv_token"}


def _strip_config_secrets(config: dict) -> dict:
    safe_config = copy.deepcopy(config or {})
    external_tools = safe_config.get("external_tools")
    if isinstance(external_tools, dict):
        for key in CONFIG_SECRET_KEYS:
            external_tools.pop(key, None)
    return safe_config


def _load_public_config_sync() -> dict:
    from utils import CONFIG_PATH
    import yaml
    if not CONFIG_PATH.exists():
        return _strip_config_secrets(get_config())
    with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    return _strip_config_secrets(config)


@app.get("/api/config")
async def get_app_config():
    return await asyncio.to_thread(_load_public_config_sync)

@app.post("/api/config")
async def update_app_config(new_config: dict):
    return await asyncio.to_thread(_update_app_config_sync, new_config)

def _update_app_config_sync(new_config: dict):
    from utils import CONFIG_PATH
    import yaml
    safe_config = _strip_config_secrets(new_config)
    atomic_write_text(CONFIG_PATH, yaml.dump(safe_config, default_flow_style=False, allow_unicode=True))
    return {"status": "success"}

@app.get("/")
async def root(): return {"status": "LMZ API Running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web_api:app", host="127.0.0.1", port=8000, reload=True)
