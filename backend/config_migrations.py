import copy
import os
import tempfile
from pathlib import Path

import yaml


LEGACY_AUTH_KEYS = ("cookies_path", "pixiv_token")


def migrate_workspace_config(config_path: str | Path) -> bool:
    path = Path(config_path).expanduser().resolve()
    if not path.exists():
        return False
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return False

    migrated = copy.deepcopy(data)
    changed = False
    paths = migrated.get("paths")
    if isinstance(paths, dict) and "secrets" in paths:
        paths.pop("secrets", None)
        changed = True
        if not paths:
            migrated.pop("paths", None)

    external_tools = migrated.get("external_tools")
    if isinstance(external_tools, dict):
        for key in LEGACY_AUTH_KEYS:
            if key in external_tools:
                external_tools.pop(key, None)
                changed = True
        if not external_tools:
            migrated.pop("external_tools", None)

    if not changed:
        return False

    payload = yaml.safe_dump(migrated, sort_keys=False, allow_unicode=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)
    return True
