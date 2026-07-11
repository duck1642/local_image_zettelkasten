import importlib
import shutil
import sys
import tempfile
import time
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"


def fresh_api(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.delenv("LMZ_CONFIG_PATH", raising=False)
    monkeypatch.setenv("LMZ_DATA_ROOT", str(tmp_path / ".lmz"))
    monkeypatch.setenv("LMZ_AUTH_ROOT", str(tmp_path / "app-auth"))
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
    from app_paths import get_app_paths
    from config_repository import bootstrap_data_home

    bootstrap_data_home(get_app_paths())
    monkeypatch.setattr(common, "_api_key_path", lambda: tmp_path / "secrets" / ".api_key")
    return app_module


def write_registry(path: Path, active: str, workspaces: dict):
    for entry in workspaces.values():
        if entry.get("config_path") == "config/config.yaml":
            entry["config_path"] = "default/config.yaml"
    path.write_text(
        yaml.safe_dump({"schema_version": 1, "active_workspace": active, "workspaces": workspaces}, sort_keys=False),
        encoding="utf-8",
    )


def workspace_config(path: Path, vault_root: str = "data/vaults/default"):
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
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

    settings_response = client.get("/api/app/settings")
    assert settings_response.status_code == 200
    assert client.get("/api/runtime/session").json() == {"loaded": False}

    workspace_response = client.get("/api/workspaces")
    assert workspace_response.status_code == 200
    missing = [item for item in workspace_response.json()["items"] if item["id"] == "missing"][0]
    assert missing["exists"] is False

    logs_response = client.get("/api/logs/location")
    assert logs_response.status_code == 200
    assert logs_response.json()["mode"] == "startup"

    ui_log_response = client.post(
        "/api/logs/ui",
        json={"level": "INFO", "message": "launcher log probe", "extra": {}},
        headers={"X-LMZ-API-KEY": api_key(client)},
    )
    assert ui_log_response.status_code == 200
    assert ui_log_response.json()["status"] == "ok"


def test_launcher_mode_creates_lmz_workspace(monkeypatch, tmp_path):
    app_module = fresh_api(monkeypatch, tmp_path)
    workspaces = importlib.import_module("workspaces")
    registry_path = tmp_path / "workspaces.yaml"
    write_registry(
        registry_path,
        "default",
        {"default": {"name": "Default", "config_path": "config/config.yaml"}},
    )
    monkeypatch.setattr(workspaces, "REGISTRY_PATH", registry_path)

    client = TestClient(app_module.app)
    key = api_key(client)
    parent = (Path(tempfile.gettempdir()) / f"lmz-api-workspace-{time.time_ns()}").resolve()

    try:
        response = client.post(
            "/api/workspaces",
            json={"path": str(parent), "name": "API Workspace"},
            headers={"X-LMZ-API-KEY": key},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "success"
        config_path = parent / "lmz" / "config.yaml"
        assert Path(payload["workspace"]["config_path"]) == config_path
        saved_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert saved_config["vaults"]["default"]["root"] == "data/vaults/default"
        assert "paths" not in saved_config
        assert set(saved_config) == {"schema_version", "active_vault", "vaults"}
        assert Path(payload["workspace"]["marker_path"]).exists()
        assert payload["workspace"]["managed"] is True
        assert not (parent / "lmz" / "data" / "models").exists()
        assert not (parent / "lmz" / "data" / "secrets").exists()
        load = client.post("/api/workspaces/api-workspace/load", headers={"X-LMZ-API-KEY": key})
        assert load.status_code == 200
        assert load.json()["status"] == "success"
    finally:
        shutil.rmtree(parent, ignore_errors=True)


def test_workspace_delete_api_uses_explicit_full_mode(monkeypatch, tmp_path):
    app_module = fresh_api(monkeypatch, tmp_path)
    workspaces = importlib.import_module("workspaces")
    registry_path = tmp_path / "workspaces.yaml"
    write_registry(
        registry_path,
        "default",
        {"default": {"name": "Default", "config_path": "config/config.yaml"}},
    )
    monkeypatch.setattr(workspaces, "REGISTRY_PATH", registry_path)
    client = TestClient(app_module.app)
    key = api_key(client)
    parent = (Path(tempfile.gettempdir()) / f"lmz-api-delete-{time.time_ns()}").resolve()

    try:
        loaded = client.post("/api/workspaces/default/load", headers={"X-LMZ-API-KEY": key})
        assert loaded.status_code == 200
        created = client.post(
            "/api/workspaces",
            json={"path": str(parent), "name": "Delete Me"},
            headers={"X-LMZ-API-KEY": key},
        )
        assert created.status_code == 200
        workspace_id = next(item["id"] for item in created.json()["items"] if item["name"] == "Delete Me")

        deleted = client.delete(
            f"/api/workspaces/{workspace_id}?mode=all",
            headers={"X-LMZ-API-KEY": key},
        )

        assert deleted.status_code == 200
        assert deleted.json()["mode"] == "all"
        assert deleted.json()["cleanup_status"] == "complete"
        assert not (parent / "lmz").exists()
    finally:
        shutil.rmtree(parent, ignore_errors=True)



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
    assert workspaces.load_workspace_registry()["active_workspace"] == "default"


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
    assert client.get("/api/logs/location").json()["mode"] == "startup"
    assert workspaces.load_workspace_registry()["active_workspace"] == "default"


def test_fresh_clone_default_workspace_initializes_missing_data(monkeypatch, tmp_path):
    app_module = fresh_api(monkeypatch, tmp_path)
    runtime_context = importlib.import_module("runtime_context")
    workspaces = importlib.import_module("workspaces")
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    workspace_config(config_path)
    registry_path = config_dir / "workspaces.yaml"
    write_registry(
        registry_path,
        "default",
        {"default": {"name": "Default", "config_path": str(config_path)}},
    )
    monkeypatch.setattr(workspaces, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(workspaces, "REGISTRY_PATH", registry_path)
    monkeypatch.setattr(runtime_context, "PROJECT_ROOT", tmp_path)
    patch_runtime_services(monkeypatch)

    client = TestClient(app_module.app)
    response = client.post(
        "/api/workspaces/default/load",
        headers={"X-LMZ-API-KEY": api_key(client)},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert (config_dir / "data" / "vaults" / "default" / "vault" / "assets").is_dir()
    assert (config_dir / "data" / "vaults" / "default" / "db" / "lmz_main.db").is_file()


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
    assert client.get("/api/logs/location").json()["mode"] == "vault"
    assert workspaces.load_workspace_registry()["active_workspace"] == "ready"


def test_vault_relocation_activates_runtime_and_vault_logs(monkeypatch, tmp_path):
    app_module = fresh_api(monkeypatch, tmp_path)
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
    patch_runtime_services(monkeypatch)

    client = TestClient(app_module.app)
    key = api_key(client)
    response = client.post("/api/workspaces/offline-vault/load", headers={"X-LMZ-API-KEY": key})
    assert response.json()["status"] == "relocate_vault"

    vault_root = ws_root / "data" / "vaults" / "default"
    vault_root.mkdir(parents=True)
    relocate = client.post(
        "/api/vaults/relocate",
        json={"vault_id": "default", "new_vault_root": str(vault_root)},
        headers={"X-LMZ-API-KEY": key},
    )

    assert relocate.status_code == 200
    assert relocate.json()["status"] == "success"
    saved_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved_config["vaults"]["default"]["root"] == "data/vaults/default"
    location = client.get("/api/logs/location").json()
    assert location["mode"] == "vault"
    assert location["vault"] == "default"


def test_vault_relocation_rejects_outside_workspace(monkeypatch, tmp_path):
    app_module = fresh_api(monkeypatch, tmp_path)
    workspaces = importlib.import_module("workspaces")
    registry_path = tmp_path / "workspaces.yaml"
    ws_root = tmp_path / "workspace"
    ws_root.mkdir()
    config_path = ws_root / "config.yaml"
    workspace_config(config_path)
    vault_root = ws_root / "data" / "vaults" / "default"
    vault_root.mkdir(parents=True)
    outside_root = tmp_path / "outside-vault"
    outside_root.mkdir()
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
    key = api_key(client)
    response = client.post("/api/workspaces/ready/load", headers={"X-LMZ-API-KEY": key})
    assert response.json()["status"] == "success"

    relocate = client.post(
        "/api/vaults/relocate",
        json={"vault_id": "default", "new_vault_root": str(outside_root)},
        headers={"X-LMZ-API-KEY": key},
    )

    assert relocate.status_code == 400
    saved_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved_config["vaults"]["default"]["root"] == "data/vaults/default"
