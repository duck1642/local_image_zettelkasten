import re
import threading
from pathlib import Path

from external_ingestion import ExternalIngestor
from utils import QUEUES_DIR, setup_directories


QUEUE_FILES = {
    "normal": "normal_pending_links.md",
    "force": "force_pending_links.md",
    "failed": "failed_links.md",
}

QUEUE_LABELS = {
    "normal": "Normal",
    "force": "Force",
    "failed": "Failed",
}

INGESTION_LOCK = threading.Lock()
QUEUE_LOCK = threading.RLock()


def queue_path(queue: str) -> Path:
    if queue not in QUEUE_FILES:
        raise ValueError(f"invalid queue: {queue}")
    return QUEUES_DIR / QUEUE_FILES[queue]


def ensure_queue_files():
    with QUEUE_LOCK:
        setup_directories()
        defaults = {
            "normal": "# LIZ Normal Pending Links\n",
            "force": "# LIZ Force Pending Links\n",
            "failed": "# LIZ Failed Links Log\n",
        }
        for queue, text in defaults.items():
            path = queue_path(queue)
            if not path.exists():
                path.write_text(text, encoding="utf-8")


def read_queue(queue: str) -> str:
    with QUEUE_LOCK:
        ensure_queue_files()
        return queue_path(queue).read_text(encoding="utf-8", errors="replace")


def write_queue(queue: str, text: str):
    with QUEUE_LOCK:
        ensure_queue_files()
        queue_path(queue).write_text(text, encoding="utf-8")


def parse_urls(text: str) -> list[str]:
    urls = []
    md_link_pattern = re.compile(r'\[.*?\]\((https?://.*?)\)')
    bare_pattern = re.compile(r'(https?://\S+)')
    for line in text.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        md_match = md_link_pattern.search(raw)
        if md_match:
            urls.append(clean_url(md_match.group(1)))
            continue
        bare_match = bare_pattern.search(raw)
        if bare_match:
            urls.append(clean_url(bare_match.group(1)))
    return [url for url in urls if url]


def clean_url(url: str) -> str:
    return url.strip().rstrip(").,;")


def queue_counts() -> dict[str, int]:
    with QUEUE_LOCK:
        ensure_queue_files()
        return {
            queue: len(parse_urls(queue_path(queue).read_text(encoding="utf-8", errors="replace")))
            for queue in QUEUE_FILES
        }


def append_urls(queue: str, urls: list[str]):
    with QUEUE_LOCK:
        ensure_queue_files()
        existing = queue_path(queue).read_text(encoding="utf-8", errors="replace").rstrip()
        lines = [clean_url(url) for url in urls if clean_url(url)]
        if not lines:
            return
        body = "\n".join(lines)
        queue_path(queue).write_text(f"{existing}\n\n{body}\n" if existing else f"{body}\n", encoding="utf-8")


def move_failed_urls(target_queue: str) -> int:
    with QUEUE_LOCK:
        if target_queue not in {"normal", "force"}:
            return 0
        ensure_queue_files()
        failed_text = queue_path("failed").read_text(encoding="utf-8", errors="replace")
        urls = parse_urls(failed_text)
        if not urls:
            return 0
        append_urls(target_queue, urls)
        queue_path("failed").write_text("# LIZ Failed Links Log\n", encoding="utf-8")
        return len(urls)


def clear_failed():
    write_queue("failed", "# LIZ Failed Links Log\n")


def run_queue(queue: str) -> dict:
    if queue not in {"normal", "force"}:
        raise ValueError("failed queue cannot be started")
    path = queue_path(queue)
    skip_validation = queue == "force"
    ingestor = ExternalIngestor(str(path), skip_validation=skip_validation)
    return ingestor.run()
