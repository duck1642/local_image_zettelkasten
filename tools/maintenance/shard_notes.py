import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from utils import NOTES_DIR, PROJECT_ROOT as LIZ_ROOT, note_path_for


def flat_notes() -> list[Path]:
    if not NOTES_DIR.exists():
        return []
    return sorted(path for path in NOTES_DIR.glob("*.md") if path.is_file())


def backup_notes() -> Path:
    backup_root = LIZ_ROOT / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_root / f"notes_before_shard_{stamp}"
    if NOTES_DIR.exists():
        shutil.copytree(NOTES_DIR, backup_path / "notes")
    else:
        (backup_path / "notes").mkdir(parents=True, exist_ok=True)
    return backup_path


def build_plan() -> list[dict]:
    plan = []
    for source in flat_notes():
        file_hash = source.stem
        target = note_path_for(file_hash)
        status = "move"
        if target.exists():
            try:
                status = "remove_flat" if target.read_text(encoding="utf-8") == sharded_note_text(source) else "conflict"
            except OSError:
                status = "conflict"
        elif source.resolve() == target.resolve():
            status = "skip"
        plan.append({"source": source, "target": target, "status": status})
    return plan


def print_plan(plan: list[dict], backup_path: Path = None):
    move_count = sum(1 for item in plan if item["status"] == "move")
    conflict_count = sum(1 for item in plan if item["status"] == "conflict")
    skip_count = sum(1 for item in plan if item["status"] == "skip")
    remove_flat_count = sum(1 for item in plan if item["status"] == "remove_flat")
    print(f"Flat notes: {len(plan)}")
    print(f"Will move: {move_count}")
    print(f"Flat duplicates to remove: {remove_flat_count}")
    print(f"Conflicts: {conflict_count}")
    print(f"Skipped: {skip_count}")
    if backup_path:
        print(f"Backup: {backup_path}")
    for item in plan:
        print(f"{item['status'].upper()} {item['source']} -> {item['target']}")


def sharded_note_text(source: Path) -> str:
    text = source.read_text(encoding="utf-8")
    return text.replace("](../assets/", "](../../assets/")


def apply_plan(plan: list[dict]) -> dict:
    moved = 0
    skipped = 0
    conflicted = 0
    removed_flat = 0
    delete_failed = 0
    for item in plan:
        source = item["source"]
        target = item["target"]
        if item["status"] == "conflict":
            conflicted += 1
            continue
        if item["status"] == "remove_flat":
            try:
                source.unlink()
                removed_flat += 1
            except OSError:
                delete_failed += 1
            continue
        if item["status"] != "move":
            skipped += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(sharded_note_text(source), encoding="utf-8")
        try:
            source.unlink()
        except OSError:
            delete_failed += 1
        moved += 1
    return {"moved": moved, "skipped": skipped, "conflicted": conflicted, "removed_flat": removed_flat, "delete_failed": delete_failed}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    plan = build_plan()
    if not args.apply:
        print_plan(plan)
        return
    backup_path = backup_notes()
    result = apply_plan(plan)
    print_plan(plan, backup_path)
    print(f"Moved: {result['moved']}")
    print(f"Removed flat duplicates: {result['removed_flat']}")
    print(f"Skipped: {result['skipped']}")
    print(f"Conflicted: {result['conflicted']}")
    print(f"Delete failures: {result['delete_failed']}")


if __name__ == "__main__":
    main()
