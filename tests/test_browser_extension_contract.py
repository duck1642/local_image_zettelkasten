from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTENSION_ROOT = ROOT / "tools" / "browser_extension"
SOURCE_ROOT = EXTENSION_ROOT / "src"
TARGETS = ("chrome", "edge", "firefox")
SHARED_FILES = ("api.js", "background.js", "db.js", "icons.js", "popup.html", "popup.js", "styles.css")


def test_generated_extension_copies_match_shared_source():
    for target in TARGETS:
        for filename in SHARED_FILES:
            assert (EXTENSION_ROOT / target / filename).read_bytes() == (SOURCE_ROOT / filename).read_bytes(), (
                f"{target}/{filename} is stale; run sync_extensions.py"
            )


def test_shared_popup_keeps_v1_api_contract():
    popup = (SOURCE_ROOT / "popup.js").read_text(encoding="utf-8")
    html = (SOURCE_ROOT / "popup.html").read_text(encoding="utf-8")

    assert 'const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";' in popup
    assert "/api/capture/preview/${encodeURIComponent(item.staged_id)}" in popup
    assert "/api/capture/stage/${encodeURIComponent(item.staged_id)}" in popup
    assert "`${config.apiBaseUrl}/api/capture/stage`" in popup
    assert "`${config.apiBaseUrl}/api/capture/commit`" in popup
    assert "`${config.apiBaseUrl}/api/queue/${queue}/append`" in popup

    for field in ("file", "source_url", "media_url", "page_title"):
        assert f'formData.append("{field}"' in popup
    for field in ("staged_id", "artist", "platform"):
        assert f"{field}:" in popup
    for field in ("url", "artist", "platform"):
        assert f"{field}:" in popup

    assert ".lmz/app/secrets/.api_key" in html
    assert "/api/session-key" not in popup
