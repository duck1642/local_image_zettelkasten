
from abc import ABC, abstractmethod
from typing import List, Tuple, Optional, Any, Dict

class BaseSearcher(ABC):


    @abstractmethod
    def add(self, item_hash: str, signature: Any):

        pass

    @abstractmethod
    def query(self, signature: Any, threshold: Any) -> List[Tuple[str, Any]]:

        pass

class VPTreeSearcher(BaseSearcher):

    def __init__(self, distance_func):
        self.distance_func = distance_func
        self.tree = None
        self.items = []

    def add(self, item_hash: str, signature: Any):

        if signature is not None:
            self.items.append((item_hash, signature))
            if self.tree is not None:

                self.tree = self._make_tree(self.items)

    def build_index(self):

        if not self.items:
            return
        self.tree = self._make_tree(self.items)


    def _make_tree(self, items):
        if not items:
            return None


        vp_item = items[0]
        if len(items) == 1:
            return (vp_item, 0, None, None)


        distances = []
        for i in range(1, len(items)):
            dist = self.distance_func(vp_item[1], items[i][1])
            distances.append((dist, items[i]))


        distances.sort(key=lambda x: x[0])
        median_idx = len(distances) // 2
        median_dist = distances[median_idx][0]

        left_items = [d[1] for d in distances[:median_idx]]
        right_items = [d[1] for d in distances[median_idx:]]

        return (vp_item, median_dist, self._make_tree(left_items), self._make_tree(right_items))

    def query(self, query_sig: Any, threshold: float) -> List[Tuple[str, float]]:
        if self.tree is None:
            return []

        results = []
        self._search(self.tree, query_sig, threshold, results)
        return sorted(results, key=lambda x: x[1])

    def _search(self, node, query_sig, threshold, results):
        if node is None:
            return

        vp_item, median_dist, left_child, right_child = node
        dist = self.distance_func(query_sig, vp_item[1])

        if dist <= threshold:
            results.append((vp_item[0], dist))


        if dist - threshold <= median_dist:
            self._search(left_child, query_sig, threshold, results)

        if dist + threshold >= median_dist:
            self._search(right_child, query_sig, threshold, results)

class BKTreeSearcher(BaseSearcher):

    def __init__(self):
        self.tree = None

    def _hamming_distance(self, h1: str, h2: str) -> int:


        try:
            val1 = int(h1, 16)
            val2 = int(h2, 16)

            return (val1 ^ val2).bit_count()
        except (ValueError, TypeError):
            return 65

    def add(self, item_hash: str, phash_str: str):

        if not phash_str or phash_str == "None":
            return

        if self.tree is None:
            self.tree = (phash_str, [item_hash], {})
            return

        curr_node = self.tree
        while True:
            node_phash, node_hashes, children = curr_node
            dist = self._hamming_distance(phash_str, node_phash)

            if dist == 0:

                if item_hash not in node_hashes:
                    node_hashes.append(item_hash)
                break

            if dist in children:
                curr_node = children[dist]
            else:
                children[dist] = (phash_str, [item_hash], {})
                break

    def query(self, query_phash: str, threshold: int) -> List[Tuple[str, int]]:

        if self.tree is None or not query_phash:
            return []

        results = []
        candidates = [self.tree]

        while candidates:
            node_phash, node_hashes, children = candidates.pop()
            dist = self._hamming_distance(query_phash, node_phash)

            if dist <= threshold:
                for h in node_hashes:
                    results.append((h, dist))


            for child_dist, child_node in children.items():
                if dist - threshold <= child_dist <= dist + threshold:
                    candidates.append(child_node)

        return sorted(results, key=lambda x: x[1])

class FlatVectorSearcher(BaseSearcher):

    def __init__(self):
        import numpy as np
        self.np = np
        self.hashes = []
        self.matrix = None
        self._pending_vectors = []

    def add(self, item_hash: str, vector_bytes: bytes):

        if not vector_bytes: return

        vector = self.np.frombuffer(vector_bytes, dtype=self.np.float32).copy()

        norm = self.np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm

        self.hashes.append(item_hash)

        if self.matrix is not None:

            self.matrix = self.np.vstack([self.matrix, vector.reshape(1, -1)])
        else:

            self._pending_vectors.append(vector)

    def build_index(self):

        if self._pending_vectors:
            self.matrix = self.np.array(self._pending_vectors)
            self._pending_vectors = []

    def query(self, query_vector_bytes: bytes, threshold: float = 0.08) -> List[Tuple[str, float]]:


        if self._pending_vectors:
            self.build_index()

        if self.matrix is None or not query_vector_bytes:
            return []

        query_vec = self.np.frombuffer(query_vector_bytes, dtype=self.np.float32)
        q_norm = self.np.linalg.norm(query_vec)
        if q_norm == 0: return []
        query_vec = query_vec / q_norm


        similarities = self.np.dot(self.matrix, query_vec)
        distances = 1.0 - similarities

        results = []
        match_indices = self.np.where(distances <= threshold)[0]

        for idx in match_indices:
            results.append((self.hashes[idx], float(distances[idx])))

        return sorted(results, key=lambda x: x[1])

class URLRegistry:

    def __init__(self):
        self.seen_urls = set()

    def add(self, url: str):
        if url:
            self.seen_urls.add(url.strip().lower())

    def exists(self, url: str) -> bool:
        if not url:
            return False
        return url.strip().lower() in self.seen_urls

    def count(self) -> int:
        return len(self.seen_urls)
