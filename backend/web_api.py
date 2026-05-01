import os
import sys
import json
import asyncio
import traceback
import secrets
import threading
from collections import Counter
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from db.sqlite_operator import init_database, normalize_source_url
from utils import get_config, ASSETS_DIR, REVIEW_DIR, note_path_for, asset_path_for
from processor import process_file
from logs.logger import log_svelte, log_system, RAW_LOGS_DIR, STRUCTURED_LOGS_DIR
from md_generator import load_note_topics, load_note_wd_tags, generate_markdown
from tagging import load_tag_cache, tag_media
from thumbnails import get_or_generate_thumbnail
from utils import SECRETS_DIR, WD_TAGS_DIR, atomic_write_text

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

app = FastAPI(title="LIZ API")

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
    "ingestion.jsonl": STRUCTURED_LOGS_DIR / "ingestion.jsonl",
    "activity.jsonl": STRUCTURED_LOGS_DIR / "activity.jsonl",
    "terminal.log": RAW_LOGS_DIR / "terminal.log",
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(ALLOWED_ORIGINS),
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    provided = request.headers.get("X-LIZ-API-KEY", "")
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
if REVIEW_DIR.exists():
    app.mount("/review-assets", StaticFiles(directory=str(REVIEW_DIR)), name="review-assets")

@app.get("/api/stats")
async def get_stats():
    return await asyncio.to_thread(_get_stats_sync)

def _get_stats_sync():
    conn = init_database()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM items")
        count = cursor.fetchone()[0]
        return {"total_items": count}
    finally:
        conn.close()

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
        commands = [">masonry", ">masonry-exp", ">masonry-measured", ">grid", ">zoom-in", ">zoom-out"]
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

        cursor.execute("SELECT hash FROM items ORDER BY date_added DESC")
        rows = cursor.fetchall()
        if kind == "topic":
            items = _count_python_facets(rows, load_note_topics, needle, limit)
        else:
            items = _count_python_facets(rows, _wd_names_for_hash, needle, limit)
        return {"kind": kind, "items": items}
    finally:
        conn.close()

@app.get("/api/thumbnails/{item_hash}")
async def get_thumbnail(item_hash: str):
    return await asyncio.to_thread(_get_thumbnail_sync, item_hash)

def _get_thumbnail_sync(item_hash: str):
    conn = init_database()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT file_extension, mime_type FROM items WHERE hash = ?", (item_hash,))
        row = cursor.fetchone()
        if not row: raise HTTPException(status_code=404)
        thumb_path = get_or_generate_thumbnail(item_hash, row[0], row[1])
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

def _item_after_cursor(item: dict, cursor: str, sort: str) -> bool:
    if not cursor:
        return True
    try:
        cursor_date, cursor_hash = cursor.rsplit("_", 1)
    except ValueError:
        cursor_date, cursor_hash = cursor, ""
    item_key = (str(item.get("date_added") or ""), str(item.get("hash") or ""))
    cursor_key = (cursor_date, cursor_hash)
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

def _wd_names_for_hash(item_hash: str) -> list[str]:
    wd_data = load_note_wd_tags(item_hash)
    if wd_data.get("status") != "ok":
        cache_data = load_tag_cache(item_hash)
        if cache_data.get("status") == "ok":
            wd_data = {
                "rating": cache_data.get("rating") or {},
                "character_tags": cache_data.get("character_tags") or [],
                "tags": cache_data.get("tags") or []
            }
    names = []
    rating = wd_data.get("rating", {})
    if rating:
        names.append(rating.get("label", "") or rating.get("name", ""))
    for tag in wd_data.get("character_tags", []):
        if isinstance(tag, str):
            names.append(tag)
        elif isinstance(tag, dict):
            names.append(tag.get("display_name", "") or tag.get("name", ""))
    for tag in wd_data.get("tags", []):
        if isinstance(tag, str):
            names.append(tag)
        elif isinstance(tag, dict):
            names.append(tag.get("display_name", "") or tag.get("name", ""))
    return [name for name in names if name]

