import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "backend"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from utils import PROJECT_ROOT as LMZ_ROOT, WD_TAGS_DIR, wd_tag_cache_path_for


LEGACY_TOPICS_DIR = LMZ_ROOT / "data" / "topics"


def legacy_json_files() -> list[Path]:
    if not LEGACY_TOPICS_DIR.exists():
        return []
    return sorted(path for path in LEGACY_TOPICS_DIR.glob("*.json") if path.is_file())


def backup_wd_tags() -> Path:
    backup_root = LMZ_ROOT / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_root / f"wd_tags_before_shard_{stamp}"
    if LEGACY_TOPICS_DIR.exists():
        shutil.copytree(LEGACY_TOPICS_DIR, backup_path / "topics")
    else:
        (backup_path / "topics").mkdir(parents=True, exist_ok=True)
    if WD_TAGS_DIR.exists():
        shutil.copytree(WD_TAGS_DIR, backup_path / "wd-tags")
    else:
        (backup_path / "wd-tags").mkdir(parents=True, exist_ok=True)
    return backup_path


def build_plan() -> list[dict]:
    plan = []
    for source in legacy_json_files():
        file_hash = source.stem
        target = wd_tag_cache_path_for(file_hash)
        status = "move"
        if target.exists():
            status = "remove_flat" if target.read_bytes() == source.read_bytes() else "conflict"
        plan.append({"source": source, "target": target, "status": status})
    return plan


def print_plan(plan: list[dict], backup_path: Path = None):
    move_count = sum(1 for item in plan if item["status"] == "move")
    conflict_count = sum(1 for item in plan if item["status"] == "conflict")
    remove_flat_count = sum(1 for item in plan if item["status"] == "remove_flat")
    print(f"Flat WD tag JSON files: {len(plan)}")
    print(f"Will move: {move_count}")
    print(f"Flat duplicates to remove: {remove_flat_count}")
    print(f"Conflicts: {conflict_count}")
    if backup_path:
        print(f"Backup: {backup_path}")
    for item in plan:
        print(f"{item['status'].upper()} {item['source']} -> {item['target']}")


def apply_plan(plan: list[dict]) -> dict:
    moved = 0
    removed_flat = 0
    conflicted = 0
    errors = 0
    for item in plan:
        source = item["source"]
        target = item["target"]
        if item["status"] == "conflict":
            conflicted += 1
            continue
        try:
            if item["status"] == "remove_flat":
                source.unlink()
                removed_flat += 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            moved += 1
        except OSError as exc:
            errors += 1
            print(f"ERROR {source} {str(exc).encode('ascii', errors='backslashreplace').decode('ascii')}")
    return {"moved": moved, "removed_flat": removed_flat, "conflicted": conflicted, "errors": errors}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    plan = build_plan()
    if not args.apply:
        print_plan(plan)
        return 0
    backup_path = backup_wd_tags()
    result = apply_plan(plan)
    print_plan(plan, backup_path)
    print(f"Moved: {result['moved']}")
    print(f"Removed flat duplicates: {result['removed_flat']}")
    print(f"Conflicted: {result['conflicted']}")
    print(f"Errors: {result['errors']}")
    return 1 if result["errors"] or result["conflicted"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
