
import sqlite3
import yaml
from datetime import datetime

from tagging import wd_frontmatter_fields
from utils import existing_note_path_for

MANUAL_FRONTMATTER_FIELDS = (
    "title",
    "artist",
    "date_added",
    "topics",
    "wd_rating",
    "wd_character_tags",
    "wd_tags",
)
WD_FRONTMATTER_FIELDS = ("wd_rating", "wd_character_tags", "wd_tags")


def _format_date_added(date_added) -> str:
    if not date_added:
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(date_added, datetime):
        return date_added.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(date_added, str):
        return date_added.split(".")[0] if "." in date_added else date_added
    return str(date_added)


def generate_markdown(conn: sqlite3.Connection, file_hash: str, asset_rel_path: str | None = None, title: str = "", topics_override: list | None = None, manual_overrides: dict | None = None) -> str:

    cursor = conn.cursor()
    cursor.execute('''
        SELECT original_filename, mime_type, file_extension, source_url, platform, source_artist, date_added, phash
        FROM items
        WHERE hash = ?
    ''', (file_hash,))

    row = cursor.fetchone()

    if not row:
        return ""

    original_filename, mime_type, file_extension, source_url, platform, source_artist, date_added, phash = row

    existing_frontmatter = load_note_frontmatter(file_hash)
    date_added_str = _format_date_added(date_added)

    shard_folder = file_hash[:2]
    asset_link = asset_rel_path if asset_rel_path else f"../../assets/{shard_folder}/{file_hash}{file_extension}"

    is_video = mime_type.startswith('video/')
    asset_type = "video" if is_video else "image"


    frontmatter = {
        "hash": file_hash,
        "title": title or "",
        "filename": original_filename or "",
        "date_added": date_added_str,
        "type": asset_type,
        "source_url": source_url or "",
        "platform": platform or "",
        "artist": source_artist or "",
        "phash": phash or "",
        "topics": topics_override if topics_override is not None else load_note_topics(file_hash),
        "file_format": mime_type or ""
    }
    for field in ("title", "artist", "date_added"):
        if field in existing_frontmatter:
            frontmatter[field] = existing_frontmatter[field]
    if topics_override is None and "topics" in existing_frontmatter:
        frontmatter["topics"] = normalize_topic_list(existing_frontmatter.get("topics"))

    cache_wd_fields = wd_frontmatter_fields(file_hash)
    for field in WD_FRONTMATTER_FIELDS:
        frontmatter[field] = existing_frontmatter[field] if field in existing_frontmatter else cache_wd_fields.get(field, [] if field != "wd_rating" else "")
    for field, value in (manual_overrides or {}).items():
        if field in MANUAL_FRONTMATTER_FIELDS:
            frontmatter[field] = value


    fm_str = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False, allow_unicode=True)

    return f"""---
{fm_str}---

![]({asset_link})
"""


def normalize_topic_list(topics) -> list[str]:
    if not topics:
        return []
    if isinstance(topics, list):
        return [str(topic).strip() for topic in topics if str(topic).strip()]
    normalized = str(topics).replace("\r", "\n").replace(",", "\n")
    return [topic.strip() for topic in normalized.split("\n") if topic.strip()]


def load_note_frontmatter(file_hash: str) -> dict:
    path = existing_note_path_for(file_hash)
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    text = text.lstrip("\ufeff")
    if not text.startswith("---"):
        return {}
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = index
            break
    if end_index is None:
        return {}
    yaml_text = "\n".join(lines[1:end_index])
    try:
        data = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def load_note_topics(file_hash: str, fallback=None) -> list[str]:
    frontmatter = load_note_frontmatter(file_hash)
    if "topics" in frontmatter:
        return normalize_topic_list(frontmatter.get("topics"))
    return normalize_topic_list(fallback)


def load_note_wd_tags(file_hash: str) -> dict:
    frontmatter = load_note_frontmatter(file_hash)
    has_wd_fields = any(field in frontmatter for field in WD_FRONTMATTER_FIELDS)
    rating = str(frontmatter.get("wd_rating") or "").strip()
    characters = normalize_topic_list(frontmatter.get("wd_character_tags"))
    tags = normalize_topic_list(frontmatter.get("wd_tags"))
    return {
        "status": "ok" if has_wd_fields else "missing",
        "source": "yaml",
        "rating": {"label": rating} if rating else {},
        "character_tags": [{"name": tag} for tag in characters],
        "tags": [{"name": tag} for tag in tags],
    }