def _get_items_sync(field, value, sort, media_type, artist, platform, filename, topic, wd_tag, text, cursor, limit):
    limit = max(1, min(limit, 100))
    topic_filters = _clean_filter_values(topic)
    wd_tag_filters = _clean_filter_values(wd_tag)
    conn = init_database()
    cursor_obj = conn.cursor()
    try:
        base_query = "SELECT hash, file_extension, mime_type, original_filename, source_url, date_added, platform, source_artist, width, height FROM items"
        conditions = []
        params = []

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

        has_frontmatter_filter = bool(topic_filters or wd_tag_filters)

        if cursor and not has_frontmatter_filter:
            try:
                cursor_date, cursor_hash = cursor.rsplit("_", 1)
            except ValueError:
                cursor_date, cursor_hash = cursor, ""
            if sort == 'oldest':
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
        elif sort == 'artist': order_clause = " ORDER BY source_artist COLLATE NOCASE ASC, date_added DESC"

        sql_limit = 100000 if has_frontmatter_filter else limit + 1

        cursor_obj.execute(f"{base_query}{where_clause}{order_clause} LIMIT {sql_limit}", tuple(params))
        rows = cursor_obj.fetchall()

        items = []
        topic_lowers = [value.lower() for value in topic_filters]
        wd_tag_lowers = [value.lower() for value in wd_tag_filters]

        for row in rows:
            h, ext = row[0], (row[1] or "")

            if topic_lowers:
                note_topics = load_note_topics(h)
                topic_strings = [t.lower() for t in note_topics]
                if not all(any(topic_value in topic_string for topic_string in topic_strings) for topic_value in topic_lowers):
                    continue

            if wd_tag_lowers:
                wd_strings = [name.lower() for name in _wd_names_for_hash(h)]
                if not all(any(wd_value in wd_string for wd_string in wd_strings) for wd_value in wd_tag_lowers):
                    continue

            items.append({
                "hash": h, "extension": ext, "mime_type": row[2],
                "original_filename": row[3], "source_url": row[4],
                "date_added": row[5], "platform": row[6], "artist": row[7],
                "url": f"/vault/{h[:2]}/{h}{ext}",
                "thumbnail_url": f"/api/thumbnails/{h}",
                "width": row[8], "height": row[9]
            })

        if has_frontmatter_filter and cursor:
            items = [item for item in items if _item_after_cursor(item, cursor, sort)]

        has_more = len(items) > limit
        if has_more:
            items = items[:limit]

        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = f"{last['date_added']}_{last['hash']}"

        return {"items": items, "next_cursor": next_cursor, "has_more": has_more}
    finally:
        conn.close()

def _get_item_details(h, row):
    ext = row[1] or ""
    topics = load_note_topics(h)
    wd_data = load_note_wd_tags(h)
    if wd_data.get("status") != "ok":
        cache_data = load_tag_cache(h)
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
        "url": f"/vault/{h[:2]}/{h}{ext}",
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
        cursor.execute("SELECT hash, file_extension, mime_type, original_filename, source_url, date_added, platform, source_artist, width, height FROM items WHERE hash = ?", (item_hash,))
        row = cursor.fetchone()
        if not row: raise HTTPException(status_code=404)
        return _get_item_details(item_hash, row)
    finally:
        conn.close()

@app.get("/api/items/{item_hash}/path")
async def get_item_path(item_hash: str):
    return await asyncio.to_thread(_get_item_path_sync, item_hash)

