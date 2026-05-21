import asyncio
import concurrent.futures
import importlib
import inspect
import io
import json
import logging
import os
import re
import runpy
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

import pytest
import yaml
from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FIXTURE = ROOT / "tests" / "fixtures" / "mock-vault"


def fresh_backend(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *module_names: str):
    work = tmp_path / "mock-vault"
    shutil.copytree(FIXTURE, work)
    monkeypatch.setenv("LMZ_CONFIG_PATH", str(work / "config.yaml"))
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    for name in list(sys.modules):
        if name in {"utils", "runtime_context", "web_api", "queue_service", "md_generator", "metadata_index", "processor", "external_ingestion", "thumbnails", "fingerprint", "artists", "platforms", "review_cache", "topics", "vaults", "workspace_db"} or name.startswith(("logger", "db.", "tagging", "downloaders")):
            del sys.modules[name]
    return [importlib.import_module(name) for name in module_names]


def insert_mock_item(sqlite_operator, item_hash: str, artist: str = "DB Artist", date_added: str = "2026-01-02 03:04:05"):
    conn = sqlite_operator.init_database()
    storage_id = sqlite_operator.allocate_storage_id(conn)
    conn.execute(
        """
        INSERT INTO items(hash, storage_id, original_filename, file_extension, mime_type, size_bytes, date_added, source_url, source_url_norm, platform, source_artist, phash)
        VALUES (?, ?, ?, '.jpg', 'image/jpeg', 10, ?, '', '', 'local', ?, '')
        """,
        (item_hash, storage_id, f"{item_hash}.jpg", date_added, artist),
    )
    conn.commit()
    return conn


def storage_id_for(conn, item_hash: str) -> str:
    row = conn.execute("SELECT storage_id FROM items WHERE hash = ?", (item_hash,)).fetchone()
    assert row and row[0]
    return row[0]


def frontmatter_from_markdown(text: str) -> dict:
    return yaml.safe_load(text.split("---", 2)[1]) or {}


def load_maintenance_tool(name: str):
    tool_path = ROOT / "tools" / "maintenance" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", tool_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_maintenance_script(name: str):
    return load_maintenance_tool(name)


def write_compact_note(utils, conn, item_hash: str, text: str):
    storage_id = storage_id_for(conn, item_hash)
    note_path = utils.note_path_for(item_hash, storage_id)
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(text, encoding="utf-8")
    return note_path


def test_config_override_resolves_paths_inside_mock_vault(monkeypatch, tmp_path):
    utils, runtime_context = fresh_backend(monkeypatch, tmp_path, "utils", "runtime_context")
    ctx = runtime_context.get_runtime_context()

    assert utils.CONFIG_PATH == tmp_path / "mock-vault" / "config.yaml"
    assert ctx.config_path == utils.CONFIG_PATH
    assert ctx.root == utils.CONFIG_ROOT
    assert ctx.active_vault.id == utils.ACTIVE_VAULT_ID
    assert ctx.active_vault.root == utils.ACTIVE_VAULT_ROOT
    assert ctx.active_vault.db_path == utils.DB_PATH
    assert ctx.topics_dir == utils.TOPICS_DIR
    assert utils.VAULT_DIR == tmp_path / "mock-vault" / "data" / "vaults" / "default" / "vault"
    assert utils.DB_PATH == tmp_path / "mock-vault" / "data" / "vaults" / "default" / "db" / "lmz_main.db"
    assert utils.LOCAL_INGEST_DIR == tmp_path / "mock-vault" / "data" / "vaults" / "default" / "local_ingest"
    assert utils.ONLINE_INGEST_DIR == tmp_path / "mock-vault" / "data" / "vaults" / "default" / "online_ingest"
    assert utils.THUMBNAILS_DIR == tmp_path / "mock-vault" / "data" / "vaults" / "default" / "ui_cache" / "thumbnails"
    assert utils.TOPICS_DIR == tmp_path / "mock-vault" / "data" / "topics"
    assert utils.get_configured_cookie_path() == tmp_path / "mock-vault" / "secrets" / "cookies.txt"
    assert str(ROOT / "data") not in str(utils.VAULT_DIR)


def test_injected_runtime_context_paths_and_databases(monkeypatch, tmp_path):
    utils, runtime_context, sqlite_operator, workspace_db = fresh_backend(
        monkeypatch,
        tmp_path,
        "utils",
        "runtime_context",
        "db.sqlite_operator",
        "workspace_db",
    )
    work = tmp_path / "mock-vault"
    injected_root = tmp_path / "injected-workspace"
    injected_root.mkdir()
    config = yaml.safe_load((work / "config.yaml").read_text(encoding="utf-8"))
    config["active_vault"] = "alt"
    config["vaults"] = {
        "alt": {
            "name": "Alt",
            "root": "data/vaults/alt",
        }
    }
    injected_config = injected_root / "config.yaml"
    injected_config.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")
    injected_ctx = runtime_context.build_runtime_context(injected_config)

    assert injected_ctx.config_path == injected_config
    assert injected_ctx.root == injected_root
    assert injected_ctx.active_vault.id == "alt"
    assert injected_ctx.active_vault.db_path == injected_root / "data" / "vaults" / "alt" / "db" / "lmz_main.db"
    assert utils.DB_PATH == work / "data" / "vaults" / "default" / "db" / "lmz_main.db"
    assert utils.note_path_for("ab" * 32, "000000000001", ctx=injected_ctx) == injected_root / "data" / "vaults" / "alt" / "vault" / "notes" / "ab" / "000000000001.md"
    assert utils.note_path_for("ab" * 32, "000000000001") == work / "data" / "vaults" / "default" / "vault" / "notes" / "ab" / "000000000001.md"

    vault_conn = sqlite_operator.init_database(ctx=injected_ctx)
    try:
        assert vault_conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0
    finally:
        vault_conn.close()
    assert injected_ctx.active_vault.db_path.exists()
    assert utils.DB_PATH.resolve() != injected_ctx.active_vault.db_path.resolve()

    ws_conn = workspace_db.connect_workspace_database(injected_ctx)
    try:
        assert ws_conn.execute("SELECT COUNT(*) FROM platforms").fetchone()[0] >= 1
    finally:
        ws_conn.close()
    assert injected_ctx.workspace_db_path.exists()


def injected_context_for(runtime_context, tmp_path: Path):
    work = tmp_path / "mock-vault"
    injected_root = tmp_path / "injected-workspace"
    injected_root.mkdir(exist_ok=True)
    config = yaml.safe_load((work / "config.yaml").read_text(encoding="utf-8"))
    config["active_vault"] = "alt"
    config["vaults"] = {"alt": {"name": "Alt", "root": "data/vaults/alt"}}
    injected_config = injected_root / "config.yaml"
    injected_config.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return runtime_context.build_runtime_context(injected_config)


def test_queue_service_context_isolates_vault_queues(monkeypatch, tmp_path):
    utils, runtime_context, queue_service = fresh_backend(monkeypatch, tmp_path, "utils", "runtime_context", "queue_service")
    injected_ctx = injected_context_for(runtime_context, tmp_path)

    queue_service.write_queue("normal", "https://default.example/item\n")
    queue_service.write_queue("normal", "https://injected.example/item\n", ctx=injected_ctx)

    assert queue_service.read_queue("normal") == "https://default.example/item\n"
    assert queue_service.read_queue("normal", ctx=injected_ctx) == "https://injected.example/item\n"
    assert queue_service.queue_path("normal").is_relative_to(utils.QUEUES_DIR)
    assert queue_service.queue_path("normal", ctx=injected_ctx).is_relative_to(injected_ctx.active_vault.queues_dir)
    assert queue_service.queue_path("normal") != queue_service.queue_path("normal", ctx=injected_ctx)


def test_review_cache_context_isolates_vaults(monkeypatch, tmp_path):
    utils, runtime_context, review_cache = fresh_backend(monkeypatch, tmp_path, "utils", "runtime_context", "review_cache")
    injected_ctx = injected_context_for(runtime_context, tmp_path)
    default_hash = "11" * 32
    injected_hash = "22" * 32
    default_file = utils.REVIEW_DIR / "default.jpg"
    injected_file = injected_ctx.active_vault.review_dir / "injected.jpg"
    default_file.parent.mkdir(parents=True, exist_ok=True)
    injected_file.parent.mkdir(parents=True, exist_ok=True)
    default_file.write_bytes(b"default")
    injected_file.write_bytes(b"injected")
    default_file.with_suffix(".jpg.json").write_text(json.dumps({"state": "pending", "file_hash": default_hash}), encoding="utf-8")
    injected_file.with_suffix(".jpg.json").write_text(json.dumps({"state": "pending", "file_hash": injected_hash}), encoding="utf-8")

    assert review_cache.pending_review_match(default_hash)["file_hash"] == default_hash
    assert review_cache.pending_review_match(injected_hash) is None
    assert review_cache.pending_review_match(injected_hash, ctx=injected_ctx)["file_hash"] == injected_hash
    assert review_cache.pending_review_match(default_hash, ctx=injected_ctx) is None


def test_logger_reconfigure_writes_to_context_logs(monkeypatch, tmp_path):
    runtime_context, lmz_logger = fresh_backend(monkeypatch, tmp_path, "runtime_context", "logger")
    default_ctx = runtime_context.get_runtime_context()
    injected_ctx = injected_context_for(runtime_context, tmp_path)

    try:
        lmz_logger.reconfigure_logging(injected_ctx)
        lmz_logger.log_system("INFO", "context logger test")
        log_file = injected_ctx.active_vault.logs_dir / "structured" / "system.jsonl"
        assert log_file.exists()
        assert "context logger test" in log_file.read_text(encoding="utf-8")
    finally:
        lmz_logger.reconfigure_logging(default_ctx)


def test_web_api_dynamic_media_routes_use_active_context_and_block_traversal(monkeypatch, tmp_path):
    utils, web_api = fresh_backend(monkeypatch, tmp_path, "utils", "web_api")
    asset = utils.ASSETS_DIR / "aa" / "item.jpg"
    review = utils.REVIEW_DIR / "review.jpg"
    asset.parent.mkdir(parents=True, exist_ok=True)
    review.parent.mkdir(parents=True, exist_ok=True)
    asset.write_bytes(b"asset")
    review.write_bytes(b"review")

    assert Path(web_api._file_response_under(utils.ASSETS_DIR, "aa/item.jpg").path) == asset
    assert Path(web_api._file_response_under(utils.REVIEW_DIR, "review.jpg").path) == review
    with pytest.raises(HTTPException):
        web_api._file_response_under(utils.ASSETS_DIR, "../config.yaml")


def test_metadata_watchdog_uses_injected_notes_and_wd_dirs(monkeypatch, tmp_path):
    runtime_context, metadata_index = fresh_backend(monkeypatch, tmp_path, "runtime_context", "metadata_index")
    injected_ctx = injected_context_for(runtime_context, tmp_path)
    scheduled: list[tuple[str, bool]] = []

    class FakeHandler:
        pass

    class FakeObserver:
        daemon = False

        def schedule(self, handler, path, recursive=False):
            scheduled.append((path, recursive))

        def start(self):
            pass

        def stop(self):
            pass

        def join(self, timeout=None):
            pass

    monkeypatch.setitem(sys.modules, "watchdog", types.ModuleType("watchdog"))
    events_module = types.ModuleType("watchdog.events")
    events_module.FileSystemEventHandler = FakeHandler
    observers_module = types.ModuleType("watchdog.observers")
    observers_module.Observer = FakeObserver
    monkeypatch.setitem(sys.modules, "watchdog.events", events_module)
    monkeypatch.setitem(sys.modules, "watchdog.observers", observers_module)

    try:
        assert metadata_index.start_metadata_watchdog(ctx=injected_ctx)["status"] == "started"
        assert (str(injected_ctx.active_vault.notes_dir), True) in scheduled
        assert (str(injected_ctx.active_vault.wd_tags_dir), True) in scheduled
    finally:
        metadata_index.reset_metadata_watchdog_state(ctx=injected_ctx)


def test_workspace_registry_resolves_active_and_env_override(monkeypatch, tmp_path):
    monkeypatch.delenv("LMZ_CONFIG_PATH", raising=False)
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    for name in ["utils", "runtime_context", "workspaces"]:
        sys.modules.pop(name, None)
    workspaces = importlib.import_module("workspaces")
    registry_path = tmp_path / "workspaces.yaml"
    custom_root = tmp_path / "custom-workspace"
    custom_root.mkdir()
    custom_config = custom_root / "config.yaml"
    shutil.copy2(FIXTURE / "config.yaml", custom_config)
    monkeypatch.setattr(workspaces, "REGISTRY_PATH", registry_path)
    workspaces.save_workspace_registry({
        "active": "custom",
        "workspaces": {
            "default": {"name": "Default", "config_path": str(FIXTURE / "config.yaml")},
            "custom": {"name": "Custom", "config_path": str(custom_config)},
        },
    })

    utils = importlib.import_module("utils")
    assert utils.CONFIG_PATH == custom_config
    assert utils.CONFIG_ROOT == custom_root

    monkeypatch.setenv("LMZ_CONFIG_PATH", str(FIXTURE / "config.yaml"))
    sys.modules.pop("utils", None)
    sys.modules.pop("runtime_context", None)
    utils = importlib.import_module("utils")
    assert utils.CONFIG_PATH == FIXTURE / "config.yaml"


def test_obsidian_workspace_setup_creates_lmz_layout_and_resolves_paths(monkeypatch, tmp_path):
    setup_tool = load_maintenance_script("setup_obsidian_workspace")
    obsidian_vault = (Path(tempfile.gettempdir()) / f"lmz-obsidian-test-{time.time_ns()}").resolve()

    payload = setup_tool.setup_obsidian_workspace(obsidian_vault)
    config_path = Path(payload["config_path"])

    assert config_path == obsidian_vault / "lmz" / "config.yaml"
    for relative in [
        "data/topics",
        "data/vaults/default/vault/notes",
        "data/vaults/default/vault/assets",
        "data/vaults/default/db",
        "data/vaults/default/logs/raw",
        "data/vaults/default/logs/structured",
        "data/vaults/default/review",
        "data/vaults/default/wd-tags",
    ]:
        assert (obsidian_vault / "lmz" / relative).exists()

    monkeypatch.setenv("LMZ_CONFIG_PATH", str(config_path))
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    for name in list(sys.modules):
        if name in {"utils", "runtime_context", "db.sqlite_operator", "web_api", "topics", "vaults", "metadata_index", "md_generator", "artists", "platforms", "workspace_db", "review_cache"} or name.startswith(("logger", "db.", "tagging")):
            del sys.modules[name]
    utils = importlib.import_module("utils")
    sqlite_operator = importlib.import_module("db.sqlite_operator")
    web_api = importlib.import_module("web_api")

    assert utils.CONFIG_ROOT == obsidian_vault / "lmz"
    assert utils.TOPICS_DIR == obsidian_vault / "lmz" / "data" / "topics"
    assert utils.VAULT_DIR == obsidian_vault / "lmz" / "data" / "vaults" / "default" / "vault"
    assert utils.DB_PATH == obsidian_vault / "lmz" / "data" / "vaults" / "default" / "db" / "lmz_main.db"
    assert utils.get_configured_cookie_path() == obsidian_vault / "lmz" / "data" / "secrets" / "cookies.txt"
    utils.validate_config_schema(utils.get_config())
    conn = sqlite_operator.init_database()
    item_hash = "97" * 32
    storage_id = sqlite_operator.allocate_storage_id(conn)
    conn.execute(
        """
        INSERT INTO items(hash, storage_id, original_filename, file_extension, mime_type, size_bytes, date_added, source_url, source_url_norm, platform, source_artist, phash)
        VALUES (?, ?, ?, '.jpg', 'image/jpeg', 10, '2026-01-01 00:00:00', '', '', 'local', 'artist', '')
        """,
        (item_hash, storage_id, f"{item_hash}.jpg"),
    )
    conn.commit()
    conn.close()

    detail = web_api._update_item_sync(item_hash, web_api.ItemUpdate(topics=["obsidian topic"]))
    assert detail["topics"] == ["obsidian_topic"]
    assert (obsidian_vault / "lmz" / "data" / "topics" / "obsidian_topic.md").exists()
    assert utils.note_path_for(item_hash, storage_id).exists()
    runtime = web_api._load_public_config_sync()["_runtime"]
    assert runtime["workspace_mode"] == "obsidian"
    assert runtime["active_vault"] == "default"
    shutil.rmtree(obsidian_vault, ignore_errors=True)


def test_obsidian_workspace_setup_refuses_runtime_paths(tmp_path):
    setup_tool = load_maintenance_script("setup_obsidian_workspace")
    for dangerous in [ROOT, ROOT / "data", ROOT / "config", ROOT / "logs", ROOT / "secrets"]:
        with pytest.raises(ValueError):
            setup_tool.setup_obsidian_workspace(dangerous)


def test_workspace_api_lists_registers_and_sets_active(monkeypatch, tmp_path):
    web_api, workspaces = fresh_backend(monkeypatch, tmp_path, "web_api", "workspaces")
    registry_path = tmp_path / "workspaces.yaml"
    monkeypatch.setattr(workspaces, "REGISTRY_PATH", registry_path)
    obsidian_vault = (Path(tempfile.gettempdir()) / f"lmz-obsidian-api-test-{time.time_ns()}").resolve()
    try:
        initial = web_api._get_workspaces_sync()
        assert initial["active"] == "default"
        assert initial["items"][0]["id"] == "default"

        added = web_api._add_obsidian_workspace_sync({"path": str(obsidian_vault), "name": "API Obsidian"})
        assert any(item["name"] == "API Obsidian" for item in added["items"])

        workspace_id = next(item["id"] for item in added["items"] if item["name"] == "API Obsidian")
        active = web_api._set_workspace_active_sync({"id": workspace_id})
        assert active["restart_required"] is True
        assert active["active"] == workspace_id
    finally:
        shutil.rmtree(obsidian_vault, ignore_errors=True)


def test_vault_api_creates_sets_active_and_rejects_active_delete(monkeypatch, tmp_path):
    web_api, vaults = fresh_backend(monkeypatch, tmp_path, "web_api", "vaults")

    created = web_api._create_vault_sync({"name": "Second Vault"})
    second = next(item for item in created["items"] if item["id"] == "second-vault")

    assert Path(second["root"]).exists()
    assert Path(second["db_path"]).exists()

    active = web_api._set_vault_active_sync({"id": "second-vault"})
    assert active["restart_required"] is True
    assert active["active"] == "second-vault"

    with pytest.raises(HTTPException) as exc:
        web_api._delete_vault_sync("second-vault", confirm=True)
    assert exc.value.status_code == 400


def test_vault_merge_reallocates_storage_ids_and_keeps_source(monkeypatch, tmp_path):
    vaults, sqlite_operator = fresh_backend(monkeypatch, tmp_path, "vaults", "db.sqlite_operator")
    vaults.create_vault("Source")
    vaults.create_vault("Target")
    items = {item["id"]: item for item in vaults.vault_list()}
    source_root = Path(items["source"]["root"])
    target_root = Path(items["target"]["root"])

    item_hash = "ab" * 32
    source_storage_id = "00000000000a"
    source_db = Path(items["source"]["db_path"])
    conn = sqlite_operator.init_database(source_db)
    conn.execute(
        """
        INSERT INTO items(hash, storage_id, original_filename, file_extension, mime_type, size_bytes, date_added, source_url, source_url_norm, platform, source_artist, phash)
        VALUES (?, ?, ?, '.jpg', 'image/jpeg', 10, '2026-01-01 00:00:00', '', '', 'Local', 'Artist', '')
        """,
        (item_hash, source_storage_id, "source.jpg"),
    )
    conn.commit()
    conn.close()
    source_asset = source_root / "vault" / "assets" / item_hash[:2] / f"{source_storage_id}.jpg"
    source_note = source_root / "vault" / "notes" / item_hash[:2] / f"{source_storage_id}.md"
    source_asset.parent.mkdir(parents=True, exist_ok=True)
    source_note.parent.mkdir(parents=True, exist_ok=True)
    source_asset.write_bytes(b"asset")
    source_note.write_text("---\ntopics: []\n---\n", encoding="utf-8")

    result = vaults.merge_vaults("target", ["source"])

    target_conn = sqlite3.connect(items["target"]["db_path"])
    source_conn = sqlite3.connect(items["source"]["db_path"])
    target_row = target_conn.execute("SELECT storage_id FROM items WHERE hash = ?", (item_hash,)).fetchone()
    source_count = source_conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    target_conn.close()
    source_conn.close()

    assert result["imported"] == 1
    assert target_row is not None
    assert target_row[0] != source_storage_id
    assert (target_root / "vault" / "assets" / item_hash[:2] / f"{target_row[0]}.jpg").exists()
    assert source_count == 1


