
import sqlite3
from pathlib import Path
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from utils import DB_PATH


def normalize_source_url(url: str) -> str:

    if not url:
        return ""
    raw = str(url).strip()
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return raw.lower()
    scheme = (parsed.scheme or "https").lower()
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    return urlunsplit((scheme, host, path, query, ""))

def init_database():

    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute('PRAGMA journal_mode=WAL;')
    cursor.execute('PRAGMA foreign_keys = ON;')


    cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            hash TEXT PRIMARY KEY,
            original_filename TEXT,
            file_extension TEXT,
            mime_type TEXT,
            size_bytes INTEGER,
            date_added DATETIME DEFAULT CURRENT_TIMESTAMP,
            source_url TEXT,
            source_url_norm TEXT,
            platform TEXT,
            source_artist TEXT,
            phash TEXT,
            audio_hash BLOB,
            visual_embedding BLOB,
            width INTEGER,
            height INTEGER
        )
    ''')


    cursor.execute('''
        CREATE TABLE IF NOT EXISTS item_tiles (
            parent_hash TEXT,
            tile_index INTEGER,
            tile_phash TEXT,
            UNIQUE(parent_hash, tile_index),
            FOREIGN KEY(parent_hash) REFERENCES items(hash) ON DELETE CASCADE
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tile_phash ON item_tiles(tile_phash)')


    cursor.execute('CREATE INDEX IF NOT EXISTS idx_source_url ON items(source_url)')


    cursor.execute("PRAGMA table_info(items)")
    columns = [row[1] for row in cursor.fetchall()]

    if 'audio_hash' not in columns:
        cursor.execute("ALTER TABLE items ADD COLUMN audio_hash BLOB")
    if 'visual_embedding' not in columns:
        cursor.execute("ALTER TABLE items ADD COLUMN visual_embedding BLOB")
    if 'width' not in columns:
        cursor.execute("ALTER TABLE items ADD COLUMN width INTEGER")
    if 'height' not in columns:
        cursor.execute("ALTER TABLE items ADD COLUMN height INTEGER")
    if 'source_url_norm' not in columns:
        cursor.execute("ALTER TABLE items ADD COLUMN source_url_norm TEXT")

    cursor.execute('SELECT hash, source_url FROM items WHERE source_url IS NOT NULL AND source_url != "" AND (source_url_norm IS NULL OR source_url_norm = "")')
    rows = cursor.fetchall()
    cursor.executemany(
        'UPDATE items SET source_url_norm = ? WHERE hash = ?',
        [(normalize_source_url(source_url), file_hash) for file_hash, source_url in rows]
    )
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_source_url_norm ON items(source_url_norm)')

    conn.commit()
    return conn

def check_duplicate_hash(conn: sqlite3.Connection, file_hash: str) -> bool:

    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM items WHERE hash = ?', (file_hash,))
    return cursor.fetchone() is not None

def get_all_phashes(conn: sqlite3.Connection) -> list[tuple[str, str]]:

    cursor = conn.cursor()
    cursor.execute('SELECT hash, phash FROM items WHERE phash IS NOT NULL AND phash != ""')
    return cursor.fetchall()

def get_all_urls(conn: sqlite3.Connection) -> list[str]:

    cursor = conn.cursor()
    cursor.execute('SELECT source_url FROM items WHERE source_url IS NOT NULL AND source_url != ""')
    return [row[0] for row in cursor.fetchall()]

def get_all_tiles(conn: sqlite3.Connection) -> list[tuple[str, int, str]]:

    cursor = conn.cursor()
    cursor.execute('SELECT parent_hash, tile_index, tile_phash FROM item_tiles')
    return cursor.fetchall()

def insert_tiles(conn: sqlite3.Connection, parent_hash: str, tiles: list[tuple[int, str]]):

    if not tiles:
        return

    cursor = conn.cursor()

    cursor.execute('DELETE FROM item_tiles WHERE parent_hash = ?', (parent_hash,))

    cursor.executemany('''
        INSERT INTO item_tiles (parent_hash, tile_index, tile_phash)
        VALUES (?, ?, ?)
    ''', [(parent_hash, index, phash) for index, phash in tiles])

def get_all_video_signatures(conn: sqlite3.Connection) -> list[tuple[str, bytes, bytes]]:

    cursor = conn.cursor()
    cursor.execute('SELECT hash, audio_hash, visual_embedding FROM items WHERE audio_hash IS NOT NULL OR visual_embedding IS NOT NULL')
    return cursor.fetchall()

def reset_database():

    conn = sqlite3.connect(DB_PATH, timeout=5)
    try:
        cursor = conn.cursor()
        cursor.execute('PRAGMA foreign_keys = ON;')
        cursor.execute('BEGIN IMMEDIATE')
        cursor.execute('DROP TABLE IF EXISTS item_tiles')
        cursor.execute('DROP TABLE IF EXISTS items')
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    with init_database() as conn:
        conn.commit()

def check_duplicate_url(conn: sqlite3.Connection, url: str) -> bool:

    if not url: return False
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM items WHERE source_url_norm = ?', (normalize_source_url(url),))
    return cursor.fetchone() is not None

def insert_to_database(conn: sqlite3.Connection, filepath: Path, file_hash: str, mime_type: str, target_ext: str, metadata: dict = None, file_size: int = None, timestamp: datetime = None, phash: str = None, audio_hash: bytes = None, visual_embedding: bytes = None, width: int = None, height: int = None):
    metadata = metadata or {}
    source_url = metadata.get('source_url', "")
    source_url_norm = normalize_source_url(source_url)
    platform = metadata.get('platform', "")
    source_artist = metadata.get('artist', "")

    if file_size is None:
        file_size = filepath.stat().st_size

    if timestamp is None:
        timestamp = datetime.now()

    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO items
        (hash, original_filename, file_extension, mime_type, size_bytes, date_added, source_url, source_url_norm, platform, source_artist, phash, audio_hash, visual_embedding, width, height)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(hash) DO UPDATE SET
            original_filename = excluded.original_filename,
            file_extension = excluded.file_extension,
            mime_type = excluded.mime_type,
            size_bytes = excluded.size_bytes,
            date_added = excluded.date_added,
            source_url = excluded.source_url,
            source_url_norm = excluded.source_url_norm,
            platform = excluded.platform,
            source_artist = excluded.source_artist,
            phash = excluded.phash,
            audio_hash = excluded.audio_hash,
            visual_embedding = excluded.visual_embedding,
            width = excluded.width,
            height = excluded.height
    ''', (
        file_hash,
        filepath.name,
        target_ext,
        mime_type,
        file_size,
        timestamp,
        source_url,
        source_url_norm,
        platform,
        source_artist,
        phash,
        audio_hash,
        visual_embedding,
        width,
        height
    ))
