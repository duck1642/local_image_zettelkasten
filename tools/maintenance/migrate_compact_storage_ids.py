import argparse
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "backend"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from db.sqlite_operator import int_to_storage_id, storage_id_to_int
from utils import (
    DB_PATH,
    PROJECT_ROOT,
    legacy_asset_path_for,
    legacy_note_path_for,
    legacy_sharded_note_path_for,
    legacy_wd_tag_cache_path_for,
    note_path_for,
    storage_asset_path_for,
    storage_shard_for_hash,
    wd_tag_cache_path_for,
)
from thumbnails import THUMBNAIL_DIR, thumbnail_path_for, video_thumbnail_path_for


@dataclass
class ItemPlan:
    file_hash: str
    file_extension: str
    mime_type: str
    storage_id: str
    assigned: bool


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
    return row is not None


def backup_database() -> Path:
    backup_dir = PROJECT_ROOT / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"lmz_main_before_compact_storage_{stamp}.db"
    if DB_PATH.exists():
        shutil.copy2(DB_PATH, backup_path)
    for suffix in ("-wal", "-shm"):
        sidecar = DB_PATH.with_name(DB_PATH.name + suffix)
        if sidecar.exists():
            shutil.copy2(sidecar, backup_dir / f"{backup_path.name}{suffix}")
    return backup_path


def next_counter_value(conn: sqlite3.Connection) -> int:
    max_value = 0
    if "storage_id" in columns(conn, "items"):
        for row in conn.execute('SELECT storage_id FROM items WHERE storage_id IS NOT NULL AND storage_id != ""'):
            parsed = storage_id_to_int(row["storage_id"])
            if parsed is not None:
                max_value = max(max_value, parsed)
    if table_exists(conn, "storage_id_counter"):
        row = conn.execute("SELECT next_value FROM storage_id_counter WHERE id = 1").fetchone()
        if row:
            max_value = max(max_value, int(row["next_value"]) - 1)
    return max_value + 1


def planned_items(conn: sqlite3.Connection) -> list[ItemPlan]:
    has_storage = "storage_id" in columns(conn, "items")
    storage_expr = "storage_id" if has_storage else "NULL AS storage_id"
    rows = conn.execute(
        f"""
        SELECT hash, file_extension, mime_type, {storage_expr}
        FROM items
        ORDER BY date_added ASC, hash ASC
        """
    ).fetchall()
    used = {str(row["storage_id"]) for row in rows if row["storage_id"]}
    next_value = next_counter_value(conn)
    plans = []
    for row in rows:
        storage_id = str(row["storage_id"] or "")
        assigned = False
        if not storage_id:
            while True:
                storage_id = int_to_storage_id(next_value)
                next_value += 1
                if storage_id not in used:
                    break
            used.add(storage_id)
            assigned = True
        plans.append(ItemPlan(row["hash"], row["file_extension"] or "", row["mime_type"] or "", storage_id, assigned))
    return plans


