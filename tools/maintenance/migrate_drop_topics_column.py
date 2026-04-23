import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from utils import DB_PATH


ITEM_COLUMNS = [
    "hash",
    "original_filename",
    "file_extension",
    "mime_type",
    "size_bytes",
    "date_added",
    "source_url",
    "platform",
    "source_artist",
    "phash",
    "audio_hash",
    "visual_embedding",
]


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _items_columns(conn: sqlite3.Connection) -> list[str]:
    return [row[1] for row in conn.execute("PRAGMA table_info(items)").fetchall()]


def _has_topics_column(conn: sqlite3.Connection) -> bool:
    return "topics" in _items_columns(conn)


def _backup_database(db_path: Path) -> Path:
    backup_dir = ROOT / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"liz_main_before_drop_topics_{timestamp}.db"
    conn = _connect(db_path)
    try:
        conn.execute("PRAGMA wal_checkpoint(FULL);")
    finally:
        conn.close()
    shutil.copy2(db_path, backup_path)
    for suffix in ("-wal", "-shm"):
        sidecar = db_path.with_name(db_path.name + suffix)
        if sidecar.exists():
            shutil.copy2(sidecar, backup_dir / f"{backup_path.name}{suffix}")
    return backup_path


def _migrate(conn: sqlite3.Connection):
    columns = set(_items_columns(conn))
    select_parts = []
    for column in ITEM_COLUMNS:
        if column in columns:
            select_parts.append(column)
        else:
            select_parts.append(f"NULL AS {column}")
    select_sql = ", ".join(select_parts)

    conn.execute("PRAGMA foreign_keys = OFF;")
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            """
            CREATE TABLE items_new (
                hash TEXT PRIMARY KEY,
                original_filename TEXT,
                file_extension TEXT,
                mime_type TEXT,
                size_bytes INTEGER,
                date_added DATETIME DEFAULT CURRENT_TIMESTAMP,
                source_url TEXT,
                platform TEXT,
                source_artist TEXT,
                phash TEXT,
                audio_hash BLOB,
                visual_embedding BLOB
            )
            """
        )
        conn.execute(
            f"""
            INSERT INTO items_new ({", ".join(ITEM_COLUMNS)})
            SELECT {select_sql}
            FROM items
            """
        )
        conn.execute("DROP TABLE items")
        conn.execute("ALTER TABLE items_new RENAME TO items")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_source_url ON items(source_url)")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON;")


def main():
    db_path = Path(DB_PATH)
    if not db_path.exists():
        print(f"[ERROR] Database not found: {db_path}")
        raise SystemExit(1)
    conn = _connect(db_path)
    try:
        if not _has_topics_column(conn):
            print("[OK] items.topics does not exist. No migration needed.")
            return
    finally:
        conn.close()

    backup_path = _backup_database(db_path)
    conn = _connect(db_path)
    try:
        _migrate(conn)
    finally:
        conn.close()
    for suffix in ("-wal", "-shm"):
        sidecar = db_path.with_name(db_path.name + suffix)
        if sidecar.exists():
            try:
                sidecar.unlink()
            except OSError:
                pass
    print(f"[OK] Backup created: {backup_path}")
    print(f"[OK] Removed items.topics from: {db_path}")


if __name__ == "__main__":
    main()
