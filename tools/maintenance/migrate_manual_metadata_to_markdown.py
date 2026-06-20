import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "backend"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from runtime_context import get_runtime_context, has_runtime_context
from utils import atomic_write_text, note_path_for
import utils


def split_frontmatter(text: str):
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    return parts[1], parts[2]


def backup_notes() -> Path:
    backup_root = get_runtime_context().root / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_root / f"notes_before_manual_metadata_migration_{stamp}"
    suffix = 1
    while backup_path.exists():
        suffix += 1
        backup_path = backup_root / f"notes_before_manual_metadata_migration_{stamp}_{suffix}"
    if utils.NOTES_DIR.exists():
        shutil.copytree(utils.NOTES_DIR, backup_path / "notes")
    else:
        (backup_path / "notes").mkdir(parents=True, exist_ok=True)
    return backup_path


def load_db_rows(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT hash, storage_id, source_artist, date_added FROM items ORDER BY date_added DESC, hash DESC"
    ).fetchall()
    return [
        {"hash": row[0], "storage_id": row[1] or "", "artist": row[2] or "", "date_added": row[3] or ""}
        for row in rows
    ]


def migrate_note(row: dict, apply: bool) -> str:
    note_path = note_path_for(row["hash"], row["storage_id"])
    if not note_path.exists():
        return "missing_note"
    text = note_path.read_text(encoding="utf-8")
    parts = split_frontmatter(text.lstrip("\ufeff"))
    if not parts:
        return "invalid_frontmatter"
    raw_frontmatter, body = parts
    data = yaml.safe_load(raw_frontmatter) or {}
    if not isinstance(data, dict):
        return "invalid_frontmatter"

    changed = False
    if "artist" not in data:
        data["artist"] = row["artist"]
        changed = True
    if "date_added" not in data and row["date_added"]:
        data["date_added"] = row["date_added"]
        changed = True

    if not changed:
        return "unchanged"

    if apply:
        rendered = yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
        atomic_write_text(note_path, f"---\n{rendered}---{body}")
    return "changed"


def run(apply: bool) -> dict:
    results = {
        "items": 0,
        "changed": 0,
        "unchanged": 0,
        "missing_note": 0,
        "invalid_frontmatter": 0,
        "errors": 0,
        "backup": "",
    }
    if apply:
        results["backup"] = str(backup_notes())

    conn = sqlite3.connect(utils.DB_PATH)
    try:
        rows = load_db_rows(conn)
    finally:
        conn.close()

    for row in rows:
        results["items"] += 1
        try:
            status = migrate_note(row, apply)
            if status == "changed":
                results["changed"] += 1
            elif status == "unchanged":
                results["unchanged"] += 1
            elif status == "missing_note":
                results["missing_note"] += 1
            else:
                results["invalid_frontmatter"] += 1
            print(f"{status.upper()} {row['hash']}")
        except Exception as exc:
            results["errors"] += 1
            error = str(exc).encode("ascii", errors="backslashreplace").decode("ascii")
            print(f"ERROR {row['hash']} {error}")
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if not has_runtime_context():
        from scripts.workspace_select import select_runtime_context
        select_runtime_context("migrate_manual_metadata_to_markdown")

    results = run(args.apply)
    mode = "APPLY" if args.apply else "DRY-RUN"
    if results["backup"]:
        print(f"Backup: {results['backup']}")
    print(
        f"{mode} items={results['items']} changed={results['changed']} "
        f"unchanged={results['unchanged']} missing_note={results['missing_note']} "
        f"invalid_frontmatter={results['invalid_frontmatter']} errors={results['errors']}"
    )
    return 1 if results["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
