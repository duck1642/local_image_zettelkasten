
import sys
import hashlib
import yaml
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Optional


SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent
_CONFIG_PATH_ENV = os.environ.get("LMZ_CONFIG_PATH")
if _CONFIG_PATH_ENV:
    _config_path_candidate = Path(_CONFIG_PATH_ENV).expanduser()
    CONFIG_PATH = (_config_path_candidate if _config_path_candidate.is_absolute() else PROJECT_ROOT / _config_path_candidate).resolve()
    CONFIG_ROOT = CONFIG_PATH.parent
else:
    CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"
    CONFIG_ROOT = PROJECT_ROOT

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

    path_str = _paths.get(key) or default
    p = Path(path_str)
    return p.resolve() if p.is_absolute() else (CONFIG_ROOT / p).resolve()

VAULT_DIR = _resolve_path('vault', "data/vault")

INPUT_DIR = _resolve_path('input', "data/input")
REVIEW_DIR = _resolve_path('review', "data/review")
LOCAL_INGEST_DIR = _resolve_path('local_ingest', str(INPUT_DIR / "local"))
ONLINE_INGEST_DIR = _resolve_path('online_ingest', str(INPUT_DIR / "online"))
QUEUES_DIR = _resolve_path('queues', "data/queues")
BATCHES_DIR = _resolve_path('batches', "data/batches")
SECRETS_DIR = _resolve_path('secrets', "secrets")
MODELS_DIR = _resolve_path('models', "data/models")
WD_TAGS_DIR = _resolve_path('wd_tags', "data/wd-tags")

OUTPUT_DIR = VAULT_DIR
ASSETS_DIR = OUTPUT_DIR / "assets"
NOTES_DIR = OUTPUT_DIR / "notes"

DB_PATH = _resolve_path('db', "data/db/lmz_main.db")

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

def storage_shard_for_hash(item_hash: str) -> str:
    return str(item_hash or "")[:2] or "00"

def resolve_storage_id(item_hash: str, conn=None) -> str | None:
    item_hash = str(item_hash or "").strip()
    if not item_hash:
        return None
    try:
        if conn is not None:
            row = conn.execute("SELECT storage_id FROM items WHERE hash = ?", (item_hash,)).fetchone()
        elif DB_PATH.exists():
            with sqlite3.connect(DB_PATH, timeout=5) as local_conn:
                row = local_conn.execute("SELECT storage_id FROM items WHERE hash = ?", (item_hash,)).fetchone()
        else:
            row = None
    except sqlite3.Error:
        return None
    if not row:
        return None
    return row[0] or None

def legacy_asset_path_for(item_hash: str, extension: str | None, mime_type: str | None = None) -> Path:
    ext = extension or EXT_MAP.get(mime_type or "", ".jpg")
    return ASSETS_DIR / storage_shard_for_hash(item_hash) / f"{item_hash}{ext}"

def storage_asset_path_for(item_hash: str, storage_id: str, extension: str | None, mime_type: str | None = None) -> Path:
    ext = extension or EXT_MAP.get(mime_type or "", ".jpg")
    return ASSETS_DIR / storage_shard_for_hash(item_hash) / f"{storage_id}{ext}"

def asset_path_for(item_hash: str, extension: str | None, mime_type: str | None, storage_id: str | None = None, conn=None) -> Path:
    storage_id = storage_id or resolve_storage_id(item_hash, conn)
    if storage_id:
        return storage_asset_path_for(item_hash, storage_id, extension, mime_type)
    return legacy_asset_path_for(item_hash, extension, mime_type)

def existing_asset_path_for(item_hash: str, extension: str | None, mime_type: str | None = None, storage_id: str | None = None, conn=None) -> Path:
    storage_id = storage_id or resolve_storage_id(item_hash, conn)
    if storage_id:
        compact_path = storage_asset_path_for(item_hash, storage_id, extension, mime_type)
        if compact_path.exists():
            return compact_path
    legacy_path = legacy_asset_path_for(item_hash, extension, mime_type)
    if legacy_path.exists():
        return legacy_path
    return storage_asset_path_for(item_hash, storage_id, extension, mime_type) if storage_id else legacy_path

