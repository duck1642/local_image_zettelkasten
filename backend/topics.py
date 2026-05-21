import os
import re
from pathlib import Path

import yaml

from runtime_context import WorkspaceContext, get_runtime_context
from utils import atomic_write_text, utc_now_str


MARKDOWN_LINK_RE = re.compile(r"^\s*\[([^\]]+)\]\(([^)]+)\)\s*$")


def slugify_topic_label(label: str) -> str:
    value = str(label or "").strip()
    cleaned = "".join(ch.casefold() if ch.isalnum() else "_" for ch in value)
    slug = "_".join(part for part in cleaned.split("_") if part)
    return slug or "topic"


def _topics_dir(ctx: WorkspaceContext | None = None) -> Path:
    return (ctx or get_runtime_context()).topics_dir


def topic_file_path_for_label(label: str, ctx: WorkspaceContext | None = None) -> Path:
    return _topics_dir(ctx) / f"{slugify_topic_label(label)}.md"


def rename_topic(old_label: str, new_label: str, ctx: WorkspaceContext | None = None) -> dict:
    clean_old = str(old_label or "").strip()
    clean_new = str(new_label or "").strip()
    if not clean_old:
        raise ValueError("old topic label is required")
    if not clean_new:
        raise ValueError("new topic label is required")
    old_path = topic_file_path_for_label(old_label, ctx).resolve()
    new_path = topic_file_path_for_label(new_label, ctx).resolve()
    topics_root = _topics_dir(ctx).resolve()
    if old_path.parent != topics_root or new_path.parent != topics_root:
        raise ValueError("topic path must stay inside topic root")
    if not old_path.exists():
        raise FileNotFoundError(f"topic not found: {old_path.name}")
    if old_path == new_path:
        return {"old_path": old_path, "new_path": new_path, "renamed": False}
    if new_path.exists():
        raise FileExistsError(f"topic already exists: {new_path.name}")
    new_path.parent.mkdir(parents=True, exist_ok=True)
    old_path.rename(new_path)
    return {"old_path": old_path, "new_path": new_path, "renamed": True}


def _frontmatter_bounds(text: str) -> tuple[int, int] | None:
    stripped = text.lstrip("\ufeff")
    offset = len(text) - len(stripped)
    if not stripped.startswith("---"):
        return None
    lines = stripped.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None
    cursor = offset + len(lines[0])
    for line in lines[1:]:
        next_cursor = cursor + len(line)
        if line.strip() == "---":
            return offset, next_cursor
        cursor = next_cursor
    return None


def write_topic_frontmatter_preserving_body(path: Path, frontmatter: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    fm_text = f"---\n{yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)}---\n"
    if not path.exists():
        atomic_write_text(path, fm_text + "\n")
        return
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    bounds = _frontmatter_bounds(text)
    if bounds is None:
        atomic_write_text(path, fm_text + "\n" + text)
        return
    start, end = bounds
    atomic_write_text(path, fm_text + text[end:])


def ensure_topic_file(label: str, ctx: WorkspaceContext | None = None) -> Path:
    path = topic_file_path_for_label(label, ctx)
    if path.exists():
        return path
    timestamp = utc_now_str()
    write_topic_frontmatter_preserving_body(
        path,
        {
            "created_at": timestamp,
            "updated_at": timestamp,
            "aliases": [],
        },
    )
    return path


def _relative_link(from_path: Path, to_path: Path) -> str:
    rel = os.path.relpath(to_path.resolve(), from_path.parent.resolve())
    return rel.replace("\\", "/")


def topic_markdown_link(label: str, note_path: Path, ctx: WorkspaceContext | None = None) -> str:
    topic_path = ensure_topic_file(label, ctx)
    display = topic_path.stem
    return f"[{display}]({_relative_link(note_path, topic_path)})"


def format_topics_for_note(topics, note_path: Path, ctx: WorkspaceContext | None = None) -> list[str]:
    from md_generator import normalize_topic_list

    formatted: list[str] = []
    seen: set[str] = set()
    for topic in normalize_topic_list(topics):
        entry = parse_topic_value(topic, note_path, ctx)
        label = entry["label"] or topic
        link = topic_markdown_link(label, note_path, ctx)
        key = link.casefold()
        if key not in seen:
            seen.add(key)
            formatted.append(link)
    return formatted


def parse_topic_value(raw_value: str, note_path: Path | None = None, ctx: WorkspaceContext | None = None) -> dict:
    raw = str(raw_value or "").strip()
    match = MARKDOWN_LINK_RE.match(raw)
    if not match:
        label = raw
        return {
            "raw": raw,
            "label": label,
            "topic_rel": "",
            "topic_key": f"plain:{label.casefold()}",
        }

    link_label = match.group(1).strip()
    target = match.group(2).strip()
    target_path = Path(target)
    if not target_path.is_absolute() and note_path is not None:
        target_path = note_path.parent / target_path
    target_path = target_path.resolve()

    topic_rel = ""
    try:
        topic_rel = target_path.relative_to(_topics_dir(ctx)).as_posix()
    except ValueError:
        pass

    label = target_path.stem if topic_rel else link_label
    return {
        "raw": raw,
        "label": label,
        "topic_rel": topic_rel,
        "topic_key": f"rel:{topic_rel.casefold()}" if topic_rel else f"plain:{label.casefold()}",
    }


def parse_topic_values(raw_values, note_path: Path | None = None, ctx: WorkspaceContext | None = None) -> list[dict]:
    from md_generator import normalize_topic_list

    entries: list[dict] = []
    seen: set[str] = set()
    for raw in normalize_topic_list(raw_values):
        entry = parse_topic_value(raw, note_path, ctx)
        key = entry["topic_key"]
        if entry["label"] and key not in seen:
            seen.add(key)
            entries.append(entry)
    return entries
