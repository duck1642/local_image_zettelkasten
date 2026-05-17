import argparse
import json
import time
import urllib.error

from perf_common import (
    DEFAULT_BACKEND_URL,
    compact_response_stats,
    http_json,
    load_manifest,
    ms_since,
    resolve_config_path,
    result_dir_for_config,
    start_backend,
    stop_process_tree,
    url_with_params,
    utc_now,
    wait_for_backend,
    write_json,
)


def _first_manifest_item(manifest: dict) -> dict:
    items = manifest.get("items") if isinstance(manifest, dict) else None
    if isinstance(items, list) and items:
        return items[0]
    return {}


def _cursor_from(payload) -> str:
    if isinstance(payload, dict) and payload.get("next_cursor"):
        return str(payload["next_cursor"])
    return ""


def _measure_endpoint(base_url: str, name: str, path: str, params=None) -> tuple[dict, object]:
    url = url_with_params(base_url, path, params)
    started = time.perf_counter()
    try:
        status, payload = http_json(url, timeout=60.0)
        row = {
            "name": name,
            "path": path,
            "status": status,
            "duration_ms": ms_since(started),
            "ok": 200 <= status < 300,
            "response": compact_response_stats(payload),
        }
        return row, payload
    except urllib.error.HTTPError as exc:
        return {
            "name": name,
            "path": path,
            "status": exc.code,
            "duration_ms": ms_since(started),
            "ok": False,
            "error": str(exc),
        }, None
    except Exception as exc:
        return {
            "name": name,
            "path": path,
            "status": None,
            "duration_ms": ms_since(started),
            "ok": False,
            "error": str(exc),
        }, None


def run_backend_api_perf(config_arg: str, base_url: str, use_existing_backend: bool = False) -> dict:
    config_path = resolve_config_path(config_arg)
    backend = None
    ready_ms = None
    if use_existing_backend:
        ready_ms = wait_for_backend(base_url)
    else:
        backend, ready_ms = start_backend(config_path, base_url)

    endpoints = []
    first_page_payload = None
    errors = []
    manifest = load_manifest(config_path)
    item = _first_manifest_item(manifest)
    artist = item.get("artist") or "artist-000"
    platform = item.get("platform") or "pixiv"
    topics = item.get("topics") if isinstance(item.get("topics"), list) else []
    topic = topics[0] if topics else "topic-000"

    try:
        for name, path, params in [
            ("session-key", "/api/session-key", None),
            ("items-first-page", "/api/items", {"limit": 50}),
        ]:
            row, payload = _measure_endpoint(base_url, name, path, params)
            endpoints.append(row)
            if name == "items-first-page":
                first_page_payload = payload

        cursor = _cursor_from(first_page_payload)
        if cursor:
            row, _ = _measure_endpoint(base_url, "items-cursor-page", "/api/items", {"limit": 100, "cursor": cursor})
            endpoints.append(row)

        checks = [
            ("items-filter-artist", "/api/items", [("limit", 100), ("artist", artist)]),
            ("items-filter-platform", "/api/items", [("limit", 100), ("platform", platform)]),
            ("items-filter-topic", "/api/items", [("limit", 100), ("topic", topic)]),
            ("items-filter-image", "/api/items", {"limit": 100, "media_type": "image"}),
            ("items-filter-video", "/api/items", {"limit": 100, "media_type": "video"}),
            ("facets-artist", "/api/facets", {"kind": "artist", "limit": 50}),
            ("facets-platform", "/api/facets", {"kind": "platform", "limit": 50}),
            ("facets-topic", "/api/facets", {"kind": "topic", "limit": 50}),
            ("search-suggestions-artist", "/api/search/suggestions", {"kind": "artist", "q": str(artist)[:8], "limit": 10}),
            ("metadata-index-status", "/api/metadata-index/status", None),
        ]
        for name, path, params in checks:
            row, _ = _measure_endpoint(base_url, name, path, params)
            endpoints.append(row)
        errors = [row for row in endpoints if not row.get("ok")]
    finally:
        if backend:
            stop_process_tree(backend)

    payload = {
        "kind": "backend-api",
        "run_id": config_path.parent.name,
        "config_path": str(config_path),
        "backend_url": base_url,
        "started_at": utc_now(),
        "backend_ready_ms": ready_ms,
        "ok": not errors,
        "errors": errors,
        "endpoints": endpoints,
    }
    out_path = result_dir_for_config(config_path) / "backend-api.json"
    write_json(out_path, payload)
    payload["result_path"] = str(out_path)
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Measure real backend API performance against a generated vault.")
    parser.add_argument("config_path")
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--use-existing-backend", action="store_true")
    args = parser.parse_args(argv)
    payload = run_backend_api_perf(args.config_path, args.backend_url, args.use_existing_backend)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
