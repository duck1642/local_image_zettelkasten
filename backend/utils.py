
import sys
import hashlib
import yaml
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional


SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"

def _early_load_config() -> dict:

    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}
    return {}

_config = _early_load_config()
_paths = _config.get('paths', {})

def _resolve_path(key: str, default: str) -> Path:

    path_str = _paths.get(key, default)
    p = Path(path_str)
    return p.resolve() if p.is_absolute() else (PROJECT_ROOT / p).resolve()

VAULT_DIR = _resolve_path('vault', "data/vault")

INPUT_DIR = _resolve_path('input', "data/input")
REVIEW_DIR = _resolve_path('review', "data/review")
LOCAL_INGEST_DIR = _resolve_path('local_ingest', "data/local_ingest")
ONLINE_INGEST_DIR = _resolve_path('online_ingest', "data/online_ingest")
QUEUES_DIR = _resolve_path('queues', "data/queues")
BATCHES_DIR = _resolve_path('batches', "data/batches")
SECRETS_DIR = _resolve_path('secrets', "secrets")
MODELS_DIR = _resolve_path('models', "data/models")
WD_TAGS_DIR = _resolve_path('wd_tags', "data/wd-tags")

OUTPUT_DIR = VAULT_DIR
ASSETS_DIR = OUTPUT_DIR / "assets"
NOTES_DIR = OUTPUT_DIR / "notes"

DB_PATH = _resolve_path('db', "data/db/liz_main.db")

LOGS_DIR = _resolve_path('logs', "logs")

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

DEFAULT_ALLOWED_MIMES = {
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/webp',
    'video/mp4',
    'video/webm',
    'video/ogg'
}


def setup_directories():

    for directory in [
        INPUT_DIR,
        REVIEW_DIR,
        LOCAL_INGEST_DIR,
        ONLINE_INGEST_DIR,
        QUEUES_DIR,
        BATCHES_DIR,
        MODELS_DIR,
        WD_TAGS_DIR,
        OUTPUT_DIR,
        ASSETS_DIR,
        NOTES_DIR,
        DB_PATH.parent,
        LOGS_DIR,
        SECRETS_DIR,
    ]:
        directory.mkdir(parents=True, exist_ok=True)

def note_path_for(file_hash: str) -> Path:

    return NOTES_DIR / str(file_hash)[:2] / f"{file_hash}.md"

def legacy_note_path_for(file_hash: str) -> Path:

    return NOTES_DIR / f"{file_hash}.md"

def existing_note_path_for(file_hash: str) -> Path:

    sharded_path = note_path_for(file_hash)
    if sharded_path.exists():
        return sharded_path
    return legacy_note_path_for(file_hash)

def wd_tag_cache_path_for(file_hash: str) -> Path:

    return WD_TAGS_DIR / str(file_hash)[:2] / f"{file_hash}.json"

def validate_config_schema(config: dict):

    errors = []

    if not isinstance(config, dict):
        raise ValueError("config.yaml must be a dictionary")

    if 'paths' not in config:
        errors.append("Missing mandatory section: 'paths'")
    else:
        for key in ['vault', 'db', 'logs', 'queues', 'batches', 'secrets']:
            if key not in config['paths']:
                errors.append(f"Missing mandatory key in 'paths': '{key}'")
            elif not isinstance(config['paths'][key], str):
                errors.append(f"Key 'paths.{key}' must be a string")

    if 'firewall' not in config:
        errors.append("Missing mandatory section: 'firewall'")
    else:
        for key in ['allowed_extensions', 'allowed_mimes']:
            if key not in config['firewall']:
                errors.append(f"Missing mandatory key in 'firewall': '{key}'")
            elif not isinstance(config['firewall'][key], list):
                errors.append(f"Key 'firewall.{key}' must be a list")

    if 'hash_algorithm' not in config:
        errors.append("Missing mandatory key: 'hash_algorithm'")

    if errors:
        raise ValueError("Configuration Error in config.yaml: " + "; ".join(errors))