def test_get_config_cache_hits_and_returns_defensive_copy(monkeypatch, tmp_path):
    (utils,) = fresh_backend(monkeypatch, tmp_path, "utils")
    calls = []
    original_loader = utils._load_config_uncached

    def wrapped_loader():
        calls.append("load")
        return original_loader()

    monkeypatch.setattr(utils, "_load_config_uncached", wrapped_loader)
    utils.invalidate_config_cache()

    first = utils.get_config()
    first["ui"]["vault_layout_mode"] = "grid"
    second = utils.get_config()

    assert len(calls) == 1
    assert second["ui"]["vault_layout_mode"] != "grid"


def test_get_config_cache_refreshes_when_config_mtime_changes(monkeypatch, tmp_path):
    (utils,) = fresh_backend(monkeypatch, tmp_path, "utils")
    calls = []
    original_loader = utils._load_config_uncached

    def wrapped_loader():
        calls.append("load")
        return original_loader()

    monkeypatch.setattr(utils, "_load_config_uncached", wrapped_loader)
    utils.invalidate_config_cache()
    utils.get_config()
    assert len(calls) == 1

    current = utils.CONFIG_PATH.stat().st_mtime
    os.utime(utils.CONFIG_PATH, (current + 3, current + 3))
    utils.get_config()
    assert len(calls) == 2


def test_public_config_strip_removes_secret_token(monkeypatch, tmp_path):
    web_api, utils = fresh_backend(monkeypatch, tmp_path, "web_api", "utils")
    secrets_path = utils.SECRETS_DIR / ".secrets.yaml"
    secrets_path.parent.mkdir(parents=True, exist_ok=True)
    secrets_path.write_text('pixiv_token: "secret-token"\ncookies_path: "secrets/cookies.txt"\n', encoding="utf-8")
    utils.invalidate_config_cache()

    payload = web_api._load_public_config_sync()

    ext = payload.get("external_tools", {})
    assert "pixiv_token" not in ext


def test_update_app_config_invalidates_config_cache(monkeypatch, tmp_path):
    web_api, utils = fresh_backend(monkeypatch, tmp_path, "web_api", "utils")
    called = []

    monkeypatch.setattr(web_api, "invalidate_config_cache", lambda: called.append("invalidated"))
    web_api._update_app_config_sync({
        "active_vault": "default",
        "vaults": {"default": {"name": "Default", "root": "data/vaults/default"}},
        "paths": {
            "secrets": "data/secrets",
            "models": "data/models",
        },
        "firewall": {"allowed_extensions": [".jpg"], "allowed_mimes": ["image/jpeg"]},
        "hash_algorithm": "sha256",
    })

    assert called == ["invalidated"]


def test_queue_service_uses_mock_vault_queues(monkeypatch, tmp_path):
    queue_service, utils = fresh_backend(monkeypatch, tmp_path, "queue_service", "utils")

    assert queue_service.queue_counts() == {"normal": 1, "force": 1, "failed": 1}
    moved = queue_service.move_failed_urls("normal")
    assert moved == 1
    assert queue_service.queue_counts() == {"normal": 2, "force": 1, "failed": 0}
    assert queue_service.queue_path("normal").is_relative_to(utils.QUEUES_DIR)


def test_review_cleanup_state_and_orphan_sidecar(monkeypatch, tmp_path):
    web_api, utils = fresh_backend(monkeypatch, tmp_path, "web_api", "utils")

    assert web_api._normalize_review_state("cleanup_failed") == "pending_cleanup"
    orphan = utils.REVIEW_DIR / "orphan.jpg.json"
    orphan.write_text('{"state":"resolved_delete"}', encoding="utf-8")

    result = web_api._cleanup_review_resolved_sync()

    assert result["cleaned_orphans"] == 1
    assert not orphan.exists()


def test_web_api_startup_hydrates_search_manager(monkeypatch, tmp_path):
    (web_api,) = fresh_backend(monkeypatch, tmp_path, "web_api")
    calls = []

    class FakeConnection:
        def close(self):
            calls.append("close")

    class FakeSearchManager:
        def hydrate(self, conn):
            calls.append(("hydrate", conn))

    fake_conn = FakeConnection()
    monkeypatch.setattr(web_api, "init_database", lambda: fake_conn)
    monkeypatch.setattr(web_api, "search_manager", FakeSearchManager())

    asyncio.run(web_api.startup_search_index())

    assert calls == [("hydrate", fake_conn), "close"]


def test_review_listing_does_not_auto_resolve_pending_db_hash(monkeypatch, tmp_path):
    web_api, utils, sqlite_operator = fresh_backend(monkeypatch, tmp_path, "web_api", "utils", "db.sqlite_operator")
    item_hash = "1" * 64
    conn = insert_mock_item(sqlite_operator, item_hash)
    conn.close()

    review_file = utils.REVIEW_DIR / "pending_same_hash.jpg"
    review_file.parent.mkdir(parents=True, exist_ok=True)
    review_file.write_bytes(b"review")
    sidecar = review_file.with_suffix(".jpg.json")
    sidecar.write_text(json.dumps({"state": "pending", "file_hash": item_hash, "original_name": "pending_same_hash.jpg"}), encoding="utf-8")

    items = web_api._get_review_items_sync()
    saved = json.loads(sidecar.read_text(encoding="utf-8"))
    target = next(item for item in items if item["filename"] == review_file.name)

    assert target["state"] == "pending"
    assert saved["state"] == "pending"
    assert "last_action" not in saved


def test_review_count_uses_cache_without_full_resolver(monkeypatch, tmp_path):
    web_api, = fresh_backend(monkeypatch, tmp_path, "web_api")

    def fail_resolver():
        raise AssertionError("review count should not resolve all review entries")

    monkeypatch.setattr(web_api, "_resolve_review_entries", fail_resolver)
    count = web_api._get_review_count_sync(include_resolved=True)

    assert count["pending"] >= 1
    assert count["cleanup"] >= 1
    assert count["total"] >= count["pending"] + count["cleanup"]


def test_review_count_cache_ignores_resolved_variant(monkeypatch, tmp_path):
    web_api, utils = fresh_backend(monkeypatch, tmp_path, "web_api", "utils")
    resolved_file = utils.REVIEW_DIR / "resolved-variant.webp"
    resolved_file.write_bytes(b"resolved")
    resolved_file.with_suffix(".webp.json").write_text(
        json.dumps({"state": "resolved_variant", "file_hash": "12" * 32}),
        encoding="utf-8",
    )
    web_api.mark_review_cache_dirty()

    count = web_api._get_review_count_sync(include_resolved=True)
    items = web_api._get_review_items_sync(False)

    assert all(item["filename"] != resolved_file.name for item in items)
    assert count["pending"] == 1
    assert count["cleanup"] == 1


def test_delete_item_removes_ram_indexes(monkeypatch, tmp_path):
    sqlite_operator, web_api = fresh_backend(monkeypatch, tmp_path, "db.sqlite_operator", "web_api")
    item_hash = "9a" * 32
    conn = insert_mock_item(sqlite_operator, item_hash)
    conn.execute(
        "UPDATE items SET source_url = ?, source_url_norm = ? WHERE hash = ?",
        ("https://example.test/delete", sqlite_operator.normalize_source_url("https://example.test/delete"), item_hash),
    )
    conn.commit()
    conn.close()
    removed = []

    class FakeSearchManager:
        def remove_indexes_batch(self, items):
            removed.extend(items)

    monkeypatch.setattr(web_api, "search_manager", FakeSearchManager())

    result = web_api._delete_item_sync(item_hash)

    assert result["status"] == "success"
    assert removed == [{"hash": item_hash, "source_url": "https://example.test/delete"}]


def test_local_ingest_state_guards_and_result_cap(monkeypatch, tmp_path):
    (web_api,) = fresh_backend(monkeypatch, tmp_path, "web_api")

    web_api._prepare_local_ingest_run("run-1", {"artist": "A"}, True)
    with pytest.raises(HTTPException) as exc:
        web_api._prepare_local_ingest_run("run-2", {}, False)
    assert exc.value.status_code == 409

    with web_api.LOCAL_INGEST_LOCK:
        web_api.LOCAL_INGEST_STATE["running"] = False
        web_api.LOCAL_INGEST_STATE["results"] = []
        for index in range(505):
            web_api._append_local_ingest_result({"index": index})

    assert len(web_api.LOCAL_INGEST_STATE["results"]) == 500
    assert web_api.LOCAL_INGEST_STATE["results"][0]["index"] == 5
    assert web_api.LOCAL_INGEST_STATE["last_defaults"] == {"artist": "A"}
    assert web_api.LOCAL_INGEST_STATE["last_skip_similarity"] is True


def test_local_retry_preserves_defaults_and_skip_similarity(monkeypatch, tmp_path):
    (web_api,) = fresh_backend(monkeypatch, tmp_path, "web_api")
    calls = []

    def fake_worker(paths, defaults, skip_similarity, run_id):
        calls.append((paths, defaults, skip_similarity, run_id))

    monkeypatch.setattr(web_api, "_run_local_ingest_worker", fake_worker)
    with web_api.LOCAL_INGEST_LOCK:
        web_api.LOCAL_INGEST_STATE["running"] = False
        web_api.LOCAL_INGEST_STATE["failed_paths"] = ["failed-a.jpg"]
        web_api.LOCAL_INGEST_STATE["last_defaults"] = {"artist": "Retry Artist"}
        web_api.LOCAL_INGEST_STATE["last_skip_similarity"] = True

    result = asyncio.run(web_api.local_ingest_retry_failed())

    assert result["status"] == "success"
    assert result["queued"] == 1
    assert calls[0][0] == ["failed-a.jpg"]
    assert calls[0][1] == {"artist": "Retry Artist", "platform": "Local", "source_url": ""}
    assert calls[0][2] is True


def test_local_worker_reports_wd_tagging_status_for_started_paths(monkeypatch, tmp_path):
    (web_api,) = fresh_backend(monkeypatch, tmp_path, "web_api")
    source = tmp_path / "drop_ok.jpg"
    source.write_bytes(b"fake image")

    def fake_process_file(path, config, metadata=None, delete_source=False, skip_similarity=False):
        if delete_source:
            Path(path).unlink()
        return True, "Success: drop_ok.jpg -> item.jpg", {
            "file_hash": "7" * 64,
            "tagging_status": "ok",
            "tagging_tag_count": 12,
            "tagging_error": "",
        }

    monkeypatch.setattr(web_api, "process_file", fake_process_file)
    monkeypatch.setattr(web_api, "get_config", lambda: {"firewall": {"allowed_extensions": ["jpg"]}})

    web_api._prepare_local_ingest_run("run-tags", {}, False, 1)
    web_api._run_local_ingest_worker([str(source)], {}, False, "run-tags")

    result = web_api._snapshot_local_ingest_state()["results"][-1]

    assert result["status"] == "ingested"
    assert "WD tags: ok (12)" in result["message"]


def test_local_ingest_expansion_is_streaming_not_sorted(monkeypatch, tmp_path):
    (web_api,) = fresh_backend(monkeypatch, tmp_path, "web_api")
    source = inspect.getsource(web_api._iter_local_ingest_paths)

    assert "sorted(" not in source
    assert ".rglob(\"*\")" in source


def test_local_drop_intake_accepts_supported_file_and_directory(monkeypatch, tmp_path):
    (web_api,) = fresh_backend(monkeypatch, tmp_path, "web_api")
    sample_file = tmp_path / "drop_ok.jpg"
    sample_file.write_bytes(b"ok")
    sample_dir = tmp_path / "drop_dir"
    sample_dir.mkdir(parents=True, exist_ok=True)

    payload = web_api.LocalIngestDropIntakeRequest(
        session_id="s1",
        source_tab="vault",
        paths=[str(sample_file), str(sample_dir)],
    )
    result = web_api._local_drop_intake_sync(payload)

    assert result["session_id"] == "s1"
    assert result["summary"]["received"] == 2
    assert result["summary"]["accepted"] == 2
    assert result["summary"]["skipped"] == 0
    assert str(sample_file.resolve()) in result["accepted_paths"]
    assert str(sample_dir.resolve()) in result["accepted_paths"]


def test_local_drop_intake_skips_unsupported_extension_and_missing(monkeypatch, tmp_path):
    (web_api,) = fresh_backend(monkeypatch, tmp_path, "web_api")
    bad_file = tmp_path / "drop_bad.txt"
    bad_file.write_text("x", encoding="utf-8")
    missing = tmp_path / "nope.jpg"

    payload = web_api.LocalIngestDropIntakeRequest(
        session_id="s2",
        source_tab="vault",
        paths=[str(bad_file), str(missing)],
    )
    result = web_api._local_drop_intake_sync(payload)
    reasons = {entry["reason"] for entry in result["skipped"]}

    assert result["summary"]["accepted"] == 0
    assert result["summary"]["skipped"] == 2
    assert "unsupported_extension" in reasons
    assert "missing_path" in reasons


def test_local_drop_intake_dedupes_paths(monkeypatch, tmp_path):
    (web_api,) = fresh_backend(monkeypatch, tmp_path, "web_api")
    sample_file = tmp_path / "dup_ok.jpg"
    sample_file.write_bytes(b"dup")

    payload = web_api.LocalIngestDropIntakeRequest(
        session_id="s3",
        source_tab="vault",
        paths=[str(sample_file), str(sample_file)],
    )
    result = web_api._local_drop_intake_sync(payload)

    assert result["summary"]["accepted"] == 1
    assert result["summary"]["skipped"] == 1
    assert result["skipped"][0]["reason"] == "duplicate_path"


def test_local_drop_intake_blocks_when_local_ingest_running(monkeypatch, tmp_path):
    (web_api,) = fresh_backend(monkeypatch, tmp_path, "web_api")
    with web_api.LOCAL_INGEST_LOCK:
        web_api.LOCAL_INGEST_STATE["running"] = True
    try:
        payload = web_api.LocalIngestDropIntakeRequest(session_id="s4", source_tab="vault", paths=["C:/tmp/a.jpg"])
        with pytest.raises(HTTPException) as exc:
            web_api._local_drop_intake_sync(payload)
        assert exc.value.status_code == 409
    finally:
        with web_api.LOCAL_INGEST_LOCK:
            web_api.LOCAL_INGEST_STATE["running"] = False


def test_local_drop_intake_blocks_when_online_ingest_running(monkeypatch, tmp_path):
    (web_api,) = fresh_backend(monkeypatch, tmp_path, "web_api")
    acquired = web_api.INGESTION_LOCK.acquire(blocking=False)
    assert acquired is True
    try:
        payload = web_api.LocalIngestDropIntakeRequest(session_id="s5", source_tab="vault", paths=["C:/tmp/a.jpg"])
        with pytest.raises(HTTPException) as exc:
            web_api._local_drop_intake_sync(payload)
        assert exc.value.status_code == 409
    finally:
        if acquired:
            web_api.INGESTION_LOCK.release()


def test_mime_detection_falls_back_when_magic_returns_error_text(monkeypatch, tmp_path):
    class FakeMagic:
        @staticmethod
        def from_file(path, mime=True):
            return f"cannot open `{path}' (no such file or directory)"

    monkeypatch.setitem(sys.modules, "magic", FakeMagic)
    (validators,) = fresh_backend(monkeypatch, tmp_path, "validators")

    sample = tmp_path / "WhatsApp Görsel 2024.jpg"
    sample.write_bytes(b"not actually jpeg")

    assert validators.get_mime_type(sample) == "image/jpeg"


def test_generate_markdown_mirrors_sqlite_identity_and_preserves_indexed_note_fields(monkeypatch, tmp_path):
    utils, sqlite_operator, md_generator = fresh_backend(monkeypatch, tmp_path, "utils", "db.sqlite_operator", "md_generator")
    item_hash = "d" * 64
    conn = insert_mock_item(sqlite_operator, item_hash)
    storage_id = storage_id_for(conn, item_hash)
    note_path = utils.note_path_for(item_hash, storage_id)
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(
        "---\n"
        "artist: Manual Artist\n"
        "date_added: '2020-01-01 01:02:03'\n"
        "topics:\n  - manual-topic\n"
        "wd_rating: ''\n"
        "wd_character_tags: []\n"
        "wd_tags: []\n"
        "---\nbody\n",
        encoding="utf-8",
    )
    cache_path = utils.wd_tag_cache_path_for(item_hash, storage_id)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps({"hash": item_hash, "status": "ok", "rating": {"label": "safe"}, "character_tags": [{"name": "cached_character"}], "tags": [{"name": "cached_tag"}]}),
        encoding="utf-8",
    )

    data = frontmatter_from_markdown(md_generator.generate_markdown(conn, item_hash))

    assert data["artist"] == "DB Artist"
    assert data["date_added"] == "2026-01-02 03:04:05"
    assert data["topics"] == ["manual-topic"]
    assert data["wd_rating"] == ""
    assert data["wd_character_tags"] == []
    assert data["wd_tags"] == []
    conn.close()


def test_generate_markdown_seeds_missing_wd_fields_from_cache(monkeypatch, tmp_path):
    utils, sqlite_operator, md_generator = fresh_backend(monkeypatch, tmp_path, "utils", "db.sqlite_operator", "md_generator")
    item_hash = "e" * 64
    conn = insert_mock_item(sqlite_operator, item_hash)
    storage_id = storage_id_for(conn, item_hash)
    cache_path = utils.wd_tag_cache_path_for(item_hash, storage_id)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps({"hash": item_hash, "status": "ok", "rating": {"label": "safe"}, "character_tags": [{"name": "cached_character", "display_name": "Cached Character"}], "tags": [{"name": "cached_tag", "display_name": "Cached Tag"}]}),
        encoding="utf-8",
    )

    data = frontmatter_from_markdown(md_generator.generate_markdown(conn, item_hash))

    assert data["wd_rating"] == "safe"
    assert data["wd_character_tags"] == ["Cached Character"]
    assert data["wd_tags"] == ["Cached Tag"]
    conn.close()


def test_generate_markdown_overwrites_existing_fields_if_forced(monkeypatch, tmp_path):
    utils, sqlite_operator, md_generator = fresh_backend(monkeypatch, tmp_path, "utils", "db.sqlite_operator", "md_generator")
    item_hash = "f" * 64
    conn = insert_mock_item(sqlite_operator, item_hash)
    storage_id = storage_id_for(conn, item_hash)
    
    note_path = utils.note_path_for(item_hash, storage_id)
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(
        "---\n"
        "artist: DB Artist\n"
        "date_added: '2026-01-02 03:04:05'\n"
        "topics: []\n"
        "wd_rating: 'old_rating'\n"
        "wd_character_tags: ['old_character']\n"
        "wd_tags: ['old_tag']\n"
        "---\nbody\n",
        encoding="utf-8",
    )
    
    cache_path = utils.wd_tag_cache_path_for(item_hash, storage_id)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps({
            "hash": item_hash,
            "status": "ok",
            "rating": {"label": "new_rating"},
            "character_tags": [{"name": "new_character", "display_name": "New Character"}],
            "tags": [{"name": "new_tag", "display_name": "New Tag"}]
        }),
        encoding="utf-8",
    )

    data = frontmatter_from_markdown(md_generator.generate_markdown(conn, item_hash))
    assert data["wd_rating"] == "old_rating"
    assert data["wd_character_tags"] == ["old_character"]
    assert data["wd_tags"] == ["old_tag"]

    data_forced = frontmatter_from_markdown(md_generator.generate_markdown(conn, item_hash, force_wd_from_cache=True))
    assert data_forced["wd_rating"] == "new_rating"
    assert data_forced["wd_character_tags"] == ["New Character"]
    assert data_forced["wd_tags"] == ["New Tag"]
    
    conn.close()


