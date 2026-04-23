import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from utils import INPUT_DIR, get_config, get_cookie_path
from validators import get_mime_type, is_allowed_mime


def _extract_artist(data: dict, platform: str) -> str:
    def extract_from_field(field_val) -> str:
        if isinstance(field_val, dict):
            return field_val.get('name') or field_val.get('full_name') or field_val.get('nick') or field_val.get('username') or field_val.get('account')
        if isinstance(field_val, str) and field_val.strip():
            return field_val
        return None

    if platform == "X":
        for field in ['author', 'user']:
            res = extract_from_field(data.get(field))
            if res: return res

    elif platform == "Pixiv":
        res = extract_from_field(data.get('user'))
        if res: return res

    elif platform == "Instagram":
        for field in ['owner', 'user', 'fullname', 'username']:
            res = extract_from_field(data.get(field))
            if res: return res

    elif platform == "Pinterest":
        for field in ['creator', 'user', 'owner']:
            res = extract_from_field(data.get(field))
            if res: return res

    for key in ['author', 'user', 'uploader', 'owner', 'creator', 'name', 'username', 'fullname', 'nick']:
        res = extract_from_field(data.get(key))
        if res: return res

    return None


def _normalized_url(url: str) -> str:
    u_low = url.lower()
    if "x.com" in u_low or "twitter.com" in u_low:
        if '?' in url:
            url = url.split('?')[0]
        url = url.replace("www.x.com", "twitter.com").replace("x.com", "twitter.com")
    return url


def _platform_for_url(url: str) -> str:
    u_low = url.lower()
    if 'pixiv' in u_low: return "Pixiv"
    if 'pinterest' in u_low: return "Pinterest"
    if 'instagram' in u_low: return "Instagram"
    if 'twitter' in u_low: return "X"
    return "Unknown"


def _base_args(url: str) -> list:
    config = get_config()
    ext_tools = config.get('external_tools', {})
    cookie_path = get_cookie_path()
    args = []

    if cookie_path:
        args.extend(["--cookies", str(cookie_path)])
    if ext_tools.get('pixiv_token') and "pixiv" in url.lower():
        args.extend(["--option", f"extractor.pixiv.refresh-token={ext_tools['pixiv_token']}"])
    if ext_tools.get('proxy'):
        args.extend(["--proxy", ext_tools['proxy']])
    if ext_tools.get('user_agent'):
        args.extend(["--user-agent", ext_tools['user_agent']])

    return args


def _load_metadata_lines(stdout: str) -> list:
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
    artist = "Unknown"
    media_entries = []
    expected_sizes = {}
    is_ugoira = False

    for item in meta_json:
        data = _media_data_from_item(item)
        if not data:
            continue

        if platform != "Pinterest":
            extracted_artist = _extract_artist(data, platform)
            if extracted_artist:
                artist = extracted_artist

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
        "artist": artist,
        "expected_count": expected_count,
        "expected_sizes": expected_sizes,
        "is_ugoira": is_ugoira,
        "metadata": {
            "source_url": original_url,
            "platform": platform,
            "artist": artist,
            "title": ""
        }
    }


def inspect_gallery(url: str) -> tuple[bool, dict]:
    original_url = url
    download_url = _normalized_url(url)
    meta_cmd = ["gallery-dl", "-j"] + _base_args(download_url) + [download_url]
    result = subprocess.run(meta_cmd, capture_output=True, text=True)

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
        "artist": "Unknown",
        "expected_count": 0,
        "expected_sizes": {},
        "is_ugoira": False,
        "metadata": {
            "source_url": original_url,
            "platform": platform,
            "artist": "Unknown",
            "title": ""
        }
    }


def _valid_media_files(session_dir: Path, config: dict) -> list:
    firewall_config = config.get('firewall', {})
    allowed_exts = {ext.lstrip('.').lower() for ext in firewall_config.get('allowed_extensions', [])}
    allowed_mimes = firewall_config.get('allowed_mimes', [])
    excluded_exts = {'.part', '.zip', '.json', '.txt', '.yml', '.yaml'}
    actual_files = []

    for file_path in session_dir.rglob('*'):
        if not file_path.is_file():
            continue
        suffix = file_path.suffix.lower()
        if suffix in excluded_exts:
            continue
        if suffix.lstrip('.') not in allowed_exts:
            continue
        if file_path.stat().st_size <= 0:
            continue
        mime_type = get_mime_type(file_path) or "unknown"
        if not is_allowed_mime(mime_type, allowed_mimes):
            continue
        actual_files.append(file_path)

    return sorted(actual_files, key=lambda p: str(p))


def download_gallery(url: str, metadata_info: dict = None) -> tuple[bool, dict]:
    config = get_config()
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:10]
    session_dir = INPUT_DIR / "external" / url_hash
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
        dl_res = subprocess.run(dl_cmd, capture_output=True, text=True)

        if dl_res.returncode != 0:
            shutil.rmtree(session_dir, ignore_errors=True)
            return False, {"error": dl_res.stderr}

        actual_files = _valid_media_files(session_dir, config)
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
