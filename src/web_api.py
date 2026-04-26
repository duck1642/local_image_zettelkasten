import os
import sys
import json
import asyncio
import traceback
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from db.sqlite_operator import init_database
from utils import VAULT_DIR, DB_PATH, get_config, ASSETS_DIR, LOGS_DIR, REVIEW_DIR, note_path_for, asset_path_for
from processor import process_file
from logs.logger import log_svelte, log_pyui, log_system, log_ingestion, RAW_LOGS_DIR, STRUCTURED_LOGS_DIR
from md_generator import load_note_topics, load_note_wd_tags, generate_markdown
from tagging import load_tag_cache, tag_media

# --- TERMINAL LOG REDIRECTION ---
# This ensures raw terminal output (like tracebacks) goes to a log file
class TerminalLogger:
    def __init__(self, filename, original_stream):
        self.terminal = original_stream
        self.log_path = RAW_LOGS_DIR / filename
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, message):
        self.terminal.write(message)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(message)

    def flush(self):
        self.terminal.flush()

    def isatty(self):
        return hasattr(self.terminal, 'isatty') and self.terminal.isatty()

    def __getattr__(self, attr):
        return getattr(self.terminal, attr)

# Redirect both stdout and stderr to terminal.log
sys.stdout = TerminalLogger("terminal.log", sys.stdout)
sys.stderr = TerminalLogger("terminal.log", sys.stderr)

app = FastAPI(title="LIZ API")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static mounts
if ASSETS_DIR.exists():
    app.mount("/vault", StaticFiles(directory=str(ASSETS_DIR)), name="vault")
if REVIEW_DIR.exists():
    app.mount("/review-assets", StaticFiles(directory=str(REVIEW_DIR)), name="review-assets")

# --- CORE LOGIC ENDPOINTS ---

@app.get("/api/items")
async def get_items(field: str = None, value: str = None):
    allowed = {"source_artist", "platform", "original_filename"}
    conn = init_database()
    cursor = conn.cursor()
    try:
        if field and value and field in allowed:
            cursor.execute(
                f"SELECT hash, file_extension, mime_type, original_filename, source_url, date_added, platform, source_artist FROM items WHERE {field} LIKE ? ORDER BY date_added DESC LIMIT 300",
                (f"%{value}%",),
            )
        else:
            cursor.execute("SELECT hash, file_extension, mime_type, original_filename, source_url, date_added, platform, source_artist FROM items ORDER BY date_added DESC LIMIT 300")
        
        rows = cursor.fetchall()
        items = []
        for row in rows:
            h, ext = row[0], (row[1] or "")
            items.append({
                "hash": h, "extension": ext, "mime_type": row[2],
                "original_filename": row[3], "source_url": row[4],
                "date_added": row[5], "platform": row[6], "artist": row[7],
                "url": f"/vault/{h[:2]}/{h}{ext}"
            })
        return items
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
        "topics": topics,
        "wd_tags": formatted_wd
    }

@app.get("/api/items/{item_hash}")
async def get_item(item_hash: str):
    conn = init_database()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT hash, file_extension, mime_type, original_filename, source_url, date_added, platform, source_artist FROM items WHERE hash = ?", (item_hash,))
        row = cursor.fetchone()
        if not row: raise HTTPException(status_code=404)
        return _get_item_details(item_hash, row)
    finally:
        conn.close()

@app.get("/api/items/{item_hash}/path")
async def get_item_path(item_hash: str):
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

class ItemUpdate(BaseModel):
    artist: str = None
    source_url: str = None
    platform: str = None
    topics: list[str] = None

