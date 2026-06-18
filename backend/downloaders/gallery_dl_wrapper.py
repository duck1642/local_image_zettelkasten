import hashlib
import json
import shutil
import subprocess
from urllib.parse import urlparse

from downloaders.media_filter import valid_media_files
from runtime_context import get_runtime_context
from utils import get_config, get_platform_cookie_path


_AUTH_STATUS_LOGGED = set()


def _timeout(name: str, default: int) -> int:
    try:
        value = get_config().get("external_tools", {}).get("timeouts", {}).get(name, default)
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def _normalized_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
        path = parsed.path
        return f"{parsed.scheme or 'https'}://twitter.com{path}"
    return url


def _platform_for_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.endswith('pixiv.net'): return "Pixiv"
    if host.endswith('pinterest.com') or host.endswith('pin.it'): return "Pinterest"
    if host.endswith('instagram.com'): return "Instagram"
    if host.endswith('twitter.com') or host.endswith('x.com'): return "X"
    return "Unknown"


def _base_args(url: str) -> list:
    config = get_config()
    ext_tools = config.get('external_tools', {})
    args = []
    platform = _platform_for_url(url)
    cookie_info = get_platform_cookie_path(platform)

    _log_auth_status(
        platform,
        cookie_info,
        bool(ext_tools.get('pixiv_token')),
    )

    if ext_tools.get('pixiv_token') and "pixiv" in url.lower():
        args.extend(["--option", f"extractor.pixiv.refresh-token={ext_tools['pixiv_token']}"])
    elif cookie_info.get("status") == "available" and cookie_info.get("path"):
        args.extend(["--cookies", str(cookie_info["path"])])
    if ext_tools.get('proxy'):
        args.extend(["--proxy", ext_tools['proxy']])
    if ext_tools.get('user_agent'):
        args.extend(["--user-agent", ext_tools['user_agent']])

    return args


def _log_auth_status(
    platform: str,
    cookie_info: dict,
    has_pixiv_token: bool,
):
    platform_cookie_status = cookie_info.get("status", "missing")

    pixiv_token_status = "not_required"
    if platform == "Pixiv":
        pixiv_token_status = "available" if has_pixiv_token else "missing"

    key = (
        platform,
        cookie_info.get("source"),
        platform_cookie_status,
        pixiv_token_status,
    )
    if key in _AUTH_STATUS_LOGGED:
        return
    _AUTH_STATUS_LOGGED.add(key)

    from logger import log_auth
    log_auth(
        "INFO",
        "Downloader auth status",
        downloader="gallery-dl",
        platform=platform,
        cookies=platform_cookie_status,
        cookie_source=cookie_info.get("source", "missing"),
        platform_cookies=platform_cookie_status,
        cookies_path=cookie_info.get("path", ""),
        pixiv_token=pixiv_token_status,
    )


def _load_metadata_lines(stdout: str) -> list:
    if not stdout.strip():
        return []
    
    # Try parsing the entire output as a single JSON array first (gallery-dl -j default)
    try:
        data = json.loads(stdout)
        if isinstance(data, list):
            # If it's a list of items (like [2, {...}], [3, {...}]), return it
            return data
    except json.JSONDecodeError:
        pass

    # Fallback to jsonlines parsing if gallery-dl was run with a different format
    meta_json = []
    for line in stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            meta_json.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return meta_json


def _media_data_from_item(item):
    if isinstance(item, list) and len(item) > 2 and item[0] == 3 and isinstance(item[2], dict):
        return item[2]
    if isinstance(item, dict):
        return item
    return None


def _parse_metadata(meta_json: list, original_url: str, download_url: str) -> dict:
    platform = _platform_for_url(download_url)
    media_entries = []
    expected_sizes = {}
    is_ugoira = False

    for item in meta_json:
        data = _media_data_from_item(item)
        if not data:
            continue

        is_media_event = isinstance(item, list) and len(item) > 0 and item[0] == 3
        has_media_fields = any(data.get(k) for k in ['extension', 'filename', 'url', 'file_url'])
        if is_media_event or has_media_fields:
            media_entries.append(data)
            index = len(media_entries)
            stem_candidates = []
            num = data.get('num')
            if num is not None:
                stem_candidates.append(str(num))
            stem_candidates.extend([str(index), str(index - 1)])
            filesize = data.get('filesize') or data.get('file_size') or data.get('size')
            if filesize:
                for stem in dict.fromkeys(stem_candidates):
                    expected_sizes[stem] = int(filesize)

        value_text = " ".join(str(data.get(k, "")).lower() for k in ['type', 'extension', 'filename', 'subcategory'])
        if 'ugoira' in value_text:
            is_ugoira = True

    expected_count = len(media_entries)

    return {
        "original_url": original_url,
        "download_url": download_url,
        "platform": platform,
        "expected_count": expected_count,
        "expected_sizes": expected_sizes,
        "is_ugoira": is_ugoira,
        "metadata": {
            "source_url": original_url,
            "platform": platform
        }
    }


