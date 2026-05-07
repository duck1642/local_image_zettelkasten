import subprocess
from pathlib import Path

from PIL import Image
from logger import log_system
from utils import ASSETS_DIR, PROJECT_ROOT, EXT_MAP

THUMBNAIL_DIR = PROJECT_ROOT / "data" / "ui_cache" / "thumbnails"
TARGET_WIDTH = 600
MAX_HEIGHT = 800
JPEG_QUALITY = 80


def thumbnail_path_for(item_hash: str) -> Path:
    return THUMBNAIL_DIR / item_hash[:2] / f"{item_hash}.jpg"


def video_thumbnail_path_for(item_hash: str) -> Path:
    return THUMBNAIL_DIR / item_hash[:2] / f"{item_hash}_video.jpg"


def _asset_path_for(item_hash: str, extension: str | None, mime_type: str | None) -> Path:
    ext = extension or EXT_MAP.get(mime_type or "", ".jpg")
    return ASSETS_DIR / item_hash[:2] / f"{item_hash}{ext}"


def generate_image_thumbnail(asset_path: Path, item_hash: str) -> Path:
    thumb_path = thumbnail_path_for(item_hash)
    thumb_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(asset_path) as image:
        image.thumbnail((TARGET_WIDTH, MAX_HEIGHT))
        if image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        image.save(thumb_path, "JPEG", quality=JPEG_QUALITY, optimize=True)

    log_system("INFO", "Thumbnail generated", hash=item_hash, path=str(thumb_path))
    return thumb_path


def generate_video_thumbnail(asset_path: Path, item_hash: str) -> Path:
    thumb_path = video_thumbnail_path_for(item_hash)
    thumb_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", "00:00:01", "-i", str(asset_path),
        "-vf", f"scale='min({TARGET_WIDTH},iw)':-2",
        "-frames:v", "1", str(thumb_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0 or not thumb_path.exists():
        log_system("ERROR", "Video thumbnail failed", hash=item_hash, error=result.stderr)
        raise RuntimeError("Video thumbnail generation failed")

    log_system("INFO", "Video thumbnail generated", hash=item_hash, path=str(thumb_path))
    return thumb_path


def get_or_generate_thumbnail(item_hash: str, extension: str | None, mime_type: str | None) -> Path | None:
    asset_path = _asset_path_for(item_hash, extension, mime_type)
    if not asset_path.exists():
        return None

    is_video = (mime_type or "").startswith("video/")

    if is_video:
        thumb_path = video_thumbnail_path_for(item_hash)
        if thumb_path.exists() and thumb_path.stat().st_mtime >= asset_path.stat().st_mtime:
            return thumb_path
        try:
            return generate_video_thumbnail(asset_path, item_hash)
        except Exception:
            return None
    else:
        thumb_path = thumbnail_path_for(item_hash)
        if thumb_path.exists() and thumb_path.stat().st_mtime >= asset_path.stat().st_mtime:
            return thumb_path
        try:
            return generate_image_thumbnail(asset_path, item_hash)
        except Exception as e:
            log_system("ERROR", "Thumbnail generation failed", hash=item_hash, error=str(e))
            return None
