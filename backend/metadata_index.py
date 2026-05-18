import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Iterable

import yaml

from logger import log_system
from md_generator import normalize_topic_list
from tagging import load_tag_cache
from utils import NOTES_DIR, WD_TAGS_DIR, note_path_for, wd_tag_cache_path_for, utc_now_str


READY_KEY = "initial_backfill_complete"
COUNTERS_READY_KEY = "metadata_counters_ready"
COUNTER_KEYS = {
    "indexed": "counter:indexed",
    "errors": "counter:errors",
    "topics": "counter:topics",
    "wd_tags": "counter:wd_tags",
    "facet_counts": "counter:facet_counts",
    "dirty": "counter:dirty",
}
REPAIR_BATCH_SIZE = 500
FULL_REBUILD_BATCH_SIZE = 2500
WD_FRONTMATTER_FIELDS = ("wd_rating", "wd_character_tags", "wd_tags")
METADATA_SECONDARY_INDEXES = {
    "idx_item_topics_norm": "CREATE INDEX IF NOT EXISTS idx_item_topics_norm ON item_topics(topic_norm)",
    "idx_item_topics_hash": "CREATE INDEX IF NOT EXISTS idx_item_topics_hash ON item_topics(item_hash)",
    "idx_item_wd_tags_norm": "CREATE INDEX IF NOT EXISTS idx_item_wd_tags_norm ON item_wd_tags(tag_norm)",
    "idx_item_wd_tags_hash": "CREATE INDEX IF NOT EXISTS idx_item_wd_tags_hash ON item_wd_tags(item_hash)",
    "idx_item_metadata_status": "CREATE INDEX IF NOT EXISTS idx_item_metadata_status ON item_metadata_files(status)",
}

