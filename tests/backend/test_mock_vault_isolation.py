import asyncio
import importlib
import inspect
import shutil
import sys
from pathlib import Path

import pytest
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
        if name in {"utils", "web_api", "queue_service"} or name.startswith("logger"):
            del sys.modules[name]
    return [importlib.import_module(name) for name in module_names]


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
