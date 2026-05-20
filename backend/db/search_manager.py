
import sqlite3
import threading
import time
from typing import List, Tuple, Optional

from db.searchers import BKTreeSearcher, URLRegistry, VPTreeSearcher
from db.sqlite_operator import get_all_phashes, get_all_tiles, get_all_urls, get_all_video_signatures
from logger import log_system

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

        self.global_tree = BKTreeSearcher()
        self.tile_tree = BKTreeSearcher()
        self.url_registry = URLRegistry()


        self.video_tree = VPTreeSearcher(_cosine_dist)
        self.audio_tree = VPTreeSearcher(_hamming_dist_audio)

        self.is_hydrated = False
        self._sync_lock = threading.Lock()
        self._rebuild_lock = threading.Lock()
        self._initialized = True

    def hydrate(self, conn: sqlite3.Connection):

        with self._sync_lock:
            if self.is_hydrated:
                return

            log_system('INFO', "Hydrating RAM indexes from SQLite...")


            urls = get_all_urls(conn)
            for url in urls:
                self.url_registry.add(url)


            phashes = get_all_phashes(conn)
            for f_hash, phash in phashes:
                self.global_tree.add(f_hash, phash)


            tiles = get_all_tiles(conn)
            for parent_hash, _, tile_phash in tiles:
                self.tile_tree.add(parent_hash, tile_phash)


            v_sigs = get_all_video_signatures(conn)
            for f_hash, a_hash, v_emb in v_sigs:
                if a_hash:
                    self.audio_tree.add(f_hash, a_hash)
                if v_emb:
                    self.video_tree.add(f_hash, v_emb)


            self._rebuild_deferred_indexes_locked("hydrate")

            self.is_hydrated = True
            log_system('INFO', f"Hydration complete: {len(urls)} URLs | {len(phashes)} Images | {len(v_sigs)} Videos indexed in RAM.")

    def query_image(self, phash: str, threshold: int = 5) -> List[Tuple[str, int, str]]:

        with self._sync_lock:
            global_snapshot = self.global_tree.snapshot()
            tile_snapshot = self.tile_tree.snapshot()

        results = []
        global_matches = BKTreeSearcher.query_snapshot(global_snapshot, phash, threshold)
        for h, dist in global_matches:
            results.append((h, dist, "Global"))


        tile_matches = BKTreeSearcher.query_snapshot(tile_snapshot, phash, threshold)
        for h, dist in tile_matches:
            results.append((h, dist, "Fragment-to-Whole"))

        return results

    def query_video(self, audio_hash: bytes, visual_embedding: bytes, ai_threshold: float = 0.08, audio_threshold: float = 0.85) -> List[Tuple[str, float, str]]:

        with self._sync_lock:
            audio_snapshot = self.audio_tree.snapshot()
            video_snapshot = self.video_tree.snapshot()

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

    def url_exists(self, url: str) -> bool:

        with self._sync_lock:
            return self.url_registry.exists(url)

    def query_global_only(self, phash: str, threshold: int = 5) -> list:

        with self._sync_lock:
            snapshot = self.global_tree.snapshot()
        return BKTreeSearcher.query_snapshot(snapshot, phash, threshold)

    def update_indexes(self, file_hash: str, phash: Optional[str], url: Optional[str], tiles: List[Tuple[int, str]] = None, audio_hash: bytes = None, visual_embedding: bytes = None):

        should_rebuild = False
        with self._sync_lock:
            self._update_indexes_unlocked(file_hash, phash, url, tiles, audio_hash, visual_embedding)
            if self._vp_pending_count_locked() >= self.VP_PENDING_REBUILD_THRESHOLD:
                should_rebuild = True
        if should_rebuild:
            self._rebuild_deferred_indexes("pending_threshold")

    def update_indexes_batch(self, items: list[dict]):

        if not items:
            return
        should_rebuild = False
        with self._sync_lock:
            for item in items:
                self._update_indexes_unlocked(
                    item.get("file_hash"),
                    item.get("phash"),
                    item.get("url"),
                    item.get("tiles"),
                    item.get("audio_hash"),
                    item.get("visual_embedding"),
                )
            log_system("INFO", "RAM index batch update queued", count=len(items))
            should_rebuild = self._vp_pending_count_locked() > 0
        if should_rebuild:
            self._rebuild_deferred_indexes("batch_update")

    def remove_indexes_batch(self, items: list[dict]):

        hashes = {str(item.get("hash") or item.get("file_hash") or "").strip() for item in items or []}
        hashes.discard("")
        urls = [item.get("source_url") or item.get("url") for item in items or [] if item.get("source_url") or item.get("url")]
        if not hashes and not urls:
            return {"removed": 0}

        should_rebuild = False
        with self._sync_lock:
            global_stats = self.global_tree.remove_hashes(hashes)
            tile_stats = self.tile_tree.remove_hashes(hashes)
            audio_stats = self.audio_tree.remove_hashes(hashes)
            video_stats = self.video_tree.remove_hashes(hashes)
            for url in urls:
                self.url_registry.remove(url)
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
            self._rebuild_deferred_indexes_async("batch_remove")
        return {
            "removed": removed,
            "hashes": len(hashes),
            "urls": len(urls),
            "global": global_stats,
            "tile": tile_stats,
            "audio": audio_stats,
            "video": video_stats,
        }

    def _rebuild_deferred_indexes_async(self, reason: str):

        thread = threading.Thread(
            target=self._rebuild_deferred_indexes,
            args=(reason,),
            name=f"lmz-vp-rebuild-{reason}",
            daemon=True,
        )
        thread.start()

    def rebuild_deferred_indexes(self):

        self._rebuild_deferred_indexes("explicit")

    def _update_indexes_unlocked(self, file_hash: str, phash: Optional[str], url: Optional[str], tiles: List[Tuple[int, str]] = None, audio_hash: bytes = None, visual_embedding: bytes = None):

        if url:
            self.url_registry.add(url)
        if phash:
            self.global_tree.add(file_hash, phash)
        if tiles:
            for _, tile_phash in tiles:
                self.tile_tree.add(file_hash, tile_phash)

        if audio_hash:
            self.audio_tree.add(file_hash, audio_hash)
        if visual_embedding:
            self.video_tree.add(file_hash, visual_embedding)

    def _vp_pending_count_locked(self) -> int:

        return self.audio_tree.pending_count() + self.video_tree.pending_count()

    def _vp_rebuild_needed_locked(self) -> bool:

        return bool(self.video_tree.rebuild_plan() or self.audio_tree.rebuild_plan())

    def _rebuild_deferred_indexes_locked(self, reason: str):

        for name, tree in (("video", self.video_tree), ("audio", self.audio_tree)):
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

    def _rebuild_deferred_indexes(self, reason: str):

        if not self._rebuild_lock.acquire(blocking=False):
            return
        needs_follow_up = False
        try:
            with self._sync_lock:
                plans = [
                    ("video", self.video_tree, self.video_tree.rebuild_plan()),
                    ("audio", self.audio_tree, self.audio_tree.rebuild_plan()),
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
                with self._sync_lock:
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
            with self._sync_lock:
                needs_follow_up = self._vp_pending_count_locked() >= self.VP_PENDING_REBUILD_THRESHOLD or self._vp_rebuild_needed_locked()
        finally:
            self._rebuild_lock.release()
        if needs_follow_up:
            self._rebuild_deferred_indexes(f"{reason}_followup")


search_manager = SearchManager()
