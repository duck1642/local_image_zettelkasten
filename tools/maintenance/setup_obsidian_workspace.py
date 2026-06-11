import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.maintenance.setup_workspace import lmz_workspace_config, setup_lmz_workspace


def obsidian_config() -> dict:
    return lmz_workspace_config()


def setup_obsidian_workspace(vault_path: str | Path, overwrite_config: bool = False) -> dict:
    payload = setup_lmz_workspace(vault_path, overwrite_config=overwrite_config)
    payload["obsidian_vault"] = payload["workspace_parent"]
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Create an LMZ workspace inside an Obsidian vault.")
    parser.add_argument("obsidian_vault_path")
    parser.add_argument("--overwrite-config", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload = setup_obsidian_workspace(args.obsidian_vault_path, overwrite_config=args.overwrite_config)
    except Exception as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        else:
            print(f"ERROR {exc}", file=sys.stderr)
        return 2
    payload["ok"] = True
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(payload["config_path"])
        print(f"PowerShell: $env:LMZ_CONFIG_PATH=\"{payload['config_path']}\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
