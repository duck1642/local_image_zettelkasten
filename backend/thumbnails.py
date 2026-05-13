import subprocess
import threading
from pathlib import Path

from PIL import Image
from logger import log_system
from utils import PROJECT_ROOT, asset_path_for, require_storage_id, storage_shard_for_hash

THUMBNAIL_DIR = PROJECT_ROOT / "data" / "ui_cache" / "thumbnails"
TARGET_WIDTH = 600
MAX_HEIGHT = 800
JPEG_QUALITY = 80
GENERATION_CONCURRENCY = 2
_GENERATION_SEMAPHORE = threading.Semaphore(GENERATION_CONCURRENCY)


class ThumbnailBusyError(RuntimeError):
    pass


def thumbnail_path_for(item_hash: str, storage_id: str) -> Path:
    storage_id = require_storage_id(storage_id)
    return THUMBNAIL_DIR / storage_shard_for_hash(item_hash) / f"{storage_id}.jpg"


def video_thumbnail_path_for(item_hash: str, storage_id: str) -> Path:
    storage_id = require_storage_id(storage_id)
    return THUMBNAIL_DIR / storage_shard_for_hash(item_hash) / f"{storage_id}_video.jpg"


def _expected_thumbnail_path(item_hash: str, mime_type: str | None, storage_id: str) -> Path:
    if (mime_type or "").startswith("video/"):
        return video_thumbnail_path_for(item_hash, storage_id)
    return thumbnail_path_for(item_hash, storage_id)


def _thumbnail_is_fresh(thumb_path: Path, asset_path: Path) -> bool:
    return thumb_path.exists() and thumb_path.stat().st_mtime >= asset_path.stat().st_mtime


def generate_image_thumbnail(asset_path: Path, item_hash: str, storage_id: str) -> Path:
    thumb_path = thumbnail_path_for(item_hash, storage_id)
    thumb_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(asset_path) as image:
        image.thumbnail((TARGET_WIDTH, MAX_HEIGHT))
        if image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        image.save(thumb_path, "JPEG", quality=JPEG_QUALITY, optimize=True)

    log_system("INFO", "Thumbnail generated", hash=item_hash, path=str(thumb_path))
    return thumb_path


def generate_video_thumbnail(asset_path: Path, item_hash: str, storage_id: str) -> Path:
    thumb_path = video_thumbnail_path_for(item_hash, storage_id)
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


def ensure_thumbnail(item_hash: str, extension: str | None, mime_type: str | None, wait: bool = True, storage_id: str | None = None) -> Path | None:
    storage_id = require_storage_id(storage_id)
    asset_path = asset_path_for(item_hash, extension, mime_type, storage_id=storage_id)
    if not asset_path.exists():
        return None

    thumb_path = _expected_thumbnail_path(item_hash, mime_type, storage_id)
    if _thumbnail_is_fresh(thumb_path, asset_path):
        return thumb_path

    acquired = _GENERATION_SEMAPHORE.acquire(blocking=wait)
    if not acquired:
        raise ThumbnailBusyError("thumbnail generation is busy")
    try:
        thumb_path = _expected_thumbnail_path(item_hash, mime_type, storage_id)
        if _thumbnail_is_fresh(thumb_path, asset_path):
            return thumb_path
        if (mime_type or "").startswith("video/"):
            return generate_video_thumbnail(asset_path, item_hash, storage_id)
        return generate_image_thumbnail(asset_path, item_hash, storage_id)
    except Exception as e:
        log_system("ERROR", "Thumbnail generation failed", hash=item_hash, error=str(e))
        return None
    finally:
        _GENERATION_SEMAPHORE.release()


def get_or_generate_thumbnail(item_hash: str, extension: str | None, mime_type: str | None, storage_id: str | None = None) -> Path | None:
    return ensure_thumbnail(item_hash, extension, mime_type, wait=False, storage_id=storage_id)


def repair_missing_thumbnails(conn, limit: int = 100) -> dict:
    limit = max(1, int(limit or 100))
    generated = 0
    skipped = 0
    failed = 0
    checked = 0
    rows = conn.execute(
        "SELECT hash, file_extension, mime_type, storage_id FROM items ORDER BY date_added DESC"
    )
    for item_hash, extension, mime_type, storage_id in rows:
        if checked >= limit:
            break
        checked += 1
        asset_path = asset_path_for(item_hash, extension, mime_type, storage_id=storage_id)
        if not asset_path.exists():
            skipped += 1
            continue
        thumb_path = _expected_thumbnail_path(item_hash, mime_type, storage_id)
        if _thumbnail_is_fresh(thumb_path, asset_path):
            skipped += 1
            continue
        try:
            if ensure_thumbnail(item_hash, extension, mime_type, wait=True, storage_id=storage_id):
                generated += 1
            else:
                failed += 1
        except Exception:
            failed += 1
    log_system("INFO", "Thumbnail repair batch finished", checked=checked, generated=generated, skipped=skipped, failed=failed)
    return {"checked": checked, "generated": generated, "skipped": skipped, "failed": failed}
