
from pathlib import Path
from typing import Optional

def get_mime_type(filepath: Path) -> Optional[str]:

    try:
        import magic
        mime = magic.from_file(str(filepath), mime=True)
        return mime.lower() if mime else None

    except Exception:

        ext_map = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.jfif': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.mp4': 'video/mp4',
            '.webm': 'video/webm',
            '.ogv': 'video/ogg'
        }
        return ext_map.get(filepath.suffix.lower())

def is_allowed_mime(mime_type: str, allowed_list: list) -> bool:

    return mime_type in set(allowed_list or [])