def apply_schema(conn: sqlite3.Connection, plans: list[ItemPlan]):
    item_columns = columns(conn, "items")
    if "storage_id" not in item_columns:
        conn.execute("ALTER TABLE items ADD COLUMN storage_id TEXT")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS storage_id_counter (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            next_value INTEGER NOT NULL
        )
        """
    )
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_items_storage_id ON items(storage_id)")
    for plan in plans:
        if plan.assigned:
            conn.execute("UPDATE items SET storage_id = ? WHERE hash = ?", (plan.storage_id, plan.file_hash))
    next_value = max(storage_id_to_int(plan.storage_id) or 0 for plan in plans) + 1 if plans else 1
    conn.execute(
        """
        INSERT INTO storage_id_counter(id, next_value)
        VALUES (1, ?)
        ON CONFLICT(id) DO UPDATE SET next_value = excluded.next_value
        """,
        (next_value,),
    )
    if table_exists(conn, "metadata_index_state"):
        conn.execute(
            """
            INSERT INTO metadata_index_state(key, value)
            VALUES ('initial_backfill_complete', '0')
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """
        )
    conn.commit()


def copy_file(source: Path, target: Path, apply: bool, cleanup_legacy: bool, report: dict):
    if not source.exists():
        report["missing_legacy_files"] += 1
        return
    if target.exists():
        report["files_already_present"] += 1
    else:
        report["files_to_copy"] += 1
        if apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            report["files_copied"] += 1
    if apply and cleanup_legacy and target.exists() and source.exists() and source.resolve() != target.resolve():
        source.unlink()
        report["legacy_files_removed"] += 1


def rewrite_note(source: Path, target: Path, plan: ItemPlan, apply: bool, cleanup_legacy: bool, report: dict):
    if not source.exists():
        report["missing_legacy_files"] += 1
        return
    text = source.read_text(encoding="utf-8")
    shard = storage_shard_for_hash(plan.file_hash)
    legacy_rel = f"../../assets/{shard}/{plan.file_hash}{plan.file_extension}"
    compact_rel = f"../../assets/{shard}/{plan.storage_id}{plan.file_extension}"
    rewritten = text.replace(f"]({legacy_rel})", f"]({compact_rel})")
    changed = rewritten != text
    if changed:
        report["markdown_links_rewritten"] += 1
    if target.exists():
        report["files_already_present"] += 1
    else:
        report["files_to_copy"] += 1
        if apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rewritten, encoding="utf-8")
            report["files_copied"] += 1
    if apply and changed and target.exists():
        target.write_text(rewritten, encoding="utf-8")
    if apply and cleanup_legacy and target.exists() and source.exists() and source.resolve() != target.resolve():
        source.unlink()
        report["legacy_files_removed"] += 1


def migrate_files(plans: list[ItemPlan], apply: bool, cleanup_legacy: bool) -> dict:
    report = {
        "files_to_copy": 0,
        "files_copied": 0,
        "files_already_present": 0,
        "missing_legacy_files": 0,
        "markdown_links_rewritten": 0,
        "legacy_files_removed": 0,
        "failures": 0,
    }
    for plan in plans:
        try:
            copy_file(
                legacy_asset_path_for(plan.file_hash, plan.file_extension, plan.mime_type),
                storage_asset_path_for(plan.file_hash, plan.storage_id, plan.file_extension, plan.mime_type),
                apply,
                cleanup_legacy,
                report,
            )
            note_sources = [legacy_sharded_note_path_for(plan.file_hash), legacy_note_path_for(plan.file_hash)]
            note_source = next((path for path in note_sources if path.exists()), note_sources[0])
            rewrite_note(note_source, note_path_for(plan.file_hash, storage_id=plan.storage_id), plan, apply, cleanup_legacy, report)
            copy_file(
                legacy_wd_tag_cache_path_for(plan.file_hash),
                wd_tag_cache_path_for(plan.file_hash, storage_id=plan.storage_id),
                apply,
                cleanup_legacy,
                report,
            )
            thumb_source = THUMBNAIL_DIR / storage_shard_for_hash(plan.file_hash) / f"{plan.file_hash}.jpg"
            copy_file(thumb_source, thumbnail_path_for(plan.file_hash, storage_id=plan.storage_id), apply, cleanup_legacy, report)
            video_thumb_source = THUMBNAIL_DIR / storage_shard_for_hash(plan.file_hash) / f"{plan.file_hash}_video.jpg"
            copy_file(video_thumb_source, video_thumbnail_path_for(plan.file_hash, storage_id=plan.storage_id), apply, cleanup_legacy, report)
        except Exception as exc:
            report["failures"] += 1
            print(f"[ERROR] {plan.file_hash}: {exc}")
    return report


def run(apply: bool, cleanup_legacy: bool) -> dict:
    if not DB_PATH.exists():
        raise SystemExit(f"[ERROR] Database not found: {DB_PATH}")
    if cleanup_legacy and not apply:
        raise SystemExit("[ERROR] --cleanup-legacy requires --apply")
    conn = connect()
    try:
        plans = planned_items(conn)
        backup_path = None
        if apply:
            backup_path = backup_database()
            apply_schema(conn, plans)
        file_report = migrate_files(plans, apply, cleanup_legacy)
    finally:
        conn.close()
    assigned = sum(1 for plan in plans if plan.assigned)
    report = {
        "mode": "apply" if apply else "dry-run",
        "rows_scanned": len(plans),
        "ids_assigned": assigned,
        "backup": str(backup_path) if apply and backup_path else "",
        **file_report,
    }
    return report


def main():
    parser = argparse.ArgumentParser(description="Migrate vault files from full SHA256 filenames to compact storage IDs.")
    parser.add_argument("--apply", action="store_true", help="write DB/storage changes")
    parser.add_argument("--cleanup-legacy", action="store_true", help="delete old full-hash files after verified copy")
    args = parser.parse_args()
    report = run(args.apply, args.cleanup_legacy)
    print("[INFO] Compact storage migration report")
    for key, value in report.items():
        print(f"{key}: {value}")
    if not args.apply:
        print("[INFO] Dry run only. Re-run with --apply to migrate.")


if __name__ == "__main__":
    main()