def test_reindex_does_not_sync_markdown_identity_fields_to_sqlite(monkeypatch, tmp_path):
    utils, sqlite_operator, metadata_index = fresh_backend(monkeypatch, tmp_path, "utils", "db.sqlite_operator", "metadata_index")
    item_hash = "f" * 64
    conn = insert_mock_item(sqlite_operator, item_hash, artist="DB Artist", date_added="2026-01-01 00:00:00")
    storage_id = storage_id_for(conn, item_hash)
    note_path = utils.note_path_for(item_hash, storage_id)
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(
        "---\nartist: Manual Artist\ndate_added: '2020-01-01 01:02:03'\ntopics: []\n---\n",
        encoding="utf-8",
    )

    metadata_index.reindex_item_metadata(conn, item_hash)
    conn.commit()
    row = conn.execute("SELECT source_artist, date_added FROM items WHERE hash = ?", (item_hash,)).fetchone()

    assert row == ("DB Artist", "2026-01-01 00:00:00")
    conn.close()


def test_patch_rolls_back_db_when_markdown_write_fails(monkeypatch, tmp_path):
    utils, sqlite_operator, web_api = fresh_backend(monkeypatch, tmp_path, "utils", "db.sqlite_operator", "web_api")
    item_hash = "1" * 64
    conn = insert_mock_item(sqlite_operator, item_hash, artist="Original Artist")
    storage_id = storage_id_for(conn, item_hash)
    utils.note_path_for(item_hash, storage_id).parent.mkdir(parents=True, exist_ok=True)
    utils.note_path_for(item_hash, storage_id).write_text("---\nartist: Original Artist\ntopics: []\n---\n", encoding="utf-8")
    conn.close()

    def fail_write(path, text, encoding="utf-8"):
        raise OSError("disk full")

    monkeypatch.setattr(web_api, "atomic_write_text", fail_write)
    with pytest.raises(OSError):
        web_api._update_item_sync(item_hash, web_api.ItemUpdate(artist="New Artist"))

    conn = sqlite_operator.init_database()
    artist = conn.execute("SELECT source_artist FROM items WHERE hash = ?", (item_hash,)).fetchone()[0]
    assert artist == "Original Artist"
    conn.close()


def test_processor_uses_atomic_markdown_writes(monkeypatch, tmp_path):
    (processor,) = fresh_backend(monkeypatch, tmp_path, "processor")

    source = inspect.getsource(processor.process_file)
    assert "atomic_write_text(md_path, md_content)" in source
    assert "with open(md_path" not in source


def test_processor_skips_file_already_pending_review(monkeypatch, tmp_path):
    utils, processor = fresh_backend(monkeypatch, tmp_path, "utils", "processor")
    source = tmp_path / "pending.webp"
    source.write_bytes(b"pending review bytes")
    file_hash = utils.calculate_file_hash(source)
    review_file = utils.REVIEW_DIR / "queued.webp"
    review_file.parent.mkdir(parents=True, exist_ok=True)
    review_file.write_bytes(b"existing review bytes")
    review_file.with_suffix(".webp.json").write_text(
        json.dumps({"state": "pending", "file_hash": file_hash, "original_name": "pending.webp"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(processor, "get_mime_type", lambda path: "image/webp")

    ok, message, idx_data = processor.process_file(
        source,
        {"firewall": {"allowed_mimes": ["image/webp"], "allowed_extensions": ["webp"]}},
    )

    assert not ok
    assert message.startswith("Already pending review")
    assert idx_data is None


def test_pending_review_match_uses_cache_without_sidecar_glob(monkeypatch, tmp_path):
    utils, processor = fresh_backend(monkeypatch, tmp_path, "utils", "processor")
    review_hash = "ab" * 32
    review_file = utils.REVIEW_DIR / "cached.webp"
    review_file.parent.mkdir(parents=True, exist_ok=True)
    review_file.write_bytes(b"existing review bytes")
    review_file.with_suffix(".webp.json").write_text(
        json.dumps({"state": "pending", "file_hash": review_hash, "original_name": "cached.webp"}),
        encoding="utf-8",
    )

    class FakeReviewDir:
        def glob(self, *args, **kwargs):
            raise AssertionError("pending review match should not glob sidecars")

    monkeypatch.setattr(processor, "REVIEW_DIR", FakeReviewDir())

    assert processor._pending_review_match(review_hash)["original_name"] == "cached.webp"


def test_pending_review_guard_blocks_reingest_after_restart(monkeypatch, tmp_path):
    utils, sqlite_operator, processor = fresh_backend(monkeypatch, tmp_path, "utils", "db.sqlite_operator", "processor")
    existing_hash = "2" * 64
    reingest_source = tmp_path / "9ypbteld4je61.webp"
    reingest_source.write_bytes(b"same webp bytes")
    review_hash = utils.calculate_file_hash(reingest_source)
    conn = insert_mock_item(sqlite_operator, existing_hash)
    conn.close()

    review_file = utils.REVIEW_DIR / "pending_9ypbteld4je61.webp"
    review_file.parent.mkdir(parents=True, exist_ok=True)
    review_file.write_bytes(b"same webp bytes")
    review_file.with_suffix(".webp.json").write_text(
        json.dumps({
            "state": "pending",
            "file_hash": review_hash,
            "phash": "deb02d123d1f218f",
            "best_match": existing_hash,
        }),
        encoding="utf-8",
    )

    monkeypatch.setattr(processor, "get_mime_type", lambda path: "image/webp")

    ok, message, _ = processor.process_file(
        reingest_source,
        {"firewall": {"allowed_mimes": ["image/webp"], "allowed_extensions": ["webp"]}},
    )

    conn = sqlite_operator.init_database()
    row = conn.execute("SELECT 1 FROM items WHERE hash = ?", (review_hash,)).fetchone()
    conn.close()

    assert not ok
    assert message.startswith("Already pending review")
    assert row is None


def test_ingest_seeds_markdown_artist_from_metadata_and_reindexes(monkeypatch, tmp_path):
    utils, sqlite_operator, processor = fresh_backend(monkeypatch, tmp_path, "utils", "db.sqlite_operator", "processor")
    item_hash = "5" * 64
    source = tmp_path / "source.jpg"
    source.write_bytes(b"fake image")

    class TagResult:
        status = "ok"
        error = ""

    monkeypatch.setattr(processor, "calculate_file_hash", lambda path: item_hash)
    monkeypatch.setattr(processor, "get_mime_type", lambda path: "image/jpeg")
    monkeypatch.setattr(processor, "calculate_phash", lambda path: None)
    monkeypatch.setattr(processor, "calculate_tiles", lambda path: [])
    monkeypatch.setattr(processor, "tag_media", lambda *args, **kwargs: TagResult())
    monkeypatch.setattr(processor, "_pending_review_match", lambda file_hash: None)

    ok, _, idx_data = processor.process_file(
        source,
        {"firewall": {"allowed_mimes": ["image/jpeg"], "allowed_extensions": ["jpg"]}, "tagging": {}},
        metadata={"artist": "Ingest Artist", "platform": "pixiv", "source_url": "https://example.test/item"},
        sync_index=False,
    )

    conn = sqlite_operator.init_database()
    row = conn.execute("SELECT source_artist, storage_id FROM items WHERE hash = ?", (item_hash,)).fetchone()
    note_data = frontmatter_from_markdown(utils.note_path_for(item_hash, row[1]).read_text(encoding="utf-8"))

    assert ok
    assert idx_data["file_hash"] == item_hash
    assert row[0] == "Ingest Artist"
    assert len(row[1]) == 12
    assert utils.storage_asset_path_for(item_hash, row[1], ".jpg", "image/jpeg").exists()
    assert utils.note_path_for(item_hash, row[1]).name == f"{row[1]}.md"
    assert note_data["artist"] == "Ingest Artist"
    conn.close()


def test_ingest_result_reports_wd_tagging_status(monkeypatch, tmp_path):
    utils, sqlite_operator, processor = fresh_backend(monkeypatch, tmp_path, "utils", "db.sqlite_operator", "processor")
    item_hash = "6" * 64
    source = tmp_path / "source.jpg"
    source.write_bytes(b"fake image")

    class TagResult:
        status = "ok"
        error = ""
        tags = [{"name": "tag-a"}]

    monkeypatch.setattr(processor, "calculate_file_hash", lambda path: item_hash)
    monkeypatch.setattr(processor, "get_mime_type", lambda path: "image/jpeg")
    monkeypatch.setattr(processor, "calculate_phash", lambda path: None)
    monkeypatch.setattr(processor, "calculate_tiles", lambda path: [])
    monkeypatch.setattr(processor, "tag_media", lambda *args, **kwargs: TagResult())
    monkeypatch.setattr(processor, "_pending_review_match", lambda file_hash: None)

    ok, _, idx_data = processor.process_file(
        source,
        {"firewall": {"allowed_mimes": ["image/jpeg"], "allowed_extensions": ["jpg"]}, "tagging": {}},
        metadata={"artist": "Ingest Artist", "platform": "local", "source_url": ""},
        sync_index=False,
    )

    conn = sqlite_operator.init_database()
    storage_id = conn.execute("SELECT storage_id FROM items WHERE hash = ?", (item_hash,)).fetchone()[0]
    conn.close()

    assert ok
    assert idx_data["tagging_status"] == "ok"
    assert idx_data["tagging_tag_count"] == 1
    assert utils.note_path_for(item_hash, storage_id).exists()


def test_storage_id_backfill_and_compact_asset_path(monkeypatch, tmp_path):
    utils, sqlite_operator = fresh_backend(monkeypatch, tmp_path, "utils", "db.sqlite_operator")
    item_hash = "a1" * 32
    conn = insert_mock_item(sqlite_operator, item_hash)
    conn.close()

    conn = sqlite_operator.init_database()
    storage_id = conn.execute("SELECT storage_id FROM items WHERE hash = ?", (item_hash,)).fetchone()[0]

    assert len(storage_id) == 12
    assert utils.asset_path_for(item_hash, ".jpg", "image/jpeg", storage_id=storage_id).name == f"{storage_id}.jpg"
    conn.close()


def test_storage_id_allocation_does_not_rescan_counter(monkeypatch, tmp_path):
    sqlite_operator, = fresh_backend(monkeypatch, tmp_path, "db.sqlite_operator")
    conn = sqlite_operator.init_database()

    def fail_rescan(conn):
        raise AssertionError("_ensure_storage_counter should not run during allocation")

    monkeypatch.setattr(sqlite_operator, "_ensure_storage_counter", fail_rescan)
    storage_id = sqlite_operator.allocate_storage_id(conn)
    conn.close()

    assert len(storage_id) == 12


def test_manage_review_uses_quarantine_sidecar_for_artist(monkeypatch, tmp_path):
    (utils,) = fresh_backend(monkeypatch, tmp_path, "utils")
    tool_path = ROOT / "tools" / "maintenance" / "manage_review.py"
    spec = importlib.util.spec_from_file_location("manage_review_under_test", tool_path)
    manage_review = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(manage_review)
    review_file = utils.REVIEW_DIR / "queued.jpg"
    sidecar = review_file.with_suffix(".jpg.json")
    review_file.write_bytes(b"queued")
    sidecar.write_text(json.dumps({"metadata": {"artist": "Sidecar Artist"}}), encoding="utf-8")
    captured = {}

    def fake_process_file(file_path, config, metadata=None, delete_source=False, skip_similarity=False):
        captured["metadata"] = metadata
        if delete_source:
            file_path.unlink()
        return True, "ok", {}

    monkeypatch.setattr(manage_review, "get_config", lambda: {})
    monkeypatch.setattr(manage_review, "process_file", fake_process_file)

    manage_review.approve_file("queued.jpg")

    assert captured["metadata"]["artist"] == "Sidecar Artist"
    assert not sidecar.exists()


def test_manual_metadata_migration_dry_run_and_apply(monkeypatch, tmp_path):
    utils, sqlite_operator = fresh_backend(monkeypatch, tmp_path, "utils", "db.sqlite_operator")
    tool_path = ROOT / "tools" / "maintenance" / "migrate_manual_metadata_to_markdown.py"
    spec = importlib.util.spec_from_file_location("migrate_manual_metadata_to_markdown", tool_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    item_hash = "2" * 64
    conn = insert_mock_item(sqlite_operator, item_hash, artist="DB Artist", date_added="2022-02-02 02:02:02")
    storage_id = storage_id_for(conn, item_hash)
    conn.close()
    note_path = utils.note_path_for(item_hash, storage_id)
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text("---\ntopics: []\n---\nbody\n", encoding="utf-8")

    dry_run = migration.run(False)
    assert dry_run["changed"] == 1
    assert "artist" not in frontmatter_from_markdown(note_path.read_text(encoding="utf-8"))

    applied = migration.run(True)
    data = frontmatter_from_markdown(note_path.read_text(encoding="utf-8"))

    assert applied["changed"] == 1
    assert data["artist"] == "DB Artist"
    assert data["date_added"] == "2022-02-02 02:02:02"
    assert Path(applied["backup"]).exists()


def test_review_replace_preserves_old_sqlite_identity_and_manual_indexed_metadata(monkeypatch, tmp_path):
    utils, sqlite_operator, web_api = fresh_backend(monkeypatch, tmp_path, "utils", "db.sqlite_operator", "web_api")
    old_hash = "3" * 64
    new_hash = "4" * 64
    conn = insert_mock_item(sqlite_operator, old_hash, artist="Old DB Artist", date_added="2026-01-01 00:00:00")
    old_storage_id = storage_id_for(conn, old_hash)
    conn.close()
    old_note = utils.note_path_for(old_hash, old_storage_id)
    old_note.parent.mkdir(parents=True, exist_ok=True)
    old_note.write_text(
        "---\nartist: Manual Old\ndate_added: '2020-01-01 00:00:00'\ntopics:\n  - preserved\nwd_tags: []\n---\n",
        encoding="utf-8",
    )
    review_file = utils.REVIEW_DIR / "replacement.jpg"
    review_file.write_bytes(b"replacement")
    review_file.with_suffix(".jpg.json").write_text(json.dumps({"best_match": old_hash, "metadata": {"artist": "New Artist"}}), encoding="utf-8")

    def fake_process_file(path, config, metadata=None, delete_source=False, skip_similarity=False, sync_index=True):
        conn = insert_mock_item(sqlite_operator, new_hash, artist="New Artist", date_added="2026-02-02 00:00:00")
        new_storage_id = storage_id_for(conn, new_hash)
        md = web_api.generate_markdown(conn, new_hash)
        note_path = utils.note_path_for(new_hash, new_storage_id)
        note_path.parent.mkdir(parents=True, exist_ok=True)
        utils.atomic_write_text(note_path, md)
        conn.close()
        if delete_source:
            path.unlink()
        return True, "ok", {"file_hash": new_hash}

    monkeypatch.setattr(web_api, "process_file", fake_process_file)
    monkeypatch.setattr(web_api, "_delete_item_after_replacement", lambda target_hash: {"hash": target_hash, "status": "deleted", "cleanup_errors": []})

    result = web_api._review_action_sync("replacement.jpg", "replace")
    conn = sqlite_operator.init_database()
    new_storage_id = storage_id_for(conn, new_hash)
    conn.close()
    new_data = frontmatter_from_markdown(utils.note_path_for(new_hash, new_storage_id).read_text(encoding="utf-8"))

    assert result["status"] == "success"
    assert new_data["artist"] == "Old DB Artist"
    assert new_data["date_added"] == "2026-01-01 00:00:00"
    assert new_data["topics"] == ["[preserved](../../../../../topics/preserved.md)"]
    assert new_data["wd_tags"] == []


def test_wd_tagger_reuses_cached_session(monkeypatch, tmp_path):
    service, utils = fresh_backend(monkeypatch, tmp_path, "tagging.service", "utils")
    source = tmp_path / "tagged.jpg"
    source.write_bytes(b"image")
    calls = {"sessions": 0}

    class FakeSession:
        def __init__(self, path, providers=None):
            calls["sessions"] += 1

        def get_inputs(self):
            return [types.SimpleNamespace(name="input", shape=[1, 448, 448, 3])]

        def get_outputs(self):
            return [types.SimpleNamespace(name="output")]

        def get_providers(self):
            return ["CPUExecutionProvider"]

    fake_ort = types.SimpleNamespace(
        get_available_providers=lambda: ["CPUExecutionProvider"],
        InferenceSession=FakeSession,
    )
    fake_hf = types.SimpleNamespace(hf_hub_download=lambda **kwargs: "")
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hf)
    monkeypatch.setattr(service, "get_mime_type", lambda path: "image/jpeg")
    monkeypatch.setattr(service, "_ensure_model_files", lambda repo, hf: (tmp_path / "model.onnx", tmp_path / "tags.csv"))
    monkeypatch.setattr(service, "_load_labels", lambda path: [{"name": "safe", "category": "9"}])
    monkeypatch.setattr(service.Image, "open", lambda path: types.SimpleNamespace(seek=lambda frame: None))
    monkeypatch.setattr(service, "_predict_image_tags", lambda *args, **kwargs: ({"label": "safe"}, [], [{"name": "tag"}]))

    first = service.tag_media(source, item_hash="6" * 64, config={"tagging": {"device": "cpu"}}, storage_id="000000000001")
    second = service.tag_media(source, item_hash="7" * 64, config={"tagging": {"device": "cpu"}}, storage_id="000000000002")

    assert first.status == "ok"
    assert second.status == "ok"
    assert calls["sessions"] == 1
    assert utils.wd_tag_cache_path_for("6" * 64, "000000000001").exists()


def test_wd_tagger_concurrent_calls_initialize_session_once(monkeypatch, tmp_path):
    service, = fresh_backend(monkeypatch, tmp_path, "tagging.service")
    source = tmp_path / "tagged.jpg"
    source.write_bytes(b"image")
    calls = {"sessions": 0}

    class FakeSession:
        def __init__(self, path, providers=None):
            time.sleep(0.05)
            calls["sessions"] += 1

        def get_inputs(self):
            return [types.SimpleNamespace(name="input", shape=[1, 448, 448, 3])]

        def get_outputs(self):
            return [types.SimpleNamespace(name="output")]

        def get_providers(self):
            return ["CPUExecutionProvider"]

    monkeypatch.setitem(sys.modules, "onnxruntime", types.SimpleNamespace(get_available_providers=lambda: ["CPUExecutionProvider"], InferenceSession=FakeSession))
    monkeypatch.setitem(sys.modules, "huggingface_hub", types.SimpleNamespace(hf_hub_download=lambda **kwargs: ""))
    monkeypatch.setattr(service, "get_mime_type", lambda path: "image/jpeg")
    monkeypatch.setattr(service, "_ensure_model_files", lambda repo, hf: (tmp_path / "model.onnx", tmp_path / "tags.csv"))
    monkeypatch.setattr(service, "_load_labels", lambda path: [{"name": "safe", "category": "9"}])
    monkeypatch.setattr(service.Image, "open", lambda path: types.SimpleNamespace(seek=lambda frame: None))
    monkeypatch.setattr(service, "_predict_image_tags", lambda *args, **kwargs: ({"label": "safe"}, [], []))

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda index: service.tag_media(source, item_hash=f"{index:064x}", config={"tagging": {"device": "cpu"}}), range(4)))

    assert [result.status for result in results] == ["ok", "ok", "ok", "ok"]
    assert calls["sessions"] == 1


def test_wd_tagger_failed_session_is_not_cached(monkeypatch, tmp_path):
    service, = fresh_backend(monkeypatch, tmp_path, "tagging.service")
    source = tmp_path / "tagged.jpg"
    source.write_bytes(b"image")
    calls = {"sessions": 0}

    class FakeSession:
        def __init__(self, path, providers=None):
            calls["sessions"] += 1
            if calls["sessions"] == 1:
                raise RuntimeError("load failed")

        def get_inputs(self):
            return [types.SimpleNamespace(name="input", shape=[1, 448, 448, 3])]

        def get_outputs(self):
            return [types.SimpleNamespace(name="output")]

        def get_providers(self):
            return ["CPUExecutionProvider"]

    monkeypatch.setitem(sys.modules, "onnxruntime", types.SimpleNamespace(get_available_providers=lambda: ["CPUExecutionProvider"], InferenceSession=FakeSession))
    monkeypatch.setitem(sys.modules, "huggingface_hub", types.SimpleNamespace(hf_hub_download=lambda **kwargs: ""))
    monkeypatch.setattr(service, "get_mime_type", lambda path: "image/jpeg")
    monkeypatch.setattr(service, "_ensure_model_files", lambda repo, hf: (tmp_path / "model.onnx", tmp_path / "tags.csv"))
    monkeypatch.setattr(service, "_load_labels", lambda path: [{"name": "safe", "category": "9"}])
    monkeypatch.setattr(service.Image, "open", lambda path: types.SimpleNamespace(seek=lambda frame: None))
    monkeypatch.setattr(service, "_predict_image_tags", lambda *args, **kwargs: ({"label": "safe"}, [], []))

    failed = service.tag_media(source, item_hash="8" * 64, config={"tagging": {"device": "cpu"}})
    recovered = service.tag_media(source, item_hash="9" * 64, config={"tagging": {"device": "cpu"}})

    assert failed.status == "failed"
    assert recovered.status == "ok"
    assert calls["sessions"] == 2


def test_stale_metadata_scan_streams_and_respects_limit(monkeypatch, tmp_path):
    metadata_index, = fresh_backend(monkeypatch, tmp_path, "metadata_index")
    seen = {"rows": 0}

    class Cursor:
        def __iter__(self):
            for index in range(10):
                seen["rows"] += 1
                yield (str(index), f"{index:012}", None, "", "", 0, 0, "", 0, 0, "")

        def fetchall(self):
            raise AssertionError("fetchall must not be used")

    class Conn:
        def execute(self, *args, **kwargs):
            return Cursor()

    monkeypatch.setattr(metadata_index, "ensure_metadata_schema", lambda conn: None)

    assert metadata_index.stale_metadata_hashes(Conn(), limit=3) == ["0", "1", "2"]
    assert seen["rows"] == 3


def test_metadata_dirty_queue_created_and_drained_before_scan(monkeypatch, tmp_path):
    utils, sqlite_operator, metadata_index = fresh_backend(monkeypatch, tmp_path, "utils", "db.sqlite_operator", "metadata_index")
    item_hash = "ab" * 32
    conn = insert_mock_item(sqlite_operator, item_hash)
    write_compact_note(utils, conn, item_hash, "---\ntopics:\n  - queued-topic\n---\n")
    metadata_index.enqueue_metadata_dirty(conn, item_hash, "test")
    conn.commit()

    monkeypatch.setattr(
        metadata_index,
        "stale_metadata_hashes",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("stale scan should not run while dirty queue has work")),
    )

    result = metadata_index.reindex_stale_metadata_batch(conn, limit=10)
    topics = [row[0] for row in conn.execute("SELECT topic FROM item_topics WHERE item_hash = ?", (item_hash,))]
    queued = conn.execute("SELECT COUNT(*) FROM metadata_dirty_queue").fetchone()[0]
    conn.close()

    assert result["source"] == "dirty_queue"
    assert result["indexed"] == 1
    assert result["dirty_remaining"] is False
    assert topics == ["queued-topic"]
    assert queued == 0


