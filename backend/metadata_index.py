import json
import re
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable

import yaml

from logger import log_system
from md_generator import normalize_topic_list
from tagging import load_tag_cache
from utils import DB_PATH, NOTES_DIR, WD_TAGS_DIR, existing_note_path_for, existing_wd_tag_cache_path_for


HASH_RE = re.compile(r"^[0-9a-fA-F]{64}$")
READY_KEY = "initial_backfill_complete"
REPAIR_BATCH_SIZE = 500
WD_FRONTMATTER_FIELDS = ("wd_rating", "wd_character_tags", "wd_tags")

_repair_lock = threading.Lock()
_repair_running = False
_watchdog_lock = threading.Lock()
_watchdog_observer = None
_watchdog_pending: set[str] = set()
_watchdog_timer: threading.Timer | None = None


def ensure_metadata_schema(conn: sqlite3.Connection):
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metadata_index_state (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS item_metadata_files (
            item_hash TEXT PRIMARY KEY,
            note_path TEXT,
            note_mtime_ns INTEGER,
            note_size INTEGER,
            wd_path TEXT,
            wd_mtime_ns INTEGER,
            wd_size INTEGER,
            indexed_at TEXT,
            status TEXT NOT NULL DEFAULT 'ok',
            error TEXT NOT NULL DEFAULT '',
            FOREIGN KEY(item_hash) REFERENCES items(hash) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS item_topics (
            item_hash TEXT NOT NULL,
            topic TEXT NOT NULL,
            topic_norm TEXT NOT NULL,
            PRIMARY KEY(item_hash, topic_norm),
            FOREIGN KEY(item_hash) REFERENCES items(hash) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS item_wd_tags (
            item_hash TEXT NOT NULL,
            tag TEXT NOT NULL,
            tag_norm TEXT NOT NULL,
            tag_type TEXT NOT NULL,
            PRIMARY KEY(item_hash, tag_norm, tag_type),
            FOREIGN KEY(item_hash) REFERENCES items(hash) ON DELETE CASCADE
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_item_topics_norm ON item_topics(topic_norm)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_item_topics_hash ON item_topics(item_hash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_item_wd_tags_norm ON item_wd_tags(tag_norm)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_item_wd_tags_hash ON item_wd_tags(item_hash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_item_metadata_status ON item_metadata_files(status)")


def metadata_index_ready(conn: sqlite3.Connection) -> bool:
    ensure_metadata_schema(conn)
    row = conn.execute(
        "SELECT value FROM metadata_index_state WHERE key = ?",
        (READY_KEY,),
    ).fetchone()
    return bool(row and row[0] == "1")


def _set_metadata_index_ready(conn: sqlite3.Connection, ready: bool):
    conn.execute(
        """
        INSERT INTO metadata_index_state(key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (READY_KEY, "1" if ready else "0"),
    )


def _norm(value: str) -> str:
    return str(value or "").strip().casefold()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _file_sig(path: Path) -> tuple[str, int | None, int | None]:
    try:
        stat = path.stat()
        return str(path), int(stat.st_mtime_ns), int(stat.st_size)
    except OSError:
        return str(path), None, None


def _current_sigs(item_hash: str) -> dict:
    note_path = existing_note_path_for(item_hash)
    wd_path = existing_wd_tag_cache_path_for(item_hash)
    note_path_str, note_mtime, note_size = _file_sig(note_path)
    wd_path_str, wd_mtime, wd_size = _file_sig(wd_path)
    return {
        "note_path": note_path_str,
        "note_mtime_ns": note_mtime,
        "note_size": note_size,
        "wd_path": wd_path_str,
        "wd_mtime_ns": wd_mtime,
        "wd_size": wd_size,
    }


def _load_frontmatter(item_hash: str) -> tuple[dict, str]:
    path = existing_note_path_for(item_hash)
    if not path.exists():
        return {}, ""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {}, str(exc)
    text = text.lstrip("\ufeff")
    if not text.startswith("---"):
        return {}, ""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, ""
    end_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = index
            break
    if end_index is None:
        return {}, "frontmatter terminator missing"
    yaml_text = "\n".join(lines[1:end_index])
    try:
        data = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError as exc:
        return {}, str(exc)
    return (data if isinstance(data, dict) else {}), ""


def _tag_name(tag) -> str:
    if isinstance(tag, str):
        return tag.strip()
    if isinstance(tag, dict):
        return str(tag.get("display_name") or tag.get("label") or tag.get("name") or "").strip()
    return ""


def _cache_wd_payload(item_hash: str) -> dict:
    cache_data = load_tag_cache(item_hash)
    if cache_data.get("status") != "ok":
        return {"status": "missing"}
    return {
        "status": "ok",
        "source": "cache",
        "rating": cache_data.get("rating") or {},
        "character_tags": cache_data.get("character_tags") or [],
        "tags": cache_data.get("tags") or [],
    }


def _wd_payload(item_hash: str, frontmatter: dict) -> dict:
    has_wd_fields = any(field in frontmatter for field in WD_FRONTMATTER_FIELDS)
    cache_payload = _cache_wd_payload(item_hash)
    if not has_wd_fields:
        return cache_payload

    if "wd_rating" in frontmatter:
        rating = str(frontmatter.get("wd_rating") or "").strip()
        rating_payload = {"label": rating} if rating else {}
    else:
        rating_payload = cache_payload.get("rating") or {}

    if "wd_character_tags" in frontmatter:
        characters = normalize_topic_list(frontmatter.get("wd_character_tags"))
        character_payload = [{"name": tag} for tag in characters]
    else:
        character_payload = cache_payload.get("character_tags") or []

    if "wd_tags" in frontmatter:
        tags = normalize_topic_list(frontmatter.get("wd_tags"))
        tag_payload = [{"name": tag} for tag in tags]
    else:
        tag_payload = cache_payload.get("tags") or []

    return {
        "status": "ok",
        "source": "yaml",
        "rating": rating_payload,
        "character_tags": character_payload,
        "tags": tag_payload,
    }


def _wd_rows(payload: dict) -> list[tuple[str, str]]:
    rows = []
    rating = payload.get("rating") or {}
    rating_name = _tag_name(rating)
    if rating_name:
        rows.append(("rating", rating_name))
    for tag in payload.get("character_tags") or []:
        name = _tag_name(tag)
        if name:
            rows.append(("character", name))
    for tag in payload.get("tags") or []:
        name = _tag_name(tag)
        if name:
            rows.append(("general", name))
    return rows


def _item_exists(conn: sqlite3.Connection, item_hash: str) -> bool:
    row = conn.execute("SELECT 1 FROM items WHERE hash = ?", (item_hash,)).fetchone()
    return row is not None


def reindex_item_metadata(conn: sqlite3.Connection, item_hash: str) -> dict:
    ensure_metadata_schema(conn)
    if not _item_exists(conn, item_hash):
        return {"item_hash": item_hash, "status": "missing_item"}

    sigs = _current_sigs(item_hash)
    frontmatter, error = _load_frontmatter(item_hash)
    topics = normalize_topic_list(frontmatter.get("topics")) if not error else []
    wd_payload = _wd_payload(item_hash, frontmatter) if not error else {"status": "missing"}
    wd_rows = _wd_rows(wd_payload)
    status = "error" if error else "ok"

    if not error:
        if "artist" in frontmatter:
            conn.execute("UPDATE items SET source_artist = ? WHERE hash = ?", (str(frontmatter.get("artist") or ""), item_hash))
        if "date_added" in frontmatter and str(frontmatter.get("date_added") or "").strip():
            conn.execute("UPDATE items SET date_added = ? WHERE hash = ?", (str(frontmatter.get("date_added")).strip(), item_hash))

    conn.execute("DELETE FROM item_topics WHERE item_hash = ?", (item_hash,))
    conn.execute("DELETE FROM item_wd_tags WHERE item_hash = ?", (item_hash,))
    for topic in topics:
        topic_norm = _norm(topic)
        if topic_norm:
            conn.execute(
                "INSERT OR IGNORE INTO item_topics(item_hash, topic, topic_norm) VALUES (?, ?, ?)",
                (item_hash, topic, topic_norm),
            )
    for tag_type, tag in wd_rows:
        tag_norm = _norm(tag)
        if tag_norm:
            conn.execute(
                """
                INSERT OR IGNORE INTO item_wd_tags(item_hash, tag, tag_norm, tag_type)
                VALUES (?, ?, ?, ?)
                """,
                (item_hash, tag, tag_norm, tag_type),
            )

    conn.execute(
        """
        INSERT INTO item_metadata_files(
            item_hash, note_path, note_mtime_ns, note_size,
            wd_path, wd_mtime_ns, wd_size, indexed_at, status, error
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(item_hash) DO UPDATE SET
            note_path = excluded.note_path,
            note_mtime_ns = excluded.note_mtime_ns,
            note_size = excluded.note_size,
            wd_path = excluded.wd_path,
            wd_mtime_ns = excluded.wd_mtime_ns,
            wd_size = excluded.wd_size,
            indexed_at = excluded.indexed_at,
            status = excluded.status,
            error = excluded.error
        """,
        (
            item_hash,
            sigs["note_path"],
            sigs["note_mtime_ns"],
            sigs["note_size"],
            sigs["wd_path"],
            sigs["wd_mtime_ns"],
            sigs["wd_size"],
            _now(),
            status,
            error,
        ),
    )
    if error:
        log_system("WARNING", "Metadata index parse failed", hash=item_hash, error=error)
    return {
        "item_hash": item_hash,
        "status": status,
        "topics": len(topics),
        "wd_tags": len(wd_rows),
        "error": error,
    }


def mark_metadata_index_error(conn: sqlite3.Connection, item_hash: str, error: str):
    ensure_metadata_schema(conn)
    sigs = _current_sigs(item_hash)
    conn.execute(
        """
        INSERT INTO item_metadata_files(
            item_hash, note_path, note_mtime_ns, note_size,
            wd_path, wd_mtime_ns, wd_size, indexed_at, status, error
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'error', ?)
        ON CONFLICT(item_hash) DO UPDATE SET
            note_path = excluded.note_path,
            note_mtime_ns = excluded.note_mtime_ns,
            note_size = excluded.note_size,
            wd_path = excluded.wd_path,
            wd_mtime_ns = excluded.wd_mtime_ns,
            wd_size = excluded.wd_size,
            indexed_at = excluded.indexed_at,
            status = excluded.status,
            error = excluded.error
        """,
        (
            item_hash,
            sigs["note_path"],
            sigs["note_mtime_ns"],
            sigs["note_size"],
            sigs["wd_path"],
            sigs["wd_mtime_ns"],
            sigs["wd_size"],
            _now(),
            str(error),
        ),
    )


def safe_reindex_item_metadata(conn: sqlite3.Connection, item_hash: str, context: str = "") -> dict:
    try:
        return reindex_item_metadata(conn, item_hash)
    except Exception as exc:
        try:
            mark_metadata_index_error(conn, item_hash, str(exc))
        except Exception:
            pass
        log_system("WARNING", "Metadata index update failed", hash=item_hash, context=context, error=str(exc))
        return {"item_hash": item_hash, "status": "error", "error": str(exc)}


def _row_stale(row) -> bool:
    item_hash = row[0]
    if row[1] is None:
        return True
    sigs = _current_sigs(item_hash)
    sig_changed = (
        row[2] != sigs["note_path"]
        or row[3] != sigs["note_mtime_ns"]
        or row[4] != sigs["note_size"]
        or row[5] != sigs["wd_path"]
        or row[6] != sigs["wd_mtime_ns"]
        or row[7] != sigs["wd_size"]
    )
    if row[8] != "ok":
        return sig_changed
    return sig_changed


def stale_metadata_hashes(conn: sqlite3.Connection, limit: int | None = None) -> list[str]:
    ensure_metadata_schema(conn)
    cursor = conn.execute("""
        SELECT
            items.hash,
            item_metadata_files.item_hash,
            item_metadata_files.note_path,
            item_metadata_files.note_mtime_ns,
            item_metadata_files.note_size,
            item_metadata_files.wd_path,
            item_metadata_files.wd_mtime_ns,
            item_metadata_files.wd_size,
            item_metadata_files.status
        FROM items
        LEFT JOIN item_metadata_files ON item_metadata_files.item_hash = items.hash
        ORDER BY items.date_added DESC
    """)
    stale = []
    for row in cursor:
        if _row_stale(row):
            stale.append(row[0])
            if limit and len(stale) >= limit:
                break
    return stale


def stale_metadata_count(conn: sqlite3.Connection) -> int:
    ensure_metadata_schema(conn)
    cursor = conn.execute("""
        SELECT
            items.hash,
            item_metadata_files.item_hash,
            item_metadata_files.note_path,
            item_metadata_files.note_mtime_ns,
            item_metadata_files.note_size,
            item_metadata_files.wd_path,
            item_metadata_files.wd_mtime_ns,
            item_metadata_files.wd_size,
            item_metadata_files.status
        FROM items
        LEFT JOIN item_metadata_files ON item_metadata_files.item_hash = items.hash
        ORDER BY items.date_added DESC
    """)
    return sum(1 for row in cursor if _row_stale(row))


def reindex_stale_metadata_batch(conn: sqlite3.Connection, limit: int = REPAIR_BATCH_SIZE) -> dict:
    ensure_metadata_schema(conn)
    started = time.perf_counter()
    hashes = stale_metadata_hashes(conn, limit=limit)
    ok = 0
    errors = 0
    for item_hash in hashes:
        result = safe_reindex_item_metadata(conn, item_hash, "stale_batch")
        if result.get("status") == "error":
            errors += 1
        elif result.get("status") != "missing_item":
            ok += 1
    if len(hashes) < limit:
        _set_metadata_index_ready(conn, True)
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    log_system(
        "INFO",
        "Metadata index stale batch repaired",
        queued=len(hashes),
        indexed=ok,
        errors=errors,
        duration_ms=duration_ms,
    )
    return {"queued": len(hashes), "indexed": ok, "errors": errors, "duration_ms": duration_ms}


def metadata_index_status(conn: sqlite3.Connection) -> dict:
    ensure_metadata_schema(conn)
    item_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    indexed_count = conn.execute("SELECT COUNT(*) FROM item_metadata_files").fetchone()[0]
    error_count = conn.execute("SELECT COUNT(*) FROM item_metadata_files WHERE status = 'error'").fetchone()[0]
    topic_count = conn.execute("SELECT COUNT(*) FROM item_topics").fetchone()[0]
    wd_count = conn.execute("SELECT COUNT(*) FROM item_wd_tags").fetchone()[0]
    stale_count = stale_metadata_count(conn)
    return {
        "ready": metadata_index_ready(conn),
        "repair_running": _repair_running,
        "items": item_count,
        "indexed": indexed_count,
        "stale": stale_count,
        "errors": error_count,
        "topics": topic_count,
        "wd_tags": wd_count,
    }


def _repair_worker(full: bool = False):
    global _repair_running
    try:
        from db.sqlite_operator import init_database

        conn = init_database()
        try:
            ensure_metadata_schema(conn)
            if full:
                _set_metadata_index_ready(conn, False)
                conn.execute("DELETE FROM item_topics")
                conn.execute("DELETE FROM item_wd_tags")
                conn.execute("DELETE FROM item_metadata_files")
                conn.commit()
            log_system("INFO", "Metadata index repair started", full=full)
            while True:
                result = reindex_stale_metadata_batch(conn, REPAIR_BATCH_SIZE)
                conn.commit()
                if result["queued"] < REPAIR_BATCH_SIZE:
                    break
            log_system("INFO", "Metadata index repair finished", full=full)
        finally:
            conn.close()
    except Exception as exc:
        log_system("WARNING", "Metadata index repair failed", full=full, error=str(exc))
    finally:
        with _repair_lock:
            _repair_running = False


def start_metadata_repair_worker(full: bool = False) -> dict:
    global _repair_running
    with _repair_lock:
        if _repair_running:
            return {"status": "already_running"}
        _repair_running = True
        thread = threading.Thread(target=_repair_worker, args=(full,), name="lmz-metadata-index-repair", daemon=True)
        thread.start()
    return {"status": "started", "full": full}


def _hash_from_metadata_path(path: str | Path) -> str | None:
    path = Path(path)
    if path.name.startswith("lmztmp-") or path.suffix == ".tmp":
        return None
    if path.suffix.lower() not in {".md", ".json"}:
        return None
    item_hash = path.stem
    if HASH_RE.match(item_hash):
        return item_hash
    try:
        if DB_PATH.exists():
            with sqlite3.connect(DB_PATH, timeout=5) as conn:
                row = conn.execute("SELECT hash FROM items WHERE storage_id = ?", (item_hash,)).fetchone()
                if row:
                    return row[0]
    except sqlite3.Error:
        return None
    return None


def _watchdog_flush():
    global _watchdog_timer
    with _watchdog_lock:
        hashes = sorted(_watchdog_pending)
        _watchdog_pending.clear()
        _watchdog_timer = None
    if not hashes:
        return
    try:
        from db.sqlite_operator import init_database

        conn = init_database()
        try:
            for item_hash in hashes:
                safe_reindex_item_metadata(conn, item_hash, "watchdog")
            conn.commit()
            log_system("INFO", "Metadata watchdog reindexed changes", count=len(hashes))
        finally:
            conn.close()
    except Exception as exc:
        log_system("WARNING", "Metadata watchdog reindex failed", error=str(exc))


def _watchdog_queue_hashes(hashes: Iterable[str]):
    global _watchdog_timer
    with _watchdog_lock:
        for item_hash in hashes:
            if HASH_RE.match(item_hash):
                _watchdog_pending.add(item_hash)
        if _watchdog_timer is None:
            _watchdog_timer = threading.Timer(0.5, _watchdog_flush)
            _watchdog_timer.daemon = True
            _watchdog_timer.start()


def start_metadata_watchdog() -> dict:
    global _watchdog_observer
    with _watchdog_lock:
        if _watchdog_observer is not None:
            return {"status": "already_running"}
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except Exception as exc:
            log_system("WARNING", "Metadata watchdog unavailable", error=str(exc))
            return {"status": "unavailable", "error": str(exc)}

        class MetadataEventHandler(FileSystemEventHandler):
            def on_any_event(self, event):
                paths = [getattr(event, "src_path", "")]
                dest_path = getattr(event, "dest_path", "")
                if dest_path:
                    paths.append(dest_path)
                hashes = [item_hash for item_hash in (_hash_from_metadata_path(path) for path in paths) if item_hash]
                if hashes:
                    _watchdog_queue_hashes(hashes)

        observer = Observer()
        observer.daemon = True
        handler = MetadataEventHandler()
        NOTES_DIR.mkdir(parents=True, exist_ok=True)
        WD_TAGS_DIR.mkdir(parents=True, exist_ok=True)
        observer.schedule(handler, str(NOTES_DIR), recursive=True)
        observer.schedule(handler, str(WD_TAGS_DIR), recursive=True)
        observer.start()
        _watchdog_observer = observer
        log_system("INFO", "Metadata watchdog started", notes=str(NOTES_DIR), wd_tags=str(WD_TAGS_DIR))
        return {"status": "started"}


def metadata_facets(conn: sqlite3.Connection, kind: str, needle: str, limit: int) -> list[dict]:
    ensure_metadata_schema(conn)
    table = "item_topics" if kind == "topic" else "item_wd_tags"
    value_column = "topic" if kind == "topic" else "tag"
    norm_column = "topic_norm" if kind == "topic" else "tag_norm"
    sql = f"""
        SELECT MIN({value_column}) AS value, COUNT(DISTINCT item_hash) AS count
        FROM {table}
        WHERE (? = '' OR {norm_column} LIKE ?)
        GROUP BY {norm_column}
    """
    rows = conn.execute(sql, (needle, f"%{needle}%")).fetchall()
    items = [{"value": row[0], "count": row[1]} for row in rows if row[0]]
    items.sort(
        key=lambda item: (
            0 if needle and item["value"].casefold().startswith(needle) else 1,
            -item["count"],
            item["value"].casefold(),
        )
    )
    return items[:limit]


def indexed_item_metadata(conn: sqlite3.Connection, item_hash: str) -> dict:
    ensure_metadata_schema(conn)
    row = conn.execute("""
        SELECT
            items.hash,
            item_metadata_files.item_hash,
            item_metadata_files.note_path,
            item_metadata_files.note_mtime_ns,
            item_metadata_files.note_size,
            item_metadata_files.wd_path,
            item_metadata_files.wd_mtime_ns,
            item_metadata_files.wd_size,
            item_metadata_files.status
        FROM items
        LEFT JOIN item_metadata_files ON item_metadata_files.item_hash = items.hash
        WHERE items.hash = ?
    """, (item_hash,)).fetchone()
    if row is None:
        return {"topics": [], "wd_data": {"status": "missing"}}
    if _row_stale(row):
        safe_reindex_item_metadata(conn, item_hash, "detail_refresh")
        conn.commit()
    topics = [
        row[0]
        for row in conn.execute("SELECT topic FROM item_topics WHERE item_hash = ? ORDER BY topic", (item_hash,)).fetchall()
    ]
    tag_rows = conn.execute(
        "SELECT tag_type, tag FROM item_wd_tags WHERE item_hash = ? ORDER BY tag_type, tag",
        (item_hash,),
    ).fetchall()
    rating = {}
    characters = []
    tags = []
    for tag_type, tag in tag_rows:
        if tag_type == "rating" and not rating:
            rating = {"label": tag}
        elif tag_type == "character":
            characters.append({"name": tag})
        else:
            tags.append({"name": tag})
    wd_data = {
        "status": "ok" if rating or characters or tags else "missing",
        "source": "metadata_index",
        "rating": rating,
        "character_tags": characters,
        "tags": tags,
    }
    return {"topics": topics, "wd_data": wd_data}
