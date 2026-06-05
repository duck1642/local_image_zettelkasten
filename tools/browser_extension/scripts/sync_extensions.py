from __future__ import annotations

import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TARGETS = ("edge", "chrome", "firefox")
SHARED_FILES = ("api.js", "background.js", "db.js", "popup.html", "popup.js", "styles.css")


def chromium_manifest() -> dict:
    return {
        "manifest_version": 3,
        "name": "LMZ Capture",
        "version": "0.1.0",
        "description": "Capture images and supported page URLs into Local Media Zettelkasten.",
        "permissions": ["contextMenus", "storage", "activeTab", "downloads"],
        "host_permissions": ["http://127.0.0.1:8000/*", "http://localhost:8000/*", "*://*/*"],
        "background": {
            "service_worker": "background.js",
            "type": "module",
        },
        "action": {
            "default_popup": "popup.html",
        },
    }


def firefox_manifest() -> dict:
    manifest = chromium_manifest()
    manifest["background"] = {
        "scripts": ["background.js"],
        "type": "module",
    }
    manifest["browser_specific_settings"] = {
        "gecko": {
            "id": "lmz-capture@local",
        },
    }
    return manifest


def manifest_for(target: str) -> dict:
    if target == "firefox":
        return firefox_manifest()
    return chromium_manifest()


def sync_target(target: str) -> None:
    target_dir = ROOT / target
    target_dir.mkdir(parents=True, exist_ok=True)
    for filename in SHARED_FILES:
        shutil.copy2(SRC / filename, target_dir / filename)
    manifest_text = json.dumps(manifest_for(target), indent=2) + "\n"
    (target_dir / "manifest.json").write_text(manifest_text, encoding="utf-8")


def main() -> None:
    missing = [filename for filename in SHARED_FILES if not (SRC / filename).is_file()]
    if missing:
        raise SystemExit(f"Missing shared files: {', '.join(missing)}")
    for target in TARGETS:
        sync_target(target)


if __name__ == "__main__":
    main()
