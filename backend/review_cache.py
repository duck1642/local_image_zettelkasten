import json
import mimetypes
import threading
from pathlib import Path

from utils import REVIEW_DIR, get_config

REVIEW_RESOLVED_STATES = {"resolved_variant", "resolved_delete", "resolved_replace"}
REVIEW_PENDING_STATES = {"pending", "deferred"}
REVIEW_CLEANUP_STATES = {"pending_cleanup", "cleanup_failed"}
REVIEW_VISIBLE_STATES = REVIEW_PENDING_STATES | REVIEW_CLEANUP_STATES

_lock = threading.Lock()
_dirty = True
_entries: dict[str, dict] = {}
_hash_index: dict[str, dict] = {}
_counts = {"pending": 0, "cleanup": 0, "total": 0}


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


def _iter_review_media_files() -> list[Path]:
    if not REVIEW_DIR.exists():
        return []
    allowed = {
        f".{ext.lstrip('.').lower()}"
        for ext in get_config().get("firewall", {}).get("allowed_extensions", [])
    }
    return sorted(
        [
            p
            for p in REVIEW_DIR.iterdir()
            if p.is_file()
            and p.suffix.lower() not in [".json", ".md"]
            and (not allowed or p.suffix.lower() in allowed)
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


def _entry_for(path: Path, sidecar: dict | None = None) -> dict:
    sidecar = sidecar if isinstance(sidecar, dict) else _read_sidecar(path)
    state = _normalize_review_state(str(sidecar.get("state") or "pending"))
    guessed, _ = mimetypes.guess_type(path.name)
    return {
        "path": path,
        "sidecar": sidecar,
        "state": state,
        "changed": False,
        "mime_type": guessed or "application/octet-stream",
        "extension": path.suffix.lower(),
    }


def _rebuild_unlocked():
    global _dirty, _entries, _hash_index, _counts
    entries = {}
    hash_index = {}
    pending = 0
    cleanup = 0
    for path in _iter_review_media_files():
        entry = _entry_for(path)
        entries[path.name] = entry
        state = entry["state"]
        if _is_pending_state(state):
            pending += 1
            file_hash = str(entry["sidecar"].get("file_hash") or "").strip()
            if file_hash:
                hash_index[file_hash] = entry
        elif _is_cleanup_state(state):
            cleanup += 1
    _entries = entries
    _hash_index = hash_index
    _counts = {"pending": pending, "cleanup": cleanup, "total": len(entries)}
    _dirty = False


def mark_review_cache_dirty():
    global _dirty
    with _lock:
        _dirty = True


def _ensure_unlocked():
    if _dirty:
        _rebuild_unlocked()


def review_counts(include_resolved: bool = False) -> dict:
    with _lock:
        _ensure_unlocked()
        pending = int(_counts.get("pending") or 0)
        cleanup = int(_counts.get("cleanup") or 0)
        if include_resolved:
            return {"count": pending, "pending": pending, "cleanup": cleanup, "total": int(_counts.get("total") or 0)}
        return {"count": pending, "pending": pending, "cleanup": cleanup}


def pending_review_match(file_hash: str) -> dict | None:
    clean_hash = str(file_hash or "").strip()
    if not clean_hash:
        return None
    with _lock:
        _ensure_unlocked()
        entry = _hash_index.get(clean_hash)
        if not entry:
            return None
        sidecar = entry["sidecar"]
        path = entry["path"]
        return {
            "filename": sidecar.get("storage_name") or path.name,
            "original_name": sidecar.get("original_name") or path.name,
            "state": entry["state"] or "pending",
        }


def replace_review_cache_entries(entries: list[dict]):
    global _dirty, _entries, _hash_index, _counts
    with _lock:
        mapped = {}
        hash_index = {}
        pending = 0
        cleanup = 0
        for entry in entries or []:
            path = entry.get("path")
            if not isinstance(path, Path):
                continue
            sidecar = entry.get("sidecar") if isinstance(entry.get("sidecar"), dict) else {}
            state = _normalize_review_state(entry.get("state"))
            cached = dict(entry)
            cached["state"] = state
            mapped[path.name] = cached
            if _is_pending_state(state):
                pending += 1
                file_hash = str(sidecar.get("file_hash") or "").strip()
                if file_hash:
                    hash_index[file_hash] = cached
            elif _is_cleanup_state(state):
                cleanup += 1
        _entries = mapped
        _hash_index = hash_index
        _counts = {"pending": pending, "cleanup": cleanup, "total": len(mapped)}
        _dirty = False


def upsert_review_cache_entry(path: Path, sidecar: dict):
    global _dirty, _counts
    if not isinstance(path, Path):
        return
    with _lock:
        if _dirty:
            return
        old = _entries.get(path.name)
        if old:
            old_hash = str(old.get("sidecar", {}).get("file_hash") or "").strip()
            if old_hash:
                _hash_index.pop(old_hash, None)
            old_state = old.get("state")
            if _is_pending_state(old_state):
                _counts["pending"] = max(0, _counts["pending"] - 1)
            elif _is_cleanup_state(old_state):
                _counts["cleanup"] = max(0, _counts["cleanup"] - 1)
        else:
            _counts["total"] += 1

        entry = _entry_for(path, sidecar)
        _entries[path.name] = entry
        state = entry["state"]
        if _is_pending_state(state):
            _counts["pending"] += 1
            file_hash = str(sidecar.get("file_hash") or "").strip()
            if file_hash:
                _hash_index[file_hash] = entry
        elif _is_cleanup_state(state):
            _counts["cleanup"] += 1


def remove_review_cache_entry(path: Path):
    global _dirty
    if not isinstance(path, Path):
        return
    with _lock:
        if _dirty:
            return
        entry = _entries.pop(path.name, None)
        if not entry:
            return
        file_hash = str(entry.get("sidecar", {}).get("file_hash") or "").strip()
        if file_hash:
            _hash_index.pop(file_hash, None)
        state = entry.get("state")
        if _is_pending_state(state):
            _counts["pending"] = max(0, _counts["pending"] - 1)
        elif _is_cleanup_state(state):
            _counts["cleanup"] = max(0, _counts["cleanup"] - 1)
        _counts["total"] = max(0, _counts["total"] - 1)
