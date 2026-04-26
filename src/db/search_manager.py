
import sqlite3
import threading
from typing import List, Tuple, Optional

from db.searchers import BKTreeSearcher, URLRegistry, VPTreeSearcher
from db.sqlite_operator import get_all_phashes, get_all_tiles, get_all_urls, get_all_video_signatures

def _cosine_dist(v1_bytes: bytes, v2_bytes: bytes) -> float:

    import numpy as np
    v1 = np.frombuffer(v1_bytes, dtype=np.float32)
    v2 = np.frombuffer(v2_bytes, dtype=np.float32)

    sim = np.dot(v1, v2)
    return 1.0 - float(sim)

def _hamming_dist_audio(fp1_bytes: bytes, fp2_bytes: bytes) -> float:

    from fingerprint import compare_audio_fingerprints
    sim = compare_audio_fingerprints(fp1_bytes, fp2_bytes)
    return 1.0 - float(sim)

class SearchManager:

    _instance = None
    _lock = threading.Lock()

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
        self._initialized = True

    def hydrate(self, conn: sqlite3.Connection):

        with self._sync_lock:
            if self.is_hydrated:
                return

            log_ingestion('INFO', "Hydrating RAM indexes from SQLite...")


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


            self.video_tree.build_index()
            self.audio_tree.build_index()

            self.is_hydrated = True
            log_ingestion('INFO', f"Hydration complete: {len(urls)} URLs | {len(phashes)} Images | {len(v_sigs)} Videos indexed in RAM.")

    def query_image(self, phash: str, threshold: int = 5) -> List[Tuple[str, int, str]]:

        with self._sync_lock:
            results = []


            global_matches = self.global_tree.query(phash, threshold)
            for h, dist in global_matches:
                results.append((h, dist, "Global"))


            tile_matches = self.tile_tree.query(phash, threshold)
            for h, dist in tile_matches:
                results.append((h, dist, "Fragment-to-Whole"))

            return results

    def query_video(self, audio_hash: bytes, visual_embedding: bytes, ai_threshold: float = 0.08, audio_threshold: float = 0.85) -> List[Tuple[str, float, str]]:

        with self._sync_lock:
            results = []


            if audio_hash:

                dist_threshold = 1.0 - audio_threshold
                audio_matches = self.audio_tree.query(audio_hash, dist_threshold)
                for f_hash, dist in audio_matches:
                    similarity = 1.0 - dist
                    results.append((f_hash, similarity, "Sonic"))
                    break


            if visual_embedding:
                ai_matches = self.video_tree.query(visual_embedding, ai_threshold)
                for h, dist in ai_matches:
                    similarity = 1.0 - dist
                    results.append((h, similarity, "Semantic"))

            return results

    def url_exists(self, url: str) -> bool:

        with self._sync_lock:
            return self.url_registry.exists(url)

    def query_global_only(self, phash: str, threshold: int = 5) -> list:

        with self._sync_lock:
            return self.global_tree.query(phash, threshold)

    def update_indexes(self, file_hash: str, phash: Optional[str], url: Optional[str], tiles: List[Tuple[int, str]] = None, audio_hash: bytes = None, visual_embedding: bytes = None):

        with self._sync_lock:
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


search_manager = SearchManager()
