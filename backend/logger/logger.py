import logging
from logging.handlers import RotatingFileHandler
import json
import datetime
from pathlib import Path
from utils import OUTPUT_DIR, LOGS_DIR

STRUCTURED_LOGS_DIR = LOGS_DIR / "structured"
STRUCTURED_LOGS_DIR.mkdir(parents=True, exist_ok=True)
RAW_LOGS_DIR = LOGS_DIR / "raw"
RAW_LOGS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

class JSONFormatter(logging.Formatter):
    def format(self, record):
        module_name = record.name.replace('lmz_', '') if record.name.startswith('lmz_') else record.name
        log_record = {
            "timestamp": datetime.datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S"),
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

# 1. System Logger (The Brain / FastAPI)
system_logger = logging.getLogger("lmz_system")
system_logger.setLevel(logging.INFO)
sys_handler = RotatingFileHandler(STRUCTURED_LOGS_DIR / "system.jsonl", maxBytes=5*1024*1024, backupCount=2, encoding="utf-8")
sys_handler.setFormatter(JSONFormatter())
if not system_logger.handlers: system_logger.addHandler(sys_handler)

# 2. Svelte Logger (The Face / JS Frontend)
svelte_logger = logging.getLogger("lmz_svelte")
svelte_logger.setLevel(logging.INFO)
svelte_handler = RotatingFileHandler(STRUCTURED_LOGS_DIR / "svelte.jsonl", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
svelte_handler.setFormatter(JSONFormatter())
if not svelte_logger.handlers: svelte_logger.addHandler(svelte_handler)

# 4. Ingestion Loggers (Worker)
ingest_local_logger = logging.getLogger("lmz_ingest_local")
ingest_local_logger.setLevel(logging.INFO)
ingest_local_handler = RotatingFileHandler(STRUCTURED_LOGS_DIR / "ingest_local.jsonl", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
ingest_local_handler.setFormatter(JSONFormatter())
if not ingest_local_logger.handlers: ingest_local_logger.addHandler(ingest_local_handler)

ingest_online_logger = logging.getLogger("lmz_ingest_online")
ingest_online_logger.setLevel(logging.INFO)
ingest_online_handler = RotatingFileHandler(STRUCTURED_LOGS_DIR / "ingest_online.jsonl", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
ingest_online_handler.setFormatter(JSONFormatter())
if not ingest_online_logger.handlers: ingest_online_logger.addHandler(ingest_online_handler)

# 5. Auth / credential status logger
auth_logger = logging.getLogger("lmz_auth")
auth_logger.setLevel(logging.INFO)
auth_handler = RotatingFileHandler(STRUCTURED_LOGS_DIR / "auth.jsonl", maxBytes=2*1024*1024, backupCount=2, encoding="utf-8")
auth_handler.setFormatter(JSONFormatter())
if not auth_logger.handlers: auth_logger.addHandler(auth_handler)

# 6. Review workflow logger
review_logger = logging.getLogger("lmz_review")
review_logger.setLevel(logging.INFO)
review_handler = RotatingFileHandler(STRUCTURED_LOGS_DIR / "review.jsonl", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
review_handler.setFormatter(JSONFormatter())
if not review_logger.handlers: review_logger.addHandler(review_handler)

# --- Helper Functions ---

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

def log_ingestion(level, message, **kwargs):
    _log(ingest_online_logger, level, message, **kwargs)

def log_ingest_local(level, message, **kwargs):
    _log(ingest_local_logger, level, message, **kwargs)

def log_ingest_online(level, message, **kwargs):
    _log(ingest_online_logger, level, message, **kwargs)

def log_auth(level, message, **kwargs):
    _log(auth_logger, level, message, **kwargs)

def log_review(level, message, **kwargs):
    _log(review_logger, level, message, **kwargs)
    if str(level or "").upper() in {"WARNING", "ERROR", "CRITICAL"}:
        _log(system_logger, level, message, **kwargs)

# activity logging remains unchanged
activity_logger = logging.getLogger("lmz_activity")
activity_logger.setLevel(logging.INFO)
# Canonical ingestion audit stream
act_handler = RotatingFileHandler(STRUCTURED_LOGS_DIR / "ingestion_audit.jsonl", maxBytes=5*1024*1024, backupCount=2, encoding="utf-8")
act_handler.setFormatter(JSONFormatter())
if not activity_logger.handlers: activity_logger.addHandler(act_handler)

def log_activity(original_name, vault_id, platform, artist, source_url="", timestamp_str=None):
    if timestamp_str is None: timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    extra = {"original_name": original_name, "vault_id": vault_id, "platform": platform, "artist": artist, "source_url": source_url, "event_time": timestamp_str}
    activity_logger.info("Ingestion successful", extra={"extra_data": extra})
