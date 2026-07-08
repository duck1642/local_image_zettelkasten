import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import yaml

from workspaces import WORKSPACE_MARKER_NAME, WORKSPACE_MARKER_PAYLOAD


if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = {
    PROJECT_ROOT,
    PROJECT_ROOT / "data",
    PROJECT_ROOT / "config",
    PROJECT_ROOT / "logs",
    PROJECT_ROOT / "secrets",
}


def _resolve(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _guard_workspace_parent_path(parent_path: Path):
    resolved = _resolve(parent_path)
    forbidden = {_resolve(path) for path in FORBIDDEN}
    if resolved in forbidden:
        raise ValueError(f"refusing unsafe workspace parent path: {resolved}")
    for path in forbidden:
        if _is_relative_to(resolved, path):
            raise ValueError(f"refusing workspace parent inside runtime path: {resolved}")


def lmz_workspace_config() -> dict:
    return {
        "external_tools": {
            "proxy": "",
            "user_agent": "LMZ workspace",
        },
        "firewall": {
            "allowed_extensions": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".jfif", ".mp4", ".webm", ".ogv"],
            "allowed_mimes": ["image/jpeg", "image/png", "image/gif", "image/webp", "video/mp4", "video/webm", "video/ogg"],
        },
        "hash_algorithm": "sha256",
        "active_vault": "default",
        "vaults": {
            "default": {
                "name": "Default",
                "root": "data/vaults/default",
            },
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


def setup_lmz_workspace(parent_path: str | Path, overwrite_config: bool = False) -> dict:
    workspace_parent = _resolve(parent_path)
    _guard_workspace_parent_path(workspace_parent)
    workspace = workspace_parent / "lmz"
    workspace_preexisted = workspace.exists()
    config_path = workspace / "config.yaml"
    directories = [
        workspace / "data" / "topics",
        workspace / "data" / "vaults" / "default" / "vault" / "notes",
        workspace / "data" / "vaults" / "default" / "vault" / "assets",
        workspace / "data" / "vaults" / "default" / "db",
        workspace / "data" / "vaults" / "default" / "logs" / "raw",
        workspace / "data" / "vaults" / "default" / "logs" / "structured",
        workspace / "data" / "vaults" / "default" / "review",
        workspace / "data" / "vaults" / "default" / "wd-tags",
        workspace / "data" / "vaults" / "default" / "ui_cache" / "thumbnails",
        workspace / "data" / "vaults" / "default" / "queues",
        workspace / "data" / "vaults" / "default" / "batches",
        workspace / "data" / "vaults" / "default" / "input",
        workspace / "data" / "vaults" / "default" / "local_ingest",
        workspace / "data" / "vaults" / "default" / "online_ingest",
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
    wrote_config = False
    if overwrite_config or not config_path.exists():
        config_path.write_text(yaml.safe_dump(lmz_workspace_config(), sort_keys=False, allow_unicode=True), encoding="utf-8")
        wrote_config = True
    marker_path = workspace / WORKSPACE_MARKER_NAME
    if not workspace_preexisted:
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=workspace,
                prefix=f".{WORKSPACE_MARKER_NAME}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                json.dump(WORKSPACE_MARKER_PAYLOAD, handle)
                handle.flush()
                os.fsync(handle.fileno())
                temp_path = Path(handle.name)
            os.replace(temp_path, marker_path)
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)
    return {
        "workspace_parent": str(workspace_parent),
        "workspace": str(workspace),
        "config_path": str(config_path),
        "wrote_config": wrote_config,
        "marker_path": str(marker_path),
        "managed": marker_path.exists(),
        "directories": [str(path) for path in directories],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Create an LMZ workspace under a parent folder.")
    parser.add_argument("workspace_parent_path")
    parser.add_argument("--overwrite-config", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload = setup_lmz_workspace(args.workspace_parent_path, overwrite_config=args.overwrite_config)
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
