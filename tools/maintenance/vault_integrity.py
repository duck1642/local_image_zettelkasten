import argparse
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import yaml

PROJECT_ROOT_PATH = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT_PATH / "backend"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from db.sqlite_operator import allocate_storage_id
from utils import ASSETS_DIR, DB_PATH, NOTES_DIR, PROJECT_ROOT, asset_path_for, note_path_for


def asset_path(file_hash: str, file_extension: str, mime_type: str = "", storage_id: str = "") -> Path:
    return asset_path_for(file_hash, file_extension, mime_type, storage_id=storage_id)


def load_notes() -> dict:
    notes = {}
    link_pattern = re.compile(r"!\[\]\((.*?)\)")

    for note_path in NOTES_DIR.rglob("*.md"):
        text = note_path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue

        parts = text.split("---", 2)
        if len(parts) < 3:
            continue

        meta = yaml.safe_load(parts[1]) or {}
        file_hash = meta.get("hash") or note_path.stem
        link_match = link_pattern.search(parts[2])
        linked_asset = None

        if link_match:
            linked_asset = (note_path.parent / link_match.group(1)).resolve()

        notes[file_hash] = {
            "path": note_path,
            "meta": meta,
            "asset": linked_asset
        }

    return notes


def load_db_rows(conn: sqlite3.Connection) -> dict:
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT hash, original_filename, file_extension, mime_type, size_bytes, date_added, source_url, platform, source_artist, phash, storage_id FROM items"
    ).fetchall()
    return {
        row[0]: {
            "hash": row[0],
            "original_filename": row[1],
            "file_extension": row[2],
            "mime_type": row[3],
            "size_bytes": row[4],
            "date_added": row[5],
            "source_url": row[6],
            "platform": row[7],
            "source_artist": row[8],
            "phash": row[9],
            "storage_id": row[10] or ""
        }
        for row in rows
    }


def collect_assets() -> dict:
    assets = {}
    for file_path in ASSETS_DIR.rglob("*"):
        if file_path.is_file():
            assets[file_path.stem] = file_path
    return assets


def build_report(conn: sqlite3.Connection) -> dict:
    db_rows = load_db_rows(conn)
    notes = load_notes()
    assets = collect_assets()

    missing_db_assets = []
    for row in db_rows.values():
        path = asset_path(row["hash"], row["file_extension"], row["mime_type"], row["storage_id"])
        if not path.exists():
            missing_db_assets.append(row)

    orphan_notes = {
        file_hash: note
        for file_hash, note in notes.items()
        if file_hash not in db_rows
    }
    orphan_assets = {
        file_hash: path
        for file_hash, path in assets.items()
        if file_hash not in db_rows and file_hash not in {row.get("storage_id") for row in db_rows.values()}
    }

    db_by_url = {}
    note_by_url = {}
    for row in db_rows.values():
        url = row.get("source_url") or ""
        if url:
            db_by_url[url] = db_by_url.get(url, 0) + 1
    for note in notes.values():
        url = note["meta"].get("source_url") or ""
        if url:
            note_by_url[url] = note_by_url.get(url, 0) + 1

    url_mismatches = {
        url: {
            "db": db_by_url.get(url, 0),
            "notes": note_by_url.get(url, 0)
        }
        for url in sorted(set(db_by_url) | set(note_by_url))
        if db_by_url.get(url, 0) != note_by_url.get(url, 0)
    }

    return {
        "db_rows": db_rows,
        "notes": notes,
        "assets": assets,
        "missing_db_assets": missing_db_assets,
        "orphan_notes": orphan_notes,
        "orphan_assets": orphan_assets,
        "url_mismatches": url_mismatches
    }


def matching_orphan(row: dict, report: dict):
    for file_hash, note in report["orphan_notes"].items():
        asset = note.get("asset")
        meta = note["meta"]

        if not asset or not asset.exists():
            continue
        if file_hash not in report["orphan_assets"]:
            continue
        if meta.get("source_url", "") != row.get("source_url", ""):
            continue
        if meta.get("filename", "") != row.get("original_filename", ""):
            continue
        if meta.get("file_format", "") != row.get("mime_type", ""):
            continue
        if asset.stat().st_size != row.get("size_bytes"):
            continue

        return file_hash, note

    return None


def backup_db() -> Path:
    BACKUPS_DIR = PROJECT_ROOT / "backups"
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUPS_DIR / f"lmz_main_{stamp}.db"
    shutil.copy2(DB_PATH, backup_path)
    return backup_path


def insert_note_row(conn: sqlite3.Connection, file_hash: str, note: dict):
    asset = note["asset"]
    meta = note["meta"]
    cursor = conn.cursor()
    storage_id = str(note["path"].stem or "")
    existing = cursor.execute("SELECT hash FROM items WHERE storage_id = ?", (storage_id,)).fetchone()
    if not storage_id or (existing and existing[0] != file_hash):
        storage_id = allocate_storage_id(conn)
    cursor.execute(
        "INSERT OR REPLACE INTO items "
        "(hash, storage_id, original_filename, file_extension, mime_type, size_bytes, date_added, source_url, platform, source_artist, phash, audio_hash, visual_embedding) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            file_hash,
            storage_id,
            meta.get("filename", asset.name),
            asset.suffix.lower(),
            meta.get("file_format", ""),
            asset.stat().st_size,
            meta.get("date_added", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            meta.get("source_url", ""),
            meta.get("platform", ""),
            meta.get("artist", ""),
            meta.get("phash", ""),
            None,
            None
        )
    )


def repair(conn: sqlite3.Connection, report: dict) -> dict:
    restored = 0
    removed = 0
    matched_orphans = set()

    for row in report["missing_db_assets"]:
        note_path = note_path_for(row["hash"], row.get("storage_id"))
        if note_path.exists():
            continue

        match = matching_orphan(row, report)
        if not match:
            continue

        file_hash, note = match
        conn.execute("DELETE FROM items WHERE hash = ?", (row["hash"],))
        insert_note_row(conn, file_hash, note)
        matched_orphans.add(file_hash)
        removed += 1
        restored += 1

    for file_hash, note in report["orphan_notes"].items():
        if file_hash in matched_orphans:
            continue
        asset = note.get("asset")
        if not asset or not asset.exists():
            continue
        if file_hash not in report["orphan_assets"]:
            continue
        insert_note_row(conn, file_hash, note)
        restored += 1

    conn.commit()
    return {"restored": restored, "removed": removed}


def print_report(report: dict):
    print(f"DB rows: {len(report['db_rows'])}")
    print(f"Assets: {len(report['assets'])}")
    print(f"Notes: {len(report['notes'])}")
    print(f"DB rows with missing assets: {len(report['missing_db_assets'])}")
    print(f"Notes without DB rows: {len(report['orphan_notes'])}")
    print(f"Assets without DB rows: {len(report['orphan_assets'])}")
    print(f"Source URL count mismatches: {len(report['url_mismatches'])}")

    for row in report["missing_db_assets"]:
        print(f"MISSING_ASSET {row['hash']} {row['source_url']}")

    for file_hash, note in report["orphan_notes"].items():
        source_url = note["meta"].get("source_url", "")
        print(f"ORPHAN_NOTE {file_hash} {source_url}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    try:
        report = build_report(conn)
        print_report(report)

        if args.apply:
            backup_path = backup_db()
            result = repair(conn, report)
            print(f"Backup: {backup_path}")
            print(f"Restored rows: {result['restored']}")
            print(f"Removed stale rows: {result['removed']}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