_repair_lock = threading.Lock()
_repair_running = False
_watchdog_lock = threading.Lock()
_watchdog_observer = None
_watchdog_pending: set[str] = set()
_watchdog_timer: threading.Timer | None = None
_watchdog_storage_map: dict[str, str] = {}
_watchdog_storage_map_lock = threading.Lock()


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
            storage_id TEXT,
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
    columns = {row[1] for row in cursor.execute("PRAGMA table_info(item_metadata_files)").fetchall()}
    if "storage_id" not in columns:
        cursor.execute("ALTER TABLE item_metadata_files ADD COLUMN storage_id TEXT")
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metadata_facet_counts (
            kind TEXT NOT NULL,
            value_norm TEXT NOT NULL,
            value TEXT NOT NULL,
            count INTEGER NOT NULL,
            PRIMARY KEY(kind, value_norm)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metadata_dirty_queue (
            item_hash TEXT PRIMARY KEY,
            reason TEXT NOT NULL,
            queued_at TEXT NOT NULL,
            FOREIGN KEY(item_hash) REFERENCES items(hash) ON DELETE CASCADE
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_metadata_facet_counts_kind_count ON metadata_facet_counts(kind, count DESC, value_norm)")
    _create_metadata_secondary_indexes(conn)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_metadata_dirty_queue_queued_at ON metadata_dirty_queue(queued_at)")


def _create_metadata_secondary_indexes(conn: sqlite3.Connection):
    for sql in METADATA_SECONDARY_INDEXES.values():
        conn.execute(sql)


def _drop_metadata_secondary_indexes(conn: sqlite3.Connection):
    for name in METADATA_SECONDARY_INDEXES:
        conn.execute(f"DROP INDEX IF EXISTS {name}")


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


def _set_state(conn: sqlite3.Connection, key: str, value: str | int):
    conn.execute(
        """
        INSERT INTO metadata_index_state(key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, str(value)),
    )


def _state_int(conn: sqlite3.Connection, key: str) -> int | None:
    row = conn.execute("SELECT value FROM metadata_index_state WHERE key = ?", (key,)).fetchone()
    if row is None:
        return None
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return None


def _counters_ready(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT value FROM metadata_index_state WHERE key = ?", (COUNTERS_READY_KEY,)).fetchone()
    return bool(row and row[0] == "1")


def _set_counter(conn: sqlite3.Connection, name: str, value: int):
    _set_state(conn, COUNTER_KEYS[name], max(0, int(value or 0)))


def _adjust_counter(conn: sqlite3.Connection, name: str, delta: int):
    current = _state_int(conn, COUNTER_KEYS[name])
    if current is None:
        current = 0
    _set_counter(conn, name, current + int(delta or 0))


def refresh_metadata_index_counters(conn: sqlite3.Connection) -> dict:
    ensure_metadata_schema(conn)
    counters = {
        "indexed": conn.execute("SELECT COUNT(*) FROM item_metadata_files").fetchone()[0],
        "errors": conn.execute("SELECT COUNT(*) FROM item_metadata_files WHERE status = 'error'").fetchone()[0],
        "topics": conn.execute("SELECT COUNT(*) FROM item_topics").fetchone()[0],
        "wd_tags": conn.execute("SELECT COUNT(*) FROM item_wd_tags").fetchone()[0],
        "facet_counts": conn.execute("SELECT COUNT(*) FROM metadata_facet_counts").fetchone()[0],
        "dirty": conn.execute("SELECT COUNT(*) FROM metadata_dirty_queue").fetchone()[0],
    }
    for name, value in counters.items():
        _set_counter(conn, name, value)
    _set_state(conn, COUNTERS_READY_KEY, "1")
    return counters


def _counter_snapshot(conn: sqlite3.Connection) -> dict:
    snapshot = {}
    for name, key in COUNTER_KEYS.items():
        snapshot[name] = _state_int(conn, key)
    return snapshot


def _norm(value: str) -> str:
    return str(value or "").strip().casefold()


def _now() -> str:
    return utc_now_str()


def _file_sig(path: Path) -> tuple[str, int | None, int | None]:
    try:
        stat = path.stat()
        return str(path), int(stat.st_mtime_ns), int(stat.st_size)
    except OSError:
        return str(path), None, None


def _current_sigs(item_hash: str, storage_id: str) -> dict:
    note_path = note_path_for(item_hash, storage_id)
    wd_path = wd_tag_cache_path_for(item_hash, storage_id)
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


_SIMPLE_FRONTMATTER_KEYS = {
    "title",
    "hash",
    "storage_id",
    "source_url",
    "platform",
    "source_artist",
    "artist",
    "date_added",
    "topics",
    "wd_rating",
    "wd_character_tags",
    "wd_tags",
}


def _simple_scalar(value: str) -> str | None:
    text = value.strip()
    if not text:
        return ""
    if text[0] in {"[", "{", "|", ">", "&", "*", "!"}:
        return None
    if " #" in text or "\t" in text:
        return None
    if text[0] in {"'", '"'}:
        quote = text[0]
        if len(text) < 2 or text[-1] != quote or text.count(quote) != 2:
            return None
        return text[1:-1]
    return text


def _parse_simple_frontmatter(yaml_text: str) -> dict | None:
    data: dict[str, object] = {}
    current_key = None
    current_list: list[str] | None = None
    for raw_line in yaml_text.splitlines():
        if not raw_line.strip():
            continue
        if raw_line.lstrip() != raw_line:
            stripped = raw_line.strip()
            if current_list is None or not stripped.startswith("- "):
                return None
            value = _simple_scalar(stripped[2:])
            if value is None:
                return None
            current_list.append(value)
            continue
        if raw_line.startswith("- "):
            if current_list is None:
                return None
            value = _simple_scalar(raw_line[2:])
            if value is None:
                return None
            current_list.append(value)
            continue
        if ":" not in raw_line:
            return None
        key, value = raw_line.split(":", 1)
        key = key.strip()
        if not key or key not in _SIMPLE_FRONTMATTER_KEYS:
            return None
        value = value.strip()
        current_key = key
        if not value:
            current_list = []
            data[key] = current_list
            continue
        scalar = _simple_scalar(value)
        if scalar is None:
            return None
        current_list = None
        data[current_key] = scalar
    return data


def _load_frontmatter(item_hash: str, storage_id: str, stages: dict[str, float] | None = None) -> tuple[dict, str]:
    path = note_path_for(item_hash, storage_id)
    stage_started = time.perf_counter()
    if not path.exists():
        _add_stage(stages, "frontmatter_read", stage_started)
        return {}, ""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        _add_stage(stages, "frontmatter_read", stage_started)
        return {}, str(exc)
    _add_stage(stages, "frontmatter_read", stage_started)
    stage_started = time.perf_counter()
    text = text.lstrip("\ufeff")
    if not text.startswith("---"):
        _add_stage(stages, "frontmatter_extract", stage_started)
        return {}, ""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        _add_stage(stages, "frontmatter_extract", stage_started)
        return {}, ""
    end_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = index
            break
    if end_index is None:
        _add_stage(stages, "frontmatter_extract", stage_started)
        return {}, "frontmatter terminator missing"
    yaml_text = "\n".join(lines[1:end_index])
    _add_stage(stages, "frontmatter_extract", stage_started)
    stage_started = time.perf_counter()
    simple = _parse_simple_frontmatter(yaml_text)
    _add_stage(stages, "frontmatter_fast_parse", stage_started)
    if simple is not None:
        return simple, ""
    stage_started = time.perf_counter()
    try:
        data = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError as exc:
        _add_stage(stages, "frontmatter_yaml_parse", stage_started)
        return {}, str(exc)
    _add_stage(stages, "frontmatter_yaml_parse", stage_started)
    return (data if isinstance(data, dict) else {}), ""


def _tag_name(tag) -> str:
    if isinstance(tag, str):
        return tag.strip()
    if isinstance(tag, dict):
        return str(tag.get("display_name") or tag.get("label") or tag.get("name") or "").strip()
    return ""


def _cache_wd_payload(item_hash: str, storage_id: str) -> dict:
    cache_data = load_tag_cache(item_hash, storage_id)
    if cache_data.get("status") != "ok":
        return {"status": "missing"}
    return {
        "status": "ok",
        "source": "cache",
        "rating": cache_data.get("rating") or {},
        "character_tags": cache_data.get("character_tags") or [],
        "tags": cache_data.get("tags") or [],
    }


def _wd_payload(item_hash: str, storage_id: str, frontmatter: dict) -> dict:
    has_wd_fields = any(field in frontmatter for field in WD_FRONTMATTER_FIELDS)
    cache_payload = _cache_wd_payload(item_hash, storage_id)
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


def _item_storage_id(conn: sqlite3.Connection, item_hash: str) -> str | None:
    row = conn.execute("SELECT storage_id FROM items WHERE hash = ?", (item_hash,)).fetchone()
    if row is None:
        return None
    return row[0] or ""


def _remember_watchdog_storage(item_hash: str, storage_id: str):
    if not storage_id:
        return
    with _watchdog_storage_map_lock:
        _watchdog_storage_map[storage_id] = item_hash


def rebuild_metadata_facet_counts(conn: sqlite3.Connection, ensure_schema: bool = True):
    if ensure_schema:
        ensure_metadata_schema(conn)
    conn.execute("DELETE FROM metadata_facet_counts")
    conn.execute("""
        INSERT INTO metadata_facet_counts(kind, value_norm, value, count)
        SELECT 'artist', LOWER(TRIM(source_artist)), MIN(TRIM(source_artist)), COUNT(*)
        FROM items
        WHERE source_artist IS NOT NULL AND TRIM(source_artist) != ''
        GROUP BY LOWER(TRIM(source_artist))
    """)
    conn.execute("""
        INSERT INTO metadata_facet_counts(kind, value_norm, value, count)
        SELECT 'platform', LOWER(TRIM(platform)), MIN(TRIM(platform)), COUNT(*)
        FROM items
        WHERE platform IS NOT NULL AND TRIM(platform) != ''
        GROUP BY LOWER(TRIM(platform))
    """)
    conn.execute("""
        INSERT INTO metadata_facet_counts(kind, value_norm, value, count)
        SELECT 'topic', topic_norm, MIN(topic), COUNT(*)
        FROM item_topics
        GROUP BY topic_norm
    """)
    conn.execute("""
        INSERT INTO metadata_facet_counts(kind, value_norm, value, count)
        SELECT 'wd_tag', tag_norm, MIN(tag), COUNT(DISTINCT item_hash)
        FROM item_wd_tags
        GROUP BY tag_norm
    """)
    _set_counter(conn, "facet_counts", conn.execute("SELECT COUNT(*) FROM metadata_facet_counts").fetchone()[0])


def refresh_metadata_facet_counts_for_values(conn: sqlite3.Connection, values: Iterable[tuple[str, str]]):
    ensure_metadata_schema(conn)
    cleaned = sorted({(str(kind or "").strip(), _norm(value)) for kind, value in values if _norm(value)})
    for kind, value_norm in cleaned:
        if kind == "topic":
            row = conn.execute(
                "SELECT MIN(topic), COUNT(*) FROM item_topics WHERE topic_norm = ?",
                (value_norm,),
            ).fetchone()
        elif kind == "wd_tag":
            row = conn.execute(
                "SELECT MIN(tag), COUNT(DISTINCT item_hash) FROM item_wd_tags WHERE tag_norm = ?",
                (value_norm,),
            ).fetchone()
        elif kind == "artist":
            row = conn.execute(
                """
                SELECT MIN(TRIM(source_artist)), COUNT(*)
                FROM items
                WHERE LOWER(TRIM(source_artist)) = ?
                """,
                (value_norm,),
            ).fetchone()
        elif kind == "platform":
            row = conn.execute(
                """
                SELECT MIN(TRIM(platform)), COUNT(*)
                FROM items
                WHERE LOWER(TRIM(platform)) = ?
                """,
                (value_norm,),
            ).fetchone()
        else:
            continue
        count = int(row[1] or 0) if row else 0
        if count <= 0:
            conn.execute(
                "DELETE FROM metadata_facet_counts WHERE kind = ? AND value_norm = ?",
                (kind, value_norm),
            )
            continue
        conn.execute(
            """
            INSERT INTO metadata_facet_counts(kind, value_norm, value, count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(kind, value_norm) DO UPDATE SET
                value = excluded.value,
                count = excluded.count
            """,
            (kind, value_norm, str(row[0] or value_norm), count),
        )
    if cleaned:
        _set_counter(conn, "facet_counts", conn.execute("SELECT COUNT(*) FROM metadata_facet_counts").fetchone()[0])


def _item_facet_values(conn: sqlite3.Connection, item_hash: str) -> set[tuple[str, str]]:
    values: set[tuple[str, str]] = set()
    row = conn.execute("SELECT source_artist, platform FROM items WHERE hash = ?", (item_hash,)).fetchone()
    if row:
        artist_norm = _norm(row[0])
        platform_norm = _norm(row[1])
        if artist_norm:
            values.add(("artist", artist_norm))
        if platform_norm:
            values.add(("platform", platform_norm))
    for (topic_norm,) in conn.execute("SELECT topic_norm FROM item_topics WHERE item_hash = ?", (item_hash,)).fetchall():
        if topic_norm:
            values.add(("topic", topic_norm))
    for (tag_norm,) in conn.execute("SELECT tag_norm FROM item_wd_tags WHERE item_hash = ?", (item_hash,)).fetchall():
        if tag_norm:
            values.add(("wd_tag", tag_norm))
    return values


def item_core_facet_values(conn: sqlite3.Connection, item_hash: str) -> set[tuple[str, str]]:
    ensure_metadata_schema(conn)
    row = conn.execute("SELECT source_artist, platform FROM items WHERE hash = ?", (item_hash,)).fetchone()
    if not row:
        return set()
    values = set()
    artist_norm = _norm(row[0])
    platform_norm = _norm(row[1])
    if artist_norm:
        values.add(("artist", artist_norm))
    if platform_norm:
        values.add(("platform", platform_norm))
    return values


def _item_metadata_counts(conn: sqlite3.Connection, item_hash: str) -> dict:
    row = conn.execute("SELECT status FROM item_metadata_files WHERE item_hash = ?", (item_hash,)).fetchone()
    return {
        "indexed": 1 if row else 0,
        "errors": 1 if row and row[0] == "error" else 0,
        "topics": conn.execute("SELECT COUNT(*) FROM item_topics WHERE item_hash = ?", (item_hash,)).fetchone()[0],
        "wd_tags": conn.execute("SELECT COUNT(*) FROM item_wd_tags WHERE item_hash = ?", (item_hash,)).fetchone()[0],
    }


def _apply_item_counter_delta(conn: sqlite3.Connection, before: dict, after: dict):
    if not _counters_ready(conn):
        refresh_metadata_index_counters(conn)
        return
    for name in ("indexed", "errors", "topics", "wd_tags"):
        _adjust_counter(conn, name, int(after.get(name) or 0) - int(before.get(name) or 0))


def enqueue_metadata_dirty(conn: sqlite3.Connection, item_hash: str, reason: str = "changed"):
    ensure_metadata_schema(conn)
    item_hash = str(item_hash or "").strip()
    if not item_hash:
        return
    existed = conn.execute("SELECT 1 FROM metadata_dirty_queue WHERE item_hash = ?", (item_hash,)).fetchone()
    conn.execute(
        """
        INSERT INTO metadata_dirty_queue(item_hash, reason, queued_at)
        VALUES (?, ?, ?)
        ON CONFLICT(item_hash) DO UPDATE SET
            reason = excluded.reason,
            queued_at = excluded.queued_at
        """,
        (item_hash, str(reason or "changed"), _now()),
    )
    if existed is None and _counters_ready(conn):
        _adjust_counter(conn, "dirty", 1)


def enqueue_metadata_dirty_many(conn: sqlite3.Connection, item_hashes: Iterable[str], reason: str = "changed"):
    for item_hash in item_hashes:
        enqueue_metadata_dirty(conn, item_hash, reason)


def clear_metadata_dirty(conn: sqlite3.Connection, item_hash: str):
    ensure_metadata_schema(conn)
    row = conn.execute("SELECT 1 FROM metadata_dirty_queue WHERE item_hash = ?", (item_hash,)).fetchone()
    conn.execute("DELETE FROM metadata_dirty_queue WHERE item_hash = ?", (item_hash,))
    if row is not None and _counters_ready(conn):
        _adjust_counter(conn, "dirty", -1)


def dirty_metadata_hashes(conn: sqlite3.Connection, limit: int | None = None) -> list[str]:
    ensure_metadata_schema(conn)
    sql = "SELECT item_hash FROM metadata_dirty_queue ORDER BY queued_at ASC, item_hash ASC"
    params: tuple = ()
    if limit:
        sql += " LIMIT ?"
        params = (int(limit),)
    return [row[0] for row in conn.execute(sql, params).fetchall()]


def reindex_item_metadata(conn: sqlite3.Connection, item_hash: str, update_facets: bool = True) -> dict:
    ensure_metadata_schema(conn)
    storage_id = _item_storage_id(conn, item_hash)
    if storage_id is None:
        clear_metadata_dirty(conn, item_hash)
        return {"item_hash": item_hash, "status": "missing_item"}
    if not storage_id:
        raise ValueError(f"item {item_hash} is missing storage_id")

    _remember_watchdog_storage(item_hash, storage_id)
    previous_counts = _item_metadata_counts(conn, item_hash)
    previous_facet_values = _item_facet_values(conn, item_hash) if update_facets else set()
    sigs = _current_sigs(item_hash, storage_id)
    frontmatter, error = _load_frontmatter(item_hash, storage_id)
    topics = normalize_topic_list(frontmatter.get("topics")) if not error else []
    wd_payload = _wd_payload(item_hash, storage_id, frontmatter) if not error else {"status": "missing"}
    wd_rows = _wd_rows(wd_payload)
    status = "error" if error else "ok"

    if not error:
        if "artist" in frontmatter:
            conn.execute("UPDATE items SET source_artist = ? WHERE hash = ?", (str(frontmatter.get("artist") or ""), item_hash))
        if "date_added" in frontmatter and str(frontmatter.get("date_added") or "").strip():
            conn.execute("UPDATE items SET date_added = ? WHERE hash = ?", (str(frontmatter.get("date_added")).strip(), item_hash))

    conn.execute("DELETE FROM item_topics WHERE item_hash = ?", (item_hash,))
    conn.execute("DELETE FROM item_wd_tags WHERE item_hash = ?", (item_hash,))
    topic_rows = []
    for topic in topics:
        topic_norm = _norm(topic)
        if topic_norm:
            topic_rows.append((item_hash, topic, topic_norm))
    conn.executemany(
        "INSERT OR IGNORE INTO item_topics(item_hash, topic, topic_norm) VALUES (?, ?, ?)",
        topic_rows,
    )
    wd_insert_rows = []
    for tag_type, tag in wd_rows:
        tag_norm = _norm(tag)
        if tag_norm:
            wd_insert_rows.append((item_hash, tag, tag_norm, tag_type))
    conn.executemany(
        """
        INSERT OR IGNORE INTO item_wd_tags(item_hash, tag, tag_norm, tag_type)
        VALUES (?, ?, ?, ?)
        """,
        wd_insert_rows,
    )
    if update_facets:
        current_facet_values = item_core_facet_values(conn, item_hash)
        current_facet_values.update(("topic", row[2]) for row in topic_rows)
        current_facet_values.update(("wd_tag", row[2]) for row in wd_insert_rows)
        refresh_metadata_facet_counts_for_values(conn, previous_facet_values | current_facet_values)

    conn.execute(
        """
        INSERT INTO item_metadata_files(
            item_hash, storage_id, note_path, note_mtime_ns, note_size,
            wd_path, wd_mtime_ns, wd_size, indexed_at, status, error
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(item_hash) DO UPDATE SET
            storage_id = excluded.storage_id,
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
            storage_id,
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
    clear_metadata_dirty(conn, item_hash)
    _apply_item_counter_delta(conn, previous_counts, _item_metadata_counts(conn, item_hash))
    if error:
        log_system("WARNING", "Metadata index parse failed", hash=item_hash, error=error)
    return {
        "item_hash": item_hash,
        "storage_id": storage_id,
        "status": status,
        "topics": len(topics),
        "wd_tags": len(wd_rows),
        "error": error,
    }


def mark_metadata_index_error(conn: sqlite3.Connection, item_hash: str, error: str):
    ensure_metadata_schema(conn)
    storage_id = _item_storage_id(conn, item_hash)
    if storage_id is None:
        return
    if not storage_id:
        raise ValueError(f"item {item_hash} is missing storage_id")
    _remember_watchdog_storage(item_hash, storage_id)
    sigs = _current_sigs(item_hash, storage_id)
    conn.execute(
        """
        INSERT INTO item_metadata_files(
            item_hash, storage_id, note_path, note_mtime_ns, note_size,
            wd_path, wd_mtime_ns, wd_size, indexed_at, status, error
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'error', ?)
        ON CONFLICT(item_hash) DO UPDATE SET
            storage_id = excluded.storage_id,
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
            storage_id,
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


def safe_reindex_item_metadata(
    conn: sqlite3.Connection,
    item_hash: str,
    context: str = "",
    update_facets: bool = True,
    update_dirty_queue: bool = True,
) -> dict:
    if update_dirty_queue:
        enqueue_metadata_dirty(conn, item_hash, context or "reindex")
    try:
        return reindex_item_metadata(conn, item_hash, update_facets=update_facets)
    except Exception as exc:
        try:
            mark_metadata_index_error(conn, item_hash, str(exc))
        except Exception:
            pass
        log_system("WARNING", "Metadata index update failed", hash=item_hash, context=context, error=str(exc))
        return {"item_hash": item_hash, "status": "error", "error": str(exc)}


def _row_stale(row) -> bool:
    item_hash = row[0]
    storage_id = row[1]
    indexed_hash = row[2]
    indexed_storage_id = row[3]
    if indexed_hash is None:
        return True
    if not storage_id:
        return True
    if indexed_storage_id != storage_id:
        return True
    sigs = _current_sigs(item_hash, storage_id)
    sig_changed = (
        row[4] != sigs["note_path"]
        or row[5] != sigs["note_mtime_ns"]
        or row[6] != sigs["note_size"]
        or row[7] != sigs["wd_path"]
        or row[8] != sigs["wd_mtime_ns"]
        or row[9] != sigs["wd_size"]
    )
    if row[10] != "ok":
        return sig_changed
    return sig_changed


def stale_metadata_hashes(conn: sqlite3.Connection, limit: int | None = None) -> list[str]:
    ensure_metadata_schema(conn)
    cursor = conn.execute("""
        SELECT
            items.hash,
            items.storage_id,
            item_metadata_files.item_hash,
            item_metadata_files.storage_id,
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
            items.storage_id,
            item_metadata_files.item_hash,
            item_metadata_files.storage_id,
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
    hashes = dirty_metadata_hashes(conn, limit=limit)
    source = "dirty_queue" if hashes else "stale_scan"
    if not hashes:
        hashes = stale_metadata_hashes(conn, limit=limit)
    ok = 0
    errors = 0
    for item_hash in hashes:
        result = safe_reindex_item_metadata(conn, item_hash, "stale_batch")
        if result.get("status") == "error":
            errors += 1
        elif result.get("status") != "missing_item":
            ok += 1
    dirty_remaining = bool(dirty_metadata_hashes(conn, limit=1)) if source == "dirty_queue" else False
    if source == "stale_scan" and len(hashes) < limit:
        _set_metadata_index_ready(conn, True)
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    log_system(
        "INFO",
        "Metadata index stale batch repaired",
        source=source,
        queued=len(hashes),
        indexed=ok,
        errors=errors,
        dirty_remaining=dirty_remaining,
        duration_ms=duration_ms,
    )
    return {
        "queued": len(hashes),
        "indexed": ok,
        "errors": errors,
        "dirty_remaining": dirty_remaining,
        "duration_ms": duration_ms,
        "source": source,
    }


def metadata_index_status(conn: sqlite3.Connection, deep: bool = False) -> dict:
    ensure_metadata_schema(conn)
    item_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    counters = _counter_snapshot(conn)
    indexed_count = counters["indexed"]
    error_count = counters["errors"]
    topic_count = counters["topics"]
    wd_count = counters["wd_tags"]
    facet_count = counters["facet_counts"]
    dirty_count = counters["dirty"]
    if indexed_count is None:
        indexed_count = conn.execute("SELECT COUNT(*) FROM item_metadata_files").fetchone()[0]
    if error_count is None:
        error_count = conn.execute("SELECT COUNT(*) FROM item_metadata_files WHERE status = 'error'").fetchone()[0]
    if facet_count is None:
        facet_count = conn.execute("SELECT COUNT(*) FROM metadata_facet_counts").fetchone()[0]
    stale_count = stale_metadata_count(conn) if deep else None
    return {
        "ready": metadata_index_ready(conn),
        "repair_running": _repair_running,
        "items": item_count,
        "indexed": indexed_count or 0,
        "stale": stale_count,
        "stale_deep": bool(deep),
        "errors": error_count or 0,
        "topics": topic_count or 0,
        "wd_tags": wd_count or 0,
        "facet_counts": facet_count or 0,
        "dirty": dirty_count or 0,
    }


def _add_stage(stages: dict[str, float] | None, key: str, started: float):
    if stages is not None:
        stages[key] += (time.perf_counter() - started) * 1000


def _metadata_payload(conn: sqlite3.Connection, item_hash: str, storage_id: str, stages: dict[str, float] | None = None) -> dict:
    _remember_watchdog_storage(item_hash, storage_id)
    stage_started = time.perf_counter()
    sigs = _current_sigs(item_hash, storage_id)
    _add_stage(stages, "metadata_sigs", stage_started)
    stage_started = time.perf_counter()
    frontmatter, error = _load_frontmatter(item_hash, storage_id, stages=stages)
    _add_stage(stages, "frontmatter_load_parse", stage_started)
    stage_started = time.perf_counter()
    topics = normalize_topic_list(frontmatter.get("topics")) if not error else []
    _add_stage(stages, "topic_normalize", stage_started)
    stage_started = time.perf_counter()
    wd_payload = _wd_payload(item_hash, storage_id, frontmatter) if not error else {"status": "missing"}
    _add_stage(stages, "wd_payload", stage_started)
    stage_started = time.perf_counter()
    wd_rows = _wd_rows(wd_payload)
    _add_stage(stages, "wd_rows", stage_started)
    return {
        "sigs": sigs,
        "frontmatter": frontmatter,
        "error": error,
        "topics": topics,
        "wd_rows": wd_rows,
        "status": "error" if error else "ok",
    }


def _metadata_file_row(item_hash: str, storage_id: str, payload: dict) -> tuple:
    sigs = payload["sigs"]
    return (
        item_hash,
        storage_id,
        sigs["note_path"],
        sigs["note_mtime_ns"],
        sigs["note_size"],
        sigs["wd_path"],
        sigs["wd_mtime_ns"],
        sigs["wd_size"],
        _now(),
        payload["status"],
        payload["error"],
    )


def rebuild_all_metadata(conn: sqlite3.Connection, batch_size: int = FULL_REBUILD_BATCH_SIZE, context: str = "full") -> dict:
    ensure_metadata_schema(conn)
    started = time.perf_counter()
    stages: dict[str, float] = {
        "item_fetch": 0.0,
        "metadata_read_parse": 0.0,
        "metadata_sigs": 0.0,
        "frontmatter_load_parse": 0.0,
        "frontmatter_read": 0.0,
        "frontmatter_extract": 0.0,
        "frontmatter_fast_parse": 0.0,
        "frontmatter_yaml_parse": 0.0,
        "topic_normalize": 0.0,
        "wd_payload": 0.0,
        "wd_rows": 0.0,
        "row_building": 0.0,
        "db_flushes": 0.0,
        "item_updates": 0.0,
        "metadata_file_inserts": 0.0,
        "topic_inserts": 0.0,
        "wd_tag_inserts": 0.0,
        "commits": 0.0,
        "secondary_index_drop": 0.0,
        "secondary_index_rebuild": 0.0,
        "facet_rebuild": 0.0,
        "counter_refresh": 0.0,
    }
    _set_metadata_index_ready(conn, False)
    success = False
    try:
        stage_started = time.perf_counter()
        _drop_metadata_secondary_indexes(conn)
        stages["secondary_index_drop"] += (time.perf_counter() - stage_started) * 1000

        conn.execute("DELETE FROM item_topics")
        conn.execute("DELETE FROM item_wd_tags")
        conn.execute("DELETE FROM item_metadata_files")
        conn.execute("DELETE FROM metadata_facet_counts")
        conn.execute("DELETE FROM metadata_dirty_queue")
        for name in COUNTER_KEYS:
            _set_counter(conn, name, 0)
        _set_state(conn, COUNTERS_READY_KEY, "1")

        stage_started = time.perf_counter()
        rows = conn.execute("SELECT hash, storage_id FROM items ORDER BY date_added DESC, hash DESC").fetchall()
        stages["item_fetch"] += (time.perf_counter() - stage_started) * 1000
        indexed = 0
        errors = 0
        item_updates: list[tuple[str, str]] = []
        date_updates: list[tuple[str, str]] = []
        metadata_rows: list[tuple] = []
        topic_rows: list[tuple] = []
        wd_rows: list[tuple] = []

        def flush():
            flush_started = time.perf_counter()
            if item_updates:
                sub_started = time.perf_counter()
                conn.executemany("UPDATE items SET source_artist = ? WHERE hash = ?", item_updates)
                stages["item_updates"] += (time.perf_counter() - sub_started) * 1000
                item_updates.clear()
            if date_updates:
                sub_started = time.perf_counter()
                conn.executemany("UPDATE items SET date_added = ? WHERE hash = ?", date_updates)
                stages["item_updates"] += (time.perf_counter() - sub_started) * 1000
                date_updates.clear()
            if metadata_rows:
                sub_started = time.perf_counter()
                conn.executemany(
                    """
                    INSERT INTO item_metadata_files(
                        item_hash, storage_id, note_path, note_mtime_ns, note_size,
                        wd_path, wd_mtime_ns, wd_size, indexed_at, status, error
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    metadata_rows,
                )
                stages["metadata_file_inserts"] += (time.perf_counter() - sub_started) * 1000
                metadata_rows.clear()
            if topic_rows:
                sub_started = time.perf_counter()
                conn.executemany(
                    "INSERT INTO item_topics(item_hash, topic, topic_norm) VALUES (?, ?, ?)",
                    topic_rows,
                )
                stages["topic_inserts"] += (time.perf_counter() - sub_started) * 1000
                topic_rows.clear()
            if wd_rows:
                sub_started = time.perf_counter()
                conn.executemany(
                    """
                    INSERT INTO item_wd_tags(item_hash, tag, tag_norm, tag_type)
                    VALUES (?, ?, ?, ?)
                    """,
                    wd_rows,
                )
                stages["wd_tag_inserts"] += (time.perf_counter() - sub_started) * 1000
                wd_rows.clear()
            stages["db_flushes"] += (time.perf_counter() - flush_started) * 1000

        for index, (item_hash, storage_id) in enumerate(rows, start=1):
            if not storage_id:
                errors += 1
                log_system("WARNING", "Metadata full rebuild skipped item missing storage_id", hash=item_hash, context=context)
                continue
            stage_started = time.perf_counter()
            payload = _metadata_payload(conn, item_hash, storage_id, stages=stages)
            stages["metadata_read_parse"] += (time.perf_counter() - stage_started) * 1000
            stage_started = time.perf_counter()
            frontmatter = payload["frontmatter"]
            if not payload["error"]:
                if "artist" in frontmatter:
                    item_updates.append((str(frontmatter.get("artist") or ""), item_hash))
                if "date_added" in frontmatter and str(frontmatter.get("date_added") or "").strip():
                    date_updates.append((str(frontmatter.get("date_added")).strip(), item_hash))
            seen_topics: set[str] = set()
            for topic in payload["topics"]:
                topic_norm = _norm(topic)
                if topic_norm and topic_norm not in seen_topics:
                    seen_topics.add(topic_norm)
                    topic_rows.append((item_hash, topic, topic_norm))
            seen_wd: set[tuple[str, str]] = set()
            for tag_type, tag in payload["wd_rows"]:
                tag_norm = _norm(tag)
                tag_key = (tag_norm, tag_type)
                if tag_norm and tag_key not in seen_wd:
                    seen_wd.add(tag_key)
                    wd_rows.append((item_hash, tag, tag_norm, tag_type))
            metadata_rows.append(_metadata_file_row(item_hash, storage_id, payload))
            if payload["status"] == "error":
                errors += 1
                log_system("WARNING", "Metadata index parse failed", hash=item_hash, error=payload["error"])
            else:
                indexed += 1
            stages["row_building"] += (time.perf_counter() - stage_started) * 1000
            if index % batch_size == 0:
                flush()
                commit_started = time.perf_counter()
                conn.commit()
                commit_ms = (time.perf_counter() - commit_started) * 1000
                stages["commits"] += commit_ms
                stages["db_flushes"] += commit_ms

        flush()
        stage_started = time.perf_counter()
        rebuild_metadata_facet_counts(conn, ensure_schema=False)
        stages["facet_rebuild"] += (time.perf_counter() - stage_started) * 1000
        stage_started = time.perf_counter()
        _create_metadata_secondary_indexes(conn)
        stages["secondary_index_rebuild"] += (time.perf_counter() - stage_started) * 1000
        _set_metadata_index_ready(conn, True)
        stage_started = time.perf_counter()
        counters = refresh_metadata_index_counters(conn)
        stages["counter_refresh"] += (time.perf_counter() - stage_started) * 1000
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        stages_ms = {key: round(value, 2) for key, value in stages.items()}
        success = True
        return {"indexed": indexed, "errors": errors, "duration_ms": duration_ms, "stages_ms": stages_ms, **counters}
    finally:
        if not success:
            _set_metadata_index_ready(conn, False)
            stage_started = time.perf_counter()
            _create_metadata_secondary_indexes(conn)
            stages["secondary_index_rebuild"] += (time.perf_counter() - stage_started) * 1000


def _repair_worker(full: bool = False):
    global _repair_running
    try:
        from db.sqlite_operator import init_database

        conn = init_database()
        try:
            ensure_metadata_schema(conn)
            log_system("INFO", "Metadata index repair started", full=full)
            if full:
                rebuild_all_metadata(conn, FULL_REBUILD_BATCH_SIZE, "repair_full")
                conn.commit()
            else:
                while True:
                    result = reindex_stale_metadata_batch(conn, REPAIR_BATCH_SIZE)
                    conn.commit()
                    if result.get("source") == "dirty_queue" and not result.get("dirty_remaining"):
                        continue
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


def _load_watchdog_storage_map():
    try:
        from db.sqlite_operator import init_database

        conn = init_database()
        try:
            rows = conn.execute(
                "SELECT storage_id, hash FROM items WHERE storage_id IS NOT NULL AND storage_id != ''"
            ).fetchall()
        finally:
            conn.close()
    except Exception as exc:
        log_system("WARNING", "Metadata watchdog storage map refresh failed", error=str(exc))
        return
    with _watchdog_storage_map_lock:
        _watchdog_storage_map.clear()
        _watchdog_storage_map.update({str(storage_id): item_hash for storage_id, item_hash in rows if storage_id and item_hash})


def _hash_from_metadata_path(path: str | Path) -> str | None:
    path = Path(path)
    if path.name.startswith("lmztmp-") or path.suffix == ".tmp":
        return None
    if path.suffix.lower() not in {".md", ".json"}:
        return None
    storage_id = path.stem.removesuffix("_video")
    with _watchdog_storage_map_lock:
        return _watchdog_storage_map.get(storage_id)


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
            if item_hash:
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
        _load_watchdog_storage_map()
        observer.start()
        _watchdog_observer = observer
        log_system("INFO", "Metadata watchdog started", notes=str(NOTES_DIR), wd_tags=str(WD_TAGS_DIR))
        return {"status": "started"}


def metadata_facets(conn: sqlite3.Connection, kind: str, needle: str, limit: int) -> list[dict]:
    ensure_metadata_schema(conn)
    count_rows_built = conn.execute(
        "SELECT 1 FROM metadata_facet_counts WHERE kind = ? LIMIT 1",
        (kind,),
    ).fetchone() is not None
    params: list = [kind]
    where_sql = "WHERE kind = ?"
    if needle:
        where_sql += " AND value_norm LIKE ?"
        params.append(f"%{needle}%")
    rows = conn.execute(
        f"""
        SELECT value, count
        FROM metadata_facet_counts
        {where_sql}
        ORDER BY
            CASE WHEN ? != '' AND value_norm LIKE ? THEN 0 ELSE 1 END,
            count DESC,
            value_norm ASC
        LIMIT ?
        """,
        (*params, needle, f"{needle}%", limit),
    ).fetchall()
    if rows:
        return [{"value": row[0], "count": row[1]} for row in rows if row[0]]
    if count_rows_built:
        return []

    if kind in {"artist", "platform"}:
        value_column = "source_artist" if kind == "artist" else "platform"
        norm_expr = f"LOWER(TRIM({value_column}))"
        where_sql = f" WHERE {value_column} IS NOT NULL AND TRIM({value_column}) != ''"
        params = []
        if needle:
            where_sql += f" AND {norm_expr} LIKE ?"
            params.append(f"%{needle}%")
        sql = f"""
            SELECT MIN(TRIM({value_column})) AS value, COUNT(*) AS count
            FROM items
            {where_sql}
            GROUP BY {norm_expr}
        """
    else:
        table = "item_topics" if kind == "topic" else "item_wd_tags"
        value_column = "topic" if kind == "topic" else "tag"
        norm_column = "topic_norm" if kind == "topic" else "tag_norm"
        count_expr = "COUNT(*)" if kind == "topic" else "COUNT(DISTINCT item_hash)"
        where_sql = f" WHERE {norm_column} LIKE ?" if needle else ""
        params = [f"%{needle}%"] if needle else []
        sql = f"""
            SELECT MIN({value_column}) AS value, {count_expr} AS count
            FROM {table}
            {where_sql}
            GROUP BY {norm_column}
        """
    rows = conn.execute(sql, params).fetchall()
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
            items.storage_id,
            item_metadata_files.item_hash,
            item_metadata_files.storage_id,
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
