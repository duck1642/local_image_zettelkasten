import asyncio
import concurrent.futures
import importlib
import inspect
import json
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
        if name in {"utils", "web_api", "queue_service", "md_generator", "metadata_index", "processor", "external_ingestion"} or name.startswith(("logger", "db.", "tagging")):
            del sys.modules[name]
    return [importlib.import_module(name) for name in module_names]


def insert_mock_item(sqlite_operator, item_hash: str, artist: str = "DB Artist", date_added: str = "2026-01-02 03:04:05"):
    conn = sqlite_operator.init_database()
    conn.execute(
        """
        INSERT INTO items(hash, original_filename, file_extension, mime_type, size_bytes, date_added, source_url, source_url_norm, platform, source_artist, phash)
        VALUES (?, ?, '.jpg', 'image/jpeg', 10, ?, '', '', 'local', ?, '')
        """,
        (item_hash, f"{item_hash}.jpg", date_added, artist),
    )
    conn.commit()
    return conn


def frontmatter_from_markdown(text: str) -> dict:
    return yaml.safe_load(text.split("---", 2)[1]) or {}


def test_config_override_resolves_paths_inside_mock_vault(monkeypatch, tmp_path):
    (utils,) = fresh_backend(monkeypatch, tmp_path, "utils")

    assert utils.CONFIG_PATH == tmp_path / "mock-vault" / "config.yaml"
    assert utils.VAULT_DIR == tmp_path / "mock-vault" / "data" / "vault"
    assert utils.DB_PATH == tmp_path / "mock-vault" / "data" / "db" / "lmz_mock.db"
    assert utils.LOCAL_INGEST_DIR == tmp_path / "mock-vault" / "data" / "local_ingest"
    assert utils.ONLINE_INGEST_DIR == tmp_path / "mock-vault" / "data" / "online_ingest"
    assert str(ROOT / "data") not in str(utils.VAULT_DIR)


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


def test_generate_markdown_preserves_manual_fields_and_explicit_empty_wd(monkeypatch, tmp_path):
    utils, sqlite_operator, md_generator = fresh_backend(monkeypatch, tmp_path, "utils", "db.sqlite_operator", "md_generator")
    item_hash = "d" * 64
    conn = insert_mock_item(sqlite_operator, item_hash)
    note_path = utils.note_path_for(item_hash)
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
    cache_path = utils.wd_tag_cache_path_for(item_hash)
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
    cache_path = utils.wd_tag_cache_path_for(item_hash)
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
    note_path = utils.note_path_for(item_hash)
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
    utils.note_path_for(item_hash).parent.mkdir(parents=True, exist_ok=True)
    utils.note_path_for(item_hash).write_text("---\nartist: Original Artist\ntopics: []\n---\n", encoding="utf-8")
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

    ok, _, idx_data = processor.process_file(
        source,
        {"firewall": {"allowed_mimes": ["image/jpeg"], "allowed_extensions": ["jpg"]}, "tagging": {}},
        metadata={"artist": "Ingest Artist", "platform": "pixiv", "source_url": "https://example.test/item"},
        sync_index=False,
    )

    conn = sqlite_operator.init_database()
    row = conn.execute("SELECT source_artist FROM items WHERE hash = ?", (item_hash,)).fetchone()
    note_data = frontmatter_from_markdown(utils.note_path_for(item_hash).read_text(encoding="utf-8"))

    assert ok
    assert idx_data["file_hash"] == item_hash
    assert row[0] == "Ingest Artist"
    assert note_data["artist"] == "Ingest Artist"
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
    conn.close()
    note_path = utils.note_path_for(item_hash)
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
    conn.close()
    old_note = utils.note_path_for(old_hash)
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
        md = web_api.generate_markdown(conn, new_hash)
        note_path = utils.note_path_for(new_hash)
        note_path.parent.mkdir(parents=True, exist_ok=True)
        utils.atomic_write_text(note_path, md)
        conn.close()
        if delete_source:
            path.unlink()
        return True, "ok", {"file_hash": new_hash}

    monkeypatch.setattr(web_api, "process_file", fake_process_file)
    monkeypatch.setattr(web_api, "_delete_item_after_replacement", lambda target_hash: {"hash": target_hash, "status": "deleted", "cleanup_errors": []})

    result = web_api._review_action_sync("replacement.jpg", "replace")
    new_data = frontmatter_from_markdown(utils.note_path_for(new_hash).read_text(encoding="utf-8"))

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

    first = service.tag_media(source, item_hash="6" * 64, config={"tagging": {"device": "cpu"}})
    second = service.tag_media(source, item_hash="7" * 64, config={"tagging": {"device": "cpu"}})

    assert first.status == "ok"
    assert second.status == "ok"
    assert calls["sessions"] == 1
    assert utils.wd_tag_cache_path_for("6" * 64).exists()


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
                yield (str(index), None, "", 0, 0, "", 0, 0, "")

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
            yield ("a", None, "", 0, 0, "", 0, 0, "")
            yield ("b", "b", "", 0, 0, "", 0, 0, "ok")

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


def test_topic_filter_not_ready_skips_legacy_disk_scan(monkeypatch, tmp_path):
    web_api, = fresh_backend(monkeypatch, tmp_path, "web_api")
    repair_calls = []
    monkeypatch.setattr(web_api, "metadata_index_ready", lambda conn: False)
    monkeypatch.setattr(web_api, "start_metadata_repair_worker", lambda full=False: repair_calls.append(full) or {"status": "started"})
    monkeypatch.setattr(web_api, "load_note_topics", lambda item_hash: (_ for _ in ()).throw(AssertionError("legacy note scan called")))
    monkeypatch.setattr(web_api, "_wd_names_for_hash", lambda item_hash: (_ for _ in ()).throw(AssertionError("legacy wd scan called")))

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
