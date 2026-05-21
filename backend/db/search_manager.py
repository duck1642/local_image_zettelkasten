
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple, Optional

from db.searchers import BKTreeSearcher, URLRegistry, VPTreeSearcher
from db.sqlite_operator import get_all_phashes, get_all_tiles, get_all_urls, get_all_video_signatures
from logger import log_system
from runtime_context import WorkspaceContext, get_runtime_context

def _cosine_dist(v1_bytes: bytes, v2_bytes: bytes) -> float:

    import numpy as np
    v1 = np.frombuffer(v1_bytes, dtype=np.float32)
    v2 = np.frombuffer(v2_bytes, dtype=np.float32)
    if len(v1) != len(v2) or len(v1) == 0:
        return 1.0
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 1.0

    sim = np.dot(v1, v2) / (norm1 * norm2)
    return 1.0 - float(sim)

def _hamming_dist_audio(fp1_bytes: bytes, fp2_bytes: bytes) -> float:

    from fingerprint import compare_audio_fingerprints
    sim = compare_audio_fingerprints(fp1_bytes, fp2_bytes)
    return 1.0 - float(sim)


@dataclass
class _SearchIndexState:
    global_tree: BKTreeSearcher = field(default_factory=BKTreeSearcher)
    tile_tree: BKTreeSearcher = field(default_factory=BKTreeSearcher)
    url_registry: URLRegistry = field(default_factory=URLRegistry)
    video_tree: VPTreeSearcher = field(default_factory=lambda: VPTreeSearcher(_cosine_dist))
    audio_tree: VPTreeSearcher = field(default_factory=lambda: VPTreeSearcher(_hamming_dist_audio))
    is_hydrated: bool = False
    sync_lock: threading.Lock = field(default_factory=threading.Lock)
    rebuild_lock: threading.Lock = field(default_factory=threading.Lock)