def test_metadata_repair_idles_without_dirty_queue_by_default(monkeypatch, tmp_path):
    sqlite_operator, metadata_index = fresh_backend(monkeypatch, tmp_path, "db.sqlite_operator", "metadata_index")
    conn = sqlite_operator.init_database()

    monkeypatch.setattr(
        metadata_index,
        "stale_metadata_hashes",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("default repair should not stale scan")),
    )

    result = metadata_index.reindex_stale_metadata_batch(conn, limit=10)
    conn.close()

    assert result["source"] == "idle"
    assert result["queued"] == 0


def test_metadata_repair_allows_explicit_stale_scan(monkeypatch, tmp_path):
    sqlite_operator, metadata_index = fresh_backend(monkeypatch, tmp_path, "db.sqlite_operator", "metadata_index")
    conn = sqlite_operator.init_database()
    calls = []

    monkeypatch.setattr(metadata_index, "stale_metadata_hashes", lambda *args, **kwargs: calls.append("scan") or [])

    result = metadata_index.reindex_stale_metadata_batch(conn, limit=10, allow_scan=True)
    conn.close()

    assert calls == ["scan"]
    assert result["source"] == "stale_scan"
    assert result["queued"] == 0


def test_metadata_watchdog_keeps_pending_hashes_after_failure(monkeypatch, tmp_path):
    sqlite_operator, metadata_index = fresh_backend(monkeypatch, tmp_path, "db.sqlite_operator", "metadata_index")
    sqlite_operator.init_database().close()

    class FakeTimer:
        def __init__(self, delay, callback):
            self.delay = delay
            self.callback = callback
            self.daemon = False
            self.started = False

        def start(self):
            self.started = True

    monkeypatch.setattr(metadata_index.threading, "Timer", FakeTimer)
    metadata_index._watchdog_pending = {"watch-hash"}
    metadata_index._watchdog_timer = None
    metadata_index._watchdog_flushing = False

    def fail_reindex(conn, item_hash, reason):
        raise RuntimeError("locked")

    monkeypatch.setattr(metadata_index, "safe_reindex_item_metadata", fail_reindex)
    metadata_index._watchdog_flush()

    assert metadata_index._watchdog_pending == {"watch-hash"}
    assert isinstance(metadata_index._watchdog_timer, FakeTimer)
    assert metadata_index._watchdog_timer.delay == 2.0

    calls = []

    def ok_reindex(conn, item_hash, reason):
        calls.append((item_hash, reason))
        return {"status": "ok"}

    metadata_index._watchdog_timer = None
    monkeypatch.setattr(metadata_index, "safe_reindex_item_metadata", ok_reindex)
    metadata_index._watchdog_flush()

    assert calls == [("watch-hash", "watchdog")]
    assert metadata_index._watchdog_pending == set()


def test_metadata_cached_counters_update_after_reindex(monkeypatch, tmp_path):
    utils, sqlite_operator, metadata_index = fresh_backend(monkeypatch, tmp_path, "utils", "db.sqlite_operator", "metadata_index")
    item_hash = "ac" * 32
    conn = insert_mock_item(sqlite_operator, item_hash)
    write_compact_note(
        utils,
        conn,
        item_hash,
        "---\ntopics:\n  - one\n  - two\nwd_rating: safe\nwd_tags:\n  - shared\n---\n",
    )
    metadata_index.reindex_item_metadata(conn, item_hash)
    first = metadata_index.metadata_index_status(conn)

    write_compact_note(utils, conn, item_hash, "---\ntopics:\n  - one\nwd_rating: explicit\n---\n")
    metadata_index.reindex_item_metadata(conn, item_hash)
    second = metadata_index.metadata_index_status(conn)
    conn.close()

    assert first["indexed"] == 1
    assert first["topics"] == 2
    assert first["wd_tags"] == 2
    assert first["facet_counts"] == 6
    assert second["indexed"] == 1
    assert second["topics"] == 1
    assert second["wd_tags"] == 1
    assert second["dirty"] == 0


def test_metadata_status_fast_path_skips_stale_count(monkeypatch, tmp_path):
    metadata_index, = fresh_backend(monkeypatch, tmp_path, "metadata_index")

    class ScalarCursor:
        def __init__(self, value):
            self.value = value

        def fetchone(self):
            return (self.value,)

    class StaleCursor:
        def __iter__(self):
            yield ("a", "000000000001", None, "", "", 0, 0, "", 0, 0, "")
            yield ("b", "000000000002", "b", "000000000002", "", 0, 0, "", 0, 0, "ok")

        def fetchall(self):
            raise AssertionError("fetchall must not be used")

    class Conn:
        def execute(self, sql, *args):
            if "FROM items" in sql and "LEFT JOIN item_metadata_files" in sql:
                raise AssertionError("fast status must not scan stale rows")
            return ScalarCursor(0)

    monkeypatch.setattr(metadata_index, "ensure_metadata_schema", lambda conn: None)
    monkeypatch.setattr(metadata_index, "metadata_index_ready", lambda conn: False)

    status = metadata_index.metadata_index_status(Conn())

    assert status["stale"] is None
    assert status["stale_deep"] is False


def test_metadata_status_deep_uses_streaming_stale_count(monkeypatch, tmp_path):
    metadata_index, = fresh_backend(monkeypatch, tmp_path, "metadata_index")

    class ScalarCursor:
        def __init__(self, value):
            self.value = value

        def fetchone(self):
            return (self.value,)

    class StaleCursor:
        def __iter__(self):
            yield ("a", "000000000001", None, "", "", 0, 0, "", 0, 0, "")
            yield ("b", "000000000002", "b", "000000000002", "", 0, 0, "", 0, 0, "ok")

        def fetchall(self):
            raise AssertionError("fetchall must not be used")

    class Conn:
        def execute(self, sql, *args):
            if "FROM items" in sql and "LEFT JOIN item_metadata_files" in sql:
                return StaleCursor()
            return ScalarCursor(0)

    monkeypatch.setattr(metadata_index, "ensure_metadata_schema", lambda conn: None)
    monkeypatch.setattr(metadata_index, "metadata_index_ready", lambda conn: False)
    monkeypatch.setattr(metadata_index, "_row_stale", lambda row: row[0] == "a")

    status = metadata_index.metadata_index_status(Conn(), deep=True)

    assert status["stale"] == 1
    assert status["stale_deep"] is True


def test_rebuild_metadata_index_status_does_not_clear_rows(monkeypatch, tmp_path):
    utils, sqlite_operator, metadata_index = fresh_backend(monkeypatch, tmp_path, "utils", "db.sqlite_operator", "metadata_index")
    tool = load_maintenance_tool("rebuild_metadata_index")
    item_hash = "aa" * 32
    conn = insert_mock_item(sqlite_operator, item_hash)
    write_compact_note(utils, conn, item_hash, "---\ntopics:\n  - keep-topic\n---\n")
    metadata_index.reindex_item_metadata(conn, item_hash)
    conn.commit()
    before = conn.execute("SELECT COUNT(*) FROM item_topics").fetchone()[0]
    conn.close()

    report = tool.run("status")

    conn = sqlite_operator.init_database()
    after = conn.execute("SELECT COUNT(*) FROM item_topics").fetchone()[0]
    conn.close()
    assert report["action"] == "status"
    assert before == 1
    assert after == before


def test_simple_frontmatter_parser_matches_yaml_for_common_fields(monkeypatch, tmp_path):
    metadata_index, = fresh_backend(monkeypatch, tmp_path, "metadata_index")
    yaml_text = """hash: abc
title: lmz000001.jpg
storage_id: lmz000001
source_url: https://example.test/item
platform: pixiv
source_artist: artist-001
artist: artist-001
date_added: '2026-01-01 00:00:00'
topics:
- topic-a
- topic-b
wd_rating: safe
wd_character_tags:
- character-a
wd_tags:
- tag-a
- tag-b
"""

    parsed = metadata_index._parse_simple_frontmatter(yaml_text)
    expected = yaml.safe_load(yaml_text)

    assert parsed is not None
    assert str(parsed.pop("date_added")) == str(expected.pop("date_added"))
    assert parsed == expected


def test_simple_frontmatter_parser_falls_back_for_complex_yaml(monkeypatch, tmp_path):
    metadata_index, = fresh_backend(monkeypatch, tmp_path, "metadata_index")
    yaml_text = """topics: [topic-a, topic-b]
manual:
  nested: true
"""

    assert metadata_index._parse_simple_frontmatter(yaml_text) is None


def test_rebuild_metadata_index_fails_when_storage_id_missing(monkeypatch, tmp_path):
    sqlite_operator, = fresh_backend(monkeypatch, tmp_path, "db.sqlite_operator")
    tool = load_maintenance_tool("rebuild_metadata_index")
    item_hash = "bb" * 32
    conn = insert_mock_item(sqlite_operator, item_hash)
    conn.execute("UPDATE items SET storage_id = '' WHERE hash = ?", (item_hash,))
    conn.commit()
    conn.close()

    assert tool.main(["--stale"]) == 2


def test_rebuild_metadata_index_stale_reindexes_compact_files(monkeypatch, tmp_path):
    utils, sqlite_operator = fresh_backend(monkeypatch, tmp_path, "utils", "db.sqlite_operator")
    tool = load_maintenance_tool("rebuild_metadata_index")
    item_hash = "cc" * 32
    conn = insert_mock_item(sqlite_operator, item_hash)
    write_compact_note(utils, conn, item_hash, "---\ntopics:\n  - stale-topic\n---\n")
    conn.close()

    report = tool.run("stale")

    conn = sqlite_operator.init_database()
    topics = [row[0] for row in conn.execute("SELECT topic FROM item_topics WHERE item_hash = ?", (item_hash,))]
    conn.close()
    assert report["indexed"] == 1
    assert topics == ["stale-topic"]


def test_rebuild_metadata_index_full_clears_and_rebuilds(monkeypatch, tmp_path):
    utils, sqlite_operator, metadata_index = fresh_backend(monkeypatch, tmp_path, "utils", "db.sqlite_operator", "metadata_index")
    tool = load_maintenance_tool("rebuild_metadata_index")
    item_hash = "dd" * 32
    conn = insert_mock_item(sqlite_operator, item_hash)
    write_compact_note(utils, conn, item_hash, "---\ntopics:\n  - rebuilt-topic\n---\n")
    metadata_index.ensure_metadata_schema(conn)
    conn.execute(
        "INSERT OR IGNORE INTO item_topics(item_hash, topic, topic_norm) VALUES (?, 'old-topic', 'old-topic')",
        (item_hash,),
    )
    conn.commit()
    conn.close()

    report = tool.run("full")

    conn = sqlite_operator.init_database()
    topics = [row[0] for row in conn.execute("SELECT topic FROM item_topics WHERE item_hash = ? ORDER BY topic", (item_hash,))]
    index_names = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND name LIKE 'idx_item_%'"
        ).fetchall()
    }
    ready = metadata_index.metadata_index_ready(conn)
    status = metadata_index.metadata_index_status(conn)
    conn.close()
    assert report["indexed"] == 1
    assert topics == ["rebuilt-topic"]
    assert ready is True
    assert status["indexed"] == 1
    assert status["topics"] == 1
    assert status["facet_counts"] == 3
    assert set(metadata_index.METADATA_SECONDARY_INDEXES).issubset(index_names)
    assert set(report["stages_ms"]) >= {
        "item_fetch",
        "metadata_read_parse",
        "row_building",
        "db_flushes",
        "item_updates",
        "metadata_file_inserts",
        "topic_inserts",
        "wd_tag_inserts",
        "commits",
        "secondary_index_drop",
        "secondary_index_rebuild",
        "facet_rebuild",
        "counter_refresh",
    }


def test_rebuild_metadata_progress_callback_reports_full_rebuild(monkeypatch, tmp_path):
    utils, sqlite_operator, metadata_index = fresh_backend(monkeypatch, tmp_path, "utils", "db.sqlite_operator", "metadata_index")
    item_hash = "d8" * 32
    conn = insert_mock_item(sqlite_operator, item_hash)
    write_compact_note(utils, conn, item_hash, "---\ntopics:\n  - progress-topic\n---\n")
    events = []

    result = metadata_index.rebuild_all_metadata(conn, progress_callback=lambda **event: events.append(event))
    conn.close()

    assert result["indexed"] == 1
    assert any(event.get("items_total") == 1 for event in events)
    assert any(event.get("items_done") == 1 for event in events)
    assert {event.get("stage") for event in events if event.get("stage")} >= {
        "reading metadata",
        "rebuilding facets",
        "rebuilding indexes",
        "refreshing counters",
    }


def test_metadata_status_includes_maintenance_rebuild_job(monkeypatch, tmp_path):
    sqlite_operator, metadata_index = fresh_backend(monkeypatch, tmp_path, "db.sqlite_operator", "metadata_index")
    conn = sqlite_operator.init_database()

    metadata_index._reset_maintenance_rebuild_job("full")
    metadata_index._update_maintenance_rebuild_job(stage="reading metadata", items_total=10, items_done=3)
    status = metadata_index.metadata_index_status(conn)
    metadata_index._finish_maintenance_rebuild_job("completed", items_done=10)
    finished = metadata_index.maintenance_rebuild_status()
    conn.close()

    assert status["maintenance_rebuild"]["running"] is True
    assert status["maintenance_rebuild"]["mode"] == "full"
    assert status["maintenance_rebuild"]["items_total"] == 10
    assert status["maintenance_rebuild"]["items_done"] == 3
    assert finished["running"] is False
    assert finished["status"] == "completed"


def test_metadata_rebuild_api_starts_maintenance_job(monkeypatch, tmp_path):
    web_api, = fresh_backend(monkeypatch, tmp_path, "web_api")
    calls = []

    def fake_start(full=False, maintenance=False):
        calls.append((full, maintenance))
        return {"status": "started", "full": full, "maintenance_rebuild": {"running": True}}

    monkeypatch.setattr(web_api, "start_metadata_repair_worker", fake_start)

    result = asyncio.run(web_api.rebuild_metadata_index())

    assert result["status"] == "started"
    assert calls == [(True, True)]


def test_rebuild_metadata_index_full_skips_deep_validation_by_default(monkeypatch, tmp_path):
    utils, sqlite_operator = fresh_backend(monkeypatch, tmp_path, "utils", "db.sqlite_operator")
    tool = load_maintenance_tool("rebuild_metadata_index")
    item_hash = "de" * 32
    conn = insert_mock_item(sqlite_operator, item_hash)
    write_compact_note(utils, conn, item_hash, "---\ntopics:\n  - fast-full\n---\n")
    conn.close()

    monkeypatch.setattr(
        tool,
        "stale_metadata_count",
        lambda conn: (_ for _ in ()).throw(AssertionError("deep stale scan should not run")),
    )

    report = tool.run("full")

    assert report["indexed"] == 1
    assert report["stale_before"] is None
    assert report["stale_after"] is None
    assert report["status"]["stale_deep"] is False


def test_rebuild_metadata_index_full_deep_validate_preserves_stale_scan(monkeypatch, tmp_path):
    utils, sqlite_operator, metadata_index = fresh_backend(monkeypatch, tmp_path, "utils", "db.sqlite_operator", "metadata_index")
    tool = load_maintenance_tool("rebuild_metadata_index")
    item_hash = "df" * 32
    conn = insert_mock_item(sqlite_operator, item_hash)
    write_compact_note(utils, conn, item_hash, "---\ntopics:\n  - deep-full\n---\n")
    conn.close()

    calls = {"count": 0}
    original = metadata_index.stale_metadata_count

    def counted(conn):
        calls["count"] += 1
        return original(conn)

    monkeypatch.setattr(metadata_index, "stale_metadata_count", counted)
    monkeypatch.setattr(tool, "stale_metadata_count", counted)

    report = tool.run("full", deep_validate=True)

    assert report["indexed"] == 1
    assert report["status"]["stale_deep"] is True
    assert calls["count"] >= 2


