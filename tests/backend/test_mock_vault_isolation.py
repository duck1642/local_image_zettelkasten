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
import sys
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
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    for name in list(sys.modules):
        if name in {"utils", "web_api", "queue_service", "md_generator", "metadata_index", "processor", "external_ingestion", "thumbnails", "fingerprint"} or name.startswith(("logger", "db.", "tagging", "downloaders")):
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


def write_compact_note(utils, conn, item_hash: str, text: str):
    storage_id = storage_id_for(conn, item_hash)
    note_path = utils.note_path_for(item_hash, storage_id)
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(text, encoding="utf-8")
    return note_path


def test_config_override_resolves_paths_inside_mock_vault(monkeypatch, tmp_path):
    (utils,) = fresh_backend(monkeypatch, tmp_path, "utils")

    assert utils.CONFIG_PATH == tmp_path / "mock-vault" / "config.yaml"
    assert utils.VAULT_DIR == tmp_path / "mock-vault" / "data" / "vault"
    assert utils.DB_PATH == tmp_path / "mock-vault" / "data" / "db" / "lmz_mock.db"
    assert utils.LOCAL_INGEST_DIR == tmp_path / "mock-vault" / "data" / "local_ingest"
    assert utils.ONLINE_INGEST_DIR == tmp_path / "mock-vault" / "data" / "online_ingest"
    assert utils.THUMBNAILS_DIR == tmp_path / "mock-vault" / "data" / "ui_cache" / "thumbnails"
    assert str(ROOT / "data") not in str(utils.VAULT_DIR)


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
    web_api._update_app_config_sync({"paths": {"vault": "data/vault", "db": "data/db/lmz_mock.db", "logs": "data/logs", "queues": "data/queues", "batches": "data/batches", "secrets": "data/secrets"}, "firewall": {"allowed_extensions": [".jpg"], "allowed_mimes": ["image/jpeg"]}, "hash_algorithm": "sha256"})

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
    assert calls[0][1] == {"artist": "Retry Artist"}
    assert calls[0][2] is True


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


def test_generate_markdown_preserves_manual_fields_and_explicit_empty_wd(monkeypatch, tmp_path):
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

    assert data["artist"] == "Manual Artist"
    assert data["date_added"] == "2020-01-01 01:02:03"
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


def test_reindex_syncs_markdown_artist_and_date_to_sqlite(monkeypatch, tmp_path):
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

    assert row == ("Manual Artist", "2020-01-01 01:02:03")
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


def test_review_replace_preserves_old_manual_metadata(monkeypatch, tmp_path):
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
    assert new_data["artist"] == "Manual Old"
    assert new_data["date_added"] == "2020-01-01 00:00:00"
    assert new_data["topics"] == ["preserved"]
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


def test_metadata_status_uses_streaming_stale_count(monkeypatch, tmp_path):
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

    status = metadata_index.metadata_index_status(Conn())

    assert status["stale"] == 1


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
    ready = metadata_index.metadata_index_ready(conn)
    conn.close()
    assert report["indexed"] == 1
    assert topics == ["rebuilt-topic"]
    assert ready is True


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
    assert report["stale_after"] == 1


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