@app.patch("/api/items/{item_hash}")
async def update_item(item_hash: str, update: ItemUpdate):
    conn = init_database()
    cursor = conn.cursor()
    try:
        if update.artist is not None:
            cursor.execute("UPDATE items SET source_artist = ? WHERE hash = ?", (update.artist, item_hash))
        if update.source_url is not None:
            cursor.execute("UPDATE items SET source_url = ? WHERE hash = ?", (update.source_url, item_hash))
        if update.platform is not None:
            cursor.execute("UPDATE items SET platform = ? WHERE hash = ?", (update.platform, item_hash))
        conn.commit()
        
        md_content = generate_markdown(conn, item_hash)
        if md_content:
            note_path = note_path_for(item_hash)
            note_path.parent.mkdir(parents=True, exist_ok=True)
            note_path.write_text(md_content, encoding="utf-8")
            
        return {"status": "success"}
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
            if not row: return None
            
            # Using utils instead of ui
            asset_path = asset_path_for(item_hash, row[0] or "", row[1] or "")
            if not asset_path.exists(): return None

            log_system("INFO", f"Triggering AI tagging for {item_hash}")
            tag_media(asset_path, item_hash=item_hash, config=get_config())
            
            md_content = generate_markdown(conn, item_hash)
            if md_content:
                note_path = note_path_for(item_hash)
                note_path.parent.mkdir(parents=True, exist_ok=True)
                note_path.write_text(md_content, encoding="utf-8")
            
            cursor.execute("SELECT hash, file_extension, mime_type, original_filename, source_url, date_added, platform, source_artist FROM items WHERE hash = ?", (item_hash,))
            updated_row = cursor.fetchone()
            return _get_item_details(item_hash, updated_row)
        finally:
            conn.close()

    try:
        return await asyncio.to_thread(sync_tagging)
    except Exception as e:
        print(f"!!! TAGGING CRASH !!!\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

# --- LOGGING ENDPOINTS ---

@app.get("/api/logs")
async def stream_logs(filename: str = Query("system.jsonl")):
    if filename.endswith(".jsonl"):
        log_file = STRUCTURED_LOGS_DIR / filename
    else:
        log_file = RAW_LOGS_DIR / filename

    if not log_file.exists():
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.touch()
    
    async def log_generator():
        # Last 150 lines for terminal
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            for line in lines[-150:]:
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
    if filename.endswith(".jsonl"):
        log_file = STRUCTURED_LOGS_DIR / filename
    else:
        log_file = RAW_LOGS_DIR / filename
        
    if not log_file.exists(): raise HTTPException(status_code=404)
    try:
        if os.name == 'nt': os.startfile(str(log_file))
        else:
            import subprocess
            opener = "open" if os.uname().sysname == "Darwin" else "xdg-open"
            subprocess.call([opener, str(log_file)])
        return {"status": "opened"}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

# --- QUEUE & INGESTION ---
class QueueUpdate(BaseModel):
    content: str
from queue_service import read_queue, write_queue, queue_counts, INGESTION_LOCK, run_queue, clear_failed, move_failed_urls, parse_urls, queue_path

@app.get("/api/queue/{queue_name}")
async def get_queue(queue_name: str):
    return {"content": read_queue(queue_name), "count": queue_counts().get(queue_name, 0)}

@app.post("/api/queue/{queue_name}")
async def save_queue(queue_name: str, update: QueueUpdate):
    write_queue(queue_name, update.content)
    return {"status": "success", "count": queue_counts().get(queue_name, 0)}

@app.post("/api/queue/{queue_name}/parse")
async def parse_queue_content(queue_name: str, update: QueueUpdate):
    return {"count": len(parse_urls(update.content))}

@app.post("/api/queue/actions/clear-failed")
async def api_clear_failed():
    clear_failed()
    return {"status": "success", "counts": queue_counts()}

class RetryFailedBody(BaseModel):
    target: str

@app.post("/api/queue/actions/retry-failed")
async def api_retry_failed(body: RetryFailedBody):
    if body.target not in ["normal", "force"]: raise HTTPException(400, "Invalid target")
    moved = move_failed_urls(body.target)
    return {"status": "success", "moved": moved, "counts": queue_counts()}

@app.post("/api/queue/{queue_name}/open")
async def open_queue_external(queue_name: str):
    path = queue_path(queue_name)
    if not path.exists():
        read_queue(queue_name) # creates it if missing
    try:
        if os.name == 'nt': os.startfile(str(path))
        else:
            import subprocess
            opener = "open" if os.uname().sysname == "Darwin" else "xdg-open"
            subprocess.call([opener, str(path)])
        return {"status": "opened"}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ingest/{queue_name}")
async def start_ingestion(queue_name: str):
    if INGESTION_LOCK.locked(): return {"status": "error", "message": "Already running"}
    def run_in_background():
        with INGESTION_LOCK:
            try: run_queue(queue_name)
            except Exception as e: print(e)
    asyncio.get_event_loop().run_in_executor(None, run_in_background)
    return {"status": "success"}

@app.get("/api/queue-stats")
async def get_queue_stats(): return queue_counts()

# --- REVIEW ---
@app.get("/api/review")
async def get_review_items():
    if not REVIEW_DIR.exists(): return []
    items = []
    for p in sorted(REVIEW_DIR.iterdir()):
        if p.is_file() and p.suffix.lower() not in [".json", ".md"]:
            meta_path = p.with_suffix(p.suffix + ".json")
            meta = {}
            if meta_path.exists():
                with open(meta_path, "r", encoding="utf-8") as f: meta = json.load(f)
            best_match = meta.get("best_match")
            match_data = None
            if best_match:
                conn = init_database()
                cursor = conn.cursor()
                cursor.execute("SELECT hash, file_extension, mime_type, source_artist FROM items WHERE hash = ?", (best_match,))
                row = cursor.fetchone()
                if row: match_data = {"hash": row[0], "url": f"/vault/{row[0][:2]}/{row[0]}{row[1]}" if row[1] else f"/vault/{row[0][:2]}/{row[0]}", "artist": row[3]}
                conn.close()
            items.append({"filename": p.name, "url": f"/review-assets/{p.name}", "metadata": meta, "best_match": match_data})
    return items

@app.post("/api/review/{filename}/action")
async def review_action(filename: str, action: str):
    file_path = REVIEW_DIR / filename
    if not file_path.exists(): raise HTTPException(status_code=404)
    if action == "delete":
        file_path.unlink()
        meta_path = file_path.with_suffix(file_path.suffix + ".json")
        if meta_path.exists(): meta_path.unlink()
    elif action == "keep":
        meta_path = file_path.with_suffix(file_path.suffix + ".json")
        meta = {}
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f: meta = json.load(f)
        process_file(file_path, get_config(), metadata=meta, delete_source=True)
    return {"status": "success"}

# --- CONFIG ---
@app.get("/api/config")
async def get_app_config(): return get_config()

@app.post("/api/config")
async def update_app_config(new_config: dict):
    from utils import CONFIG_PATH
    import yaml
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(new_config, f, default_flow_style=False, allow_unicode=True)
    return {"status": "success"}

@app.get("/")
async def root(): return {"status": "LIZ API Running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web_api:app", host="127.0.0.1", port=8000, reload=True)