def inspect_gallery(url: str) -> tuple[bool, dict]:
    original_url = url
    download_url = _normalized_url(url)
    meta_cmd = ["gallery-dl", "-j"] + _base_args(download_url) + [download_url]
    result = subprocess.run(meta_cmd, capture_output=True, text=True, timeout=_timeout("gallery_metadata", 120))

    if result.returncode != 0:
        return False, {"error": f"Metadata failed: {result.stderr}"}

    meta_json = _load_metadata_lines(result.stdout)
    if not meta_json:
        return False, {"error": "Metadata failed: no JSON output"}

    info = _parse_metadata(meta_json, original_url, download_url)
    if info["platform"] == "Pixiv" and info["expected_count"] <= 0:
        return False, {"error": "Pixiv metadata failed: no downloadable media entries found"}

    return True, info


def _minimal_download_info(url: str) -> dict:
    original_url = url
    download_url = _normalized_url(url)
    platform = _platform_for_url(download_url)
    return {
        "original_url": original_url,
        "download_url": download_url,
        "platform": platform,
        "expected_count": 0,
        "expected_sizes": {},
        "is_ugoira": False,
        "metadata": {
            "source_url": original_url,
            "platform": platform
        }
    }


def download_gallery(url: str, metadata_info: dict = None) -> tuple[bool, dict]:
    config = get_config()
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    session_dir = get_runtime_context().active_vault.online_ingest_dir / url_hash
    session_dir.mkdir(parents=True, exist_ok=True)

    try:
        if metadata_info is None:
            base_info = _minimal_download_info(url)
            if base_info["platform"] == "X":
                metadata_info = base_info
            else:
                meta_success, metadata_info = inspect_gallery(url)
                if not meta_success:
                    shutil.rmtree(session_dir, ignore_errors=True)
                    return False, metadata_info

        platform = metadata_info["platform"]
        download_url = metadata_info["download_url"]

        dl_cmd = ["gallery-dl", "-d", str(session_dir), "-f", "{num}.{extension}"] + _base_args(download_url)
        if platform == "Pixiv":
            dl_cmd.extend(["--ugoira", "webm"])
        dl_cmd.append(download_url)

        print(f"   [INFO] Running gallery-dl for {platform}...")
        dl_res = subprocess.run(dl_cmd, capture_output=True, text=True, timeout=_timeout("gallery_download", 300))

        if dl_res.returncode != 0:
            shutil.rmtree(session_dir, ignore_errors=True)
            return False, {"error": dl_res.stderr}

        actual_files = valid_media_files(session_dir, config)
        downloaded_count = len(actual_files)
        expected_count = metadata_info.get("expected_count", 0)

        if platform in {"Pixiv", "Instagram", "Pinterest"} and expected_count > 0:
            if downloaded_count != expected_count:
                shutil.rmtree(session_dir, ignore_errors=True)
                return False, {
                    "error": f"{platform} incomplete download: expected {expected_count}, got {downloaded_count}",
                    "expected_count": expected_count,
                    "downloaded_count": downloaded_count
                }
        if platform == "Pixiv":
            if metadata_info.get("is_ugoira"):
                converted = [p for p in actual_files if p.suffix.lower() in {'.webm', '.mp4'}]
                if len(converted) != 1:
                    shutil.rmtree(session_dir, ignore_errors=True)
                    return False, {
                        "error": f"Pixiv ugoira conversion failed: expected 1 converted video, got {len(converted)}",
                        "expected_count": expected_count,
                        "downloaded_count": downloaded_count
                    }

        if not actual_files:
            shutil.rmtree(session_dir, ignore_errors=True)
            return False, {"error": "No valid media files found after download"}

        return True, {
            "file_paths": [str(f) for f in actual_files],
            "metadata": metadata_info["metadata"],
            "expected_sizes": metadata_info.get("expected_sizes", {}),
            "expected_count": expected_count,
            "downloaded_count": downloaded_count,
            "download_url": download_url,
            "platform": platform,
            "session_dir": str(session_dir)
        }

    except Exception as e:
        if session_dir.exists():
            shutil.rmtree(session_dir, ignore_errors=True)
        return False, {"error": str(e)}