class SearchManager:

    _instance = None
    _lock = threading.Lock()
    VP_PENDING_REBUILD_THRESHOLD = 512

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SearchManager, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._states: dict[Path, _SearchIndexState] = {}
        self._states_lock = threading.Lock()
        self._initialized = True

    def _db_path_from_conn(self, conn: sqlite3.Connection) -> Path | None:
        try:
            rows = conn.execute("PRAGMA database_list").fetchall()
            for row in rows:
                if row[1] == "main" and row[2]:
                    return Path(row[2]).resolve()
        except Exception:
            return None
        return None

    def _state_key(self, ctx: WorkspaceContext | None = None, conn: sqlite3.Connection | None = None) -> Path:
        if ctx is not None:
            return ctx.active_vault.db_path.resolve()
        if conn is not None:
            db_path = self._db_path_from_conn(conn)
            if db_path is not None:
                return db_path
        return get_runtime_context().active_vault.db_path.resolve()

    def _state_for(self, ctx: WorkspaceContext | None = None, conn: sqlite3.Connection | None = None) -> _SearchIndexState:
        key = self._state_key(ctx, conn)
        with self._states_lock:
            state = self._states.get(key)
            if state is None:
                state = _SearchIndexState()
                self._states[key] = state
            return state

    def reset(self, ctx: WorkspaceContext | None = None):
        key = self._state_key(ctx)
        with self._states_lock:
            self._states.pop(key, None)

    def reset_all(self):
        with self._states_lock:
            self._states.clear()

    @property
    def global_tree(self):
        return self._state_for().global_tree

    @global_tree.setter
    def global_tree(self, value):
        self._state_for().global_tree = value

    @property
    def tile_tree(self):
        return self._state_for().tile_tree

    @tile_tree.setter
    def tile_tree(self, value):
        self._state_for().tile_tree = value

    @property
    def url_registry(self):
        return self._state_for().url_registry

    @url_registry.setter
    def url_registry(self, value):
        self._state_for().url_registry = value

    @property
    def video_tree(self):
        return self._state_for().video_tree

    @video_tree.setter
    def video_tree(self, value):
        self._state_for().video_tree = value

    @property
    def audio_tree(self):
        return self._state_for().audio_tree

    @audio_tree.setter
    def audio_tree(self, value):
        self._state_for().audio_tree = value

    @property
    def is_hydrated(self):
        return self._state_for().is_hydrated

    @is_hydrated.setter
    def is_hydrated(self, value):
        self._state_for().is_hydrated = bool(value)

    def hydrate(self, conn: sqlite3.Connection, ctx: WorkspaceContext | None = None):
        state = self._state_for(ctx, conn)

        with state.sync_lock:
            if state.is_hydrated:
                return

            log_system('INFO', "Hydrating RAM indexes from SQLite...")


            urls = get_all_urls(conn)
            for url in urls:
                state.url_registry.add(url)


            phashes = get_all_phashes(conn)
            for f_hash, phash in phashes:
                state.global_tree.add(f_hash, phash)


            tiles = get_all_tiles(conn)
            for parent_hash, _, tile_phash in tiles:
                state.tile_tree.add(parent_hash, tile_phash)


            v_sigs = get_all_video_signatures(conn)
            for f_hash, a_hash, v_emb in v_sigs:
                if a_hash:
                    state.audio_tree.add(f_hash, a_hash)
                if v_emb:
                    state.video_tree.add(f_hash, v_emb)


            self._rebuild_deferred_indexes_locked(state, "hydrate")

            state.is_hydrated = True
            log_system('INFO', f"Hydration complete: {len(urls)} URLs | {len(phashes)} Images | {len(v_sigs)} Videos indexed in RAM.")

    def query_image(self, phash: str, threshold: int = 5, ctx: WorkspaceContext | None = None) -> List[Tuple[str, int, str]]:
        state = self._state_for(ctx)

        with state.sync_lock:
            global_snapshot = state.global_tree.snapshot()
            tile_snapshot = state.tile_tree.snapshot()

        results = []
        global_matches = BKTreeSearcher.query_snapshot(global_snapshot, phash, threshold)
        for h, dist in global_matches:
            results.append((h, dist, "Global"))


        tile_matches = BKTreeSearcher.query_snapshot(tile_snapshot, phash, threshold)
        for h, dist in tile_matches:
            results.append((h, dist, "Fragment-to-Whole"))

        return results

    def query_video(self, audio_hash: bytes, visual_embedding: bytes, ai_threshold: float = 0.08, audio_threshold: float = 0.85, ctx: WorkspaceContext | None = None) -> List[Tuple[str, float, str]]:
        state = self._state_for(ctx)

        with state.sync_lock:
            audio_snapshot = state.audio_tree.snapshot()
            video_snapshot = state.video_tree.snapshot()

        results = []

        if audio_hash:

            dist_threshold = 1.0 - audio_threshold
            audio_matches = VPTreeSearcher.query_snapshot(audio_snapshot, audio_hash, dist_threshold)
            for f_hash, dist in audio_matches:
                similarity = 1.0 - dist
                results.append((f_hash, similarity, "Sonic"))


        if visual_embedding:
            ai_matches = VPTreeSearcher.query_snapshot(video_snapshot, visual_embedding, ai_threshold)
            for h, dist in ai_matches:
                similarity = 1.0 - dist
                results.append((h, similarity, "Semantic"))

        return results

    def url_exists(self, url: str, ctx: WorkspaceContext | None = None) -> bool:
        state = self._state_for(ctx)

        with state.sync_lock:
            return state.url_registry.exists(url)

    def query_global_only(self, phash: str, threshold: int = 5, ctx: WorkspaceContext | None = None) -> list:
        state = self._state_for(ctx)

        with state.sync_lock:
            snapshot = state.global_tree.snapshot()
        return BKTreeSearcher.query_snapshot(snapshot, phash, threshold)

    def update_indexes(self, file_hash: str, phash: Optional[str], url: Optional[str], tiles: List[Tuple[int, str]] = None, audio_hash: bytes = None, visual_embedding: bytes = None, ctx: WorkspaceContext | None = None):
        state = self._state_for(ctx)

        should_rebuild = False
        with state.sync_lock:
            self._update_indexes_unlocked(state, file_hash, phash, url, tiles, audio_hash, visual_embedding)
            if self._vp_pending_count_locked(state) >= self.VP_PENDING_REBUILD_THRESHOLD:
                should_rebuild = True
        if should_rebuild:
            self._rebuild_deferred_indexes("pending_threshold", ctx=ctx)

    def update_indexes_batch(self, items: list[dict], ctx: WorkspaceContext | None = None):

        if not items:
            return
        state = self._state_for(ctx)
        should_rebuild = False
        with state.sync_lock:
            for item in items:
                self._update_indexes_unlocked(
                    state,
                    item.get("file_hash"),
                    item.get("phash"),
                    item.get("url"),
                    item.get("tiles"),
                    item.get("audio_hash"),
                    item.get("visual_embedding"),
                )
            log_system("INFO", "RAM index batch update queued", count=len(items))
            should_rebuild = self._vp_pending_count_locked(state) > 0
        if should_rebuild:
            self._rebuild_deferred_indexes("batch_update", ctx=ctx)

    def remove_indexes_batch(self, items: list[dict], ctx: WorkspaceContext | None = None):

        hashes = {str(item.get("hash") or item.get("file_hash") or "").strip() for item in items or []}
        hashes.discard("")
        urls = [item.get("source_url") or item.get("url") for item in items or [] if item.get("source_url") or item.get("url")]
        if not hashes and not urls:
            return {"removed": 0}

        state = self._state_for(ctx)
        should_rebuild = False
        with state.sync_lock:
            global_stats = state.global_tree.remove_hashes(hashes)
            tile_stats = state.tile_tree.remove_hashes(hashes)
            audio_stats = state.audio_tree.remove_hashes(hashes)
            video_stats = state.video_tree.remove_hashes(hashes)
            for url in urls:
                state.url_registry.remove(url)
            should_rebuild = bool(audio_stats.get("deferred") or video_stats.get("deferred"))

        removed = sum(
            int(stats.get("removed") or 0)
            for stats in (global_stats, tile_stats, audio_stats, video_stats)
        )
        log_system(
            "INFO",
            "RAM indexes removed deleted items",
            hashes=len(hashes),
            urls=len(urls),
            removed=removed,
            global_removed=global_stats.get("removed", 0),
            tile_removed=tile_stats.get("removed", 0),
            audio_removed=audio_stats.get("removed", 0),
            video_removed=video_stats.get("removed", 0),
        )
        if should_rebuild:
            if ctx is None:
                self._rebuild_deferred_indexes_async("batch_remove")
            else:
                self._rebuild_deferred_indexes_async("batch_remove", ctx=ctx)
        return {
            "removed": removed,
            "hashes": len(hashes),
            "urls": len(urls),
            "global": global_stats,
            "tile": tile_stats,
            "audio": audio_stats,
            "video": video_stats,
        }

    def _rebuild_deferred_indexes_async(self, reason: str, ctx: WorkspaceContext | None = None):

        thread = threading.Thread(
            target=self._rebuild_deferred_indexes,
            args=(reason, ctx),
            name=f"lmz-vp-rebuild-{reason}",
            daemon=True,
        )
        thread.start()

    def rebuild_deferred_indexes(self, ctx: WorkspaceContext | None = None):

        self._rebuild_deferred_indexes("explicit", ctx=ctx)

    def _update_indexes_unlocked(self, state: _SearchIndexState, file_hash: str, phash: Optional[str], url: Optional[str], tiles: List[Tuple[int, str]] = None, audio_hash: bytes = None, visual_embedding: bytes = None):

        if url:
            state.url_registry.add(url)
        if phash:
            state.global_tree.add(file_hash, phash)
        if tiles:
            for _, tile_phash in tiles:
                state.tile_tree.add(file_hash, tile_phash)

        if audio_hash:
            state.audio_tree.add(file_hash, audio_hash)
        if visual_embedding:
            state.video_tree.add(file_hash, visual_embedding)

    def _vp_pending_count_locked(self, state: _SearchIndexState) -> int:

        return state.audio_tree.pending_count() + state.video_tree.pending_count()

    def _vp_rebuild_needed_locked(self, state: _SearchIndexState) -> bool:

        return bool(state.video_tree.rebuild_plan() or state.audio_tree.rebuild_plan())

    def _rebuild_deferred_indexes_locked(self, state: _SearchIndexState, reason: str):

        for name, tree in (("video", state.video_tree), ("audio", state.audio_tree)):
            pending = tree.pending_count()
            if pending <= 0 and not tree.dirty:
                continue
            started = time.perf_counter()
            stats = tree.build_index()
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            log_system(
                "INFO",
                "VP-tree index rebuilt" if stats.get("rebuilt") else "VP-tree index rebuild skipped",
                tree=name,
                reason=reason,
                indexed=stats.get("indexed", tree.indexed_count()),
                merged=stats.get("merged", pending),
                pending=tree.pending_count(),
                duration_ms=duration_ms,
                rebuild_count=tree.rebuild_count,
            )

    def _rebuild_deferred_indexes(self, reason: str, ctx: WorkspaceContext | None = None):
        state = self._state_for(ctx)

        if not state.rebuild_lock.acquire(blocking=False):
            return
        needs_follow_up = False
        try:
            with state.sync_lock:
                plans = [
                    ("video", state.video_tree, state.video_tree.rebuild_plan()),
                    ("audio", state.audio_tree, state.audio_tree.rebuild_plan()),
                ]

            replacements = []
            for name, tree, plan in plans:
                if not plan:
                    continue
                started = time.perf_counter()
                replacement = tree.build_replacement(plan)
                duration_ms = round((time.perf_counter() - started) * 1000, 2)
                replacements.append((name, tree, plan, replacement, duration_ms))

            for name, tree, plan, replacement, duration_ms in replacements:
                with state.sync_lock:
                    stats = tree.apply_replacement(plan, replacement)
                    pending = tree.pending_count()
                    rebuild_count = tree.rebuild_count
                log_system(
                    "INFO",
                    "VP-tree index rebuilt" if stats.get("rebuilt") else "VP-tree index rebuild skipped",
                    tree=name,
                    reason=reason,
                    indexed=stats.get("indexed", tree.indexed_count()),
                    merged=stats.get("merged", 0),
                    pending=pending,
                    duration_ms=duration_ms,
                    rebuild_count=rebuild_count,
                )
            with state.sync_lock:
                needs_follow_up = self._vp_pending_count_locked(state) >= self.VP_PENDING_REBUILD_THRESHOLD or self._vp_rebuild_needed_locked(state)
        finally:
            state.rebuild_lock.release()
        if needs_follow_up:
            self._rebuild_deferred_indexes(f"{reason}_followup", ctx=ctx)


search_manager = SearchManager()
