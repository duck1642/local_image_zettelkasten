import hashlib
import html
import json
import re
import shutil
import subprocess
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener

from downloaders.media_filter import valid_media_files
from utils import ONLINE_INGEST_DIR, get_config, get_cookie_auth_status, get_cookie_path


_AUTH_STATUS_LOGGED = set()


def _timeout(name: str, default: int) -> int:
    try:
        value = get_config().get("external_tools", {}).get("timeouts", {}).get(name, default)
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def _is_community_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    query = parse_qs(parsed.query)
    return path.startswith('/post/') or (path.endswith('/community') and bool(query.get('lb')))


def _post_id(url: str) -> str:
    parsed = urlparse(url)
    path_match = re.search(r'/post/([^/?#]+)', parsed.path, re.IGNORECASE)
    if path_match:
        return path_match.group(1)
    query = parse_qs(parsed.query)
    values = query.get('lb') or []
    return values[0] if values else ""


def _opener(config: dict):
    handlers = []
    cookie_path = get_cookie_path()
    _log_auth_status("YouTube", get_cookie_auth_status())
    if cookie_path:
        jar = MozillaCookieJar()
        try:
            jar.load(str(cookie_path), ignore_discard=True, ignore_expires=True)
            handlers.append(HTTPCookieProcessor(jar))
        except Exception as exc:
            from logger import log_ingest_online
            log_ingest_online("WARNING", "Cookie jar load failed", path=str(cookie_path), error=str(exc))
    proxy = config.get('external_tools', {}).get('proxy')
    if proxy:
        handlers.append(ProxyHandler({'http': proxy, 'https': proxy}))
    return build_opener(*handlers)


def _log_auth_status(
    platform: str,
    cookie_status: dict,
):
    platform_cookie_status = cookie_status.get("youtube", "missing")

    key = (platform, cookie_status.get("cookies"), platform_cookie_status)
    if key in _AUTH_STATUS_LOGGED:
        return
    _AUTH_STATUS_LOGGED.add(key)

    from logger import log_auth
    log_auth(
        "INFO",
        "Downloader auth status",
        downloader="yt-dlp",
        platform=platform,
        cookies=cookie_status.get("cookies"),
        platform_cookies=platform_cookie_status,
        cookies_path=cookie_status.get("path", ""),
    )


def _fetch_text(url: str, config: dict) -> tuple[bool, str]:
    user_agent = config.get('external_tools', {}).get('user_agent') or "Mozilla/5.0"
    request = Request(url, headers={"User-Agent": user_agent, "Accept-Language": "en-US,en;q=0.9"})
    try:
        with _opener(config).open(request, timeout=30) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return True, response.read().decode(charset, errors="replace")
    except Exception as e:
        return False, str(e)


def _extract_balanced_json(text: str, marker: str) -> dict:
    index = text.find(marker)
    if index < 0:
        return {}
    start = text.find('{', index)
    if start < 0:
        return {}
    depth = 0
    in_string = False
    escape = False
    for pos in range(start, len(text)):
        char = text[pos]
        if in_string:
            if escape:
                escape = False
            elif char == '\\':
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:pos + 1])
                except json.JSONDecodeError:
                    return {}
    return {}


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _text_from_runs(value) -> str:
    if not isinstance(value, dict):
        return ""
    runs = value.get('runs')
    if isinstance(runs, list):
        return "".join(str(run.get('text', '')) for run in runs if isinstance(run, dict)).strip()
    return str(value.get('simpleText', '')).strip()


def _community_renderers(data: dict) -> list:
    renderers = []
    for node in _walk(data):
        renderer = node.get('backstagePostRenderer')
        if isinstance(renderer, dict):
            renderers.append(renderer)
    return renderers


def _value_contains_post_id(value, post_id: str) -> bool:
    if isinstance(value, str):
        return post_id in value
    if isinstance(value, dict):
        return any(_value_contains_post_id(child, post_id) for child in value.values())
    if isinstance(value, list):
        return any(_value_contains_post_id(child, post_id) for child in value)
    return False


