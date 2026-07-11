import datetime
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from runtime_context import WorkspaceContext, get_runtime_context, try_get_runtime_context
from utils import get_app_settings, utc_now_str
from app_paths import get_app_paths

import sys
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
STARTUP_LOGS_DIR = get_app_paths().logs_dir / "startup"
RAW_LOGS_DIR = STARTUP_LOGS_DIR / "raw"
STRUCTURED_LOGS_DIR = STARTUP_LOGS_DIR / "structured"


class JSONFormatter(logging.Formatter):
    def format(self, record):
        module_name = record.name.replace('lmz_', '') if record.name.startswith('lmz_') else record.name
        log_record = {
            "timestamp": datetime.datetime.fromtimestamp(record.created, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "level": record.levelname,
            "module": module_name,
            "message": record.getMessage()
        }
        if hasattr(record, 'extra_data') and isinstance(record.extra_data, dict):
            for key, value in record.extra_data.items():
                safe_key = key if key not in log_record else f"extra_{key}"
                log_record[safe_key] = value
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)


system_logger = logging.getLogger("lmz_system")
svelte_logger = logging.getLogger("lmz_svelte")
ingest_local_logger = logging.getLogger("lmz_ingest_local")
ingest_online_logger = logging.getLogger("lmz_ingest_online")
auth_logger = logging.getLogger("lmz_auth")
review_logger = logging.getLogger("lmz_review")
activity_logger = logging.getLogger("lmz_activity")

_LOGGER_SPECS = {
    system_logger: ("system.jsonl", 5 * 1024 * 1024, 2),
    svelte_logger: ("svelte.jsonl", 5 * 1024 * 1024, 3),
    ingest_local_logger: ("ingest_local.jsonl", 5 * 1024 * 1024, 3),
    ingest_online_logger: ("ingest_online.jsonl", 5 * 1024 * 1024, 3),
    auth_logger: ("auth.jsonl", 2 * 1024 * 1024, 2),
    review_logger: ("review.jsonl", 5 * 1024 * 1024, 3),
    activity_logger: ("ingestion_audit.jsonl", 5 * 1024 * 1024, 2),
}


def startup_log_dirs() -> tuple[Path, Path]:
    return STARTUP_LOGS_DIR / "raw", STARTUP_LOGS_DIR / "structured"


def log_dirs(ctx: WorkspaceContext | None = None) -> tuple[Path, Path]:
    runtime = ctx or try_get_runtime_context()
    if runtime is None:
        return startup_log_dirs()
    if not runtime.active_vault.root.exists():
        return startup_log_dirs()
    logs_dir = runtime.active_vault.logs_dir
    return logs_dir / "raw", logs_dir / "structured"


def log_location(ctx: WorkspaceContext | None = None) -> dict:
    runtime = ctx or try_get_runtime_context()
    raw_dir, structured_dir = log_dirs(runtime)
    if runtime is None or not runtime.active_vault.root.exists():
        return {
            "mode": "startup",
            "label": "Startup logs",
            "raw_dir": str(raw_dir),
            "structured_dir": str(structured_dir),
            "vault": "",
        }
    return {
        "mode": "vault",
        "label": f"Vault logs: {runtime.active_vault.id}",
        "raw_dir": str(raw_dir),
        "structured_dir": str(structured_dir),
        "vault": runtime.active_vault.id,
    }


def _remove_owned_handlers(logger: logging.Logger):
    for handler in list(logger.handlers):
        if getattr(handler, "_lmz_owned", False):
            logger.removeHandler(handler)
            handler.close()


def configure_logging(ctx: WorkspaceContext | None = None, force: bool = False):
    global RAW_LOGS_DIR, STRUCTURED_LOGS_DIR

    formatter = JSONFormatter()
    runtime = ctx or try_get_runtime_context()
    level = getattr(logging, get_app_settings()["logging"]["level"])
    for logger, (filename, max_bytes, backup_count) in _LOGGER_SPECS.items():
        logger.setLevel(level)
        if force:
            _remove_owned_handlers(logger)
        if any(getattr(handler, "_lmz_owned", False) for handler in logger.handlers):
            continue
        RAW_LOGS_DIR, STRUCTURED_LOGS_DIR = log_dirs(runtime)
        RAW_LOGS_DIR.mkdir(parents=True, exist_ok=True)
        STRUCTURED_LOGS_DIR.mkdir(parents=True, exist_ok=True)
        if runtime is not None and runtime.active_vault.root.exists():
            runtime.active_vault.vault_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            STRUCTURED_LOGS_DIR / filename,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        handler.setFormatter(formatter)
        handler._lmz_owned = True
        logger.addHandler(handler)


def reconfigure_logging(ctx: WorkspaceContext | None = None):
    configure_logging(ctx, force=True)


def _log(logger, level, message, **kwargs):
    exc_info = kwargs.pop("exc_info", None)
    level_name = str(level or "INFO").upper()
    if level_name not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        level_name = "INFO"
        kwargs = {"invalid_level": level, **kwargs}
    logger.log(
        getattr(logging, level_name),
        message,
        extra={"extra_data": kwargs} if kwargs else {},
        exc_info=exc_info,
    )


def log_system(level, message, **kwargs):
    _log(system_logger, level, message, **kwargs)


def log_svelte(level, message, **kwargs):
    _log(svelte_logger, level, message, **kwargs)


def log_ingest_local(level, message, **kwargs):
    _log(ingest_local_logger, level, message, **kwargs)


def log_ingest_online(level, message, **kwargs):
    _log(ingest_online_logger, level, message, **kwargs)


def log_ingest_audit(level, message, **kwargs):
    _log(activity_logger, level, message, **kwargs)


def log_auth(level, message, **kwargs):
    _log(auth_logger, level, message, **kwargs)


def log_review(level, message, **kwargs):
    _log(review_logger, level, message, **kwargs)
    if str(level or "").upper() in {"WARNING", "ERROR", "CRITICAL"}:
        _log(system_logger, level, message, **kwargs)


def log_activity(
    original_name,
    vault_id,
    platform,
    artist,
    source_url="",
    timestamp_str=None,
    ingest_type="unknown",
    run_id="",
    status="success",
):
    if timestamp_str is None:
        timestamp_str = utc_now_str()
    extra = {
        "original_name": original_name,
        "vault_id": vault_id,
        "platform": platform,
        "artist": artist,
        "source_url": source_url,
        "event_time": timestamp_str,
        "ingest_type": ingest_type,
        "run_id": run_id,
        "status": status,
    }
    normalized_status = str(status or "unknown").lower()
    level = "INFO" if normalized_status == "success" else "ERROR"
    message = "Ingestion successful" if normalized_status == "success" else f"Ingestion {normalized_status}"
    _log(activity_logger, level, message, **extra)