def test_rebuild_metadata_index_failure_recreates_secondary_indexes(monkeypatch, tmp_path):
    utils, sqlite_operator, metadata_index = fresh_backend(monkeypatch, tmp_path, "utils", "db.sqlite_operator", "metadata_index")
    item_hash = "d9" * 32
    conn = insert_mock_item(sqlite_operator, item_hash)
    write_compact_note(utils, conn, item_hash, "---\ntopics:\n  - fail-full\n---\n")
    metadata_index.ensure_metadata_schema(conn)
    conn.commit()

    def fail_payload(*args, **kwargs):
        raise RuntimeError("forced rebuild failure")

    monkeypatch.setattr(metadata_index, "_metadata_payload", fail_payload)

    with pytest.raises(RuntimeError, match="forced rebuild failure"):
        metadata_index.rebuild_all_metadata(conn)

    index_names = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        ).fetchall()
    }
    ready_row = conn.execute(
        "SELECT value FROM metadata_index_state WHERE key = ?",
        (metadata_index.READY_KEY,),
    ).fetchone()
    conn.close()

    assert set(metadata_index.METADATA_SECONDARY_INDEXES).issubset(index_names)
    assert ready_row == ("0",)


def test_rebuild_metadata_index_stale_limit_caps_work(monkeypatch, tmp_path):
    utils, sqlite_operator = fresh_backend(monkeypatch, tmp_path, "utils", "db.sqlite_operator")
    tool = load_maintenance_tool("rebuild_metadata_index")
    hashes = ["ee" * 32, "ef" * 32]
    conn = insert_mock_item(sqlite_operator, hashes[0])
    write_compact_note(utils, conn, hashes[0], "---\ntopics:\n  - first-topic\n---\n")
    conn.close()
    conn = insert_mock_item(sqlite_operator, hashes[1])
    write_compact_note(utils, conn, hashes[1], "---\ntopics:\n  - second-topic\n---\n")
    conn.close()

    report = tool.run("stale", limit=1)

    conn = sqlite_operator.init_database()
    indexed = conn.execute("SELECT COUNT(*) FROM item_metadata_files").fetchone()[0]
    conn.close()
    assert report["indexed"] == 1
    assert indexed == 1
    assert report["stale_after"] is None