def load_secrets() -> dict:

    secrets_path = SECRETS_DIR / ".secrets.yaml"
    if not secrets_path.exists():
        return {}
    try:
        with open(secrets_path, 'r', encoding='utf-8') as f:
            secrets = yaml.safe_load(f)
            return secrets if isinstance(secrets, dict) else {}
    except Exception:
        return {}

def get_config() -> dict:

    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            validate_config_schema(config)


            secrets = load_secrets()
            if secrets:
                if 'external_tools' not in config:
                    config['external_tools'] = {}
                config['external_tools'].update(secrets)

            return config

    except FileNotFoundError:
        return {
            'paths': {
                'vault': str(VAULT_DIR),
                'db': str(DB_PATH),
                'logs': str(LOGS_DIR),
                'queues': str(QUEUES_DIR),
                'batches': str(BATCHES_DIR),
                'secrets': str(SECRETS_DIR),
                'models': str(MODELS_DIR),
                'wd_tags': str(WD_TAGS_DIR),
            },
            'ui': {
                'vault_layout_mode': 'masonry',
                'vault_tile_min_width': 190,
                'prefixes': {
                    'command': '>',
                    'platform': '@',
                    'artist': 'a:',
                    'tag': '#'
                }
            },
            'firewall': {
                'allowed_extensions': ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.jfif', '.mp4', '.webm', '.ogv'],
                'allowed_mimes': list(DEFAULT_ALLOWED_MIMES)
            },
            'hash_algorithm': 'sha256',
            'tagging': {
                'enabled': True,
                'model_repo': 'SmilingWolf/wd-vit-tagger-v3',
                'device': 'auto',
                'display_source': 'yaml',
                'threshold': 0.35,
                'max_tags': 30,
                'fail_ingestion_on_error': False,
                'video': {
                    'enabled': True,
                    'frame_count': 5,
                    'merge_min_frames': 2,
                    'merge_high_confidence': 0.75
                }
            }
        }

def atomic_write_text(path: Path, text: str, encoding: str = "utf-8"):

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="liztmp-", suffix=".tmp", dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            temp_path.replace(path)
        except PermissionError:
            if path.exists():
                path.unlink()
            shutil.move(str(temp_path), str(path))
    except Exception:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise

def calculate_file_hash(filepath: Path, algorithm: str = 'sha256') -> str:

    hasher = hashlib.new(algorithm)

    with open(filepath, 'rb') as f:
        while chunk := f.read(8192):
            hasher.update(chunk)

    return hasher.hexdigest()

def get_normalization_color(proc_config: dict) -> tuple:

    preset = proc_config.get('background_preset', 'white').lower()

    presets = {
        "white": (255, 255, 255),
        "black": (0, 0, 0),
        "gray": (128, 128, 128)
    }

    if preset == "custom":
        return tuple(proc_config.get('custom_color', [255, 255, 255]))

    return presets.get(preset, (255, 255, 255))

def flatten_image(img, background_color=(255, 255, 255)):

    from PIL import Image
    if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):

        background = Image.new('RGB', img.size, background_color)
        if img.mode == 'P':
            img = img.convert('RGBA')


        background.paste(img, (0, 0), img)
        return background
    return img.convert('RGB')

def calculate_phash(filepath: Path) -> Optional[str]:

    try:
        from PIL import Image
        import imagehash

        config = get_config()
        proc_config = config.get('processing', {})
        do_flatten = proc_config.get('flatten_transparency', False)
        bg_color = get_normalization_color(proc_config)

        with Image.open(filepath) as img:
            if do_flatten:
                img = flatten_image(img, bg_color)


            hash_obj = imagehash.phash(img)
            return str(hash_obj)
    except Exception:
        return None

def get_cookie_path() -> Optional[Path]:

    config = get_config()
    cookie_str = config.get('external_tools', {}).get('cookies_path')

    if not cookie_str:
        return None

    path = Path(cookie_str)
    if not path.is_absolute():
        path = PROJECT_ROOT / path

    resolved_path = path.resolve()
    return resolved_path if resolved_path.exists() else None
