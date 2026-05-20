import argparse
import json
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = {
    ROOT,
    ROOT / "data",
    ROOT / "config",
    ROOT / "logs",
    ROOT / "secrets",
}


def _resolve(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _guard_vault_path(vault_path: Path):
    resolved = _resolve(vault_path)
    forbidden = {_resolve(path) for path in FORBIDDEN}
    if resolved in forbidden:
        raise ValueError(f"refusing unsafe Obsidian vault path: {resolved}")
    for path in forbidden:
        if _is_relative_to(resolved, path):
            raise ValueError(f"refusing Obsidian vault inside runtime path: {resolved}")


def obsidian_config() -> dict:
    return {
        "external_tools": {
            "cookies_path": "data/secrets/cookies.txt",
            "proxy": "",
            "user_agent": "LMZ Obsidian workspace",
        },
        "firewall": {
            "allowed_extensions": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".jfif", ".mp4", ".webm", ".ogv"],
            "allowed_mimes": ["image/jpeg", "image/png", "image/gif", "image/webp", "video/mp4", "video/webm", "video/ogg"],
        },
        "hash_algorithm": "sha256",
        "paths": {
            "batches": "data/batches",
            "db": "data/db/lmz_main.db",
            "input": "data/input",
            "local_ingest": "data/local_ingest",
            "logs": "data/logs",
            "models": "data/models",
            "online_ingest": "data/online_ingest",
            "queues": "data/queues",
            "review": "data/review",
            "secrets": "data/secrets",
            "thumbnails": "data/ui_cache/thumbnails",
            "vault": "data/vault",
            "wd_tags": "data/wd-tags",
        },
        "processing": {
            "background_preset": "white",
            "custom_color": [255, 255, 255],
            "flatten_transparency": True,
        },
        "tagging": {
            "enabled": True,
            "model_repo": "SmilingWolf/wd-vit-tagger-v3",
            "device": "auto",
            "display_source": "yaml",
            "threshold": 0.35,
            "max_tags": 30,
            "fail_ingestion_on_error": False,
            "video": {
                "enabled": True,
                "frame_count": 5,
                "merge_min_frames": 2,
                "merge_high_confidence": 0.75,
            },
        },
        "ui": {
            "vault_layout_mode": "masonry",
            "vault_tile_min_width": 190,
            "inspector_width": 400,
            "inspector_visible": True,
            "ram_track_enabled": False,
        },
    }


def setup_obsidian_workspace(vault_path: str | Path, overwrite_config: bool = False) -> dict:
    obsidian_vault = _resolve(vault_path)
    _guard_vault_path(obsidian_vault)
    workspace = obsidian_vault / "lmz"
    config_path = workspace / "config.yaml"
    directories = [
        workspace / "data" / "topics",
        workspace / "data" / "vault" / "notes",
        workspace / "data" / "vault" / "assets",
        workspace / "data" / "db",
        workspace / "data" / "logs",
        workspace / "data" / "review",
        workspace / "data" / "wd-tags",
        workspace / "data" / "ui_cache" / "thumbnails",
        workspace / "data" / "queues",
        workspace / "data" / "batches",
        workspace / "data" / "input",
        workspace / "data" / "local_ingest",
        workspace / "data" / "online_ingest",
        workspace / "data" / "models",
        workspace / "data" / "secrets",
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
    wrote_config = False
    if overwrite_config or not config_path.exists():
        config_path.write_text(yaml.safe_dump(obsidian_config(), sort_keys=False, allow_unicode=True), encoding="utf-8")
        wrote_config = True
    return {
        "obsidian_vault": str(obsidian_vault),
        "workspace": str(workspace),
        "config_path": str(config_path),
        "wrote_config": wrote_config,
        "directories": [str(path) for path in directories],
    }


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