def test_rebuild_metadata_index_json_output(monkeypatch, tmp_path, capsys):
    sqlite_operator, = fresh_backend(monkeypatch, tmp_path, "db.sqlite_operator")
    conn = sqlite_operator.init_database()
    conn.close()
    tool = load_maintenance_tool("rebuild_metadata_index")

    assert tool.main(["--status", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["action"] == "status"
    assert "items" in payload


def test_maintenance_cli_default_and_alias_run_update_downloaders(monkeypatch, tmp_path):
    tool = load_maintenance_tool("maintenance_cli")
    calls = []
    monkeypatch.setattr(tool, "update_downloaders", lambda: calls.append("update") or 0)

    assert tool.main([]) == 0
    assert tool.main(["update-tools"]) == 0
    assert tool.main(["update"]) == 0
    assert calls == ["update", "update", "update"]


def test_maintenance_cli_check_invokes_readiness_script(monkeypatch, tmp_path):
    tool = load_maintenance_tool("maintenance_cli")
    commands = []

    def fake_run(cmd, text=True, **kwargs):
        commands.append(cmd)
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(tool.subprocess, "run", fake_run)

    assert tool.main(["check"]) == 0
    assert commands
    assert commands[0][0] == sys.executable
    assert commands[0][-1] == "--non-interactive"
    assert "lmz_readiness_check.py" in commands[0][1]


def test_maintenance_cli_install_playwright_browser(monkeypatch, tmp_path):
    tool = load_maintenance_tool("maintenance_cli")
    commands = []

    def fake_run(cmd, text=True, **kwargs):
        commands.append(cmd)
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(tool.subprocess, "run", fake_run)

    assert tool.main(["install-playwright-browser"]) == 0
    assert commands == [[sys.executable, "-m", "playwright", "install", "chromium"]]


def test_update_tools_wrapper_runs_update_downloaders(monkeypatch, tmp_path):
    captured = []
    fake_cli = types.SimpleNamespace(main=lambda argv: captured.append(argv) or 0)
    monkeypatch.setitem(sys.modules, "maintenance_cli", fake_cli)
    monkeypatch.setattr(sys, "argv", ["update_tools.py"])

    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(ROOT / "tools" / "maintenance" / "update_tools.py"), run_name="__main__")

    assert exc.value.code == 0
    assert captured == [["update-downloaders"]]


def test_insert_to_database_default_timestamp_is_utc_format(monkeypatch, tmp_path):
    sqlite_operator, = fresh_backend(monkeypatch, tmp_path, "db.sqlite_operator")
    sample = tmp_path / "utc-check.jpg"
    sample.write_bytes(b"utc")
    file_hash = "ab" * 32
    conn = sqlite_operator.init_database()
    sqlite_operator.insert_to_database(
        conn,
        sample,
        file_hash,
        "image/jpeg",
        ".jpg",
        metadata={},
        file_size=sample.stat().st_size,
    )
    conn.commit()
    row = conn.execute("SELECT date_added FROM items WHERE hash = ?", (file_hash,)).fetchone()
    conn.close()
    assert row and re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", str(row[0]))


def test_review_state_timestamp_uses_standard_format(monkeypatch, tmp_path):
    web_api, = fresh_backend(monkeypatch, tmp_path, "web_api")
    updated = web_api._set_review_state({}, "resolved_delete")
    value = str(updated.get("resolved_at") or "")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", value)


def test_stream_logs_tail_then_heartbeat_and_truncate_recovery(monkeypatch, tmp_path):
    web_api, = fresh_backend(monkeypatch, tmp_path, "web_api")
    log_file = web_api.LOG_FILES["system.jsonl"]
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text('{"message":"tail"}\n', encoding="utf-8")

    monotonic_counter = {"value": 0.0}

    def fake_monotonic():
        monotonic_counter["value"] += 20.0
        return monotonic_counter["value"]

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(web_api.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(web_api.asyncio, "sleep", fake_sleep)

    async def _run():
        response = await web_api.stream_logs("system.jsonl")
        gen = response.body_iterator
        first = await gen.__anext__()
        second = await gen.__anext__()
        log_file.write_text("", encoding="utf-8")
        log_file.write_text('{"message":"after-clear"}\n', encoding="utf-8")
        third = await gen.__anext__()
        await gen.aclose()
        return first, second, third

    first, second, third = asyncio.run(_run())
    first_text = first.decode() if isinstance(first, bytes) else str(first)
    second_text = second.decode() if isinstance(second, bytes) else str(second)
    third_text = third.decode() if isinstance(third, bytes) else str(third)

    assert "tail" in first_text
    assert "keep-alive" in second_text
    assert "after-clear" in third_text


def test_topic_filter_not_ready_skips_disk_scan(monkeypatch, tmp_path):
    web_api, = fresh_backend(monkeypatch, tmp_path, "web_api")
    repair_calls = []
    monkeypatch.setattr(web_api, "metadata_index_ready", lambda conn: False)
    monkeypatch.setattr(web_api, "start_metadata_repair_worker", lambda full=False: repair_calls.append(full) or {"status": "started"})
    monkeypatch.setattr(web_api, "load_note_topics", lambda *args: (_ for _ in ()).throw(AssertionError("note scan called")))

    result = web_api._get_items_sync(None, None, "newest", "all", [], [], [], ["topic"], [], [], None, 25)

    assert result == {"items": [], "has_more": False, "next_cursor": None}
    assert repair_calls == [False]

    facet = web_api._get_facets_sync("topic", "topic", 25)

    assert facet == {"kind": "topic", "items": []}
    assert repair_calls == [False, False]


def test_metadata_facets_keep_counts_correct(monkeypatch, tmp_path):
    sqlite_operator, metadata_index = fresh_backend(monkeypatch, tmp_path, "db.sqlite_operator", "metadata_index")
    item_a = "aa" * 32
    item_b = "bb" * 32
    conn = insert_mock_item(sqlite_operator, item_a)
    conn.close()
    conn = insert_mock_item(sqlite_operator, item_b)
    metadata_index.ensure_metadata_schema(conn)
    conn.execute("INSERT OR IGNORE INTO item_topics(item_hash, topic, topic_norm) VALUES (?, 'Alpha', 'alpha')", (item_a,))
    conn.execute("INSERT OR IGNORE INTO item_topics(item_hash, topic, topic_norm) VALUES (?, 'Alpha', 'alpha')", (item_b,))
    conn.execute("INSERT OR IGNORE INTO item_wd_tags(item_hash, tag, tag_norm, tag_type) VALUES (?, 'Shared', 'shared', 'general')", (item_a,))
    conn.execute("INSERT OR IGNORE INTO item_wd_tags(item_hash, tag, tag_norm, tag_type) VALUES (?, 'Shared', 'shared', 'character')", (item_a,))
    conn.commit()

    topics = metadata_index.metadata_facets(conn, "topic", "", 10)
    wd_tags = metadata_index.metadata_facets(conn, "wd_tag", "", 10)

    conn.close()
    assert topics == [{"value": "Alpha", "count": 2}]
    assert wd_tags == [{"value": "Shared", "count": 1}]


def test_metadata_facet_counts_refresh_and_fallback(monkeypatch, tmp_path):
    utils, sqlite_operator, metadata_index, web_api = fresh_backend(
        monkeypatch,
        tmp_path,
        "utils",
        "db.sqlite_operator",
        "metadata_index",
        "web_api",
    )
    item_hash = "41" * 32
    conn = insert_mock_item(sqlite_operator, item_hash)
    write_compact_note(utils, conn, item_hash, "---\ntopics:\n  - Alpha\nwd_tags:\n  - Shared\n---\n")
    metadata_index.reindex_item_metadata(conn, item_hash)
    metadata_index._set_metadata_index_ready(conn, True)
    conn.commit()

    count_row = conn.execute(
        "SELECT value, count FROM metadata_facet_counts WHERE kind = 'wd_tag' AND value_norm = 'shared'"
    ).fetchone()
    assert count_row == ("Shared", 1)

    conn.execute("DELETE FROM metadata_facet_counts")
    conn.commit()
    fallback = metadata_index.metadata_facets(conn, "wd_tag", "share", 10)
    assert fallback == [{"value": "Shared", "count": 1}]

    write_compact_note(utils, conn, item_hash, "---\ntopics:\n  - Beta\nwd_tags:\n  - New Tag\n---\n")
    metadata_index.reindex_item_metadata(conn, item_hash)
    metadata_index._set_metadata_index_ready(conn, True)
    conn.commit()
    conn.close()

    facet = web_api._get_facets_sync("wd_tag", "", 10)
    assert facet == {"kind": "wd_tag", "items": [{"value": "New Tag", "count": 1}]}


def test_item_details_include_topic_and_wd_counts(monkeypatch, tmp_path):
    utils, sqlite_operator, metadata_index, web_api = fresh_backend(
        monkeypatch,
        tmp_path,
        "utils",
        "db.sqlite_operator",
        "metadata_index",
        "web_api",
    )
    item_a = "91" * 32
    item_b = "92" * 32
    conn = insert_mock_item(sqlite_operator, item_a)
    write_compact_note(conn=conn, utils=utils, item_hash=item_a, text="---\ntopics:\n  - Shared Topic\nwd_rating: safe\nwd_tags:\n  - Shared Tag\n---\n")
    metadata_index.reindex_item_metadata(conn, item_a)
    conn.commit()
    conn.close()

    conn = insert_mock_item(sqlite_operator, item_b)
    write_compact_note(conn=conn, utils=utils, item_hash=item_b, text="---\ntopics:\n  - Shared Topic\nwd_rating: safe\nwd_tags:\n  - Shared Tag\n---\n")
    metadata_index.reindex_item_metadata(conn, item_b)
    conn.commit()
    conn.close()

    detail = web_api._get_item_sync(item_a)

    assert detail["topic_counts"]["Shared Topic"] == 2
    assert detail["wd_tag_counts"]["safe"] == 2
    assert detail["wd_tag_counts"]["Shared Tag"] == 2


def test_patch_item_updates_topics_and_wd_frontmatter_for_one_item(monkeypatch, tmp_path):
    utils, sqlite_operator, metadata_index, web_api = fresh_backend(
        monkeypatch,
        tmp_path,
        "utils",
        "db.sqlite_operator",
        "metadata_index",
        "web_api",
    )
    item_a = "93" * 32
    item_b = "94" * 32
    conn = insert_mock_item(sqlite_operator, item_a)
    write_compact_note(
        utils,
        conn,
        item_a,
        "---\ntopics:\n  - keep\nwd_rating: safe\nwd_character_tags:\n  - wrong character\nwd_tags:\n  - promote me\n  - remove me\n---\n",
    )
    metadata_index.reindex_item_metadata(conn, item_a)
    conn.commit()
    conn.close()

    conn = insert_mock_item(sqlite_operator, item_b)
    write_compact_note(
        utils,
        conn,
        item_b,
        "---\ntopics:\n  - keep\nwd_rating: safe\nwd_character_tags:\n  - wrong character\nwd_tags:\n  - promote me\n  - remove me\n---\n",
    )
    metadata_index.reindex_item_metadata(conn, item_b)
    conn.commit()
    conn.close()

    result = web_api._update_item_sync(
        item_a,
        web_api.ItemUpdate(
            topics=["keep", "promote me"],
            wd_rating="",
            wd_character_tags=[],
            wd_tags=["promote me"],
        ),
    )

    conn = sqlite_operator.init_database()
    storage_a = storage_id_for(conn, item_a)
    storage_b = storage_id_for(conn, item_b)
    data_a = frontmatter_from_markdown(utils.note_path_for(item_a, storage_a).read_text(encoding="utf-8"))
    data_b = frontmatter_from_markdown(utils.note_path_for(item_b, storage_b).read_text(encoding="utf-8"))
    rows_a = conn.execute("SELECT tag_type, tag FROM item_wd_tags WHERE item_hash = ? ORDER BY tag_type, tag", (item_a,)).fetchall()
    rows_b = conn.execute("SELECT tag_type, tag FROM item_wd_tags WHERE item_hash = ? ORDER BY tag_type, tag", (item_b,)).fetchall()
    conn.close()

    assert result["topics"] == ["keep", "promote_me"]
    assert result["wd_tags"]["rating"] == "None"
    assert result["wd_tags"]["characters"] == []
    assert result["wd_tags"]["general"] == ["promote me"]
    assert data_a["topics"][0].startswith("[keep](")
    assert data_a["topics"][1].startswith("[promote_me](")
    assert data_a["wd_rating"] == ""
    assert data_a["wd_character_tags"] == []
    assert data_a["wd_tags"] == ["promote me"]
    assert data_b["topics"] == ["keep"]
    assert data_b["wd_rating"] == "safe"
    assert data_b["wd_character_tags"] == ["wrong character"]
    assert data_b["wd_tags"] == ["promote me", "remove me"]
    assert rows_a == [("general", "promote me")]
    assert rows_b == [("character", "wrong character"), ("general", "promote me"), ("general", "remove me"), ("rating", "safe")]


def test_topic_file_creation_preserves_body_and_item_markdown_uses_links(monkeypatch, tmp_path):
    utils, sqlite_operator, web_api, topics = fresh_backend(monkeypatch, tmp_path, "utils", "db.sqlite_operator", "web_api", "topics")
    item_hash = "95" * 32
    conn = insert_mock_item(sqlite_operator, item_hash)
    storage_id = storage_id_for(conn, item_hash)
    note_path = utils.note_path_for(item_hash, storage_id)

    existing_topic = utils.TOPICS_DIR / "syntax.md"
    existing_topic.parent.mkdir(parents=True, exist_ok=True)
    existing_topic.write_text("---\ncreated_at: old\n---\n\npersonal notes stay\n", encoding="utf-8")

    result = web_api._update_item_sync(
        item_hash,
        web_api.ItemUpdate(topics=["syntax", "color theory"]),
    )
    data = frontmatter_from_markdown(note_path.read_text(encoding="utf-8"))

    assert result["topics"] == ["color_theory", "syntax"]
    assert data["topics"][0].startswith("[syntax](")
    assert data["topics"][1].startswith("[color_theory](")
    assert "personal notes stay" in existing_topic.read_text(encoding="utf-8")
    assert (utils.TOPICS_DIR / "color_theory.md").exists()

    parsed = topics.parse_topic_values(data["topics"], note_path)
    assert [entry["label"] for entry in parsed] == ["syntax", "color_theory"]
    assert [entry["topic_rel"] for entry in parsed] == ["syntax.md", "color_theory.md"]
    conn.close()


def test_repeated_topic_promotions_create_each_topic_file(monkeypatch, tmp_path):
    utils, sqlite_operator, web_api = fresh_backend(monkeypatch, tmp_path, "utils", "db.sqlite_operator", "web_api")
    item_hash = "99" * 32
    conn = insert_mock_item(sqlite_operator, item_hash)
    storage_id = storage_id_for(conn, item_hash)
    conn.close()

    first = web_api._update_item_sync(
        item_hash,
        web_api.ItemUpdate(topics=["karin (blue archive)"]),
    )
    assert first["topics"] == ["karin_blue_archive"]
    assert (utils.TOPICS_DIR / "karin_blue_archive.md").exists()

    second = web_api._update_item_sync(
        item_hash,
        web_api.ItemUpdate(topics=["karin_blue_archive", "black hair"]),
    )
    note_path = utils.note_path_for(item_hash, storage_id)
    data = frontmatter_from_markdown(note_path.read_text(encoding="utf-8"))

    assert second["topics"] == ["black_hair", "karin_blue_archive"]
    assert (utils.TOPICS_DIR / "karin_blue_archive.md").exists()
    assert (utils.TOPICS_DIR / "black_hair.md").exists()
    assert data["topics"] == [
        "[karin_blue_archive](../../../../../topics/karin_blue_archive.md)",
        "[black_hair](../../../../../topics/black_hair.md)",
    ]


def test_metadata_index_parses_linked_and_legacy_topics(monkeypatch, tmp_path):
    utils, sqlite_operator, metadata_index, topics = fresh_backend(monkeypatch, tmp_path, "utils", "db.sqlite_operator", "metadata_index", "topics")
    item_hash = "96" * 32
    conn = insert_mock_item(sqlite_operator, item_hash)
    storage_id = storage_id_for(conn, item_hash)
    note_path = utils.note_path_for(item_hash, storage_id)
    linked = topics.topic_markdown_link("syntax", note_path)
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(f"---\ntopics:\n  - '{linked}'\n  - legacy topic\n---\n", encoding="utf-8")

    metadata_index.reindex_item_metadata(conn, item_hash)

    rows = conn.execute(
        "SELECT topic, topic_norm, topic_rel, topic_key FROM item_topics WHERE item_hash = ? ORDER BY topic",
        (item_hash,),
    ).fetchall()
    assert rows == [
        ("legacy topic", "legacy topic", "", "plain:legacy topic"),
        ("syntax", "syntax", "syntax.md", "rel:syntax.md"),
    ]
    assert metadata_index.metadata_facets(conn, "topic", "synt", 10) == [{"value": "syntax", "count": 1}]
    conn.close()


def test_workspace_topic_rename_updates_linked_legacy_and_cross_vault_refs(monkeypatch, tmp_path):
    utils, sqlite_operator, metadata_index, web_api, topics, vaults = fresh_backend(
        monkeypatch,
        tmp_path,
        "utils",
        "db.sqlite_operator",
        "metadata_index",
        "web_api",
        "topics",
        "vaults",
    )
    vaults.create_vault("Second")
    vault_items = {item["id"]: item for item in vaults.vault_list()}
    second_root = Path(vault_items["second"]["root"])
    second_db = Path(vault_items["second"]["db_path"])

    linked_hash = "a7" * 32
    legacy_hash = "a8" * 32
    second_hash = "a9" * 32
    linked_conn = insert_mock_item(sqlite_operator, linked_hash, date_added="2026-01-01 00:00:01")
    linked_conn.close()
    legacy_conn = insert_mock_item(sqlite_operator, legacy_hash, date_added="2026-01-01 00:00:02")
    legacy_storage = storage_id_for(legacy_conn, legacy_hash)
    write_compact_note(utils, legacy_conn, legacy_hash, "---\ntopics:\n  - Old Topic\n---\n")
    metadata_index.reindex_item_metadata(legacy_conn, legacy_hash)
    legacy_conn.commit()
    legacy_conn.close()

    web_api._update_item_sync(linked_hash, web_api.ItemUpdate(topics=["Old Topic"]))
    old_topic = utils.TOPICS_DIR / "old_topic.md"
    old_topic.write_text("---\ncreated_at: old\n---\n\npersonal notes stay\n", encoding="utf-8")

    second_conn = sqlite_operator.init_database(second_db)
    second_storage = sqlite_operator.allocate_storage_id(second_conn)
    second_conn.execute(
        """
        INSERT INTO items(hash, storage_id, original_filename, file_extension, mime_type, size_bytes, date_added, source_url, source_url_norm, platform, source_artist, phash)
        VALUES (?, ?, ?, '.jpg', 'image/jpeg', 10, '2026-01-01 00:00:03', '', '', 'local', 'DB Artist', '')
        """,
        (second_hash, second_storage, f"{second_hash}.jpg"),
    )
    second_note = second_root / "vault" / "notes" / second_hash[:2] / f"{second_storage}.md"
    second_note.parent.mkdir(parents=True, exist_ok=True)
    second_link = topics.topic_markdown_link("Old Topic", second_note)
    second_note.write_text(f"---\ntopics:\n  - '{second_link}'\n---\n", encoding="utf-8")
    metadata_index.ensure_metadata_schema(second_conn)
    for entry in topics.parse_topic_values([second_link], second_note):
        second_conn.execute(
            "INSERT INTO item_topics(item_hash, topic, topic_norm, topic_rel, topic_key) VALUES (?, ?, ?, ?, ?)",
            (second_hash, entry["label"], entry["label"].casefold(), entry["topic_rel"], entry["topic_key"]),
        )
    second_conn.commit()
    second_conn.close()

    ready_conn = sqlite_operator.init_database()
    metadata_index._set_metadata_index_ready(ready_conn, True)
    ready_conn.commit()
    ready_conn.close()

    result = web_api._rename_topic_sync("Old Topic", "New Topic")

    assert result["status"] == "success"
    assert set(result["vaults_touched"]) == {"default", "second"}
    assert result["notes_rewritten"] == 3
    assert result["legacy_plain_refs_rewritten"] == 1
    assert not old_topic.exists()
    new_topic = utils.TOPICS_DIR / "new_topic.md"
    assert new_topic.exists()
    assert "personal notes stay" in new_topic.read_text(encoding="utf-8")

    conn = sqlite_operator.init_database()
    linked_storage = storage_id_for(conn, linked_hash)
    linked_data = frontmatter_from_markdown(utils.note_path_for(linked_hash, linked_storage).read_text(encoding="utf-8"))
    legacy_data = frontmatter_from_markdown(utils.note_path_for(legacy_hash, legacy_storage).read_text(encoding="utf-8"))
    rows = conn.execute("SELECT item_hash, topic, topic_norm, topic_rel, topic_key FROM item_topics ORDER BY item_hash").fetchall()
    new_items = web_api._get_items_sync(None, None, "newest", "all", [], [], [], ["new_topic"], [], [], None, 25)
    old_items = web_api._get_items_sync(None, None, "newest", "all", [], [], [], ["old_topic"], [], [], None, 25)
    all_topics = web_api._get_facets_sync("topic", "", 50, "all")["items"]
    conn.close()

    assert linked_data["topics"] == ["[new_topic](../../../../../topics/new_topic.md)"]
    assert legacy_data["topics"] == ["[new_topic](../../../../../topics/new_topic.md)"]
    assert rows == [
        (linked_hash, "new_topic", "new_topic", "new_topic.md", "rel:new_topic.md"),
        (legacy_hash, "new_topic", "new_topic", "new_topic.md", "rel:new_topic.md"),
    ]
    assert [item["hash"] for item in new_items["items"]] == [legacy_hash, linked_hash]
    assert old_items["items"] == []
    assert "new_topic" in {item["value"] for item in all_topics}
    assert "old_topic" not in {item["value"] for item in all_topics}

    second_conn = sqlite3.connect(second_db)
    try:
        second_rows = second_conn.execute("SELECT topic, topic_norm, topic_rel, topic_key FROM item_topics WHERE item_hash = ?", (second_hash,)).fetchall()
    finally:
        second_conn.close()
    assert second_rows == [("new_topic", "new_topic", "new_topic.md", "rel:new_topic.md")]
    assert "[new_topic](" in second_note.read_text(encoding="utf-8")


def test_workspace_topic_rename_rejects_missing_and_existing_target(monkeypatch, tmp_path):
    utils, web_api = fresh_backend(monkeypatch, tmp_path, "utils", "web_api")
    (utils.TOPICS_DIR / "old_topic.md").parent.mkdir(parents=True, exist_ok=True)
    (utils.TOPICS_DIR / "old_topic.md").write_text("---\n---\n", encoding="utf-8")
    (utils.TOPICS_DIR / "new_topic.md").write_text("---\n---\n", encoding="utf-8")

    with pytest.raises(HTTPException) as conflict:
        web_api._rename_topic_sync("Old Topic", "New Topic")
    assert conflict.value.status_code == 409

    with pytest.raises(HTTPException) as missing:
        web_api._rename_topic_sync("Missing Topic", "Other Topic")
    assert missing.value.status_code == 404


def test_metadata_facets_no_match_uses_built_count_table_without_scan(monkeypatch, tmp_path):
    metadata_index, = fresh_backend(monkeypatch, tmp_path, "metadata_index")

    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        def fetchone(self):
            return self.rows[0] if self.rows else None

        def fetchall(self):
            return self.rows

    class Conn:
        def execute(self, sql, params=()):
            if "SELECT 1 FROM metadata_facet_counts" in sql:
                return Cursor([(1,)])
            if "FROM metadata_facet_counts" in sql:
                return Cursor([])
            if "FROM item_wd_tags" in sql:
                raise AssertionError("built count table should not fall back to scan")
            return Cursor([])

    monkeypatch.setattr(metadata_index, "ensure_metadata_schema", lambda conn: None)

    assert metadata_index.metadata_facets(Conn(), "wd_tag", "missing", 10) == []


def test_metadata_facets_empty_ready_kind_does_not_scan(monkeypatch, tmp_path):
    metadata_index, = fresh_backend(monkeypatch, tmp_path, "metadata_index")

    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        def fetchone(self):
            return self.rows[0] if self.rows else None

        def fetchall(self):
            return self.rows

    class Conn:
        def execute(self, sql, params=()):
            if "SELECT 1 FROM metadata_facet_counts" in sql:
                return Cursor([])
            if "FROM metadata_facet_kind_state" in sql and params == ("artist",):
                return Cursor([("1",)])
            if "SELECT COUNT(*) FROM metadata_facet_counts" in sql:
                return Cursor([(0,)])
            if "FROM metadata_facet_counts" in sql:
                return Cursor([])
            if "FROM items" in sql or "FROM item_topics" in sql or "FROM item_wd_tags" in sql:
                raise AssertionError("ready empty facet cache should not fall back to scan")
            return Cursor([])

    monkeypatch.setattr(metadata_index, "ensure_metadata_schema", lambda conn: None)

    assert metadata_index.metadata_facets(Conn(), "artist", "missing", 10) == []


def test_metadata_filters_use_exact_when_available_and_partial_when_needed(monkeypatch, tmp_path):
    utils, sqlite_operator, metadata_index, web_api = fresh_backend(
        monkeypatch,
        tmp_path,
        "utils",
        "db.sqlite_operator",
        "metadata_index",
        "web_api",
    )

    def add_item(item_hash: str, frontmatter: str, date_added: str):
        conn = insert_mock_item(sqlite_operator, item_hash, date_added=date_added)
        write_compact_note(utils, conn, item_hash, frontmatter)
        metadata_index.reindex_item_metadata(conn, item_hash)
        conn.commit()
        conn.close()

    alpha_hash = "10" * 32
    alpha_extra_hash = "20" * 32
    beta_hash = "30" * 32
    wd_hash = "40" * 32
    add_item(alpha_hash, "---\ntopics:\n  - alpha\n---\n", "2026-01-01 00:00:01")
    add_item(alpha_extra_hash, "---\ntopics:\n  - alpha-extra\n---\n", "2026-01-01 00:00:02")
    add_item(beta_hash, "---\ntopics:\n  - beta\n---\n", "2026-01-01 00:00:03")
    add_item(wd_hash, "---\ntopics: []\nwd_tags:\n  - wd-one\n---\n", "2026-01-01 00:00:04")

    conn = sqlite_operator.init_database()
    metadata_index._set_metadata_index_ready(conn, True)
    assert web_api._metadata_filter_has_exact(conn, "item_topics", "topic_norm", "alpha") is True
    assert web_api._metadata_filter_has_exact(conn, "item_topics", "topic_norm", "alph") is False
    assert web_api._metadata_filter_has_exact(conn, "item_wd_tags", "tag_norm", "wd-one") is True
    conn.commit()
    conn.close()

    exact_topic = web_api._get_items_sync(None, None, "newest", "all", [], [], [], ["alpha"], [], [], None, 25)
    partial = web_api._get_items_sync(None, None, "newest", "all", [], [], [], ["alph"], [], [], None, 25)
    exact = web_api._get_items_sync(None, None, "newest", "all", [], [], [], ["beta"], [], [], None, 25)
    wd_exact = web_api._get_items_sync(None, None, "newest", "all", [], [], [], [], ["wd-one"], [], None, 25)

    assert [item["hash"] for item in exact_topic["items"]] == [alpha_hash]
    assert [item["hash"] for item in partial["items"]] == [alpha_extra_hash, alpha_hash]
    assert [item["hash"] for item in exact["items"]] == [beta_hash]
    assert [item["hash"] for item in wd_exact["items"]] == [wd_hash]


def test_artist_platform_facets_and_filters_use_exact_first(monkeypatch, tmp_path):
    utils, sqlite_operator, metadata_index, web_api = fresh_backend(
        monkeypatch,
        tmp_path,
        "utils",
        "db.sqlite_operator",
        "metadata_index",
        "web_api",
    )

    def add_item(item_hash: str, artist: str, platform: str, date_added: str):
        conn = insert_mock_item(sqlite_operator, item_hash, artist=artist, date_added=date_added)
        conn.execute("UPDATE items SET platform = ? WHERE hash = ?", (platform, item_hash))
        write_compact_note(utils, conn, item_hash, "---\ntopics: []\n---\n")
        metadata_index.reindex_item_metadata(conn, item_hash)
        metadata_index._set_metadata_index_ready(conn, True)
        conn.commit()
        conn.close()

    artist_one_hash = "51" * 32
    artist_extra_hash = "52" * 32
    platform_hash = "53" * 32
    add_item(artist_one_hash, "artist1", "site1", "2026-01-01 00:00:01")
    add_item(artist_extra_hash, "artist11", "site11", "2026-01-01 00:00:02")
    add_item(platform_hash, "other", "site1", "2026-01-01 00:00:03")

    artist_facets = web_api._get_facets_sync("artist", "artist", 10)
    platform_facets = web_api._get_facets_sync("platform", "site", 10)
    exact_artist = web_api._get_items_sync(None, None, "newest", "all", ["artist1"], [], [], [], [], [], None, 25)
    partial_artist = web_api._get_items_sync(None, None, "newest", "all", ["artist"], [], [], [], [], [], None, 25)
    exact_platform = web_api._get_items_sync(None, None, "newest", "all", [], ["site1"], [], [], [], [], None, 25)

    assert artist_facets["items"][0] == {"value": "artist1", "count": 1}
    assert {item["value"] for item in platform_facets["items"]} >= {"site1", "site11"}
    assert [item["hash"] for item in exact_artist["items"]] == [artist_one_hash]
    assert [item["hash"] for item in partial_artist["items"]] == [artist_extra_hash, artist_one_hash]
    assert [item["hash"] for item in exact_platform["items"]] == [platform_hash, artist_one_hash]


def test_artist_schema_backfills_from_item_artists(monkeypatch, tmp_path):
    sqlite_operator, artists = fresh_backend(monkeypatch, tmp_path, "db.sqlite_operator", "artists")
    first_hash = "61" * 32
    second_hash = "62" * 32
    third_hash = "66" * 32
    conn = insert_mock_item(sqlite_operator, first_hash, artist="Artist One")
    conn.close()
    conn = insert_mock_item(sqlite_operator, second_hash, artist="artist one")
    conn.close()
    conn = insert_mock_item(sqlite_operator, third_hash, artist="Unknown")

    artists.ensure_artist_schema(conn)
    artists.ensure_artist_schema(conn)
    rows = conn.execute("SELECT name, name_norm, kind FROM artists").fetchall()
    conn.close()

    assert rows == [("Artist One", "artist one", "artist")]


def test_artist_resolver_uses_aliases_and_skips_placeholders(monkeypatch, tmp_path):
    sqlite_operator, artists = fresh_backend(monkeypatch, tmp_path, "db.sqlite_operator", "artists")
    conn = sqlite_operator.init_database()
    canonical = artists.resolve_artist_name(conn, "Canonical Artist")
    artist_id = conn.execute("SELECT id FROM artists WHERE name = ?", (canonical,)).fetchone()[0]
    artists.add_artist_alias(conn, artist_id, "Old Artist")

    assert artists.resolve_artist_name(conn, "old artist") == "Canonical Artist"
    assert artists.resolve_artist_name(conn, "Unknown") == "Unknown"
    assert conn.execute("SELECT 1 FROM artists WHERE name_norm = 'unknown'").fetchone() is None
    conn.close()


def test_platform_schema_backfills_and_api_lists(monkeypatch, tmp_path):
    sqlite_operator, platforms_module, workspace_db, web_api = fresh_backend(monkeypatch, tmp_path, "db.sqlite_operator", "platforms", "workspace_db", "web_api")
    conn = insert_mock_item(sqlite_operator, "67" * 32, artist="Platform Artist")
    conn.execute("UPDATE items SET platform = ? WHERE hash = ?", ("twitter", "67" * 32))
    conn.commit()
    conn.close()
    workspace_conn = workspace_db.connect_workspace_database()
    platforms_module.resolve_platform_label(workspace_conn, "Fanbox", create=True)
    workspace_conn.commit()
    workspace_conn.close()

    platforms = web_api._get_platforms_sync("", 20)["items"]
    used_platforms = web_api._get_platforms_sync("", 20, "used")["items"]
    x_platform = next(item for item in platforms if item["display_name"] == "X")

    assert x_platform["key_norm"] == "x"
    assert x_platform["item_count"] == 1
    assert any(item["display_name"] == "Fanbox" and item["item_count"] == 0 for item in platforms)
    assert all(item["item_count"] > 0 for item in used_platforms)


def test_stats_scope_used_and_all_for_artists_and_topics(monkeypatch, tmp_path):
    utils, sqlite_operator, artists_module, topics_module, metadata_index, workspace_db, web_api = fresh_backend(
        monkeypatch,
        tmp_path,
        "utils",
        "db.sqlite_operator",
        "artists",
        "topics",
        "metadata_index",
        "workspace_db",
        "web_api",
    )
    item_hash = "68" * 32
    conn = insert_mock_item(sqlite_operator, item_hash, artist="Used Artist")
    conn.commit()
    conn.close()
    workspace_conn = workspace_db.connect_workspace_database()
    artists_module.resolve_artist_name(workspace_conn, "Unused Artist", create=True)
    workspace_conn.commit()
    workspace_conn.close()

    web_api._update_item_sync(item_hash, web_api.ItemUpdate(topics=["used topic"]))
    web_api._update_item_sync(item_hash, web_api.ItemUpdate(wd_tags=["used wd tag"]))
    topics_module.ensure_topic_file("unused topic")
    workspace_conn = workspace_db.connect_workspace_database()
    workspace_db.upsert_wd_dictionary_tags(workspace_conn, [("general", "unused wd tag")])
    workspace_conn.commit()
    workspace_conn.close()
    conn = sqlite_operator.connect_database()
    metadata_index.rebuild_all_metadata(conn)
    conn.commit()
    conn.close()

    all_artists = web_api._get_artists_sync("", 20, "all")["items"]
    used_artists = web_api._get_artists_sync("", 20, "used")["items"]
    all_topics = web_api._get_facets_sync("topic", "", 20, "all")["items"]
    used_topics = web_api._get_facets_sync("topic", "", 20, "used")["items"]
    all_wd = web_api._get_facets_sync("wd_tag", "", 20, "all")["items"]
    used_wd = web_api._get_facets_sync("wd_tag", "", 20, "used")["items"]

    assert any(item["name"] == "Unused Artist" and item["item_count"] == 0 for item in all_artists)
    assert all(item["item_count"] > 0 for item in used_artists)
    assert any(item == {"value": "unused_topic", "count": 0} for item in all_topics)
    assert all(item["count"] > 0 for item in used_topics)
    assert any(item == {"value": "unused wd tag", "count": 0} for item in all_wd)
    assert all(item["count"] > 0 for item in used_wd)


def test_artist_api_lists_details_and_edits(monkeypatch, tmp_path):
    utils, sqlite_operator, web_api = fresh_backend(monkeypatch, tmp_path, "utils", "db.sqlite_operator", "web_api")
    item_hash = "63" * 32
    conn = insert_mock_item(sqlite_operator, item_hash, artist="Artist API")
    conn.close()

    listing = web_api._get_artists_sync("", 10)
    artist = next(item for item in listing["items"] if item["name"] == "Artist API")
    detail = web_api._get_artist_sync(artist["id"])
    alias = web_api._post_artist_alias_sync(artist["id"], web_api.ArtistAliasCreate(alias="API Alias"))
    link = web_api._post_artist_link_sync(
        artist["id"],
        web_api.ArtistLinkCreate(platform="twitter2", url="https://x.com/api_artist"),
    )
    updated = web_api._patch_artist_sync(
        artist["id"],
        web_api.ArtistUpdate(name="Artist Canonical", kind="brand", notes="note"),
    )

    assert artist["item_count"] == 1
    assert detail["name"] == "Artist API"
    assert alias["alias_norm"] == "api alias"
    assert link["platform"] == "X"
    assert link["handle"] == "api_artist"
    assert updated["name"] == "Artist Canonical"
    assert updated["kind"] == "brand"
    assert updated["notes"] == "note"
    conn = sqlite_operator.init_database()
    row = conn.execute("SELECT source_artist, storage_id FROM items WHERE hash = ?", (item_hash,)).fetchone()
    assert row[0] == "Artist Canonical"
    note_data = frontmatter_from_markdown(utils.note_path_for(item_hash, row[1]).read_text(encoding="utf-8"))
    assert note_data["artist"] == "Artist Canonical"
    conn.close()

    deleted_alias = web_api._delete_alias_sync(artist["id"], alias["id"])
    deleted_link = web_api._delete_link_sync(artist["id"], link["id"])
    assert deleted_alias == {"status": "success"}
    assert deleted_link == {"status": "success"}


def test_artist_api_rejects_duplicate_names_and_aliases(monkeypatch, tmp_path):
    sqlite_operator, web_api = fresh_backend(monkeypatch, tmp_path, "db.sqlite_operator", "web_api")
    conn = insert_mock_item(sqlite_operator, "64" * 32, artist="Artist A")
    conn.close()
    conn = insert_mock_item(sqlite_operator, "65" * 32, artist="Artist B")
    conn.close()

    artists = web_api._get_artists_sync("", 10)["items"]
    artist_a = next(item for item in artists if item["name"] == "Artist A")
    artist_b = next(item for item in artists if item["name"] == "Artist B")

    with pytest.raises(HTTPException) as duplicate_name:
        web_api._patch_artist_sync(artist_b["id"], web_api.ArtistUpdate(name="Artist A"))
    assert duplicate_name.value.status_code == 409

    with pytest.raises(HTTPException) as duplicate_alias:
        web_api._post_artist_alias_sync(artist_a["id"], web_api.ArtistAliasCreate(alias="Artist B"))
    assert duplicate_alias.value.status_code == 409

    with pytest.raises(HTTPException) as empty_link:
        web_api._post_artist_link_sync(artist_a["id"], web_api.ArtistLinkCreate(platform="", url=""))
    assert empty_link.value.status_code == 400

    with pytest.raises(HTTPException) as placeholder_name:
        web_api._patch_artist_sync(artist_a["id"], web_api.ArtistUpdate(name="Unknown"))
    assert placeholder_name.value.status_code == 400


def test_artist_merge_absorbs_sources_and_rewrites_items(monkeypatch, tmp_path):
    utils, sqlite_operator, artists, workspace_db, web_api = fresh_backend(
        monkeypatch,
        tmp_path,
        "utils",
        "db.sqlite_operator",
        "artists",
        "workspace_db",
        "web_api",
    )
    target_hash = "68" * 32
    source_hash = "69" * 32
    second_source_hash = "70" * 32
    alias_hash = "71" * 32
    for item_hash, artist_name in [
        (target_hash, "iomayashi"),
        (source_hash, "nixeu"),
        (second_source_hash, "iomaya"),
        (alias_hash, "old nix"),
    ]:
        conn = insert_mock_item(sqlite_operator, item_hash, artist=artist_name)
        md_content = web_api.generate_markdown(conn, item_hash)
        row = conn.execute("SELECT storage_id FROM items WHERE hash = ?", (item_hash,)).fetchone()
        utils.atomic_write_text(utils.note_path_for(item_hash, row[0]), md_content)
        conn.close()

    listing = web_api._get_artists_sync("", 20)["items"]
    ids = {artist["name"]: artist["id"] for artist in listing}
    workspace_conn = workspace_db.connect_workspace_database()
    workspace_conn.execute("DELETE FROM artists WHERE id = ?", (ids["old nix"],))
    artists.add_artist_alias(workspace_conn, ids["nixeu"], "old nix")
    artists.add_artist_link(workspace_conn, ids["iomayashi"], "X", "https://x.com/shared")
    artists.add_artist_link(workspace_conn, ids["nixeu"], "X", "https://x.com/shared")
    artists.add_artist_link(workspace_conn, ids["iomaya"], "Pixiv", "https://www.pixiv.net/users/iomaya")
    workspace_conn.execute("UPDATE artists SET notes = ? WHERE id = ?", ("old nixeu notes", ids["nixeu"]))
    workspace_conn.execute("UPDATE artists SET notes = ? WHERE id = ?", ("old iomaya notes", ids["iomaya"]))
    workspace_conn.commit()
    workspace_conn.close()

    preview = web_api._preview_artist_merge_sync(
        ids["iomayashi"],
        web_api.ArtistMergeRequest(source_artist_ids=[ids["nixeu"], ids["iomaya"]]),
    )
    assert preview["affected_items"] == 3
    assert {alias["value"] for alias in preview["aliases"]["add"]} == {"nixeu", "iomaya"}
    assert {alias["value"] for alias in preview["aliases"]["move"]} == {"old nix"}
    assert len(preview["links"]["move"]) == 1
    assert len(preview["links"]["duplicates"]) == 1
    assert preview["notes_appended"] == 2
    conn = sqlite_operator.init_database()
    workspace_conn = workspace_db.connect_workspace_database()
    assert workspace_conn.execute("SELECT name FROM artists WHERE id = ?", (ids["nixeu"],)).fetchone()[0] == "nixeu"
    assert conn.execute("SELECT source_artist FROM items WHERE hash = ?", (source_hash,)).fetchone()[0] == "nixeu"
    assert workspace_conn.execute("SELECT artist_id FROM artist_links WHERE url_norm = ?", ("https://www.pixiv.net/users/iomaya",)).fetchone()[0] == ids["iomaya"]
    conn.close()
    workspace_conn.close()

    merged = web_api._merge_artist_sync(
        ids["iomayashi"],
        web_api.ArtistMergeRequest(source_artist_ids=[ids["nixeu"], ids["iomaya"]]),
    )
    assert merged["merged"] is True
    assert merged["target_detail"]["name"] == "iomayashi"
    assert "merged from nixeu" in merged["target_detail"]["notes"]
    assert "old iomaya notes" in merged["target_detail"]["notes"]

    conn = sqlite_operator.init_database()
    workspace_conn = workspace_db.connect_workspace_database()
    names = {row[0] for row in workspace_conn.execute("SELECT name FROM artists").fetchall()}
    assert "iomayashi" in names
    assert "nixeu" not in names
    assert "iomaya" not in names
    aliases = {row[0] for row in workspace_conn.execute("SELECT alias FROM artist_aliases WHERE artist_id = ?", (ids["iomayashi"],)).fetchall()}
    assert {"nixeu", "iomaya", "old nix"} <= aliases
    item_artists = {
        row[0]
        for row in conn.execute(
            "SELECT source_artist FROM items WHERE hash IN (?, ?, ?)",
            (source_hash, second_source_hash, alias_hash),
        ).fetchall()
    }
    assert item_artists == {"iomayashi"}
    links = workspace_conn.execute("SELECT platform, url FROM artist_links WHERE artist_id = ?", (ids["iomayashi"],)).fetchall()
    assert len(links) == 2
    assert artists.resolve_artist_name(workspace_conn, "nixeu") == "iomayashi"
    row = conn.execute("SELECT storage_id FROM items WHERE hash = ?", (source_hash,)).fetchone()
    note_data = frontmatter_from_markdown(utils.note_path_for(source_hash, row[0]).read_text(encoding="utf-8"))
    assert note_data["artist"] == "iomayashi"
    conn.close()
    workspace_conn.close()


def test_artist_merge_preview_reports_alias_conflicts_without_mutating(monkeypatch, tmp_path):
    sqlite_operator, artists, workspace_db, web_api = fresh_backend(monkeypatch, tmp_path, "db.sqlite_operator", "artists", "workspace_db", "web_api")
    conn = insert_mock_item(sqlite_operator, "73" * 32, artist="Target Merge")
    conn.close()
    conn = insert_mock_item(sqlite_operator, "74" * 32, artist="Source Merge")
    conn.close()
    conn = insert_mock_item(sqlite_operator, "75" * 32, artist="Unrelated Merge")
    conn.close()

    listing = web_api._get_artists_sync("", 20)["items"]
    ids = {artist["name"]: artist["id"] for artist in listing}
    workspace_conn = workspace_db.connect_workspace_database()
    artists.add_artist_alias(workspace_conn, ids["Source Merge"], "conflict alias")
    workspace_conn.execute(
        "INSERT INTO artist_aliases(artist_id, alias, alias_norm, created_at) VALUES (?, ?, ?, ?)",
        (ids["Unrelated Merge"], "Source Merge", "source merge", "2026-01-01 00:00:00"),
    )
    workspace_conn.commit()
    workspace_conn.close()

    preview = web_api._preview_artist_merge_sync(
        ids["Target Merge"],
        web_api.ArtistMergeRequest(source_artist_ids=[ids["Source Merge"]]),
    )

    assert {alias["value"] for alias in preview["aliases"]["move"]} == {"conflict alias"}
    assert {alias["value"] for alias in preview["aliases"]["conflicts"]} == {"Source Merge"}

    workspace_conn = workspace_db.connect_workspace_database()
    before_alias_owner = workspace_conn.execute("SELECT artist_id FROM artist_aliases WHERE alias_norm = 'conflict alias'").fetchone()[0]
    assert before_alias_owner == ids["Source Merge"]
    assert workspace_conn.execute("SELECT name FROM artists WHERE id = ?", (ids["Source Merge"],)).fetchone()[0] == "Source Merge"
    assert workspace_conn.execute("SELECT artist_id FROM artist_aliases WHERE alias_norm = 'source merge'").fetchone()[0] == ids["Unrelated Merge"]
    workspace_conn.close()


def test_artist_merge_rejects_invalid_sources(monkeypatch, tmp_path):
    sqlite_operator, workspace_db, web_api = fresh_backend(monkeypatch, tmp_path, "db.sqlite_operator", "workspace_db", "web_api")
    conn = insert_mock_item(sqlite_operator, "72" * 32, artist="Merge Target")
    workspace_conn = workspace_db.connect_workspace_database()
    workspace_conn.execute(
        """
        INSERT INTO artists(name, name_norm, kind, notes, created_at, updated_at)
        VALUES ('Unknown', 'unknown', 'artist', '', '2026-01-01 00:00:00', '2026-01-01 00:00:00')
        """
    )
    workspace_conn.commit()
    placeholder_id = workspace_conn.execute("SELECT id FROM artists WHERE name_norm = 'unknown'").fetchone()[0]
    workspace_conn.close()
    conn.close()
    artist = next(item for item in web_api._get_artists_sync("", 10)["items"] if item["name"] == "Merge Target")

    with pytest.raises(HTTPException) as empty_sources:
        web_api._preview_artist_merge_sync(artist["id"], web_api.ArtistMergeRequest(source_artist_ids=[]))
    assert empty_sources.value.status_code == 400

    with pytest.raises(HTTPException) as self_merge:
        web_api._merge_artist_sync(artist["id"], web_api.ArtistMergeRequest(source_artist_ids=[artist["id"]]))
    assert self_merge.value.status_code == 400

    with pytest.raises(HTTPException) as placeholder_source:
        web_api._merge_artist_sync(artist["id"], web_api.ArtistMergeRequest(source_artist_ids=[placeholder_id]))
    assert placeholder_source.value.status_code == 400

    with pytest.raises(HTTPException) as placeholder_target:
        web_api._merge_artist_sync(placeholder_id, web_api.ArtistMergeRequest(source_artist_ids=[artist["id"]]))
    assert placeholder_target.value.status_code == 400


def test_search_manager_query_sees_pending_during_vp_rebuild(monkeypatch, tmp_path):
    search_manager_module, = fresh_backend(monkeypatch, tmp_path, "db.search_manager")
    manager = search_manager_module.SearchManager()
    manager.video_tree = search_manager_module.VPTreeSearcher(search_manager_module._cosine_dist)
    manager.audio_tree = search_manager_module.VPTreeSearcher(search_manager_module._hamming_dist_audio)
    manager.global_tree = search_manager_module.BKTreeSearcher()
    manager.tile_tree = search_manager_module.BKTreeSearcher()
    manager.url_registry = search_manager_module.URLRegistry()

    import numpy as np

    sig = np.array([1.0, 0.0], dtype=np.float32).tobytes()
    manager.video_tree.add("video-hash", sig)
    started = threading.Event()
    release = threading.Event()
    original_make_tree = search_manager_module.VPTreeSearcher._make_tree

    def slow_make_tree(self, items):
        started.set()
        release.wait(timeout=2)
        return original_make_tree(self, items)

    monkeypatch.setattr(search_manager_module.VPTreeSearcher, "_make_tree", slow_make_tree)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(manager.rebuild_deferred_indexes)
        assert started.wait(timeout=2)
        matches = manager.query_video(None, sig, ai_threshold=0.01)
        release.set()
        future.result(timeout=2)

    assert matches == [("video-hash", 1.0, "Semantic")]


def test_search_manager_removes_deleted_hashes_and_urls(monkeypatch, tmp_path):
    search_manager_module, = fresh_backend(monkeypatch, tmp_path, "db.search_manager")
    manager = search_manager_module.SearchManager()
    manager.video_tree = search_manager_module.VPTreeSearcher(search_manager_module._cosine_dist)
    manager.audio_tree = search_manager_module.VPTreeSearcher(search_manager_module._hamming_dist_audio)
    manager.global_tree = search_manager_module.BKTreeSearcher()
    manager.tile_tree = search_manager_module.BKTreeSearcher()
    manager.url_registry = search_manager_module.URLRegistry()

    import numpy as np

    phash = "0" * 16
    tile_phash = "f" * 16
    sig = np.array([1.0, 0.0], dtype=np.float32).tobytes()
    manager.update_indexes("deleted-hash", phash, "https://example.test/item", [(0, tile_phash)], visual_embedding=sig)
    manager.rebuild_deferred_indexes()

    assert manager.query_image(phash)
    assert manager.query_image(tile_phash)
    assert manager.query_video(None, sig, ai_threshold=0.01)
    assert manager.url_exists("https://example.test/item")

    manager.remove_indexes_batch([{"hash": "deleted-hash", "source_url": "https://example.test/item"}])

    assert manager.query_image(phash) == []
    assert manager.query_image(tile_phash) == []
    assert manager.query_video(None, sig, ai_threshold=0.01) == []
    assert not manager.url_exists("https://example.test/item")


def test_search_manager_vp_delete_defers_rebuild_outside_remove(monkeypatch, tmp_path):
    search_manager_module, = fresh_backend(monkeypatch, tmp_path, "db.search_manager")
    manager = search_manager_module.SearchManager()
    manager.video_tree = search_manager_module.VPTreeSearcher(search_manager_module._cosine_dist)
    manager.audio_tree = search_manager_module.VPTreeSearcher(search_manager_module._hamming_dist_audio)
    manager.global_tree = search_manager_module.BKTreeSearcher()
    manager.tile_tree = search_manager_module.BKTreeSearcher()
    manager.url_registry = search_manager_module.URLRegistry()

    import numpy as np

    sig = np.array([1.0, 0.0], dtype=np.float32).tobytes()
    manager.update_indexes("deleted-video", None, None, visual_embedding=sig)
    manager.rebuild_deferred_indexes()
    assert manager.query_video(None, sig, ai_threshold=0.01)

    def fail_sync_rebuild(self, items):
        raise AssertionError("remove should not rebuild VP tree synchronously")

    scheduled = []
    monkeypatch.setattr(search_manager_module.VPTreeSearcher, "_make_tree", fail_sync_rebuild)
    monkeypatch.setattr(manager, "_rebuild_deferred_indexes_async", lambda reason: scheduled.append(reason))

    result = manager.remove_indexes_batch([{"hash": "deleted-video"}])

    assert result["video"]["deferred"] is True
    assert scheduled == ["batch_remove"]
    assert manager.query_video(None, sig, ai_threshold=0.01) == []


def test_vp_rebuild_apply_does_not_resurrect_concurrent_delete(monkeypatch, tmp_path):
    search_manager_module, = fresh_backend(monkeypatch, tmp_path, "db.search_manager")
    tree = search_manager_module.VPTreeSearcher(search_manager_module._cosine_dist)

    import numpy as np

    sig_x = np.array([1.0, 0.0], dtype=np.float32).tobytes()
    sig_y = np.array([0.0, 1.0], dtype=np.float32).tobytes()
    tree.add("x", sig_x)
    tree.add("y", sig_y)
    tree.build_index()
    tree.dirty = True

    plan = tree.rebuild_plan()
    replacement = tree.build_replacement(plan)

    removed = tree.remove_hashes({"y"})
    assert removed["removed"] == 1

    applied = tree.apply_replacement(plan, replacement)
    assert applied["stale"] is True
    assert [item_hash for item_hash, _ in tree.indexed_items] == ["x"]
    assert tree.query(sig_y, 0.01) == []

    tree.build_index()
    assert tree.query(sig_x, 0.01) == [("x", 0.0)]
    assert tree.query(sig_y, 0.01) == []


def test_find_visual_duplicate_stops_tile_queries_after_first_match(monkeypatch, tmp_path):
    processor, = fresh_backend(monkeypatch, tmp_path, "processor")
    calls = []

    class FakeSearchManager:
        def query_image(self, phash, threshold):
            return []

        def query_global_only(self, phash, threshold):
            calls.append(phash)
            return [("match-hash", 1)]

    monkeypatch.setattr(processor, "search_manager", FakeSearchManager())

    match, match_type, total, distance = processor.find_visual_duplicate(
        "0" * 16,
        new_tiles=[(0, "tile-a"), (1, "tile-b"), (2, "tile-c")],
    )

    assert match == "match-hash"
    assert match_type == "Whole-to-Fragment (Tile #0)"
    assert total == 1
    assert distance == 1
    assert calls == ["tile-a"]


def test_hot_ingestion_paths_use_lightweight_db_helper(monkeypatch, tmp_path):
    processor, external_ingestion = fresh_backend(monkeypatch, tmp_path, "processor", "external_ingestion")

    assert "connect_database()" in inspect.getsource(processor.process_file)
    assert "connect_database()" in inspect.getsource(external_ingestion.ExternalIngestor._url_complete)
    assert "connect_database()" in inspect.getsource(external_ingestion.ExternalIngestor._instagram_complete)
    assert "connect_database()" in inspect.getsource(external_ingestion.ExternalIngestor._rollback_batch)


def test_downloader_wrappers_use_configured_timeouts(monkeypatch, tmp_path):
    gallery, yt_dlp = fresh_backend(monkeypatch, tmp_path, "downloaders.gallery_dl_wrapper", "downloaders.yt_dlp_wrapper")
    gallery_timeouts = []
    yt_timeouts = []

    class Result:
        returncode = 1
        stdout = ""
        stderr = "failed"

    def gallery_run(*args, **kwargs):
        gallery_timeouts.append(kwargs.get("timeout"))
        return Result()

    def yt_run(*args, **kwargs):
        yt_timeouts.append(kwargs.get("timeout"))
        return Result()

    monkeypatch.setattr(gallery, "get_config", lambda: {"external_tools": {"timeouts": {"gallery_metadata": 7, "gallery_download": 8}}})
    monkeypatch.setattr(gallery, "_base_args", lambda url: [])
    monkeypatch.setattr(gallery.subprocess, "run", gallery_run)
    gallery.inspect_gallery("https://example.test/item")
    gallery.download_gallery("https://example.test/item", metadata_info={"platform": "X", "download_url": "https://example.test/item"})

    monkeypatch.setattr(yt_dlp, "get_config", lambda: {"external_tools": {"timeouts": {"yt_dlp_metadata": 9, "yt_dlp_download": 10}}})
    monkeypatch.setattr(yt_dlp, "get_cookie_path", lambda: None)
    monkeypatch.setattr(yt_dlp, "get_cookie_auth_status", lambda: {})
    monkeypatch.setattr(yt_dlp.subprocess, "run", yt_run)
    yt_dlp.download_video("https://www.youtube.com/watch?v=mock")

    assert gallery_timeouts[:2] == [7, 8]
    assert yt_timeouts[:2] == [9, 10]


def test_downloader_wrapper_timeout_defaults(monkeypatch, tmp_path):
    gallery, yt_dlp = fresh_backend(monkeypatch, tmp_path, "downloaders.gallery_dl_wrapper", "downloaders.yt_dlp_wrapper")

    monkeypatch.setattr(gallery, "get_config", lambda: {})
    monkeypatch.setattr(yt_dlp, "get_config", lambda: {})

    assert gallery._timeout("gallery_metadata", 120) == 120
    assert gallery._timeout("gallery_download", 300) == 300
    assert yt_dlp._timeout("yt_dlp_metadata", 120) == 120
    assert yt_dlp._timeout("yt_dlp_download", 600) == 600


def test_thumbnail_repair_uses_shared_helper_and_skips_fresh(monkeypatch, tmp_path):
    utils, sqlite_operator, thumbnails = fresh_backend(monkeypatch, tmp_path, "utils", "db.sqlite_operator", "thumbnails")
    fresh_hash = "a" * 64
    stale_hash = "b" * 64
    conn = insert_mock_item(sqlite_operator, fresh_hash)
    fresh_storage_id = storage_id_for(conn, fresh_hash)
    stale_storage_id = sqlite_operator.allocate_storage_id(conn)
    conn.execute(
        """
        INSERT INTO items(hash, storage_id, original_filename, file_extension, mime_type, size_bytes, date_added, source_url, source_url_norm, platform, source_artist, phash)
        VALUES (?, ?, ?, '.jpg', 'image/jpeg', 10, ?, '', '', 'local', ?, '')
        """,
        (stale_hash, stale_storage_id, f"{stale_hash}.jpg", "2026-01-03 00:00:00", "DB Artist"),
    )
    conn.commit()
    for item_hash in [fresh_hash, stale_hash]:
        storage_id = fresh_storage_id if item_hash == fresh_hash else stale_storage_id
        asset = utils.asset_path_for(item_hash, ".jpg", "image/jpeg", storage_id=storage_id)
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_bytes(b"asset")
    fresh_thumb = thumbnails.thumbnail_path_for(fresh_hash, fresh_storage_id)
    fresh_thumb.parent.mkdir(parents=True, exist_ok=True)
    fresh_thumb.write_bytes(b"thumb")
    calls = []

    def fake_ensure(item_hash, extension, mime_type, wait=True, storage_id=None):
        calls.append((item_hash, extension, mime_type, wait, storage_id))
        return thumbnails.thumbnail_path_for(item_hash, storage_id)

    monkeypatch.setattr(thumbnails, "ensure_thumbnail", fake_ensure)

    result = thumbnails.repair_missing_thumbnails(conn, limit=10)

    assert calls == [(stale_hash, ".jpg", "image/jpeg", True, stale_storage_id)]
    assert result["generated"] == 1
    assert result["skipped"] == 1
    conn.close()


def test_thumbnail_api_returns_503_when_generation_is_busy(monkeypatch, tmp_path):
    sqlite_operator, web_api = fresh_backend(monkeypatch, tmp_path, "db.sqlite_operator", "web_api")
    item_hash = "c" * 64
    conn = insert_mock_item(sqlite_operator, item_hash)
    conn.close()

    def busy(*args, **kwargs):
        raise web_api.ThumbnailBusyError("busy")

    monkeypatch.setattr(web_api, "get_or_generate_thumbnail", busy)

    with pytest.raises(HTTPException) as exc:
        web_api._get_thumbnail_sync(item_hash)

    assert exc.value.status_code == 503


def test_no_duplicate_thumbnail_generation_paths_outside_thumbnail_module(monkeypatch, tmp_path):
    processor, web_api = fresh_backend(monkeypatch, tmp_path, "processor", "web_api")

    processor_source = inspect.getsource(processor)
    web_api_source = inspect.getsource(web_api)

    assert "ensure_thumbnail(" in inspect.getsource(processor.process_file)
    assert "get_or_generate_thumbnail(" in inspect.getsource(web_api._get_thumbnail_sync)
    assert "generate_image_thumbnail(" not in processor_source
    assert "generate_video_thumbnail(" not in processor_source
    assert "generate_image_thumbnail(" not in web_api_source
    assert "generate_video_thumbnail(" not in web_api_source


def test_sampled_video_extraction_uses_one_ffmpeg_subprocess(monkeypatch, tmp_path):
    fingerprint, = fresh_backend(monkeypatch, tmp_path, "fingerprint")
    calls = []
    kwargs_seen = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        kwargs_seen.append(kwargs)
        for value in cmd:
            if isinstance(value, str) and value.endswith(".png"):
                path = Path(value)
                path.parent.mkdir(parents=True, exist_ok=True)
                from PIL import Image
                image = Image.new("RGB", (2, 2), "red")
                image.save(path)
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(fingerprint, "get_video_duration", lambda path: 10.0)
    monkeypatch.setattr(fingerprint.subprocess, "run", fake_run)

    frames = fingerprint.extract_sampled_video_frames(tmp_path / "video.mp4", frame_count=5)

    assert len(frames) == 5
    assert len(calls) == 1
    assert calls[0].count("-i") == 5
    assert kwargs_seen[0]["stderr"] == fingerprint.subprocess.DEVNULL


def test_calculate_phash_logs_failures_with_traceback(monkeypatch, tmp_path):
    utils, = fresh_backend(monkeypatch, tmp_path, "utils")
    logger = importlib.import_module("logger")
    calls = []

    def fake_log_system(level, message, **kwargs):
        calls.append((level, message, kwargs))

    def fail_open(path):
        raise OSError("bad image")

    monkeypatch.setattr(logger, "log_system", fake_log_system)
    monkeypatch.setitem(sys.modules, "imagehash", types.SimpleNamespace(phash=lambda img: "unused"))
    from PIL import Image as PILImage
    monkeypatch.setattr(PILImage, "open", fail_open)

    assert utils.calculate_phash(tmp_path / "bad.jpg") is None
    assert calls == [
        (
            "WARNING",
            "Image perceptual hash failed",
            {"file": str(tmp_path / "bad.jpg"), "exc_info": True},
        )
    ]


def test_logger_helper_writes_traceback_to_json(monkeypatch, tmp_path):
    logger_impl, = fresh_backend(monkeypatch, tmp_path, "logger.logger")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logger_impl.JSONFormatter())
    test_logger = logging.getLogger("lmz_test_exc_info")
    old_handlers = test_logger.handlers[:]
    old_propagate = test_logger.propagate
    test_logger.handlers = [handler]
    test_logger.propagate = False

    try:
        try:
            raise RuntimeError("logged failure")
        except RuntimeError:
            logger_impl._log(test_logger, "WARNING", "Traceback check", file="bad.jpg", exc_info=True)

        record = json.loads(stream.getvalue())
        assert record["message"] == "Traceback check"
        assert record["file"] == "bad.jpg"
        assert "RuntimeError: logged failure" in record["exception"]
    finally:
        test_logger.handlers = old_handlers
        test_logger.propagate = old_propagate


def test_ingest_log_helpers_route_to_separate_streams(monkeypatch, tmp_path):
    logger_impl, = fresh_backend(monkeypatch, tmp_path, "logger.logger")
    streams = {}
    targets = {
        "local": logger_impl.ingest_local_logger,
        "online": logger_impl.ingest_online_logger,
        "audit": logger_impl.activity_logger,
    }
    old_state = {}

    for name, target in targets.items():
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logger_impl.JSONFormatter())
        streams[name] = stream
        old_state[name] = (target.handlers[:], target.propagate)
        target.handlers = [handler]
        target.propagate = False

    try:
        logger_impl.log_ingest_local("INFO", "local item", run_id="run-local")
        logger_impl.log_ingest_online("INFO", "online item", queue="normal")
        logger_impl.log_ingest_audit("INFO", "audit summary", ingest_type="local")

        assert "local item" in streams["local"].getvalue()
        assert "online item" not in streams["local"].getvalue()
        assert "online item" in streams["online"].getvalue()
        assert "local item" not in streams["online"].getvalue()
        assert "audit summary" in streams["audit"].getvalue()
    finally:
        for name, target in targets.items():
            handlers, propagate = old_state[name]
            target.handlers = handlers
            target.propagate = propagate


