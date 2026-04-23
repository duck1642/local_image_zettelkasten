
import logging
from logging.handlers import RotatingFileHandler
import json
import datetime
import threading
from pathlib import Path
from utils import OUTPUT_DIR, LOGS_DIR


LOG_LOCK = threading.Lock()


LOGS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

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


system_logger = logging.getLogger("liz_system")
system_logger.setLevel(logging.INFO)
sys_handler = RotatingFileHandler(LOGS_DIR / "system.log", maxBytes=5*1024*1024, backupCount=2, encoding="utf-8")
sys_handler.setFormatter(JSONFormatter())
if not system_logger.handlers:
    system_logger.addHandler(sys_handler)


activity_logger = logging.getLogger("liz_activity")
activity_logger.setLevel(logging.INFO)
act_handler = RotatingFileHandler(OUTPUT_DIR / "activity.jsonl", maxBytes=5*1024*1024, backupCount=2, encoding="utf-8")
act_handler.setFormatter(JSONFormatter())
if not activity_logger.handlers:
    activity_logger.addHandler(act_handler)


ui_logger = logging.getLogger("liz_ui")
ui_logger.setLevel(logging.INFO)
ui_handler = RotatingFileHandler(LOGS_DIR / "ui.log", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
ui_handler.setFormatter(JSONFormatter())
if not ui_logger.handlers:
    ui_logger.addHandler(ui_handler)

def log_system(level: str, message: str, **kwargs):

    with LOG_LOCK:
        extra = {"extra_data": kwargs} if kwargs else {}
        level_upper = level.upper()

        if level_upper == "INFO":
            system_logger.info(message, extra=extra)
        elif level_upper == "WARNING":
            system_logger.warning(message, extra=extra)
        elif level_upper == "ERROR":
            system_logger.error(message, extra=extra)

def log_ui(level: str, message: str, **kwargs):

    with LOG_LOCK:
        extra = {"extra_data": kwargs} if kwargs else {}
        level_upper = level.upper()

        if level_upper == "INFO":
            ui_logger.info(message, extra=extra)
        elif level_upper == "WARNING":
            ui_logger.warning(message, extra=extra)
        elif level_upper == "ERROR":
            ui_logger.error(message, extra=extra)

def log_activity(original_name: str, vault_id: str, platform: str, artist: str, source_url: str = "", timestamp_str: str = None):

    with LOG_LOCK:
        if timestamp_str is None:
            timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        extra = {
            "original_name": original_name,
            "vault_id": vault_id,
            "platform": platform,
            "artist": artist,
            "source_url": source_url,
            "event_time": timestamp_str
        }

        activity_logger.info("Ingestion successful", extra={"extra_data": extra})

def get_recent_activity(limit: int = 10) -> list[str]:

    with LOG_LOCK:
        log_file = OUTPUT_DIR / "activity.jsonl"

        if not log_file.exists():

            old_log = OUTPUT_DIR / "activity.log"
            if old_log.exists():
                with open(old_log, "r", encoding="utf-8") as f:
                    return f.readlines()[-limit:]
            return ["No activity logged yet."]

        lines = []
        with open(log_file, "r", encoding="utf-8") as f:
            recent = f.readlines()[-limit:]

            for line in recent:
                try:
                    data = json.loads(line)
                    ts = data.get("event_time", data.get("timestamp", ""))
                    plat = data.get("platform", "Unknown")
                    art = data.get("artist", "Unknown")
                    vid = data.get("vault_id", "")
                    orig = data.get("original_name", "")
                    url = data.get("source_url", "")

                    url_str = f" | URL: {url}" if url else ""
                    formatted = f"[{ts}] [{plat:10}] Artist: {art:15} | ID: {vid} | Original: {orig}{url_str}\n"
                    lines.append(formatted)
                except json.JSONDecodeError:
                    lines.append(line)

        return lines
