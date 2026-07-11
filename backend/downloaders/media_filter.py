from pathlib import Path

from validators import get_mime_type, is_allowed_mime


def valid_media_files(session_dir: Path, config: dict) -> list[Path]:
    accepted_media = config.get('ingestion', {}).get('accepted_media', {})
    allowed_exts = {str(ext).lstrip('.').lower() for ext in accepted_media.get('extensions', [])}
    allowed_mimes = accepted_media.get('mime_types', [])
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