def test_log_activity_records_ingest_type_and_run_id(monkeypatch, tmp_path):
    logger_impl, = fresh_backend(monkeypatch, tmp_path, "logger.logger")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logger_impl.JSONFormatter())
    old_handlers = logger_impl.activity_logger.handlers[:]
    old_propagate = logger_impl.activity_logger.propagate
    logger_impl.activity_logger.handlers = [handler]
    logger_impl.activity_logger.propagate = False

    try:
        logger_impl.log_activity(
            original_name="source.jpg",
            vault_id="abc",
            platform="Local",
            artist="Tester",
            ingest_type="local",
            run_id="run-1",
        )

        record = json.loads(stream.getvalue())
        assert record["message"] == "Ingestion successful"
        assert record["ingest_type"] == "local"
        assert record["run_id"] == "run-1"
        assert record["status"] == "success"

        stream.seek(0)
        stream.truncate(0)
        logger_impl.log_activity(
            original_name="source.jpg",
            vault_id="abc",
            platform="Local",
            artist="Tester",
            ingest_type="local",
            run_id="run-1",
            status="failed",
        )
        record = json.loads(stream.getvalue())
        assert record["level"] == "ERROR"
        assert record["message"] == "Ingestion failed"
        assert record["status"] == "failed"
    finally:
        logger_impl.activity_logger.handlers = old_handlers
        logger_impl.activity_logger.propagate = old_propagate


