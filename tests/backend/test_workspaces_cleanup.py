import importlib
import json
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


@pytest.fixture
def workspace_case(monkeypatch, tmp_path):
    workspaces = importlib.import_module("workspaces")
    registry_path = tmp_path / "workspaces.yaml"
    monkeypatch.setattr(workspaces, "REGISTRY_PATH", registry_path)
    monkeypatch.setattr(workspaces, "PROJECT_ROOT", tmp_path / "runtime-install")

    workspace_root = tmp_path / "external" / "lmz"
    workspace_root.mkdir(parents=True)
    config_path = workspace_root / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "active_vault": "default",
                "vaults": {
                    "default": {"name": "Default", "root": "data/vaults/default"},
                    "archive": {"name": "Archive", "root": "data/vaults/archive"},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    registry = {
        "schema_version": 1,
        "active_workspace": "default",
        "workspaces": {
            "default": {"name": "Default", "config_path": "default/config.yaml"},
            "external": {"name": "External", "config_path": str(config_path)},
        },
    }
    registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")
    return workspaces, registry_path, workspace_root, config_path


def write_file(path: Path, value: str = "data") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return path


def read_registry(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def add_marker(workspaces, workspace_root: Path) -> Path:
    marker = workspace_root / workspaces.WORKSPACE_MARKER_NAME
    marker.write_text(json.dumps(workspaces.WORKSPACE_MARKER_PAYLOAD), encoding="utf-8")
    return marker


def test_unregister_leaves_workspace_files_untouched(workspace_case):
    workspaces, registry_path, workspace_root, config_path = workspace_case
    unknown = write_file(workspace_root / "personal-document.txt")

    result = workspaces.delete_workspace("external", mode="unregister")

    assert result["cleanup_status"] == "not_requested"
    assert "external" not in read_registry(registry_path)["workspaces"]
    assert config_path.exists()
    assert unknown.exists()


def test_generated_cleanup_deletes_only_owned_metadata_and_caches(workspace_case):
    workspaces, registry_path, workspace_root, config_path = workspace_case
    marker = add_marker(workspaces, workspace_root)
    generated = [
        write_file(workspace_root / "data" / "workspace.db"),
        write_file(workspace_root / "data" / "topics" / "topic.md"),
    ]
    for vault_id in ("default", "archive"):
        vault_root = workspace_root / "data" / "vaults" / vault_id
        generated.extend(
            [
                write_file(vault_root / "db" / "lmz_main.db"),
                write_file(vault_root / "logs" / "structured" / "backend.jsonl"),
                write_file(vault_root / "queues" / "queue.json"),
                write_file(vault_root / "batches" / "batch.json"),
                write_file(vault_root / "wd-tags" / "aa" / "tag.json"),
                write_file(vault_root / "ui_cache" / "thumbnails" / "aa" / "thumb.jpg"),
            ]
        )

    preserved = [
        write_file(workspace_root / "data" / "secrets" / "cookies.txt", "legacy secret"),
        write_file(workspace_root / "personal-document.txt"),
        write_file(workspace_root / "data" / "models" / "legacy.bin"),
        write_file(workspace_root / "data" / "vaults" / "default" / "vault" / "assets" / "aa" / "image.jpg"),
        write_file(workspace_root / "data" / "vaults" / "default" / "vault" / "notes" / "aa" / "note.md"),
        write_file(workspace_root / "data" / "vaults" / "default" / "input" / "source.jpg"),
        write_file(workspace_root / "data" / "vaults" / "default" / "review" / "pending.jpg"),
        write_file(workspace_root / "data" / "vaults" / "default" / "local_ingest" / "run" / "source.jpg"),
        write_file(workspace_root / "data" / "vaults" / "default" / "online_ingest" / "run" / "source.jpg"),
        write_file(workspace_root / "data" / "vaults" / "default" / "quarantine" / "recovery.jpg"),
    ]

    result = workspaces.delete_workspace("external", mode="generated")

    assert result["cleanup_status"] == "complete"
    assert "external" not in read_registry(registry_path)["workspaces"]
    assert not config_path.exists()
    assert not marker.exists()
    assert all(not path.exists() for path in generated)
    assert all(path.exists() for path in preserved)


def test_full_cleanup_requires_valid_ownership_marker(workspace_case):
    workspaces, registry_path, workspace_root, _ = workspace_case
    preserved = write_file(workspace_root / "personal-document.txt")

    with pytest.raises(ValueError, match="ownership marker"):
        workspaces.delete_workspace("external", mode="all")

    assert "external" in read_registry(registry_path)["workspaces"]
    assert preserved.exists()


def test_full_cleanup_removes_owned_workspace_root(workspace_case):
    workspaces, registry_path, workspace_root, _ = workspace_case
    add_marker(workspaces, workspace_root)
    write_file(workspace_root / "personal-document.txt")

    result = workspaces.delete_workspace("external", mode="all")

    assert result["cleanup_status"] == "complete"
    assert "external" not in read_registry(registry_path)["workspaces"]
    assert not workspace_root.exists()


def test_staging_failure_restores_files_and_preserves_registration(workspace_case, monkeypatch):
    workspaces, registry_path, workspace_root, config_path = workspace_case
    marker = add_marker(workspaces, workspace_root)
    database = write_file(workspace_root / "data" / "workspace.db")
    real_move = workspaces._move_path
    calls = 0

    def fail_second_move(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("locked path")
        return real_move(source, destination)

    monkeypatch.setattr(workspaces, "_move_path", fail_second_move)

    with pytest.raises(workspaces.WorkspaceDeletionError, match="locked path"):
        workspaces.delete_workspace("external", mode="generated")

    assert "external" in read_registry(registry_path)["workspaces"]
    assert config_path.exists()
    assert marker.exists()
    assert database.exists()


def test_registry_failure_restores_staged_files(workspace_case, monkeypatch):
    workspaces, registry_path, workspace_root, config_path = workspace_case
    marker = add_marker(workspaces, workspace_root)
    database = write_file(workspace_root / "data" / "workspace.db")

    def fail_registry_write(_registry):
        raise OSError("registry unavailable")

    monkeypatch.setattr(workspaces, "save_workspace_registry", fail_registry_write)

    with pytest.raises(workspaces.WorkspaceDeletionError, match="registry unavailable"):
        workspaces.delete_workspace("external", mode="generated")

    assert "external" in read_registry(registry_path)["workspaces"]
    assert config_path.exists()
    assert marker.exists()
    assert database.exists()


def test_purge_failure_returns_recoverable_cleanup_path(workspace_case, monkeypatch):
    workspaces, registry_path, workspace_root, config_path = workspace_case
    add_marker(workspaces, workspace_root)
    write_file(workspace_root / "data" / "workspace.db")

    def fail_purge(_path):
        raise OSError("antivirus lock")

    monkeypatch.setattr(workspaces, "_purge_staging_dir", fail_purge)

    result = workspaces.delete_workspace("external", mode="generated")

    assert result["cleanup_status"] == "pending"
    cleanup_path = Path(result["cleanup_path"])
    assert cleanup_path.exists()
    assert "external" not in read_registry(registry_path)["workspaces"]
    assert not config_path.exists()


def test_active_workspace_cannot_be_deleted(workspace_case):
    workspaces, registry_path, _, _ = workspace_case
    registry = read_registry(registry_path)
    registry["active_workspace"] = "external"
    registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="active workspace"):
        workspaces.delete_workspace("external", mode="unregister")

    assert "external" in read_registry(registry_path)["workspaces"]


def test_generated_cleanup_rejects_vault_root_outside_workspace(workspace_case, tmp_path):
    from config_repository import ConfigReadError
    workspaces, registry_path, _, config_path = workspace_case
    outside = tmp_path / "outside-vault"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["vaults"]["default"]["root"] = str(outside)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    with pytest.raises(ConfigReadError, match="workspace-relative"):
        workspaces.delete_workspace("external", mode="generated")

    assert "external" in read_registry(registry_path)["workspaces"]
    assert config_path.exists()