def _get_item_path_sync(item_hash: str):
    conn = init_database()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT file_extension, mime_type FROM items WHERE hash = ?", (item_hash,))
        row = cursor.fetchone()
        if not row: raise HTTPException(status_code=404)
        # Using utils instead of ui
        path = asset_path_for(item_hash, row[0] or "", row[1] or "")
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
        cursor.execute("SELECT hash FROM items WHERE hash = ?", (item_hash,))
        row = cursor.fetchone()
        if not row: raise HTTPException(status_code=404)
        path = note_path_for(item_hash)
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
        cursor.execute("SELECT file_extension, mime_type FROM items WHERE hash = ?", (item_hash,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404)
        path = asset_path_for(item_hash, row[0] or "", row[1] or "")
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
        cursor.execute("SELECT hash FROM items WHERE hash = ?", (item_hash,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404)
        path = note_path_for(item_hash)
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
        if update.artist is not None:
            cursor.execute("UPDATE items SET source_artist = ? WHERE hash = ?", (update.artist, item_hash))
        if update.source_url is not None:
            cursor.execute("UPDATE items SET source_url = ?, source_url_norm = ? WHERE hash = ?", (update.source_url, normalize_source_url(update.source_url), item_hash))
        if update.platform is not None:
            cursor.execute("UPDATE items SET platform = ? WHERE hash = ?", (update.platform, item_hash))
        conn.commit()
        
        md_content = generate_markdown(conn, item_hash, topics_override=update.topics)
        if md_content:
            note_path = note_path_for(item_hash)
            note_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(note_path, md_content)
            
        return {"status": "success"}
    finally:
        conn.close()

@app.delete("/api/items/{item_hash}")
async def delete_item(item_hash: str):
    return await asyncio.to_thread(_delete_item_sync, item_hash)

@app.post("/api/items/bulk_delete")
async def bulk_delete_items(request: BulkDeleteRequest):
    return await asyncio.to_thread(_bulk_delete_items_sync, request.hashes)

def _delete_item_row(cursor, conn, item_hash: str):
    cursor.execute("SELECT file_extension, mime_type FROM items WHERE hash = ?", (item_hash,))
    row = cursor.fetchone()
    if not row:
        return {"hash": item_hash, "status": "missing", "cleanup_errors": []}

    cleanup_paths = [
        asset_path_for(item_hash, row[0] or "", row[1] or ""),
        note_path_for(item_hash),
        WD_TAGS_DIR / item_hash[:2] / f"{item_hash}.json",
    ]

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
            cursor.execute("SELECT file_extension, mime_type FROM items WHERE hash = ?", (item_hash,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404)
            
            asset_path = asset_path_for(item_hash, row[0] or "", row[1] or "")
            if not asset_path.exists():
                raise HTTPException(status_code=404, detail="Asset missing")

            log_system("INFO", f"Triggering AI tagging for {item_hash}")
            tag_media(asset_path, item_hash=item_hash, config=get_config())
            
            md_content = generate_markdown(conn, item_hash)
            if md_content:
                note_path = note_path_for(item_hash)
                note_path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_text(note_path, md_content)
            
            cursor.execute("SELECT hash, file_extension, mime_type, original_filename, source_url, date_added, platform, source_artist, width, height FROM items WHERE hash = ?", (item_hash,))
            updated_row = cursor.fetchone()
            return _get_item_details(item_hash, updated_row)
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
    def run_in_background():
        try:
            run_queue(queue_name)
        except Exception as e:
            log_system("ERROR", "Ingestion worker crashed", error=str(e), traceback=traceback.format_exc())
        finally:
            INGESTION_LOCK.release()
    asyncio.get_running_loop().run_in_executor(None, run_in_background)
    return {"status": "success"}

@app.get("/api/queue-stats")
async def get_queue_stats(): return await asyncio.to_thread(queue_counts)

@app.get("/api/review/count")
async def get_review_count():
    return await asyncio.to_thread(_get_review_count_sync)

def _get_review_count_sync():
    if not REVIEW_DIR.exists():
        return {"count": 0}
    count = sum(
        1 for path in REVIEW_DIR.iterdir()
        if path.is_file() and path.suffix.lower() not in [".json", ".md"]
    )
    return {"count": count}

@app.get("/api/review")
async def get_review_items():
    return await asyncio.to_thread(_get_review_items_sync)

def _get_review_items_sync():
    if not REVIEW_DIR.exists(): return []
    items = []
    pending = []
    for p in sorted(REVIEW_DIR.iterdir()):
        if p.is_file() and p.suffix.lower() not in [".json", ".md"]:
            meta_path = p.with_suffix(p.suffix + ".json")
            meta = {}
            if meta_path.exists():
                with open(meta_path, "r", encoding="utf-8") as f: meta = json.load(f)
            best_match = meta.get("best_match")
            pending.append((p, meta, best_match))

    best_hashes = sorted({best for _, _, best in pending if best})
    match_map = {}
    if best_hashes:
        conn = init_database()
        try:
            placeholders = ",".join("?" for _ in best_hashes)
            cursor = conn.cursor()
            cursor.execute(f"SELECT hash, file_extension, mime_type, source_artist FROM items WHERE hash IN ({placeholders})", best_hashes)
            for row in cursor.fetchall():
                match_map[row[0]] = {"hash": row[0], "url": f"/vault/{row[0][:2]}/{row[0]}{row[1]}" if row[1] else f"/vault/{row[0][:2]}/{row[0]}", "artist": row[3]}
        finally:
            conn.close()

    for p, meta, best_match in pending:
        items.append({"filename": p.name, "url": f"/review-assets/{p.name}", "metadata": meta, "best_match": match_map.get(best_match)})
    return items

@app.post("/api/review/{filename}/action")
async def review_action(filename: str, action: str):
    return await asyncio.to_thread(_review_action_sync, filename, action)

def _review_action_sync(filename: str, action: str):
    if action not in {"delete", "keep", "variant"}:
        raise HTTPException(status_code=400, detail="Invalid review action")
    file_path = _review_path(filename)
    if not file_path.exists(): raise HTTPException(status_code=404)
    if action == "delete":
        file_path.unlink()
        meta_path = file_path.with_suffix(file_path.suffix + ".json")
        if meta_path.exists(): meta_path.unlink()
    elif action == "keep" or action == "variant":
        meta_path = file_path.with_suffix(file_path.suffix + ".json")
        meta = {}
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f: meta = json.load(f)
        process_file(file_path, get_config(), metadata=meta, delete_source=True)
    return {"status": "success"}

@app.get("/api/config")
async def get_app_config(): return await asyncio.to_thread(get_config)

@app.post("/api/config")
async def update_app_config(new_config: dict):
    return await asyncio.to_thread(_update_app_config_sync, new_config)

def _update_app_config_sync(new_config: dict):
    from utils import CONFIG_PATH
    import yaml
    atomic_write_text(CONFIG_PATH, yaml.dump(new_config, default_flow_style=False, allow_unicode=True))
    return {"status": "success"}

@app.get("/")
async def root(): return {"status": "LIZ API Running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web_api:app", host="127.0.0.1", port=8000, reload=True)
