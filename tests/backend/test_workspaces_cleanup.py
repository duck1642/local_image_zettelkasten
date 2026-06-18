import pytest
from pathlib import Path
import yaml
import importlib
import sys

# Setup sys.path so backend modules are importable
ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

def test_delete_workspace_cleanup_files(monkeypatch, tmp_path):
    workspaces = importlib.import_module("workspaces")
    
    registry_path = tmp_path / "workspaces.yaml"
    monkeypatch.setattr(workspaces, "REGISTRY_PATH", registry_path)
    
    # Setup workspace paths
    ws_root = tmp_path / "test-workspace-cleanup"
    ws_root.mkdir()
    config_path = ws_root / "config.yaml"
    
    # Write registry
    registry = {
        "active": "test-ws",
        "workspaces": {
            "default": {"name": "Default", "config_path": "config/config.yaml"},
            "test-ws": {"name": "Test Workspace", "config_path": str(config_path)},
        }
    }
    registry_path.write_text(yaml.safe_dump(registry), encoding="utf-8")
    
    # Create configuration file
    config_path.write_text(yaml.safe_dump({"vaults": {}}), encoding="utf-8")
    
    # Create dummy app files
    db_file = ws_root / "data" / "vaults" / "default" / "db" / "lmz_main.db"
    db_file.parent.mkdir(parents=True, exist_ok=True)
    db_file.write_text("dummy db content")
    
    log_file = ws_root / "data" / "vaults" / "default" / "logs" / "raw" / "terminal.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text("dummy log content")
    
    incomplete_file = ws_root / "data" / "models" / "wd-vit-tagger-v3" / ".cache" / "huggingface" / "download" / "file.incomplete"
    incomplete_file.parent.mkdir(parents=True, exist_ok=True)
    incomplete_file.write_text("dummy incomplete")
    
    gitignore_file = ws_root / "data" / "models" / "wd-vit-tagger-v3" / ".cache" / "huggingface" / ".gitignore"
    gitignore_file.parent.mkdir(parents=True, exist_ok=True)
    gitignore_file.write_text("dummy gitignore")
    
    # Create user vault notes/assets
    note_file = ws_root / "data" / "vaults" / "default" / "vault" / "notes" / "04" / "note.md"
    note_file.parent.mkdir(parents=True, exist_ok=True)
    note_file.write_text("important user note")
    
    asset_file = ws_root / "data" / "vaults" / "default" / "vault" / "assets" / "04" / "image.png"
    asset_file.parent.mkdir(parents=True, exist_ok=True)
    asset_file.write_text("important user image")
    
    # Assert everything exists before delete
    assert config_path.exists()
    assert db_file.exists()
    assert log_file.exists()
    assert incomplete_file.exists()
    assert gitignore_file.exists()
    assert note_file.exists()
    assert asset_file.exists()
    
    # Perform deletion with delete_files=True
    workspaces.delete_workspace("test-ws", delete_files=True)
    
    # Verify workspaces registry
    updated_registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    assert "test-ws" not in updated_registry["workspaces"]
    assert updated_registry["active"] == "default"
    
    # Verify file deletion and retention
    assert not config_path.exists()
    assert not db_file.exists()
    assert not log_file.exists()
    assert not incomplete_file.exists()
    assert not gitignore_file.exists()
    
    # Vault files must be protected
    assert note_file.exists()
    assert asset_file.exists()
    
    # Non-empty directories must remain, but empty ones should be deleted
    assert not (ws_root / "data" / "models").exists()
    assert not (ws_root / "data" / "vaults" / "default" / "db").exists()
    assert not (ws_root / "data" / "vaults" / "default" / "logs").exists()
    assert (ws_root / "data" / "vaults" / "default" / "vault" / "notes" / "04").exists()
    assert (ws_root / "data" / "vaults" / "default" / "vault" / "assets" / "04").exists()
