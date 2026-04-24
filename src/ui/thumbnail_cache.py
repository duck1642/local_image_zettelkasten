from pathlib import Path
import subprocess

from PIL import Image
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap, QPolygon

from logs.logger import log_ui
from utils import ASSETS_DIR, PROJECT_ROOT


THUMBNAIL_DIR = PROJECT_ROOT / "data" / "ui_cache" / "thumbnails"


EXT_MAP = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/jfif": ".jpg",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/ogg": ".ogv",
}


def asset_path_for(item_hash: str, extension: str | None, mime_type: str | None) -> Path:
    ext = extension or EXT_MAP.get(mime_type or "", ".jpg")
    return ASSETS_DIR / item_hash[:2] / f"{item_hash}{ext}"


def thumbnail_path_for(asset_path: Path, item_hash: str) -> Path:
    THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
    thumb_path = THUMBNAIL_DIR / f"{item_hash}.jpg"
    if not thumb_path.exists() or thumb_path.stat().st_mtime < asset_path.stat().st_mtime:
        with Image.open(asset_path) as image:
            image.thumbnail((512, 512))
            if image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")
            image.save(thumb_path, "JPEG", quality=84, optimize=True)
        log_ui("INFO", "Qt thumbnail generated", hash=item_hash, thumbnail_path=str(thumb_path))
    return thumb_path


def video_thumbnail_path_for(asset_path: Path, item_hash: str) -> Path:
    THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
    thumb_path = THUMBNAIL_DIR / f"{item_hash}_video.jpg"
    if not thumb_path.exists() or thumb_path.stat().st_mtime < asset_path.stat().st_mtime:
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", "00:00:01", "-i", str(asset_path), "-frames:v", "1", str(thumb_path)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0 or not thumb_path.exists():
            log_ui("ERROR", "Qt video thumbnail failed", hash=item_hash, error=result.stderr)
            raise RuntimeError("Video thumbnail generation failed")
        log_ui("INFO", "Qt video thumbnail generated", hash=item_hash, thumbnail_path=str(thumb_path))
    return thumb_path


def add_play_overlay(pixmap: QPixmap) -> QPixmap:
    output = QPixmap(pixmap)
    painter = QPainter(output)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    center = output.rect().center()
    radius = max(18, min(output.width(), output.height()) // 7)
    painter.setBrush(QBrush(QColor(13, 17, 23, 190)))
    painter.setPen(QPen(QColor("#8b949e"), 1))
    painter.drawEllipse(center, radius, radius)
    triangle = QPolygon([
        QPoint(center.x() - radius // 3, center.y() - radius // 2),
        QPoint(center.x() - radius // 3, center.y() + radius // 2),
        QPoint(center.x() + radius // 2, center.y()),
    ])
    painter.setBrush(QBrush(QColor("#f0f6fc")))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawPolygon(triangle)
    painter.end()
    return output


def pixmap_for_item(item_hash: str, extension: str | None, mime_type: str | None, size: int = 192, allow_generate: bool = True) -> QPixmap:
    asset_path = asset_path_for(item_hash, extension, mime_type)
    if not asset_path.exists():
        return placeholder_pixmap("MISSING", QColor("#f85149"), size)
    if (mime_type or "").startswith("video/"):
        thumb_path = THUMBNAIL_DIR / f"{item_hash}_video.jpg"
        if thumb_path.exists() and thumb_path.stat().st_mtime >= asset_path.stat().st_mtime:
            pixmap = QPixmap(str(thumb_path))
            if not pixmap.isNull():
                scaled = pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                return add_play_overlay(scaled)
        
        if not allow_generate:
            return placeholder_pixmap("VIDEO", QColor("#8b949e"), size)

        try:
            thumb_path = video_thumbnail_path_for(asset_path, item_hash)
            pixmap = QPixmap(str(thumb_path))
            if pixmap.isNull():
                return placeholder_pixmap("PLAY", QColor("#8b949e"), size)
            scaled = pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            return add_play_overlay(scaled)
        except Exception:
            return placeholder_pixmap("PLAY", QColor("#8b949e"), size)
    try:
        thumb_path = thumbnail_path_for(asset_path, item_hash)
        pixmap = QPixmap(str(thumb_path))
        if pixmap.isNull():
            log_ui("ERROR", "Qt thumbnail pixmap null", hash=item_hash, thumbnail_path=str(thumb_path))
            return placeholder_pixmap("IMAGE", QColor("#f85149"), size)
        return pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    except Exception as exc:
        log_ui("ERROR", "Qt thumbnail load failed", hash=item_hash, error=str(exc))
        return placeholder_pixmap("IMAGE", QColor("#f85149"), size)


def preview_pixmap(asset_path: Path, item_hash: str, mime_type: str | None, width: int = 260, height: int = 220) -> QPixmap:
    if not asset_path.exists():
        return placeholder_pixmap("MISSING", QColor("#f85149"), min(width, height))
    if (mime_type or "").startswith("video/"):
        try:
            thumb_path = video_thumbnail_path_for(asset_path, item_hash)
            pixmap = QPixmap(str(thumb_path))
            scaled = pixmap.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            return add_play_overlay(scaled)
        except Exception:
            return placeholder_pixmap("VIDEO", QColor("#8b949e"), min(width, height))
    try:
        thumb_path = thumbnail_path_for(asset_path, item_hash)
        pixmap = QPixmap(str(thumb_path))
        return pixmap.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    except Exception as exc:
        log_ui("ERROR", "Qt preview load failed", hash=item_hash, error=str(exc))
        return placeholder_pixmap("IMAGE", QColor("#f85149"), min(width, height))


def placeholder_pixmap(text: str, color: QColor, size: int = 192) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor("#161b22"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(color)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, text)
    painter.end()
    return pixmap
