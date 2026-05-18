import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "backend"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from logger import log_system
from metadata_index import (
    FULL_REBUILD_BATCH_SIZE,
    REPAIR_BATCH_SIZE,
    ensure_metadata_schema,
    metadata_index_status,
    rebuild_all_metadata,
    reindex_stale_metadata_batch,
    stale_metadata_count,
)
from utils import DB_PATH


BATCH_SIZE = FULL_REBUILD_BATCH_SIZE


def open_database():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"database not found: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA foreign_keys = ON;")
    ensure_metadata_schema(conn)
    conn.commit()
    return conn


def _missing_storage_ids(conn) -> list[str]:
    rows = conn.execute(
        """
        SELECT hash
        FROM items
        WHERE storage_id IS NULL OR storage_id = ''
        ORDER BY date_added ASC, hash ASC
        """
    ).fetchall()
    return [row[0] for row in rows]


def _base_report(action: str, conn, deep: bool = False) -> dict:
    status = metadata_index_status(conn, deep=deep)
    return {
        "action": action,
        "items": status["items"],
        "indexed": 0,
        "errors": 0,
        "stale_before": status["stale"],
        "stale_after": status["stale"],
        "duration_ms": 0.0,
        "status": status,
    }


def _require_storage_integrity(conn):
    missing = _missing_storage_ids(conn)
    if missing:
        sample = missing[:10]
        raise StorageIntegrityError(
            f"{len(missing)} item rows are missing storage_id",
            count=len(missing),
            sample=sample,
        )


class StorageIntegrityError(RuntimeError):
    def __init__(self, message: str, count: int, sample: list[str]):
        super().__init__(message)
        self.count = count
        self.sample = sample


def run_status(conn) -> dict:
    return _base_report("status", conn, deep=True)


def run_stale(conn, limit: int | None = None, deep_validate: bool = False) -> dict:
    _require_storage_integrity(conn)
    report = _base_report("stale", conn, deep=deep_validate)
    started = time.perf_counter()
    remaining = max(0, int(limit)) if limit is not None else None

    log_system("INFO", "Metadata index maintenance rebuild started", mode="stale", limit=limit or 0, deep_validate=deep_validate)
    while True:
        if remaining is not None and remaining <= 0:
            break
        batch_limit = REPAIR_BATCH_SIZE if remaining is None else min(REPAIR_BATCH_SIZE, remaining)
        result = reindex_stale_metadata_batch(conn, batch_limit)
        conn.commit()
        report["indexed"] += int(result.get("indexed") or 0)
        report["errors"] += int(result.get("errors") or 0)
        queued = int(result.get("queued") or 0)
        if remaining is not None:
            remaining -= queued
        if result.get("source") == "dirty_queue" and not result.get("dirty_remaining"):
            continue
        if queued < batch_limit:
            break

    if deep_validate:
        report["stale_after"] = stale_metadata_count(conn)
    report["status"] = metadata_index_status(conn, deep=deep_validate)
    report["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
    log_system("INFO", "Metadata index maintenance rebuild finished", **report)
    return report


def run_full(conn, deep_validate: bool = False) -> dict:
    _require_storage_integrity(conn)
    report = _base_report("full", conn, deep=deep_validate)
    started = time.perf_counter()

    log_system("INFO", "Metadata index maintenance rebuild started", mode="full", deep_validate=deep_validate)
    ensure_metadata_schema(conn)
    result = rebuild_all_metadata(conn, BATCH_SIZE, "maintenance_full")
    conn.commit()
    report["indexed"] = int(result.get("indexed") or 0)
    report["errors"] = int(result.get("errors") or 0)
    report["stages_ms"] = result.get("stages_ms", {})
    if deep_validate:
        report["stale_after"] = stale_metadata_count(conn)
    report["status"] = metadata_index_status(conn, deep=deep_validate)
    report["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
    log_system("INFO", "Metadata index maintenance rebuild finished", **report)
    return report


def run(mode: str = "status", limit: int | None = None, deep_validate: bool = False) -> dict:
    conn = open_database()
    try:
        if mode == "status":
            return run_status(conn)
        if mode == "stale":
            return run_stale(conn, limit, deep_validate=deep_validate)
        if mode == "full":
            return run_full(conn, deep_validate=deep_validate)
        raise ValueError(f"unknown mode: {mode}")
    finally:
        conn.close()


def _print_summary(report: dict, as_json: bool):
    if as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return
    print(
        f"{report['action'].upper()} "
        f"items={report['items']} indexed={report['indexed']} errors={report['errors']} "
        f"stale_before={report['stale_before']} stale_after={report['stale_after']} "
        f"duration_ms={report['duration_ms']}"
    )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Rebuild LMZ persistent metadata indexes.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--status", action="store_true", help="Print current metadata index status.")
    group.add_argument("--stale", action="store_true", help="Rebuild stale or missing metadata index rows.")
    group.add_argument("--full", action="store_true", help="Clear and rebuild all metadata index rows.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum stale rows to rebuild with --stale.")
    parser.add_argument("--deep-validate", action="store_true", help="Run expensive stale scans before/after --stale or --full.")
    parser.add_argument("--json", action="store_true", help="Print JSON summary.")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    mode = "full" if args.full else "stale" if args.stale else "status"
    try:
        report = run(mode, args.limit, deep_validate=args.deep_validate)
    except StorageIntegrityError as exc:
        payload = {
            "action": mode,
            "error": str(exc),
            "missing_storage_ids": exc.count,
            "sample_hashes": exc.sample,
        }
        log_system("ERROR", "Metadata index maintenance rebuild blocked", **payload)
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"ERROR {payload['error']}")
            if exc.sample:
                print("Sample hashes: " + ", ".join(exc.sample))
        return 2
    except Exception as exc:
        log_system("ERROR", "Metadata index maintenance rebuild failed", mode=mode, error=str(exc))
        if args.json:
            print(json.dumps({"action": mode, "error": str(exc)}, indent=2, sort_keys=True))
        else:
            print(f"ERROR {exc}")
        return 1
    _print_summary(report, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
