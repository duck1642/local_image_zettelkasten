import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "backend"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from md_generator import normalize_topic_list
from utils import PROJECT_ROOT as LMZ_ROOT
import utils


def split_frontmatter(text: str):
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    return parts[1], parts[2]


def backup_notes() -> Path:
    backup_root = LMZ_ROOT / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_root / f"notes_before_topic_normalize_{stamp}"
    shutil.copytree(utils.NOTES_DIR, backup_path / "notes")
    return backup_path


def normalize_note(path: Path, apply: bool) -> str:
    text = path.read_text(encoding="utf-8")
    parts = split_frontmatter(text)
    if not parts:
        return "no_frontmatter"
    raw_frontmatter, body = parts
    data = yaml.safe_load(raw_frontmatter) or {}
    if not isinstance(data, dict):
        return "invalid_frontmatter"
    old_topics = data.get("topics", [])
    new_topics = normalize_topic_list(old_topics)
    if isinstance(old_topics, list) and old_topics == new_topics:
        return "unchanged"
    data["topics"] = new_topics
    if apply:
        rendered = yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
        path.write_text(f"---\n{rendered}---{body}", encoding="utf-8")
    return "normalized"


def run(apply: bool) -> dict:
    results = {
        "notes": 0,
        "normalized": 0,
        "unchanged": 0,
        "skipped": 0,
        "errors": 0,
    }
    if apply:
        backup_path = backup_notes()
        print(f"Backup: {backup_path}")
    for path in sorted(utils.NOTES_DIR.rglob("*.md")):
        results["notes"] += 1
        try:
            status = normalize_note(path, apply)
            if status == "normalized":
                results["normalized"] += 1
            elif status == "unchanged":
                results["unchanged"] += 1
            else:
                results["skipped"] += 1
            print(f"{status.upper()} {path}")
        except Exception as exc:
            results["errors"] += 1
            print(f"ERROR {path} {str(exc).encode('ascii', errors='backslashreplace').decode('ascii')}")
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    from runtime_context import has_runtime_context
    if not has_runtime_context():
        from scripts.workspace_select import select_runtime_context
        select_runtime_context("normalize_topics")

    results = run(args.apply)
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"{mode} notes={results['notes']} normalized={results['normalized']} unchanged={results['unchanged']} skipped={results['skipped']} errors={results['errors']}")
    return 1 if results["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
