
import sys
import copy
import hashlib
import yaml
import os
import shutil
import tempfile
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from runtime_context import WorkspaceContext, get_runtime_context, reload_runtime_context

SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent

_RUNTIME_CONTEXT = reload_runtime_context()
CONFIG_PATH = _RUNTIME_CONTEXT.config_path
CONFIG_ROOT = _RUNTIME_CONTEXT.root

def _early_load_config() -> dict:

    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}
    return {}

_config = _early_load_config()



def _resolve_path(key: str, default: str) -> Path:

    paths = _config.get('paths', {}) if isinstance(_config.get('paths'), dict) else {}
    path_str = paths.get(key) or default
    p = Path(path_str)
    return p.resolve() if p.is_absolute() else (CONFIG_ROOT / p).resolve()

def _resolve_config_relative(path_str: str) -> Path:
    p = Path(path_str)
    return p.resolve() if p.is_absolute() else (CONFIG_ROOT / p).resolve()

_DYNAMIC_CONSTANTS = {
    "VAULTS_CONFIGURED": lambda: get_runtime_context().vaults_configured,
    "ACTIVE_VAULT_ID": lambda: get_runtime_context().active_vault.id,
    "ACTIVE_VAULT_NAME": lambda: get_runtime_context().active_vault.name,
    "ACTIVE_VAULT_ROOT": lambda: get_runtime_context().active_vault.root,

    "VAULT_DIR": lambda: get_runtime_context().active_vault.vault_dir,
    "INPUT_DIR": lambda: get_runtime_context().active_vault.input_dir,
    "REVIEW_DIR": lambda: get_runtime_context().active_vault.review_dir,
    "LOCAL_INGEST_DIR": lambda: get_runtime_context().active_vault.local_ingest_dir,
    "ONLINE_INGEST_DIR": lambda: get_runtime_context().active_vault.online_ingest_dir,
    "QUEUES_DIR": lambda: get_runtime_context().active_vault.queues_dir,
    "BATCHES_DIR": lambda: get_runtime_context().active_vault.batches_dir,
    "SECRETS_DIR": lambda: get_runtime_context().secrets_dir,
    "MODELS_DIR": lambda: get_runtime_context().models_dir,
    "WD_TAGS_DIR": lambda: get_runtime_context().active_vault.wd_tags_dir,
    "THUMBNAILS_DIR": lambda: get_runtime_context().active_vault.thumbnails_dir,
    "TOPICS_DIR": lambda: get_runtime_context().topics_dir,

    "OUTPUT_DIR": lambda: get_runtime_context().active_vault.vault_dir,
    "ASSETS_DIR": lambda: get_runtime_context().active_vault.assets_dir,
    "NOTES_DIR": lambda: get_runtime_context().active_vault.notes_dir,

    "DB_PATH": lambda: get_runtime_context().active_vault.db_path,

    "LOGS_DIR": lambda: get_runtime_context().active_vault.logs_dir,
}

def __getattr__(name: str):
    if name in _DYNAMIC_CONSTANTS:
        return _DYNAMIC_CONSTANTS[name]()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

def __dir__():
    return sorted(list(globals().keys()) + list(_DYNAMIC_CONSTANTS.keys()))

_CONFIG_CACHE_LOCK = threading.Lock()
_CONFIG_CACHE_DATA: dict | None = None
_CONFIG_CACHE_MTIMES: tuple[Path, Path, float | None, float | None] | None = None

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

def require_storage_id(storage_id: str | None) -> str:
    value = str(storage_id or "").strip()
    if not value:
        raise ValueError("storage_id is required for compact storage paths")
    return value

def _ctx(ctx: WorkspaceContext | None = None) -> WorkspaceContext:
    return ctx or get_runtime_context()


def storage_asset_path_for(item_hash: str, storage_id: str, extension: str | None, mime_type: str | None = None, ctx: WorkspaceContext | None = None) -> Path:
    storage_id = require_storage_id(storage_id)
    ext = extension or EXT_MAP.get(mime_type or "", ".jpg")
    return _ctx(ctx).active_vault.assets_dir / storage_shard_for_hash(item_hash) / f"{storage_id}{ext}"

def asset_path_for(item_hash: str, extension: str | None, mime_type: str | None, storage_id: str, ctx: WorkspaceContext | None = None) -> Path:
    return storage_asset_path_for(item_hash, storage_id, extension, mime_type, ctx=ctx)

def asset_url_for(item_hash: str, extension: str | None, mime_type: str | None = None, storage_id: str | None = None) -> str:
    storage_id = require_storage_id(storage_id)
    ext = extension or EXT_MAP.get(mime_type or "", ".jpg")
    return f"/vault/{storage_shard_for_hash(item_hash)}/{storage_id}{ext}"

DEFAULT_ALLOWED_MIMES = {
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/webp',
    'video/mp4',
    'video/webm',
    'video/ogg'
}


def setup_directories(ctx: WorkspaceContext | None = None):
    runtime = _ctx(ctx)
    vault = runtime.active_vault

    for directory in [
        vault.input_dir,
        vault.review_dir,
        vault.local_ingest_dir,
        vault.online_ingest_dir,
        vault.queues_dir,
        vault.batches_dir,
        runtime.models_dir,
        vault.wd_tags_dir,
        vault.thumbnails_dir,
        runtime.topics_dir,
        vault.vault_dir,
        vault.assets_dir,
        vault.notes_dir,
        vault.db_path.parent,
        vault.logs_dir,
        runtime.secrets_dir,
    ]:
        directory.mkdir(parents=True, exist_ok=True)

