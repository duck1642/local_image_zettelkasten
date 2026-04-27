from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap, QPainter, QBrush, QPen, QPolygon
from PySide6.QtCore import QPoint

from logs.logger import log_ui
from utils import ASSETS_DIR, PROJECT_ROOT
from thumbnails import (
    THUMBNAIL_DIR, thumbnail_path_for, video_thumbnail_path_for,
    generate_image_thumbnail, generate_video_thumbnail
)

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


def pixmap_for_item(item_hash: str, extension: str | None, mime_type: str | None, width: int = 192, allow_generate: bool = True) -> QPixmap:
    _ap = asset_path_for(item_hash, extension, mime_type)
    if not _ap.exists():
        return placeholder_pixmap("MISSING", QColor("#f85149"), width)
    if (mime_type or "").startswith("video/"):
        thumb_path = video_thumbnail_path_for(item_hash)
        if thumb_path.exists() and thumb_path.stat().st_mtime >= _ap.stat().st_mtime:
            pixmap = QPixmap(str(thumb_path))
            if not pixmap.isNull():
                scaled = pixmap.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
                return add_play_overlay(scaled)
        if not allow_generate:
            return placeholder_pixmap("VIDEO", QColor("#8b949e"), width)
        try:
            generate_video_thumbnail(_ap, item_hash)
            pixmap = QPixmap(str(thumb_path))
            if pixmap.isNull():
                return placeholder_pixmap("PLAY", QColor("#8b949e"), width)
            scaled = pixmap.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
            return add_play_overlay(scaled)
        except Exception:
            return placeholder_pixmap("PLAY", QColor("#8b949e"), width)
    try:
        generate_image_thumbnail(_ap, item_hash)
        tp = thumbnail_path_for(item_hash)
        pixmap = QPixmap(str(tp))
        if pixmap.isNull():
            log_ui("ERROR", "Qt thumbnail pixmap null", hash=item_hash, thumbnail_path=str(tp))
            return placeholder_pixmap("IMAGE", QColor("#f85149"), width)
        return pixmap.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
    except Exception as exc:
        log_ui("ERROR", "Qt thumbnail load failed", hash=item_hash, error=str(exc))
        return placeholder_pixmap("IMAGE", QColor("#f85149"), width)


def preview_pixmap(asset_path: Path, item_hash: str, mime_type: str | None, width: int = 260, height: int = 220) -> QPixmap:
    if not asset_path.exists():
        return placeholder_pixmap("MISSING", QColor("#f85149"), min(width, height))
    if (mime_type or "").startswith("video/"):
        try:
            generate_video_thumbnail(asset_path, item_hash)
            tp = video_thumbnail_path_for(item_hash)
            pixmap = QPixmap(str(tp))
            scaled = pixmap.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            return add_play_overlay(scaled)
        except Exception:
            return placeholder_pixmap("VIDEO", QColor("#8b949e"), min(width, height))
    try:
        generate_image_thumbnail(asset_path, item_hash)
        tp = thumbnail_path_for(item_hash)
        pixmap = QPixmap(str(tp))
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
