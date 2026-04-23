
import sqlite3
import yaml
from datetime import datetime

from tagging import wd_frontmatter_fields

def generate_markdown(conn: sqlite3.Connection, file_hash: str, asset_rel_path: str = None, title: str = "") -> str:

    cursor = conn.cursor()
    cursor.execute('''
        SELECT original_filename, mime_type, file_extension, source_url, platform, source_artist, date_added, phash, topics
        FROM items
        WHERE hash = ?
    ''', (file_hash,))

    row = cursor.fetchone()

    if not row:
        return ""

    original_filename, mime_type, file_extension, source_url, platform, source_artist, date_added, phash, topics = row


    if not date_added:
        date_added_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    elif isinstance(date_added, datetime):
        date_added_str = date_added.strftime('%Y-%m-%d %H:%M:%S')
    elif isinstance(date_added, str):
        if "." in date_added:
            date_added_str = date_added.split(".")[0]
        else:
            date_added_str = date_added
    else:
        date_added_str = str(date_added)

    shard_folder = file_hash[:2]
    asset_link = asset_rel_path if asset_rel_path else f"../assets/{shard_folder}/{file_hash}{file_extension}"

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
        "topics": _topics_list(topics),
        "file_format": mime_type or ""
    }
    frontmatter.update(wd_frontmatter_fields(file_hash))


    fm_str = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False, allow_unicode=True)

    return f"""---
{fm_str}---

![]({asset_link})
"""


def _topics_list(topics: str) -> list[str]:
    if not topics:
        return []
    if isinstance(topics, list):
        return [str(topic).strip() for topic in topics if str(topic).strip()]
    normalized = str(topics).replace("\r", "\n").replace(",", "\n")
    return [topic.strip() for topic in normalized.split("\n") if topic.strip()]