def note_path_for(file_hash: str, storage_id: str, ctx: WorkspaceContext | None = None) -> Path:

    storage_id = require_storage_id(storage_id)
    return _ctx(ctx).active_vault.notes_dir / storage_shard_for_hash(file_hash) / f"{storage_id}.md"

def wd_tag_cache_path_for(file_hash: str, storage_id: str, ctx: WorkspaceContext | None = None) -> Path:

    storage_id = require_storage_id(storage_id)
    return _ctx(ctx).active_vault.wd_tags_dir / storage_shard_for_hash(file_hash) / f"{storage_id}.json"

def validate_config_schema(config: dict):

    errors = []

    if not isinstance(config, dict):
        raise ValueError("config.yaml must be a dictionary")

    if 'paths' in config:
        if not isinstance(config['paths'], dict):
            errors.append("Key 'paths' must be a dictionary")
        else:
            for key in ['secrets', 'models']:
                if key in config['paths'] and not isinstance(config['paths'][key], str):
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
    if not isinstance(config.get('vaults'), dict) or not config.get('vaults'):
        errors.append("Missing mandatory section: 'vaults'")
    if not isinstance(config.get('active_vault'), str) or not config.get('active_vault').strip():
        errors.append("Missing mandatory key: 'active_vault'")

    if errors:
        raise ValueError("Configuration Error in config.yaml: " + "; ".join(errors))

def load_secrets(ctx: WorkspaceContext | None = None) -> dict:

    secrets_path = _ctx(ctx).secrets_dir / ".secrets.yaml"
    if not secrets_path.exists():
        return {}
    try:
        with open(secrets_path, 'r', encoding='utf-8') as f:
            secrets = yaml.safe_load(f)
            return secrets if isinstance(secrets, dict) else {}
    except Exception:
        return {}

def _default_config(ctx: WorkspaceContext | None = None) -> dict:
    runtime = _ctx(ctx)
    vault = runtime.active_vault
    return {
        'paths': {
            'secrets': str(runtime.secrets_dir),
            'models': str(runtime.models_dir),
        },
        'active_vault': vault.id or 'default',
        'vaults': {
            vault.id or 'default': {
                'name': vault.name or 'Default',
                'root': str(vault.root or (runtime.root / 'data' / 'vaults' / 'default')),
            }
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

def _secrets_path(ctx: WorkspaceContext | None = None) -> Path:
    return _ctx(ctx).secrets_dir / ".secrets.yaml"

def _config_mtimes(ctx: WorkspaceContext | None = None) -> tuple[Path, Path, float | None, float | None]:
    runtime = _ctx(ctx)
    config_mtime = runtime.config_path.stat().st_mtime if runtime.config_path.exists() else None
    secrets_path = _secrets_path(runtime)
    secrets_mtime = secrets_path.stat().st_mtime if secrets_path.exists() else None
    return runtime.config_path, secrets_path, config_mtime, secrets_mtime

def invalidate_config_cache():
    global _CONFIG_CACHE_DATA, _CONFIG_CACHE_MTIMES
    with _CONFIG_CACHE_LOCK:
        _CONFIG_CACHE_DATA = None
        _CONFIG_CACHE_MTIMES = None

def _load_config_uncached(ctx: WorkspaceContext | None = None) -> dict:
    runtime = _ctx(ctx)
    try:
        with open(runtime.config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            validate_config_schema(config)

            secrets = load_secrets(runtime)
            if secrets:
                if 'external_tools' not in config:
                    config['external_tools'] = {}
                config['external_tools'].update(secrets)
            return config
    except FileNotFoundError:
        return _default_config(runtime)

def get_config(ctx: WorkspaceContext | None = None) -> dict:
    global _CONFIG_CACHE_DATA, _CONFIG_CACHE_MTIMES
    runtime = _ctx(ctx)
    mtimes = _config_mtimes(runtime)
    with _CONFIG_CACHE_LOCK:
        if _CONFIG_CACHE_DATA is not None and _CONFIG_CACHE_MTIMES == mtimes:
            return copy.deepcopy(_CONFIG_CACHE_DATA)

    config = _load_config_uncached() if ctx is None else _load_config_uncached(runtime)
    refreshed_mtimes = _config_mtimes(runtime)
    with _CONFIG_CACHE_LOCK:
        _CONFIG_CACHE_DATA = config
        _CONFIG_CACHE_MTIMES = refreshed_mtimes
    return copy.deepcopy(config)

def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

def utc_now_str() -> str:
    return utc_now().strftime("%Y-%m-%d %H:%M:%S")

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

        with Image.open(filepath) as raw_img:
            img = flatten_image(raw_img, bg_color) if do_flatten else raw_img
            try:
                hash_obj = imagehash.phash(img)
                return str(hash_obj)
            finally:
                if img is not raw_img:
                    img.close()
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

def resolve_config_path(path_str: str) -> Path:

    path = Path(path_str)
    if not path.is_absolute():
        path = CONFIG_ROOT / path
    return path.resolve()

def get_configured_cookie_path() -> Optional[Path]:

    config = get_config()
    cookie_str = config.get('external_tools', {}).get('cookies_path')

    if not cookie_str:
        return None

    return resolve_config_path(cookie_str)

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
