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

# 0. Compatibility definitions (Must be at the top)
def log_ui(level, message, **kwargs):
    # This will be properly linked once pyui_logger is defined below
    getattr(logging.getLogger("liz_pyui"), level.lower(), logging.info)(message, extra={"extra_data": kwargs} if kwargs else {})

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": datetime.datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S"),
            "level": record.levelname,
            "module": record.module,
            "message": record.getMessage()
        }
        if hasattr(record, 'extra_data') and isinstance(record.extra_data, dict):
            log_record.update(record.extra_data)
        return json.dumps(log_record)

# 1. System Logger (The Brain / FastAPI)
system_logger = logging.getLogger("liz_system")
system_logger.setLevel(logging.INFO)
sys_handler = RotatingFileHandler(STRUCTURED_LOGS_DIR / "system.jsonl", maxBytes=5*1024*1024, backupCount=2, encoding="utf-8")
sys_handler.setFormatter(JSONFormatter())
if not system_logger.handlers: system_logger.addHandler(sys_handler)

# 2. Svelte Logger (The Face / JS Frontend)
svelte_logger = logging.getLogger("liz_svelte")
svelte_logger.setLevel(logging.INFO)
svelte_handler = RotatingFileHandler(STRUCTURED_LOGS_DIR / "svelte.jsonl", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
svelte_handler.setFormatter(JSONFormatter())
if not svelte_logger.handlers: svelte_logger.addHandler(svelte_handler)

# 3. Legacy UI Logger (The Ghost / PyQt)
pyui_logger = logging.getLogger("liz_pyui")
pyui_logger.setLevel(logging.INFO)
pyui_handler = RotatingFileHandler(STRUCTURED_LOGS_DIR / "pyui.jsonl", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
pyui_handler.setFormatter(JSONFormatter())
if not pyui_logger.handlers: pyui_logger.addHandler(pyui_handler)

# 4. Ingestion Logger (The Worker)
ingestion_logger = logging.getLogger("liz_ingestion")
ingestion_logger.setLevel(logging.INFO)
ingestion_handler = RotatingFileHandler(STRUCTURED_LOGS_DIR / "ingestion.jsonl", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
ingestion_handler.setFormatter(JSONFormatter())
if not ingestion_logger.handlers: ingestion_logger.addHandler(ingestion_handler)

# --- Helper Functions ---

def log_system(level, message, **kwargs):
    getattr(system_logger, level.lower(), system_logger.info)(message, extra={"extra_data": kwargs} if kwargs else {})

def log_svelte(level, message, **kwargs):
    getattr(svelte_logger, level.lower(), svelte_logger.info)(message, extra={"extra_data": kwargs} if kwargs else {})

def log_pyui(level, message, **kwargs):
    log_ui(level, message, **kwargs)

def log_ingestion(level, message, **kwargs):
    extra = {"extra_data": kwargs} if kwargs else {}
    getattr(ingestion_logger, level.lower(), ingestion_logger.info)(message, extra=extra)
    getattr(system_logger, level.lower(), system_logger.info)(message, extra=extra)

# activity logging remains unchanged
activity_logger = logging.getLogger("liz_activity")
activity_logger.setLevel(logging.INFO)
# Also move activity.jsonl to structured folder to be accessible seamlessly
act_handler = RotatingFileHandler(STRUCTURED_LOGS_DIR / "activity.jsonl", maxBytes=5*1024*1024, backupCount=2, encoding="utf-8")
act_handler.setFormatter(JSONFormatter())
if not activity_logger.handlers: activity_logger.addHandler(act_handler)

def log_activity(original_name, vault_id, platform, artist, source_url="", timestamp_str=None):
    if timestamp_str is None: timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    extra = {"original_name": original_name, "vault_id": vault_id, "platform": platform, "artist": artist, "source_url": source_url, "event_time": timestamp_str}
    activity_logger.info("Ingestion successful", extra={"extra_data": extra})
