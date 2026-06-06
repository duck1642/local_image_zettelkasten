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


def workspace_config(path: Path, vault_root: str = "data/vaults/default"):
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


def patch_runtime_services(monkeypatch: pytest.MonkeyPatch):
    metadata_index = importlib.import_module("metadata_index")
    search_manager_module = importlib.import_module("db.search_manager")
    monkeypatch.setattr(metadata_index, "restart_metadata_watchdog", lambda *args, **kwargs: None)
    monkeypatch.setattr(metadata_index, "start_metadata_repair_worker", lambda *args, **kwargs: None)
    monkeypatch.setattr(search_manager_module.search_manager, "reset_all", lambda *args, **kwargs: None)
    monkeypatch.setattr(search_manager_module.search_manager, "hydrate", lambda *args, **kwargs: None)


def test_launcher_mode_serves_recovery_routes_without_workspace(monkeypatch, tmp_path):
    app_module = fresh_api(monkeypatch, tmp_path)
    runtime_context = importlib.import_module("runtime_context")
    workspaces = importlib.import_module("workspaces")
    registry_path = tmp_path / "workspaces.yaml"
    missing_config = tmp_path / "missing" / "config.yaml"
    write_registry(
        registry_path,
        "missing",
        {
            "default": {"name": "Default", "config_path": "config/config.yaml"},
            "missing": {"name": "Missing", "config_path": str(missing_config)},
        },
    )
    monkeypatch.setattr(workspaces, "REGISTRY_PATH", registry_path)

    client = TestClient(app_module.app)
    assert runtime_context.has_runtime_context() is False
    assert client.get("/").status_code == 200

    config_response = client.get("/api/config")
    assert config_response.status_code == 503
    assert config_response.json()["detail"] == "Workspace not loaded"

    workspace_response = client.get("/api/workspaces")
    assert workspace_response.status_code == 200
    missing = [item for item in workspace_response.json()["items"] if item["id"] == "missing"][0]
    assert missing["exists"] is False


def test_missing_workspace_config_load_does_not_persist_active(monkeypatch, tmp_path):
    app_module = fresh_api(monkeypatch, tmp_path)
    workspaces = importlib.import_module("workspaces")
    registry_path = tmp_path / "workspaces.yaml"
    missing_config = tmp_path / "offline" / "config.yaml"
    write_registry(
        registry_path,
        "default",
        {
            "default": {"name": "Default", "config_path": "config/config.yaml"},
            "offline": {"name": "Offline", "config_path": str(missing_config)},
        },
    )
    monkeypatch.setattr(workspaces, "REGISTRY_PATH", registry_path)

    client = TestClient(app_module.app)
    response = client.post(
        "/api/workspaces/offline/load",
        headers={"X-LMZ-API-KEY": api_key(client)},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "relocate_workspace"
    assert workspaces.load_workspace_registry()["active"] == "default"


def test_missing_vault_root_load_enables_vault_relocation(monkeypatch, tmp_path):
    app_module = fresh_api(monkeypatch, tmp_path)
    runtime_context = importlib.import_module("runtime_context")
    workspaces = importlib.import_module("workspaces")
    registry_path = tmp_path / "workspaces.yaml"
    ws_root = tmp_path / "workspace"
    ws_root.mkdir()
    config_path = ws_root / "config.yaml"
    workspace_config(config_path)
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
    response = client.post(
        "/api/workspaces/offline-vault/load",
        headers={"X-LMZ-API-KEY": api_key(client)},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "relocate_vault"
    assert runtime_context.has_runtime_context() is True
    vaults_response = client.get("/api/vaults")
    assert vaults_response.status_code == 200
    assert vaults_response.json()["items"][0]["exists"] is False
    assert workspaces.load_workspace_registry()["active"] == "default"


def test_valid_workspace_load_persists_active_after_services_start(monkeypatch, tmp_path):
    app_module = fresh_api(monkeypatch, tmp_path)
    workspaces = importlib.import_module("workspaces")
    registry_path = tmp_path / "workspaces.yaml"
    ws_root = tmp_path / "workspace"
    vault_root = ws_root / "data" / "vaults" / "default"
    (vault_root / "vault" / "assets").mkdir(parents=True)
    config_path = ws_root / "config.yaml"
    workspace_config(config_path)
    write_registry(
        registry_path,
        "default",
        {
            "default": {"name": "Default", "config_path": "config/config.yaml"},
            "ready": {"name": "Ready", "config_path": str(config_path)},
        },
    )
    monkeypatch.setattr(workspaces, "REGISTRY_PATH", registry_path)
    patch_runtime_services(monkeypatch)

    client = TestClient(app_module.app)
    response = client.post(
        "/api/workspaces/ready/load",
        headers={"X-LMZ-API-KEY": api_key(client)},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["active_workspace"] == "ready"
    assert response.json()["active_vault"] == "default"
    assert workspaces.load_workspace_registry()["active"] == "ready"
