import json
import mimetypes
import threading
from dataclasses import dataclass, field
from pathlib import Path

from runtime_context import WorkspaceContext, get_runtime_context
from utils import get_config

REVIEW_RESOLVED_STATES = {"resolved_variant", "resolved_delete", "resolved_replace"}
REVIEW_PENDING_STATES = {"pending", "deferred"}
REVIEW_CLEANUP_STATES = {"pending_cleanup", "cleanup_failed"}
REVIEW_VISIBLE_STATES = REVIEW_PENDING_STATES | REVIEW_CLEANUP_STATES


@dataclass
class _ReviewCacheState:
    dirty: bool = True
    entries: dict[str, dict] = field(default_factory=dict)
    hash_index: dict[str, dict] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=lambda: {"pending": 0, "cleanup": 0, "total": 0})


_lock = threading.Lock()
_states: dict[Path, _ReviewCacheState] = {}


def _ctx(ctx: WorkspaceContext | None = None) -> WorkspaceContext:
    return ctx or get_runtime_context()


def _review_dir(ctx: WorkspaceContext | None = None) -> Path:
    return _ctx(ctx).active_vault.review_dir.resolve()


def _state_for(ctx: WorkspaceContext | None = None) -> _ReviewCacheState:
    root = _review_dir(ctx)
    state = _states.get(root)
    if state is None:
        state = _ReviewCacheState()
        _states[root] = state
    return state


def reset_review_cache(ctx: WorkspaceContext | None = None):
    with _lock:
        _states.pop(_review_dir(ctx), None)


def _normalize_review_state(state: str | None) -> str:
    clean = str(state or "").strip()
    if clean == "cleanup_failed":
        return "pending_cleanup"
    if clean in REVIEW_RESOLVED_STATES or clean in REVIEW_PENDING_STATES or clean == "pending_cleanup":
        return clean
    return "pending"


def _is_pending_state(state: str | None) -> bool:
    return _normalize_review_state(state) in REVIEW_PENDING_STATES


def _is_cleanup_state(state: str | None) -> bool:
    return _normalize_review_state(state) == "pending_cleanup"


def _iter_review_media_files(ctx: WorkspaceContext | None = None) -> list[Path]:
    review_dir = _review_dir(ctx)
    if not review_dir.exists():
        return []
    return sorted(
        [
            p
            for p in review_dir.iterdir()
            if p.is_file()
            and p.suffix.lower() not in [".json", ".md"]
        ]
    )


