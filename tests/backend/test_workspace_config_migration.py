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
        "external_tools": {
            "proxy": "",
            "cookies_path": "data/secrets/cookies.txt",
            "pixiv_token": "secret-token",
        },
    }


def test_migration_removes_legacy_auth_keys_without_deleting_files(tmp_path):
    migrations = importlib.import_module("config_migrations")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(legacy_config(), sort_keys=False), encoding="utf-8")
    legacy_secret = tmp_path / "data" / "secrets" / "cookies.txt"
    legacy_secret.parent.mkdir(parents=True)
    legacy_secret.write_text("keep me", encoding="utf-8")

    assert migrations.migrate_workspace_config(config_path) is True
    migrated = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert "paths" not in migrated
    assert migrated["external_tools"] == {"proxy": ""}
    assert legacy_secret.read_text(encoding="utf-8") == "keep me"
    assert migrations.migrate_workspace_config(config_path) is False


def test_migration_replace_failure_preserves_original_config(tmp_path, monkeypatch):
    migrations = importlib.import_module("config_migrations")
    config_path = tmp_path / "config.yaml"
    original = yaml.safe_dump(legacy_config(), sort_keys=False)
    config_path.write_text(original, encoding="utf-8")

    monkeypatch.setattr(migrations.os, "replace", lambda *_args: (_ for _ in ()).throw(OSError("replace failed")))

    with pytest.raises(OSError, match="replace failed"):
        migrations.migrate_workspace_config(config_path)

    assert config_path.read_text(encoding="utf-8") == original


def test_runtime_load_migrates_legacy_auth_config(tmp_path):
    runtime_context = importlib.import_module("runtime_context")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(legacy_config(), sort_keys=False), encoding="utf-8")

    context = runtime_context.build_runtime_context(config_path)
    migrated = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert context.root == tmp_path
    assert "secrets_dir" not in context.__dataclass_fields__
    assert "paths" not in migrated
    assert "cookies_path" not in migrated["external_tools"]
    assert "pixiv_token" not in migrated["external_tools"]


def test_legacy_auth_config_keys_are_rejected_after_migration_boundary(monkeypatch, tmp_path):
    monkeypatch.setenv("LMZ_AUTH_ROOT", str(tmp_path / "auth"))
    utils = importlib.import_module("utils")

    with pytest.raises(ValueError, match="paths.secrets"):
        utils.validate_config_schema({**legacy_config(), "firewall": {"allowed_extensions": [], "allowed_mimes": []}, "hash_algorithm": "sha256"})

    config = legacy_config()
    config.pop("paths")
    config["firewall"] = {"allowed_extensions": [], "allowed_mimes": []}
    config["hash_algorithm"] = "sha256"
    with pytest.raises(ValueError, match="external_tools.cookies_path"):
        utils.validate_config_schema(config)
