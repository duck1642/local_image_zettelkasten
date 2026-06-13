import argparse
import json
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "backend"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from db.sqlite_operator import init_database
from utils import note_path_for, wd_tag_cache_path_for
import utils


WD_KEYS = ["wd_rating", "wd_character_tags", "wd_tags"]


def items(target_hash: str = "") -> list[tuple[str, str]]:
    if target_hash:
        where = "WHERE hash = ?"
        params = (target_hash,)
    else:
        where = ""
        params = ()
    conn = init_database()
    try:
        rows = conn.execute(f"SELECT hash, storage_id FROM items {where} ORDER BY hash", params).fetchall()
        return [(str(row[0]), str(row[1] or "")) for row in rows]
    finally:
        conn.close()


def clear_json(file_hash: str, storage_id: str, apply: bool) -> str:
    path = wd_tag_cache_path_for(file_hash, storage_id)
    if not path.exists():
        return "missing"
    if apply:
        path.unlink()
    return "deleted"


def split_frontmatter(text: str):
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    return parts[1], parts[2]


def clear_yaml(file_hash: str, storage_id: str, apply: bool) -> str:
    path = note_path_for(file_hash, storage_id)
    if not path.exists():
        return "missing"
    text = path.read_text(encoding="utf-8")
    parts = split_frontmatter(text)
    if not parts:
        return "no_frontmatter"
    raw_frontmatter, body = parts
    data = yaml.safe_load(raw_frontmatter) or {}
    if not isinstance(data, dict):
        return "invalid_frontmatter"
    changed = False
    for key in WD_KEYS:
        if key in data:
            data.pop(key)
            changed = True
    if not changed:
        return "no_tags"
    if apply:
        rendered = yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
        path.write_text(f"---\n{rendered}---{body}", encoding="utf-8")
    return "cleared"


def run(target_hash: str, target: str, apply: bool) -> dict:
    results = {
        "items": 0,
        "json_deleted": 0,
        "json_missing": 0,
        "yaml_cleared": 0,
        "yaml_missing": 0,
        "yaml_unchanged": 0,
        "errors": 0,
    }
    for file_hash, storage_id in items(target_hash):
        results["items"] += 1
        try:
            if target in {"json", "both"}:
                status = clear_json(file_hash, storage_id, apply)
                if status == "deleted":
                    results["json_deleted"] += 1
                else:
                    results["json_missing"] += 1
                print(f"JSON {status.upper()} {file_hash}")
            if target in {"yaml", "both"}:
                status = clear_yaml(file_hash, storage_id, apply)
                if status == "cleared":
                    results["yaml_cleared"] += 1
                elif status == "missing":
                    results["yaml_missing"] += 1
                else:
                    results["yaml_unchanged"] += 1
                print(f"YAML {status.upper()} {file_hash}")
        except Exception as exc:
            results["errors"] += 1
            print(f"ERROR {file_hash} {str(exc).encode('ascii', errors='backslashreplace').decode('ascii')}")
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("hash", nargs="?")
    parser.add_argument("--target", choices=["json", "yaml", "both"], default="both")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--summary-json", action="store_true")
    args = parser.parse_args()

    from runtime_context import has_runtime_context
    if not has_runtime_context():
        from scripts.workspace_select import select_runtime_context
        select_runtime_context("clear_wd_tags")

    results = run(args.hash or "", args.target, args.apply)
    if args.summary_json:
        print(json.dumps(results, indent=2))
    else:
        mode = "APPLY" if args.apply else "DRY-RUN"
        print(f"{mode} items={results['items']} json_deleted={results['json_deleted']} yaml_cleared={results['yaml_cleared']} errors={results['errors']}")
    return 1 if results["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