def _choose_community_renderer(data: dict, post_id: str) -> dict:
    renderers = _community_renderers(data)
    if not renderers:
        return {}
    if post_id:
        for renderer in renderers:
            for node in _walk(renderer):
                if post_id in {str(node.get("postId", "")), str(node.get("post_id", "")), str(node.get("entityId", "")), str(node.get("id", ""))}:
                    return renderer
                navigation = node.get("navigationEndpoint")
                if isinstance(navigation, dict) and _value_contains_post_id(navigation, post_id):
                    return renderer
                command = node.get("commandMetadata")
                if isinstance(command, dict) and _value_contains_post_id(command, post_id):
                    return renderer
            if post_id in str(renderer.get("postId", "")):
                return renderer
    return renderers[0]


def _best_thumbnail(thumbnails: list) -> str:
    candidates = []
    for thumb in thumbnails:
        if not isinstance(thumb, dict):
            continue
        url = thumb.get('url')
        if not url:
            continue
        width = thumb.get('width') or 0
        height = thumb.get('height') or 0
        candidates.append((width * height, html.unescape(url)))
    if not candidates:
        return ""
    return sorted(candidates, reverse=True)[0][1]


def _community_image_urls(renderer: dict) -> list:
    attachment = renderer.get('backstageAttachment')
    if not isinstance(attachment, dict):
        return []
    urls = []
    for node in _walk(attachment):
        thumbnails = node.get('thumbnails')
        if isinstance(thumbnails, list):
            url = _best_thumbnail(thumbnails)
            if url:
                urls.append(url)
    return list(dict.fromkeys(urls))


def _extension_from_type(content_type: str, fallback_url: str) -> str:
    content_type = (content_type or "").split(';', 1)[0].strip().lower()
    type_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp"
    }
    if content_type in type_map:
        return type_map[content_type]
    suffix = Path(urlparse(fallback_url).path).suffix.lower()
    return suffix if suffix in type_map.values() else ".jpg"


def inspect_youtube_community(url: str) -> tuple[bool, dict]:
    if not _is_community_url(url):
        return False, {"error": "Not a YouTube community post URL"}

    config = get_config()
    fetch_success, page_text = _fetch_text(url, config)
    if not fetch_success:
        return False, {"error": f"YouTube community metadata failed: {page_text}"}

    data = _extract_balanced_json(page_text, "ytInitialData")
    if not data:
        return False, {"error": "YouTube community metadata failed: ytInitialData not found"}

    post_id = _post_id(url)
    renderer = _choose_community_renderer(data, post_id)
    if not renderer:
        return False, {"error": "YouTube community metadata failed: post renderer not found"}

    image_urls = _community_image_urls(renderer)
    if not image_urls:
        return False, {"error": "YouTube community post has no downloadable image attachments"}

    artist = _text_from_runs(renderer.get('authorText')) or "Unknown"
    title = _text_from_runs(renderer.get('contentText'))

    return True, {
        "original_url": url,
        "download_url": url,
        "platform": "YouTube",
        "artist": artist,
        "title": title,
        "expected_count": len(image_urls),
        "image_urls": image_urls,
        "metadata": {
            "source_url": url,
            "platform": "YouTube",
            "artist": artist,
            "title": title
        }
    }


def _download_community_post(url: str, metadata_info: dict = None) -> tuple[bool, dict]:
    config = get_config()
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:10]
    session_dir = ONLINE_INGEST_DIR / url_hash
    session_dir.mkdir(parents=True, exist_ok=True)

    try:
        if metadata_info is None:
            success, metadata_info = inspect_youtube_community(url)
            if not success:
                shutil.rmtree(session_dir, ignore_errors=True)
                return False, metadata_info

        user_agent = config.get('external_tools', {}).get('user_agent') or "Mozilla/5.0"
        opener = _opener(config)
        expected_sizes = {}

        download_errors = []
        for index, image_url in enumerate(metadata_info.get("image_urls", []), start=1):
            absolute_url = urljoin("https://www.youtube.com", image_url)
            request = Request(absolute_url, headers={"User-Agent": user_agent, "Referer": url})
            try:
                with opener.open(request, timeout=30) as response:
                    payload = response.read()
                    extension = _extension_from_type(response.headers.get("Content-Type", ""), absolute_url)
                    file_path = session_dir / f"{index}{extension}"
                    file_path.write_bytes(payload)
                    expected_sizes[str(index)] = len(payload)
            except Exception as exc:
                download_errors.append(f"{index}: {exc}")

        actual_files = valid_media_files(session_dir, config)
        expected_count = metadata_info.get("expected_count", 0)
        downloaded_count = len(actual_files)

        if expected_count > 0 and downloaded_count != expected_count:
            shutil.rmtree(session_dir, ignore_errors=True)
            return False, {
                "error": f"YouTube community incomplete download: expected {expected_count}, got {downloaded_count}",
                "expected_count": expected_count,
                "downloaded_count": downloaded_count,
                "download_errors": download_errors
            }

        if not actual_files:
            shutil.rmtree(session_dir, ignore_errors=True)
            return False, {"error": "No valid media files found after YouTube community download"}

        return True, {
            "file_paths": [str(f) for f in actual_files],
            "metadata": metadata_info["metadata"],
            "expected_sizes": expected_sizes,
            "expected_count": expected_count,
            "downloaded_count": downloaded_count,
            "download_url": url,
            "platform": "YouTube",
            "session_dir": str(session_dir)
        }
    except Exception as e:
        shutil.rmtree(session_dir, ignore_errors=True)
        return False, {"error": str(e)}


