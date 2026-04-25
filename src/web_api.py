import os
import json
import asyncio
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from db.sqlite_operator import init_database
from utils import VAULT_DIR, DB_PATH, get_config, ASSETS_DIR, LOGS_DIR

app = FastAPI(title="LIZ API")

# Enable CORS so the Svelte frontend can talk to this server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the vault assets directly
if ASSETS_DIR.exists():
    app.mount("/vault", StaticFiles(directory=str(ASSETS_DIR)), name="vault")

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
            h = row[0]
            ext = row[1] or ""
            shard = h[:2]
            items.append({
                "hash": h,
                "extension": ext,
                "mime_type": row[2],
                "original_filename": row[3],
                "source_url": row[4],
                "date_added": row[5],
                "platform": row[6],
                "artist": row[7],
                "url": f"/vault/{shard}/{h}{ext}"
            })
        return items
    finally:
        conn.close()

@app.get("/api/stats")
async def get_stats():
    conn = init_database()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM items")
        count = cursor.fetchone()[0]
        return {"total_items": count}
    finally:
        conn.close()

@app.get("/api/items/{item_hash}")
async def get_item(item_hash: str):
    conn = init_database()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT hash, file_extension, mime_type, original_filename, source_url, date_added, platform, source_artist FROM items WHERE hash = ?", (item_hash,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Item not found")
        
        return {
            "hash": row[0],
            "extension": row[1],
            "mime_type": row[2],
            "original_filename": row[3],
            "source_url": row[4],
            "date_added": row[5],
            "platform": row[6],
            "artist": row[7],
            "url": f"/vault/{row[0][:2]}/{row[0]}{row[1]}" if row[1] else f"/vault/{row[0][:2]}/{row[0]}"
        }
    finally:
        conn.close()

class ItemUpdate(BaseModel):
    artist: str = None
    source_url: str = None
    platform: str = None

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
        return {"status": "success"}
    finally:
        conn.close()

@app.get("/api/logs")
async def stream_logs():
    log_file = LOGS_DIR / "system.log"
    
    async def log_generator():
        # Start by sending the last 50 lines for context
        if log_file.exists():
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                for line in lines[-50:]:
                    yield f"data: {line}\n\n"

        # Now tail the file
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                # Go to end of file
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

@app.get("/")
async def root():
    return {"status": "LIZ API is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