def asset_url_for(item_hash: str, extension: str | None, mime_type: str | None = None, storage_id: str | None = None, conn=None) -> str:
    storage_id = storage_id or resolve_storage_id(item_hash, conn)
    ext = extension or EXT_MAP.get(mime_type or "", ".jpg")
    path_id = storage_id or item_hash
    if storage_id:
        compact_path = storage_asset_path_for(item_hash, storage_id, ext)
        legacy_path = legacy_asset_path_for(item_hash, ext)
        if legacy_path.exists() and not compact_path.exists():
            path_id = item_hash
    return f"/vault/{storage_shard_for_hash(item_hash)}/{path_id}{ext}"

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

def note_path_for(file_hash: str, storage_id: str | None = None, conn=None) -> Path:

    storage_id = storage_id or resolve_storage_id(file_hash, conn)
    filename_id = storage_id or file_hash
    return NOTES_DIR / storage_shard_for_hash(file_hash) / f"{filename_id}.md"

def legacy_sharded_note_path_for(file_hash: str) -> Path:

    return NOTES_DIR / storage_shard_for_hash(file_hash) / f"{file_hash}.md"

def legacy_note_path_for(file_hash: str) -> Path:

    return NOTES_DIR / f"{file_hash}.md"

def existing_note_path_for(file_hash: str, storage_id: str | None = None, conn=None) -> Path:

    compact_path = note_path_for(file_hash, storage_id, conn)
    if compact_path.exists():
        return compact_path
    legacy_sharded_path = legacy_sharded_note_path_for(file_hash)
    if legacy_sharded_path.exists():
        return legacy_sharded_path
    flat_path = legacy_note_path_for(file_hash)
    if flat_path.exists():
        return flat_path
    return compact_path

def wd_tag_cache_path_for(file_hash: str, storage_id: str | None = None, conn=None) -> Path:

    storage_id = storage_id or resolve_storage_id(file_hash, conn)
    filename_id = storage_id or file_hash
    return WD_TAGS_DIR / storage_shard_for_hash(file_hash) / f"{filename_id}.json"

def legacy_wd_tag_cache_path_for(file_hash: str) -> Path:

    return WD_TAGS_DIR / storage_shard_for_hash(file_hash) / f"{file_hash}.json"

def existing_wd_tag_cache_path_for(file_hash: str, storage_id: str | None = None, conn=None) -> Path:

    compact_path = wd_tag_cache_path_for(file_hash, storage_id, conn)
    if compact_path.exists():
        return compact_path
    legacy_path = legacy_wd_tag_cache_path_for(file_hash)
    if legacy_path.exists():
        return legacy_path
    return compact_path

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
    fd, temp_name = tempfile.mkstemp(prefix="lmztmp-", suffix=".tmp", dir=str(path.parent))
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
        from logger import log_system
        log_system("WARNING", "Image perceptual hash failed", file=str(filepath), exc_info=True)
        return None

def get_cookie_path() -> Optional[Path]:

    path = get_configured_cookie_path()
    return path if path and path.exists() else None

def resolve_project_path(path_str: str) -> Path:

    path = Path(path_str)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()

def get_configured_cookie_path() -> Optional[Path]:

    config = get_config()
    cookie_str = config.get('external_tools', {}).get('cookies_path')

    if not cookie_str:
        return None

    return resolve_project_path(cookie_str)

def get_cookie_auth_status() -> dict:

    configured_path = get_configured_cookie_path()
    if not configured_path:
        return {
            "cookies": "not_configured",
            "path": "",
            "x": "missing",
            "instagram": "missing",
            "pinterest": "missing",
            "youtube": "missing",
        }
    if not configured_path.exists():
        return {
            "cookies": "missing",
            "path": str(configured_path),
            "x": "missing",
            "instagram": "missing",
            "pinterest": "missing",
            "youtube": "missing",
        }

    platforms = {"x": False, "instagram": False, "pinterest": False, "youtube": False}
    try:
        for line in configured_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            domain = parts[0].lower()
            name = parts[5].lower()
            if (
                ("twitter.com" in domain or "x.com" in domain)
                and name in {"auth_token", "ct0"}
            ):
                platforms["x"] = True
            if "instagram.com" in domain and name == "sessionid":
                platforms["instagram"] = True
            if "pinterest.com" in domain:
                platforms["pinterest"] = True
            if "youtube.com" in domain or "google.com" in domain:
                platforms["youtube"] = True
    except OSError:
        return {
            "cookies": "unreadable",
            "path": str(configured_path),
            "x": "unknown",
            "instagram": "unknown",
            "pinterest": "unknown",
            "youtube": "unknown",
        }

    return {
        "cookies": "available",
        "path": str(configured_path),
        **{
            platform: "available" if found else "missing"
            for platform, found in platforms.items()
        },
    }