def download_video(url: str, metadata_info: dict = None) -> tuple[bool, dict]:
    if _is_community_url(url):
        return _download_community_post(url, metadata_info=metadata_info)

    config = get_config()
    ext_tools = config.get('external_tools', {})
    cookie_path = get_cookie_path()
    _log_auth_status("YouTube", get_cookie_auth_status())

    url_hash = hashlib.sha256(url.encode()).hexdigest()[:10]
    session_dir = ONLINE_INGEST_DIR / url_hash
    session_dir.mkdir(parents=True, exist_ok=True)

    try:
        meta_cmd = ["yt-dlp", "--dump-single-json", "--skip-download", "--no-playlist"]
        if cookie_path:
            meta_cmd.extend(["--cookies", str(cookie_path)])
        if ext_tools.get('proxy'):
            meta_cmd.extend(["--proxy", ext_tools['proxy']])

        if ext_tools.get('user_agent'):
            meta_cmd.extend(["--user-agent", ext_tools['user_agent']])
        meta_cmd.append(url)

        print(f"   [INFO] Fetching YouTube metadata...")
        meta_res = subprocess.run(meta_cmd, capture_output=True, text=True, timeout=_timeout("yt_dlp_metadata", 120))

        artist = "Unknown"
        title = ""
        expected_size = None

        if meta_res.returncode == 0:
            try:
                metadata = json.loads(meta_res.stdout)
                artist = metadata.get("uploader") or metadata.get("channel") or "Unknown"
                title = metadata.get("title") or ""
                expected_raw = metadata.get("filesize") or metadata.get("filesize_approx")
                expected_size = int(float(expected_raw)) if expected_raw else None
            except (json.JSONDecodeError, ValueError, TypeError):
                expected_size = None

        dl_cmd = ["yt-dlp", "-o", f"{session_dir}/1.%(ext)s", "--no-playlist"]
        if cookie_path:
            dl_cmd.extend(["--cookies", str(cookie_path)])
        if ext_tools.get('proxy'):
            dl_cmd.extend(["--proxy", ext_tools['proxy']])

        if ext_tools.get('user_agent'):
            dl_cmd.extend(["--user-agent", ext_tools['user_agent']])
        dl_cmd.append(url)

        print(f"   [INFO] Running yt-dlp for YouTube...")
        dl_res = subprocess.run(dl_cmd, capture_output=True, text=True, timeout=_timeout("yt_dlp_download", 600))

        if dl_res.returncode != 0:
            shutil.rmtree(session_dir, ignore_errors=True)
            return False, {"error": dl_res.stderr}

        actual_files = valid_media_files(session_dir, config)

        if not actual_files:
            shutil.rmtree(session_dir, ignore_errors=True)
            return False, {"error": "No files found after download"}

        return True, {
            "file_paths": [str(f) for f in actual_files],
            "metadata": {
                "source_url": url,
                "platform": "YouTube",
                "artist": artist,
                "title": title
            },
            "expected_size": expected_size,
            "session_dir": str(session_dir)
        }
    except Exception as e:
        if session_dir.exists():
            shutil.rmtree(session_dir, ignore_errors=True)
        return False, {"error": str(e)}
