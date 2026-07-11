import json
import sqlite3
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _legacy_source(root: Path) -> Path:
    (root / "config").mkdir(parents=True)
    (root / "config" / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "active_vault": "default",
                "vaults": {"default": {"name": "Legacy Default", "root": "data/vaults/default"}},
                "ui": {"privacy_blur": True},
                "hash_algorithm": "sha256",
                "tagging": {"device": "cuda"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    vault = root / "data" / "vaults" / "default"
    (vault / "vault" / "assets").mkdir(parents=True)
    (vault / "vault" / "assets" / "item.jpg").write_bytes(b"legacy-media")
    database = vault / "db" / "lmz_main.db"
    database.parent.mkdir(parents=True)
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE sample (value TEXT)")
    connection.execute("INSERT INTO sample VALUES ('preserved')")
    connection.commit()
    connection.close()
    workspace_database = root / "data" / "workspace.db"
    workspace_database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(workspace_database)
    connection.execute("CREATE TABLE sample (value TEXT)")
    connection.execute("INSERT INTO sample VALUES ('workspace-preserved')")
    connection.commit()
    connection.close()
    (root / "data" / "topics").mkdir(parents=True)
    (root / "data" / "topics" / "topic.md").write_text("legacy topic", encoding="utf-8")
    (root / "secrets").mkdir()
    (root / "secrets" / "token.txt").write_text("secret-value", encoding="utf-8")
    (root / "data" / "models" / "model-a").mkdir(parents=True)
    (root / "data" / "models" / "model-a" / "weights.bin").write_bytes(b"model")
    (root / "config" / "data").mkdir()
    (root / "config" / "data" / "ambiguous.txt").write_text("do not copy", encoding="utf-8")
    return root


def test_content_adoption_uses_fresh_configs_and_preserves_source(monkeypatch, tmp_path: Path):
    source = _legacy_source(tmp_path / "legacy")
    target = tmp_path / ".lmz"
    monkeypatch.setenv("LMZ_DATA_ROOT", str(target))

    from app_paths import get_app_paths
    from config_repository import SettingsRepository, WorkspaceConfigRepository
    from content_adoption import adopt_legacy_content

    receipt = adopt_legacy_content(source, get_app_paths())

    assert target.is_dir()
    assert source.is_dir()
    assert (source / "data" / "vaults" / "default" / "vault" / "assets" / "item.jpg").is_file()
    assert (target / "default" / "data" / "vaults" / "default" / "vault" / "assets" / "item.jpg").read_bytes() == b"legacy-media"
    assert (target / "app" / "secrets" / "token.txt").read_text(encoding="utf-8") == "secret-value"
    assert (target / "app" / "models" / "model-a" / "weights.bin").read_bytes() == b"model"
    assert not (target / "default" / "config" / "data" / "ambiguous.txt").exists()

    settings = SettingsRepository(target / "app" / "settings.yaml").read().value
    config = WorkspaceConfigRepository(target / "default" / "config.yaml").read().value
    assert settings.ui.privacy_blur is False
    assert settings.tagging.device == "auto"
    assert config.vaults["default"].name == "Legacy Default"
    assert config.vaults["default"].root == "data/vaults/default"

    copied_db = sqlite3.connect(target / "default" / "data" / "vaults" / "default" / "db" / "lmz_main.db")
    try:
        assert copied_db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert copied_db.execute("SELECT value FROM sample").fetchone()[0] == "preserved"
    finally:
        copied_db.close()

    manifest = json.loads((target / "app" / "migration-manifest.json").read_text(encoding="utf-8"))
    assert manifest["algorithm"] == "sha256"
    assert any(entry["path"].endswith("item.jpg") for entry in manifest["files"])
    assert any(entry["path"].endswith("config.yaml.bak") for entry in manifest["files"])
    assert receipt["source_deleted"] is False
    assert receipt["ambiguous_paths"] == [str(source / "config" / "data")]


def test_content_adoption_refuses_existing_target_and_cleans_failed_stage(monkeypatch, tmp_path: Path):
    from app_paths import get_app_paths
    from content_adoption import ContentAdoptionError, adopt_legacy_content

    source = _legacy_source(tmp_path / "legacy")
    target = tmp_path / ".lmz"
    monkeypatch.setenv("LMZ_DATA_ROOT", str(target))
    target.mkdir()
    marker = target / "keep.txt"
    marker.write_text("untouched", encoding="utf-8")

    with pytest.raises(ContentAdoptionError, match="refusing to merge"):
        adopt_legacy_content(source, get_app_paths())
    assert marker.read_text(encoding="utf-8") == "untouched"

    target.rmdir() if not any(target.iterdir()) else marker.unlink()
    target.rmdir()
    (source / "data" / "vaults" / "default" / "broken.db").write_bytes(b"not sqlite")
    with pytest.raises(ContentAdoptionError, match="SQLite"):
        adopt_legacy_content(source, get_app_paths())
    assert not target.exists()
    assert not list(tmp_path.glob(".lmz-migrating-*"))
    assert (source / "data" / "vaults" / "default" / "broken.db").read_bytes() == b"not sqlite"


def test_legacy_detection_is_read_only_and_requires_the_expected_topology(tmp_path: Path):
    from content_adoption import detect_legacy_source

    source = _legacy_source(tmp_path / "legacy")
    marker = source / "data" / "topics" / "topic.md"
    original = marker.read_text(encoding="utf-8")

    assert detect_legacy_source([tmp_path / "missing", source]) == source.resolve()
    assert marker.read_text(encoding="utf-8") == original
    assert detect_legacy_source([tmp_path]) is None


def test_existing_target_adoption_preserves_app_state_and_secrets(monkeypatch, tmp_path: Path):
    source = _legacy_source(tmp_path / "legacy")
    target = tmp_path / ".lmz"
    monkeypatch.setenv("LMZ_DATA_ROOT", str(target))

    from app_paths import get_app_paths
    from config_repository import bootstrap_data_home
    from content_adoption import adopt_legacy_content_into_existing

    paths = get_app_paths()
    bootstrap_data_home(paths)
    settings_before = paths.settings_path.read_bytes()
    (paths.secrets_dir / "keep.txt").write_text("do not touch", encoding="utf-8")

    receipt = adopt_legacy_content_into_existing(source, paths)

    assert paths.settings_path.read_bytes() == settings_before
    assert (paths.secrets_dir / "keep.txt").read_text(encoding="utf-8") == "do not touch"
    assert not (paths.secrets_dir / "token.txt").exists()
    assert (paths.default_workspace_dir / "data" / "vaults" / "default" / "vault" / "assets" / "item.jpg").read_bytes() == b"legacy-media"
    assert (paths.models_dir / "model-a" / "weights.bin").read_bytes() == b"model"
    workspace_db = sqlite3.connect(paths.default_workspace_dir / "data" / "workspace.db")
    try:
        assert workspace_db.execute("SELECT value FROM sample").fetchone()[0] == "workspace-preserved"
    finally:
        workspace_db.close()
    assert receipt["legacy_secrets_touched"] is False
    assert receipt["target_settings_preserved"] is True
    assert Path(receipt["rollback_backup"]).is_dir()
    assert source.is_dir()


def test_external_legacy_workspace_config_conversion_keeps_backup(tmp_path: Path):
    source = _legacy_source(tmp_path / "external")

    from config_repository import WorkspaceConfigRepository
    from content_adoption import convert_legacy_workspace_config

    config_path = source / "config" / "config.yaml"
    original = config_path.read_bytes()
    result = convert_legacy_workspace_config(config_path)

    converted = WorkspaceConfigRepository(config_path).read().value
    assert converted.vaults["default"].name == "Legacy Default"
    assert converted.vaults["default"].root == "data/vaults/default"
    assert Path(result["legacy_backup"]).read_bytes() == original
    assert result["vault_count"] == 1
