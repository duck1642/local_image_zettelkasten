import importlib
import sys
from pathlib import Path
import pytest
import yaml
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"

def fresh_api(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.delenv("LMZ_CONFIG_PATH", raising=False)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    for name in list(sys.modules):
        if name in {
            "api",
            "utils",
            "runtime_context",
            "runtime_activation",
            "web_api",
            "workspaces",
            "queue_service",
            "md_generator",
            "metadata_index",
            "metadata_maintenance",
            "processor",
            "external_ingestion",
            "thumbnails",
            "fingerprint",
            "artists",
            "platforms",
            "review_cache",
            "topics",
            "vaults",
            "workspace_db",
            "ingest_control",
        } or name.startswith(("api.", "logger", "db.", "tagging", "downloaders")):
            del sys.modules[name]
    app_module = importlib.import_module("api.app")
    common = importlib.import_module("api.common")
    monkeypatch.setattr(common, "_api_key_path", lambda: tmp_path / "secrets" / ".api_key")
    return app_module

def write_registry(path: Path, active: str, workspaces: dict):
    path.write_text(
        yaml.safe_dump({"active": active, "workspaces": workspaces}, sort_keys=False),
        encoding="utf-8",
    )

def workspace_config(path: Path, vault_root: str):
    path.write_text(
        yaml.safe_dump(
            {
                "active_vault": "default",
                "vaults": {"default": {"name": "Default", "root": vault_root}},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

def api_key(client: TestClient) -> str:
    response = client.get("/api/session-key")
    assert response.status_code == 200
    return response.json()["key"]

def test_missing_vault_root_returns_503_and_does_not_create_files(monkeypatch, tmp_path):
    app_module = fresh_api(monkeypatch, tmp_path)
    runtime_context = importlib.import_module("runtime_context")
    workspaces = importlib.import_module("workspaces")

    registry_path = tmp_path / "workspaces.yaml"
    ws_root = tmp_path / "workspace"
    ws_root.mkdir()

    # Path to a vault root that does NOT exist
    missing_vault_root = ws_root / "data" / "vaults" / "default"

    config_path = ws_root / "config.yaml"
    workspace_config(config_path, vault_root=str(missing_vault_root))

    write_registry(
        registry_path,
        "default",
        {
            "default": {"name": "Default", "config_path": "config/config.yaml"},
            "offline-vault": {"name": "Offline Vault", "config_path": str(config_path)},
        },
    )
    monkeypatch.setattr(workspaces, "REGISTRY_PATH", registry_path)

    client = TestClient(app_module.app)

    # Load workspace - this should succeed but return relocate_vault status because vault is offline
    response = client.post(
        "/api/workspaces/offline-vault/load",
        headers={"X-LMZ-API-KEY": api_key(client)},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "relocate_vault"
    assert runtime_context.has_runtime_context() is True

    # Assert missing vault root folder and db path do not exist initially
    assert not missing_vault_root.exists()

    # Now try to hit the guarded endpoints: /api/items and /api/stats
    items_response = client.get(
        "/api/items",
        headers={"X-LMZ-API-KEY": api_key(client)},
    )
    assert items_response.status_code == 503
    assert "Active vault is offline or missing" in items_response.json()["detail"]

    stats_response = client.get(
        "/api/stats",
        headers={"X-LMZ-API-KEY": api_key(client)},
    )
    assert stats_response.status_code == 503
    assert "Active vault is offline or missing" in stats_response.json()["detail"]

    # Crucial assertion: the missing vault directory was NOT created, and no database file exists
    assert not missing_vault_root.exists()


def test_config_save_rejects_absolute_vault_root(monkeypatch, tmp_path):
    app_module = fresh_api(monkeypatch, tmp_path)
    workspaces = importlib.import_module("workspaces")

    registry_path = tmp_path / "workspaces.yaml"
    ws_root = tmp_path / "workspace"
    ws_root.mkdir()
    vault_root = ws_root / "data" / "vaults" / "default"
    vault_root.mkdir(parents=True)
    config_path = ws_root / "config.yaml"
    workspace_config(config_path, "data/vaults/default")

    write_registry(
        registry_path,
        "default",
        {
            "default": {"name": "Default", "config_path": "config/config.yaml"},
            "ready": {"name": "Ready", "config_path": str(config_path)},
        },
    )
    monkeypatch.setattr(workspaces, "REGISTRY_PATH", registry_path)

    client = TestClient(app_module.app)
    key = api_key(client)
    load = client.post("/api/workspaces/ready/load", headers={"X-LMZ-API-KEY": key})
    assert load.status_code == 200
    assert load.json()["status"] == "success"

    outside_root = tmp_path / "outside"
    response = client.post(
        "/api/config",
        json={"active_vault": "default", "vaults": {"default": {"name": "Default", "root": str(outside_root)}}},
        headers={"X-LMZ-API-KEY": key},
    )

    assert response.status_code == 400
    assert "vaults.default.root must be relative" in response.text


def test_config_save_rejects_legacy_models_path(monkeypatch, tmp_path):
    app_module = fresh_api(monkeypatch, tmp_path)
    workspaces = importlib.import_module("workspaces")

    registry_path = tmp_path / "workspaces.yaml"
    ws_root = tmp_path / "workspace"
    ws_root.mkdir()
    vault_root = ws_root / "data" / "vaults" / "default"
    vault_root.mkdir(parents=True)
    config_path = ws_root / "config.yaml"
    workspace_config(config_path, "data/vaults/default")

    write_registry(
        registry_path,
        "default",
        {
            "default": {"name": "Default", "config_path": "config/config.yaml"},
            "ready": {"name": "Ready", "config_path": str(config_path)},
        },
    )
    monkeypatch.setattr(workspaces, "REGISTRY_PATH", registry_path)

    client = TestClient(app_module.app)
    key = api_key(client)
    load = client.post("/api/workspaces/ready/load", headers={"X-LMZ-API-KEY": key})
    assert load.status_code == 200
    assert load.json()["status"] == "success"

    response = client.post(
        "/api/config",
        json={
            "active_vault": "default",
            "vaults": {"default": {"name": "Default", "root": "data/vaults/default"}},
            "paths": {"models": "data/models", "secrets": "data/secrets"},
        },
        headers={"X-LMZ-API-KEY": key},
    )

    assert response.status_code == 400
    assert "paths.models is no longer supported" in response.text


def test_delete_vault_refuses_outside_workspace_root(monkeypatch, tmp_path):
    app_module = fresh_api(monkeypatch, tmp_path)
    workspaces = importlib.import_module("workspaces")

    registry_path = tmp_path / "workspaces.yaml"
    ws_root = tmp_path / "workspace"
    ws_root.mkdir()
    default_root = ws_root / "data" / "vaults" / "default"
    default_root.mkdir(parents=True)
    outside_root = tmp_path / "outside-vault"
    outside_root.mkdir()
    config_path = ws_root / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "active_vault": "default",
                "vaults": {
                    "default": {"name": "Default", "root": "data/vaults/default"},
                    "bad": {"name": "Bad", "root": str(outside_root)},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    write_registry(
        registry_path,
        "default",
        {
            "default": {"name": "Default", "config_path": "config/config.yaml"},
            "ready": {"name": "Ready", "config_path": str(config_path)},
        },
    )
    monkeypatch.setattr(workspaces, "REGISTRY_PATH", registry_path)

    client = TestClient(app_module.app)
    key = api_key(client)
    load = client.post("/api/workspaces/ready/load", headers={"X-LMZ-API-KEY": key})
    assert load.status_code == 200
    assert load.json()["status"] == "success"

    response = client.delete("/api/vaults/bad?confirm=true", headers={"X-LMZ-API-KEY": key})

    assert response.status_code == 400
    assert outside_root.exists()

def test_vault_merge_safety_and_defaults(monkeypatch, tmp_path):
    app_module = fresh_api(monkeypatch, tmp_path)
    workspaces = importlib.import_module("workspaces")
    db_sqlite = importlib.import_module("db.sqlite_operator")

    registry_path = tmp_path / "workspaces.yaml"
    ws_root = tmp_path / "workspace"
    ws_root.mkdir()

    active_root = ws_root / "data" / "vaults" / "active"
    active_root.mkdir(parents=True)
    target_root = ws_root / "data" / "vaults" / "target"
    target_root.mkdir(parents=True)
    source_root = ws_root / "data" / "vaults" / "source"
    source_root.mkdir(parents=True)

    config_path = ws_root / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "active_vault": "active",
                "vaults": {
                    "active": {"name": "Active", "root": "data/vaults/active"},
                    "target": {"name": "Target", "root": "data/vaults/target"},
                    "source": {"name": "Source", "root": "data/vaults/source"},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    write_registry(
        registry_path,
        "ready",
        {
            "default": {"name": "Default", "config_path": "config/config.yaml"},
            "ready": {"name": "Ready", "config_path": str(config_path)},
        },
    )
    monkeypatch.setattr(workspaces, "REGISTRY_PATH", registry_path)

    client = TestClient(app_module.app)
    key = api_key(client)
    load = client.post("/api/workspaces/ready/load", headers={"X-LMZ-API-KEY": key})
    assert load.status_code == 200

    # 1. Source DB is missing
    preview_res = client.post(
        "/api/vaults/merge-preview",
        json={"name": "Merged Guard", "source_vault_ids": ["target", "source"]},
        headers={"X-LMZ-API-KEY": key},
    )
    assert preview_res.status_code == 400
    assert "source database is missing" in preview_res.json()["detail"]

    merge_res = client.post(
        "/api/vaults/merge",
        json={"name": "Merged Guard", "source_vault_ids": ["target", "source"]},
        headers={"X-LMZ-API-KEY": key},
    )
    assert merge_res.status_code == 400
    assert "source database is missing" in merge_res.json()["detail"]

    # Initialize source DBs
    db_sqlite.init_database(target_root / "db" / "lmz_main.db")
    db_sqlite.init_database(source_root / "db" / "lmz_main.db")

    # 2. New merged-vault endpoints create a separate vault from selected sources
    preview_res = client.post(
        "/api/vaults/merge-preview",
        json={"name": "Merged Guard", "source_vault_ids": ["target", "source"]},
        headers={"X-LMZ-API-KEY": key},
    )
    assert preview_res.status_code == 200
    assert preview_res.json()["vault"] == "merged-guard"

    merge_res = client.post(
        "/api/vaults/merge",
        json={"name": "Merged Guard", "source_vault_ids": ["target", "source"]},
        headers={"X-LMZ-API-KEY": key},
    )
    assert merge_res.status_code == 200
    assert source_root.exists()
    assert (ws_root / "data" / "vaults" / "merged-guard").exists()


def test_vault_repair_safety(monkeypatch, tmp_path):
    app_module = fresh_api(monkeypatch, tmp_path)
    workspaces = importlib.import_module("workspaces")
    db_sqlite = importlib.import_module("db.sqlite_operator")

    registry_path = tmp_path / "workspaces.yaml"
    ws_root = tmp_path / "workspace"
    ws_root.mkdir()

    default_root = ws_root / "data" / "vaults" / "default"
    default_root.mkdir(parents=True)
    db_sqlite.init_database(default_root / "db" / "lmz_main.db")

    config_path = ws_root / "config.yaml"
    workspace_config(config_path, vault_root="data/vaults/default")

    write_registry(
        registry_path,
        "ready",
        {
            "default": {"name": "Default", "config_path": "config/config.yaml"},
            "ready": {"name": "Ready", "config_path": str(config_path)},
        },
    )
    monkeypatch.setattr(workspaces, "REGISTRY_PATH", registry_path)

    client = TestClient(app_module.app)
    key = api_key(client)
    load = client.post("/api/workspaces/ready/load", headers={"X-LMZ-API-KEY": key})
    assert load.status_code == 200

    # 1. Destructive actions without confirm (implicit/empty actions list) -> 400
    res = client.post(
        "/api/vaults/default/repair",
        json={},
        headers={"X-LMZ-API-KEY": key},
    )
    assert res.status_code == 400
    assert "destructive actions require confirmation" in res.json()["detail"]

    # 2. Destructive actions without confirm (explicit actions list containing derived_cache) -> 400
    res = client.post(
        "/api/vaults/default/repair",
        json={"actions": ["derived_cache"]},
        headers={"X-LMZ-API-KEY": key},
    )
    assert res.status_code == 400
    assert "destructive actions require confirmation" in res.json()["detail"]

    # 3. Non-destructive actions only (e.g. thumbnails) without confirm -> 200
    res = client.post(
        "/api/vaults/default/repair",
        json={"actions": ["thumbnails"]},
        headers={"X-LMZ-API-KEY": key},
    )
    assert res.status_code == 200

    # 4. Destructive actions with confirm (implicit/empty actions list) -> 200
    res = client.post(
        "/api/vaults/default/repair",
        json={"confirm_destructive": True},
        headers={"X-LMZ-API-KEY": key},
    )
    assert res.status_code == 200

    # 5. Destructive actions with confirm (explicit actions list containing derived_cache) -> 200
    res = client.post(
        "/api/vaults/default/repair",
        json={"actions": ["derived_cache"], "confirm_destructive": True},
        headers={"X-LMZ-API-KEY": key},
    )
    assert res.status_code == 200
