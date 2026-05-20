import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from vaults import migrate_legacy_layout


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Copy/move legacy single-vault data into data/vaults/default.")
    parser.add_argument("--move", action="store_true", help="Move files instead of copying them")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing default vault folders")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload = migrate_legacy_layout(copy=not args.move, overwrite=args.overwrite)
    except Exception as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"ERROR {exc}")
        return 2
    payload["ok"] = True
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(payload["target"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