def _read_sidecar(path: Path) -> dict:
    sidecar_path = path.with_suffix(path.suffix + ".json")
    if not sidecar_path.exists():
        return {}
    try:
        data = json.loads(sidecar_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _entry_for(path: Path, sidecar: dict | None = None, ctx: WorkspaceContext | None = None) -> dict:
    sidecar = sidecar if isinstance(sidecar, dict) else _read_sidecar(path)
    state = _normalize_review_state(str(sidecar.get("state") or "pending"))
    if state in REVIEW_RESOLVED_STATES:
        state = "pending_cleanup"
    guessed, _ = mimetypes.guess_type(path.name)
    allowed = {
        f".{ext.lstrip('.').lower()}"
        for ext in get_config(ctx).get("firewall", {}).get("allowed_extensions", [])
    }
    validation_warning = ""
    ext = path.suffix.lower()
    if allowed and ext not in allowed:
        validation_warning = f"File extension '{ext}' violates firewall allowed extensions."
    return {
        "path": path,
        "sidecar": sidecar,
        "state": state,
        "changed": False,
        "mime_type": guessed or "application/octet-stream",
        "extension": ext,
        "validation_warning": validation_warning,
    }


def _rebuild_unlocked(state: _ReviewCacheState, ctx: WorkspaceContext | None = None):
    entries = {}
    hash_index = {}
    pending = 0
    cleanup = 0
    for path in _iter_review_media_files(ctx):
        entry = _entry_for(path, ctx=ctx)
        entries[path.name] = entry
        entry_state = entry["state"]
        if _is_pending_state(entry_state):
            pending += 1
            file_hash = str(entry["sidecar"].get("file_hash") or "").strip()
            if file_hash:
                hash_index[file_hash] = entry
        elif _is_cleanup_state(entry_state):
            cleanup += 1
    state.entries = entries
    state.hash_index = hash_index
    state.counts = {"pending": pending, "cleanup": cleanup, "total": len(entries)}
    state.dirty = False


def mark_review_cache_dirty(ctx: WorkspaceContext | None = None):
    with _lock:
        _state_for(ctx).dirty = True


def _ensure_unlocked(state: _ReviewCacheState, ctx: WorkspaceContext | None = None):
    if state.dirty:
        _rebuild_unlocked(state, ctx)


def review_counts(include_resolved: bool = False, ctx: WorkspaceContext | None = None) -> dict:
    with _lock:
        state = _state_for(ctx)
        _ensure_unlocked(state, ctx)
        pending = int(state.counts.get("pending") or 0)
        cleanup = int(state.counts.get("cleanup") or 0)
        if include_resolved:
            return {"count": pending, "pending": pending, "cleanup": cleanup, "total": int(state.counts.get("total") or 0)}
        return {"count": pending, "pending": pending, "cleanup": cleanup}


def pending_review_match(file_hash: str, ctx: WorkspaceContext | None = None) -> dict | None:
    clean_hash = str(file_hash or "").strip()
    if not clean_hash:
        return None
    with _lock:
        state = _state_for(ctx)
        _ensure_unlocked(state, ctx)
        entry = state.hash_index.get(clean_hash)
        if not entry:
            return None
        sidecar = entry["sidecar"]
        path = entry["path"]
        return {
            "filename": sidecar.get("storage_name") or path.name,
            "original_name": sidecar.get("original_name") or path.name,
            "state": entry["state"] or "pending",
            "file_hash": clean_hash,
        }


def replace_review_cache_entries(entries: list[dict], ctx: WorkspaceContext | None = None):
    with _lock:
        state = _state_for(ctx)
        mapped = {}
        hash_index = {}
        pending = 0
        cleanup = 0
        for entry in entries or []:
            path = entry.get("path")
            if not isinstance(path, Path):
                continue
            sidecar = entry.get("sidecar") if isinstance(entry.get("sidecar"), dict) else {}
            entry_state = _normalize_review_state(entry.get("state"))
            cached = dict(entry)
            cached["state"] = entry_state
            mapped[path.name] = cached
            if _is_pending_state(entry_state):
                pending += 1
                file_hash = str(sidecar.get("file_hash") or "").strip()
                if file_hash:
                    hash_index[file_hash] = cached
            elif _is_cleanup_state(entry_state):
                cleanup += 1
        state.entries = mapped
        state.hash_index = hash_index
        state.counts = {"pending": pending, "cleanup": cleanup, "total": len(mapped)}
        state.dirty = False


def upsert_review_cache_entry(path: Path, sidecar: dict, ctx: WorkspaceContext | None = None):
    if not isinstance(path, Path):
        return
    with _lock:
        state = _state_for(ctx)
        if state.dirty:
            return
        old = state.entries.get(path.name)
        if old:
            old_hash = str(old.get("sidecar", {}).get("file_hash") or "").strip()
            if old_hash:
                state.hash_index.pop(old_hash, None)
            old_state = old.get("state")
            if _is_pending_state(old_state):
                state.counts["pending"] = max(0, state.counts["pending"] - 1)
            elif _is_cleanup_state(old_state):
                state.counts["cleanup"] = max(0, state.counts["cleanup"] - 1)
        else:
            state.counts["total"] += 1

        entry = _entry_for(path, sidecar, ctx=ctx)
        state.entries[path.name] = entry
        entry_state = entry["state"]
        if _is_pending_state(entry_state):
            state.counts["pending"] += 1
            file_hash = str(sidecar.get("file_hash") or "").strip()
            if file_hash:
                state.hash_index[file_hash] = entry
        elif _is_cleanup_state(entry_state):
            state.counts["cleanup"] += 1


def remove_review_cache_entry(path: Path, ctx: WorkspaceContext | None = None):
    if not isinstance(path, Path):
        return
    with _lock:
        state = _state_for(ctx)
        if state.dirty:
            return
        entry = state.entries.pop(path.name, None)
        if not entry:
            return
        file_hash = str(entry.get("sidecar", {}).get("file_hash") or "").strip()
        if file_hash:
            state.hash_index.pop(file_hash, None)
        entry_state = entry.get("state")
        if _is_pending_state(entry_state):
            state.counts["pending"] = max(0, state.counts["pending"] - 1)
        elif _is_cleanup_state(entry_state):
            state.counts["cleanup"] = max(0, state.counts["cleanup"] - 1)
        state.counts["total"] = max(0, state.counts["total"] - 1)
