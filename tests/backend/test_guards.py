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
