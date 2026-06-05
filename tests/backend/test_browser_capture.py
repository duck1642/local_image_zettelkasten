import base64
import concurrent.futures
import json
import threading

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException

from .test_mock_vault_isolation import fresh_backend


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def _client(monkeypatch, tmp_path):
    app_module, common = fresh_backend(monkeypatch, tmp_path, "api.app", "api.common")
    client = TestClient(app_module.app)
    client.capture_module = app_module.capture
    client.runtime_context = app_module.capture.get_runtime_context
    return client, common._api_key()


def test_capture_stage_writes_file_and_sidecar(monkeypatch, tmp_path):
    client, api_key = _client(monkeypatch, tmp_path)

    response = client.post(
        "/api/capture/stage",
        headers={"X-LMZ-API-KEY": api_key},
        files={"file": ("sample.png", PNG_BYTES, "image/png")},
        data={
            "source_url": "https://x.com/creator/status/1",
            "media_url": "https://pbs.twimg.com/media/sample.png",
            "page_title": "Sample post",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["platform_guess"] == "X"
    stage_dir = client.capture_module._capture_stage_dir(client.runtime_context())
    sidecar = json.loads((stage_dir / f"{payload['staged_id']}.json").read_text(encoding="utf-8"))
    assert sidecar["source_url"] == "https://x.com/creator/status/1"
    assert sidecar["media_url"] == "https://pbs.twimg.com/media/sample.png"
    assert (stage_dir / sidecar["stored_name"]).exists()


def test_capture_stage_rejects_unsupported_media(monkeypatch, tmp_path):
    client, api_key = _client(monkeypatch, tmp_path)

    response = client.post(
        "/api/capture/stage",
        headers={"X-LMZ-API-KEY": api_key},
        files={"file": ("sample.txt", b"not media", "text/plain")},
        data={"source_url": "https://example.com"},
    )

    assert response.status_code == 400


def test_capture_preview_requires_api_key(monkeypatch, tmp_path):
    client, api_key = _client(monkeypatch, tmp_path)
    staged = client.post(
        "/api/capture/stage",
        headers={"X-LMZ-API-KEY": api_key},
        files={"file": ("sample.png", PNG_BYTES, "image/png")},
        data={"source_url": "https://example.com"},
    ).json()

    missing = client.get(f"/api/capture/preview/{staged['staged_id']}")
    ok = client.get(
        f"/api/capture/preview/{staged['staged_id']}",
        headers={"X-LMZ-API-KEY": api_key},
    )

    assert missing.status_code == 403
    assert ok.status_code == 200
    assert ok.content


def test_capture_delete_removes_staged_artifacts(monkeypatch, tmp_path):
    client, api_key = _client(monkeypatch, tmp_path)
    staged = client.post(
        "/api/capture/stage",
        headers={"X-LMZ-API-KEY": api_key},
        files={"file": ("sample.png", PNG_BYTES, "image/png")},
        data={"source_url": "https://example.com"},
    ).json()

    response = client.delete(
        f"/api/capture/stage/{staged['staged_id']}",
        headers={"X-LMZ-API-KEY": api_key},
    )

    assert response.status_code == 200
    leftovers = list(client.capture_module._capture_stage_dir(client.runtime_context()).glob(f"{staged['staged_id']}.*"))
    assert leftovers == []


def test_capture_invalid_staged_id_rejected(monkeypatch, tmp_path):
    client, api_key = _client(monkeypatch, tmp_path)

    response = client.delete(
        "/api/capture/stage/../bad",
        headers={"X-LMZ-API-KEY": api_key},
    )

    assert response.status_code in {400, 404}


def test_capture_commit_uses_processor_metadata_and_cleans_stage(monkeypatch, tmp_path):
    client, api_key = _client(monkeypatch, tmp_path)
    staged = client.post(
        "/api/capture/stage",
        headers={"X-LMZ-API-KEY": api_key},
        files={"file": ("sample.png", PNG_BYTES, "image/png")},
        data={
            "source_url": "https://artist.example/post",
            "media_url": "https://cdn.example/sample.png",
        },
    ).json()
    capture = client.capture_module
    seen = {}

    def fake_process_file(filepath, config, metadata=None, delete_source=False, skip_similarity=False, ctx=None):
        seen["filepath"] = filepath
        seen["metadata"] = metadata
        seen["delete_source"] = delete_source
        seen["skip_similarity"] = skip_similarity
        seen["ctx"] = ctx
        return True, "Success: sample.png -> 000001.png", {"tagging_status": "not_run"}

    monkeypatch.setattr(capture, "process_file", fake_process_file)

    response = client.post(
        "/api/capture/commit",
        headers={"X-LMZ-API-KEY": api_key},
        json={"staged_id": staged["staged_id"], "artist": "Alice", "platform": "General Web"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ingested"
    assert seen["metadata"]["source_url"] == "https://artist.example/post"
    assert seen["metadata"]["media_url"] == "https://cdn.example/sample.png"
    assert seen["metadata"]["artist"] == "Alice"
    assert seen["metadata"]["staged_from"] == "browser_capture"
    assert seen["metadata"]["ingest_type"] == "capture"
    assert seen["delete_source"] is True
    leftovers = list(capture._capture_stage_dir(client.runtime_context()).glob(f"{staged['staged_id']}.*"))
    assert leftovers == []


def test_capture_commit_same_staged_id_is_locked_and_idempotent(monkeypatch, tmp_path):
    client, api_key = _client(monkeypatch, tmp_path)
    staged = client.post(
        "/api/capture/stage",
        headers={"X-LMZ-API-KEY": api_key},
        files={"file": ("sample.png", PNG_BYTES, "image/png")},
        data={"source_url": "https://example.com"},
    ).json()
    capture = client.capture_module
    started = threading.Event()
    release = threading.Event()
    calls = 0

    def fake_process_file(*args, **kwargs):
        nonlocal calls
        calls += 1
        started.set()
        assert release.wait(2)
        return True, "Success: sample.png -> 000001.png", {"tagging_status": "ok"}

    monkeypatch.setattr(capture, "process_file", fake_process_file)
    body = capture.CaptureCommitRequest(staged_id=staged["staged_id"])

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(capture._commit_capture_sync, body)
        assert started.wait(2)
        with pytest.raises(HTTPException) as exc:
            capture._commit_capture_sync(body)
        assert exc.value.status_code == 409
        release.set()
        first_result = first.result(timeout=2)

    assert first_result["status"] == "ingested"
    assert calls == 1

    repeat_result = capture._commit_capture_sync(body)
    assert repeat_result["status"] == "ingested"
    assert repeat_result["already_handled"] is True
    assert calls == 1


def test_capture_commit_maps_review_and_duplicate_statuses(monkeypatch, tmp_path):
    client, api_key = _client(monkeypatch, tmp_path)
    capture = client.capture_module

    def stage_one():
        return client.post(
            "/api/capture/stage",
            headers={"X-LMZ-API-KEY": api_key},
            files={"file": ("sample.png", PNG_BYTES, "image/png")},
            data={"source_url": "https://example.com"},
        ).json()

    monkeypatch.setattr(
        capture,
        "process_file",
        lambda *args, **kwargs: (False, "asi   Visual Match (phash) -> Moved to review/", None),
    )
    review_response = client.post(
        "/api/capture/commit",
        headers={"X-LMZ-API-KEY": api_key},
        json={"staged_id": stage_one()["staged_id"]},
    )

    monkeypatch.setattr(
        capture,
        "process_file",
        lambda *args, **kwargs: (False, "Duplicate ignored: abcdef12...", None),
    )
    duplicate_response = client.post(
        "/api/capture/commit",
        headers={"X-LMZ-API-KEY": api_key},
        json={"staged_id": stage_one()["staged_id"]},
    )

    assert review_response.json()["status"] == "quarantined"
    assert duplicate_response.json()["status"] == "duplicate"


def test_queue_append_writes_metadata_block(monkeypatch, tmp_path):
    queue_service, ingestion_api = fresh_backend(monkeypatch, tmp_path, "queue_service", "api.ingestion")

    result = ingestion_api._append_queue_entry_sync(
        "normal",
        ingestion_api.QueueAppendRequest(
            url="https://www.pixiv.net/artworks/123",
            artist="Painter",
            platform="Pixiv",
        ),
    )
    text = queue_service.read_queue("normal")
    preview = queue_service.parse_queue_preview(text)

    assert result["count"] == 2
    assert "@artist: Painter" in text
    assert "@platform: Pixiv" in text
    assert "https://www.pixiv.net/artworks/123" in text
    assert preview["entries"][-1]["artist"] == "Painter"
    assert preview["entries"][-1]["platform"] == "Pixiv"


@pytest.mark.parametrize(
    "origin",
    [
        "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "moz-extension://123e4567-e89b-12d3-a456-426614174000",
    ],
)
def test_extension_origin_requires_valid_api_key(monkeypatch, tmp_path, origin):
    client, api_key = _client(monkeypatch, tmp_path)

    missing_key = client.post(
        "/api/capture/stage",
        headers={"Origin": origin},
        files={"file": ("sample.png", PNG_BYTES, "image/png")},
        data={"source_url": "https://example.com"},
    )
    valid_key = client.post(
        "/api/capture/stage",
        headers={"Origin": origin, "X-LMZ-API-KEY": api_key},
        files={"file": ("sample.png", PNG_BYTES, "image/png")},
        data={"source_url": "https://example.com"},
    )
    web_origin = client.post(
        "/api/capture/stage",
        headers={"Origin": "https://evil.example", "X-LMZ-API-KEY": api_key},
        files={"file": ("sample.png", PNG_BYTES, "image/png")},
        data={"source_url": "https://example.com"},
    )

    assert missing_key.status_code == 403
    assert valid_key.status_code == 200
    assert web_origin.status_code == 403


@pytest.mark.parametrize(
    "origin",
    [
        "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "moz-extension://123e4567-e89b-12d3-a456-426614174000",
    ],
)
def test_extension_origin_cors_preflight_allowed(monkeypatch, tmp_path, origin):
    client, _api_key = _client(monkeypatch, tmp_path)

    response = client.options(
        "/api/capture/stage",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-LMZ-API-KEY",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