def test_fingerprint_fallback_failures_are_logged(monkeypatch, tmp_path):
    fingerprint, = fresh_backend(monkeypatch, tmp_path, "fingerprint")
    logger = importlib.import_module("logger")
    calls = []
    video = tmp_path / "bad.mp4"

    def fake_log_system(level, message, **kwargs):
        calls.append((level, message, kwargs))

    monkeypatch.setattr(logger, "log_system", fake_log_system)

    monkeypatch.setattr(fingerprint.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("ffmpeg missing")))
    assert fingerprint.is_silent(video) is True

    monkeypatch.setattr(fingerprint, "is_silent", lambda path: False)
    assert fingerprint.get_audio_fingerprint(video) == b""

    assert fingerprint.get_video_duration(video) == 0.0

    monkeypatch.setattr(fingerprint, "get_model", lambda: (_ for _ in ()).throw(RuntimeError("model load failed")))
    assert fingerprint.get_visual_embedding(video) == b""

    assert [call[1] for call in calls] == [
        "Video silence detection failed",
        "Audio fingerprint failed",
        "Video duration probe failed",
        "Video visual embedding failed",
    ]
    assert all(call[0] == "WARNING" for call in calls)
    assert all(call[2]["file"] == str(video) for call in calls)
    assert all(call[2]["exc_info"] is True for call in calls)


def test_video_frame_extraction_discards_stderr(monkeypatch, tmp_path):
    fingerprint, = fresh_backend(monkeypatch, tmp_path, "fingerprint")
    kwargs_seen = []

    def fake_run(cmd, *args, **kwargs):
        kwargs_seen.append(kwargs)
        from PIL import Image
        buffer = io.BytesIO()
        Image.new("RGB", (2, 2), "red").save(buffer, format="PNG")
        return types.SimpleNamespace(stdout=buffer.getvalue())

    monkeypatch.setattr(fingerprint.subprocess, "run", fake_run)

    frame = fingerprint.extract_video_frame(tmp_path / "video.mp4", 1.0)

    assert frame.size == (2, 2)
    assert kwargs_seen[0]["stdout"] == fingerprint.subprocess.PIPE
    assert kwargs_seen[0]["stderr"] == fingerprint.subprocess.DEVNULL


def test_search_manager_runtime_logs_route_to_system(monkeypatch, tmp_path):
    search_manager_module, = fresh_backend(monkeypatch, tmp_path, "db.search_manager")
    calls = []

    monkeypatch.setattr(search_manager_module, "log_system", lambda level, message, **kwargs: calls.append((level, message, kwargs)))
    monkeypatch.setattr(search_manager_module, "get_all_urls", lambda conn: [])
    monkeypatch.setattr(search_manager_module, "get_all_phashes", lambda conn: [])
    monkeypatch.setattr(search_manager_module, "get_all_tiles", lambda conn: [])
    monkeypatch.setattr(search_manager_module, "get_all_video_signatures", lambda conn: [])

    manager = search_manager_module.SearchManager()
    manager.is_hydrated = False
    manager.hydrate(object())
    manager.update_indexes_batch([{"file_hash": "hash", "phash": None, "url": "", "tiles": []}])

    messages = [call[1] for call in calls]
    assert "Hydrating RAM indexes from SQLite..." in messages
    assert any(message.startswith("Hydration complete:") for message in messages)
    assert "RAM index batch update queued" in messages


def test_local_ingest_worker_emits_local_and_audit_logs(monkeypatch, tmp_path):
    web_api, = fresh_backend(monkeypatch, tmp_path, "web_api")
    source = tmp_path / "source.jpg"
    source.write_bytes(b"image")
    local_calls = []
    audit_calls = []

    def fake_process_file(path, config, metadata=None, delete_source=False, skip_similarity=False):
        assert metadata["ingest_type"] == "local"
        assert metadata["run_id"] == "run-local"
        if delete_source:
            path.unlink()
        return True, "Success: source.jpg", {"file_hash": "abc", "phash": None, "url": "", "tiles": []}

    monkeypatch.setattr(web_api, "process_file", fake_process_file)
    monkeypatch.setattr(web_api, "log_ingest_local", lambda level, message, **kwargs: local_calls.append((level, message, kwargs)))
    monkeypatch.setattr(web_api, "log_ingest_audit", lambda level, message, **kwargs: audit_calls.append((level, message, kwargs)))

    web_api._prepare_local_ingest_run("run-local", {"artist": "A", "platform": "Local"}, False, 1)
    web_api._run_local_ingest_worker([str(source)], {"artist": "A", "platform": "Local"}, False, "run-local")

    local_messages = [call[1] for call in local_calls]
    assert "Local ingest run started" in local_messages
    assert "Local ingest item processed" in local_messages
    assert "Local ingest run finished" in local_messages
    assert any(call[2].get("status") == "ingested" for call in local_calls)
    assert audit_calls[-1][1] == "Local ingestion run summary"
    assert audit_calls[-1][2]["ingest_type"] == "local"
    assert audit_calls[-1][2]["summary_ingested"] == 1


def test_multi_vault_shared_workspace_metadata(monkeypatch, tmp_path):
    """Workspace DB aggregates artists/platforms/wd_tags from all vault DBs.

    Creates a second vault alongside the default one, inserts items with
    different artists into each vault's DB, and verifies:
    - Workspace DB sees artists from both vaults after rebuild
    - Active vault counts are scoped to the active vault only
    - Prune removes metadata not referenced by any vault
    - Scope=all facets include entries from all vaults
    """
    vaults, utils, sqlite_operator, workspace_db, web_api = fresh_backend(
        monkeypatch,
        tmp_path,
        "vaults",
        "utils",
        "db.sqlite_operator",
        "workspace_db",
        "web_api",
    )

    # ── Create a second vault ──
    vaults.create_vault("Second")
    vault_items = {item["id"]: item for item in vaults.vault_list()}
    assert "second" in vault_items
    second_db_path = Path(vault_items["second"]["db_path"])

    # ── Insert items into default vault (the active one) ──
    default_hash = "d1" * 32
    conn = insert_mock_item(sqlite_operator, default_hash, artist="Default Artist")
    conn.execute("UPDATE items SET platform = ? WHERE hash = ?", ("pixiv", default_hash))
    conn.commit()
    conn.close()

    # ── Insert items into second vault's DB directly ──
    second_conn = sqlite_operator.init_database(second_db_path)
    second_storage_id = sqlite_operator.allocate_storage_id(second_conn)
    second_hash = "s1" * 32
    second_conn.execute(
        """
        INSERT INTO items(hash, storage_id, original_filename, file_extension, mime_type, size_bytes, date_added, source_url, source_url_norm, platform, source_artist, phash)
        VALUES (?, ?, ?, '.jpg', 'image/jpeg', 10, '2026-01-01 00:00:00', '', '', 'instagram', 'Second Vault Artist', '')
        """,
        (second_hash, second_storage_id, f"{second_hash}.jpg"),
    )
    second_conn.commit()
    second_conn.close()

    # ── Rebuild workspace metadata — should pull from both vaults ──
    result = workspace_db.rebuild_workspace_metadata()
    assert result["status"] == "success"

    ws_conn = workspace_db.connect_workspace_database()
    try:
        artist_norms = {row[0] for row in ws_conn.execute("SELECT name_norm FROM artists").fetchall()}
        platform_norms = {row[0] for row in ws_conn.execute("SELECT key_norm FROM platforms").fetchall()}
    finally:
        ws_conn.close()

    # Both vaults' artists should be in workspace DB
    assert "default artist" in artist_norms
    assert "second vault artist" in artist_norms

    # Both vaults' platforms should be in workspace DB
    assert "pixiv" in platform_norms
    assert "instagram" in platform_norms

    # ── Verify counts are scoped to active vault (default) ──
    all_artists = web_api._get_artists_sync("", 50, "all")["items"]
    artist_map = {a["name"]: a for a in all_artists}

    # Default Artist has 1 item in the active vault
    assert artist_map["Default Artist"]["item_count"] == 1
    # Second Vault Artist has 0 items in the active vault (items are in second vault)
    assert artist_map["Second Vault Artist"]["item_count"] == 0

    # ── Verify used_only filters correctly ──
    used_artists = web_api._get_artists_sync("", 50, "used")["items"]
    used_names = {a["name"] for a in used_artists}
    assert "Default Artist" in used_names
    assert "Second Vault Artist" not in used_names

    # ── Verify facets scope=all includes workspace data ──
    all_artist_facets = web_api._get_facets_sync("artist", "", 50, "all")["items"]
    facet_values = {item["value"] for item in all_artist_facets}
    assert "Default Artist" in facet_values
    assert "Second Vault Artist" in facet_values

    all_platform_facets = web_api._get_facets_sync("platform", "", 50, "all")["items"]
    platform_values = {item["value"] for item in all_platform_facets}
    assert "Pixiv" in platform_values
    assert "Instagram" in platform_values

    # ── Prune should NOT remove Second Vault Artist (used in second vault) ──
    prune_result = workspace_db.prune_unused_workspace_metadata()
    assert prune_result["status"] == "success"
    assert prune_result["pruned"]["artists"] == 0

    # ── Insert an orphan artist, then prune should remove it ──
    ws_conn = workspace_db.connect_workspace_database()
    ws_conn.execute(
        "INSERT INTO artists(name, name_norm, kind, notes, created_at, updated_at) VALUES (?, ?, 'artist', '', '2026-01-01', '2026-01-01')",
        ("Orphan Artist", "orphan artist"),
    )
    ws_conn.commit()
    ws_conn.close()

    prune_result = workspace_db.prune_unused_workspace_metadata()
    assert prune_result["pruned"]["artists"] == 1

    ws_conn = workspace_db.connect_workspace_database()
    try:
        assert ws_conn.execute("SELECT 1 FROM artists WHERE name_norm = 'orphan artist'").fetchone() is None
        assert ws_conn.execute("SELECT 1 FROM artists WHERE name_norm = 'default artist'").fetchone() is not None
        assert ws_conn.execute("SELECT 1 FROM artists WHERE name_norm = 'second vault artist'").fetchone() is not None
    finally:
        ws_conn.close()


def test_artist_used_scope_filters_before_limit(monkeypatch, tmp_path):
    sqlite_operator, workspace_db, web_api = fresh_backend(
        monkeypatch,
        tmp_path,
        "db.sqlite_operator",
        "workspace_db",
        "web_api",
    )

    conn = insert_mock_item(sqlite_operator, "u1" * 32, artist="Zzz Used Artist")
    conn.close()

    ws_conn = workspace_db.connect_workspace_database()
    try:
        for index in range(80):
            ws_conn.execute(
                """
                INSERT OR IGNORE INTO artists(name, name_norm, kind, notes, created_at, updated_at)
                VALUES (?, ?, 'artist', '', '2026-01-01 00:00:00', '2026-01-01 00:00:00')
                """,
                (f"Aaa Unused {index:03d}", f"aaa unused {index:03d}"),
            )
        ws_conn.commit()
    finally:
        ws_conn.close()

    used_artists = web_api._get_artists_sync("", 20, "used")["items"]
    assert [artist["name"] for artist in used_artists] == ["Zzz Used Artist"]
