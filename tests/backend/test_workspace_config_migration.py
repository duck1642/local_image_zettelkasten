import importlib
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def legacy_config() -> dict:
    return {
        "active_vault": "default",
        "vaults": {"default": {"name": "Default", "root": "data/vaults/default"}},
        "paths": {"secrets": "data/secrets"},
        "external_tools": {"cookies_path": "data/secrets/cookies.txt"},
    }


def test_runtime_strictly_rejects_legacy_config_without_rewriting_it(tmp_path):
    from config_repository import ConfigReadError

    runtime_context = importlib.import_module("runtime_context")
    config_path = tmp_path / "config.yaml"
    original = yaml.safe_dump(legacy_config(), sort_keys=False)
    config_path.write_text(original, encoding="utf-8")
    legacy_secret = tmp_path / "data" / "secrets" / "cookies.txt"
    legacy_secret.parent.mkdir(parents=True)
    legacy_secret.write_text("keep me", encoding="utf-8")

    with pytest.raises(ConfigReadError, match="paths|external_tools"):
        runtime_context.build_runtime_context(config_path)

    assert config_path.read_text(encoding="utf-8") == original
    assert legacy_secret.read_text(encoding="utf-8") == "keep me"


def test_no_automatic_legacy_config_migration_module_exists():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("config_migrations")
