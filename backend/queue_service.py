import re
import threading
from pathlib import Path

from runtime_context import WorkspaceContext, get_runtime_context
from utils import setup_directories


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


def _ctx(ctx: WorkspaceContext | None = None) -> WorkspaceContext:
    return ctx or get_runtime_context()


def queue_path(queue: str, ctx: WorkspaceContext | None = None) -> Path:
    if queue not in QUEUE_FILES:
        raise ValueError(f"invalid queue: {queue}")
    return _ctx(ctx).active_vault.queues_dir / QUEUE_FILES[queue]


def ensure_queue_files(ctx: WorkspaceContext | None = None):
    runtime = _ctx(ctx)
    with QUEUE_LOCK:
        setup_directories(runtime)
        defaults = {
            "normal": "# LMZ Normal Pending Links\n",
            "force": "# LMZ Force Pending Links\n",
            "failed": "# LMZ Failed Links Log\n",
        }
        for queue, text in defaults.items():
            path = queue_path(queue, runtime)
            if not path.exists():
                path.write_text(text, encoding="utf-8")


def read_queue(queue: str, ctx: WorkspaceContext | None = None) -> str:
    runtime = _ctx(ctx)
    with QUEUE_LOCK:
        ensure_queue_files(runtime)
        return queue_path(queue, runtime).read_text(encoding="utf-8", errors="replace")


def write_queue(queue: str, text: str, ctx: WorkspaceContext | None = None):
    runtime = _ctx(ctx)
    with QUEUE_LOCK:
        ensure_queue_files(runtime)
        queue_path(queue, runtime).write_text(text, encoding="utf-8")


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


def queue_counts(ctx: WorkspaceContext | None = None) -> dict[str, int]:
    runtime = _ctx(ctx)
    with QUEUE_LOCK:
        ensure_queue_files(runtime)
        return {
            queue: len(parse_urls(queue_path(queue, runtime).read_text(encoding="utf-8", errors="replace")))
            for queue in QUEUE_FILES
        }


def append_urls(queue: str, urls: list[str], ctx: WorkspaceContext | None = None):
    runtime = _ctx(ctx)
    with QUEUE_LOCK:
        ensure_queue_files(runtime)
        path = queue_path(queue, runtime)
        existing = path.read_text(encoding="utf-8", errors="replace").rstrip()
        lines = [clean_url(url) for url in urls if clean_url(url)]
        if not lines:
            return
        body = "\n".join(lines)
        path.write_text(f"{existing}\n\n{body}\n" if existing else f"{body}\n", encoding="utf-8")


def move_failed_urls(target_queue: str, ctx: WorkspaceContext | None = None) -> int:
    runtime = _ctx(ctx)
    with QUEUE_LOCK:
        if target_queue not in {"normal", "force"}:
            return 0
        ensure_queue_files(runtime)
        failed_path = queue_path("failed", runtime)
        failed_text = failed_path.read_text(encoding="utf-8", errors="replace")
        urls = parse_urls(failed_text)
        if not urls:
            return 0
        append_urls(target_queue, urls, runtime)
        failed_path.write_text("# LMZ Failed Links Log\n", encoding="utf-8")
        return len(urls)


def clear_failed(ctx: WorkspaceContext | None = None):
    write_queue("failed", "# LMZ Failed Links Log\n", ctx)


def run_queue(queue: str, ctx: WorkspaceContext | None = None) -> dict:
    if queue not in {"normal", "force"}:
        raise ValueError("failed queue cannot be started")
    from external_ingestion import ExternalIngestor

    path = queue_path(queue, ctx)
    skip_validation = queue == "force"
    ingestor = ExternalIngestor(str(path), skip_validation=skip_validation)
    return ingestor.run()
