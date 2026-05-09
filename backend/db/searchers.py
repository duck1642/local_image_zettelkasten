
from abc import ABC, abstractmethod
import copy
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
        self.indexed_items = []
        self.pending_items = []
        self.dirty = False
        self.rebuild_count = 0

    def add(self, item_hash: str, signature: Any):

        if signature is not None:
            self.pending_items.append((item_hash, signature))
            self.dirty = True

    def build_index(self):

        pending_count = len(self.pending_items)
        if pending_count:
            self.indexed_items.extend(self.pending_items)
            self.pending_items = []
        if not self.indexed_items:
            self.tree = None
            self.dirty = False
            return {"indexed": 0, "merged": pending_count, "rebuilt": False}
        if not self.dirty and self.tree is not None:
            return {"indexed": len(self.indexed_items), "merged": 0, "rebuilt": False}
        self.tree = self._make_tree(self.indexed_items)
        self.dirty = False
        self.rebuild_count += 1
        return {"indexed": len(self.indexed_items), "merged": pending_count, "rebuilt": True}

    def rebuild_plan(self):
        pending_count = len(self.pending_items)
        if pending_count <= 0 and not self.dirty:
            return None
        return {
            "indexed_items": list(self.indexed_items),
            "pending_items": list(self.pending_items),
            "dirty": self.dirty,
            "rebuild_count": self.rebuild_count,
        }

    def build_replacement(self, plan: dict):
        indexed_items = list(plan["indexed_items"])
        pending_items = list(plan["pending_items"])
        combined_items = indexed_items + pending_items
        if not combined_items:
            return {
                "tree": None,
                "indexed_items": [],
                "merged": len(pending_items),
                "rebuilt": False,
            }
        if not pending_items and not plan.get("dirty") and self.tree is not None:
            return {
                "tree": self.tree,
                "indexed_items": indexed_items,
                "merged": 0,
                "rebuilt": False,
            }
        return {
            "tree": self._make_tree(combined_items),
            "indexed_items": combined_items,
            "merged": len(pending_items),
            "rebuilt": True,
        }

    def apply_replacement(self, plan: dict, replacement: dict):
        merged = int(replacement.get("merged") or 0)
        if merged:
            self.pending_items = self.pending_items[merged:]
        self.indexed_items = list(replacement.get("indexed_items") or [])
        self.tree = replacement.get("tree")
        self.dirty = bool(self.pending_items)
        if replacement.get("rebuilt"):
            self.rebuild_count += 1
        return {
            "indexed": len(self.indexed_items),
            "merged": merged,
            "rebuilt": bool(replacement.get("rebuilt")),
        }

    def snapshot(self) -> dict:
        return {
            "tree": self.tree,
            "pending_items": list(self.pending_items),
            "distance_func": self.distance_func,
        }

    @property
    def items(self):
        return self.indexed_items + self.pending_items

    def pending_count(self) -> int:
        return len(self.pending_items)

    def indexed_count(self) -> int:
        return len(self.indexed_items)


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
        return self.query_snapshot(self.snapshot(), query_sig, threshold)

    @classmethod
    def query_snapshot(cls, snapshot: dict, query_sig: Any, threshold: float) -> List[Tuple[str, float]]:
        results = []
        tree = snapshot.get("tree")
        distance_func = snapshot["distance_func"]
        if tree is not None:
            cls._search_snapshot(tree, query_sig, threshold, results, distance_func)
        for item_hash, signature in snapshot.get("pending_items") or []:
            dist = distance_func(query_sig, signature)
            if dist <= threshold:
                results.append((item_hash, dist))
        return sorted(results, key=lambda x: x[1])

    @classmethod
    def _search_snapshot(cls, node, query_sig, threshold, results, distance_func):
        if node is None:
            return

        vp_item, median_dist, left_child, right_child = node
        dist = distance_func(query_sig, vp_item[1])

        if dist <= threshold:
            results.append((vp_item[0], dist))

        if dist - threshold <= median_dist:
            cls._search_snapshot(left_child, query_sig, threshold, results, distance_func)

        if dist + threshold >= median_dist:
            cls._search_snapshot(right_child, query_sig, threshold, results, distance_func)

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

    @staticmethod
    def _hamming_distance(h1: str, h2: str) -> int:


        try:
            val1 = int(h1, 16)
            val2 = int(h2, 16)

            return (val1 ^ val2).bit_count()
        except (ValueError, TypeError):
            return max(len(str(h1 or "")), len(str(h2 or ""))) * 4 + 1

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
        return self.query_snapshot(self.snapshot(), query_phash, threshold)

    def snapshot(self):
        return copy.deepcopy(self.tree)

    @classmethod
    def query_snapshot(cls, tree, query_phash: str, threshold: int) -> List[Tuple[str, int]]:

        if tree is None or not query_phash:
            return []

        results = []
        candidates = [tree]

        while candidates:
            node_phash, node_hashes, children = candidates.pop()
            dist = cls._hamming_distance(query_phash, node_phash)

            if dist <= threshold:
                for h in node_hashes:
                    results.append((h, dist))


            for child_dist, child_node in children.items():
                if dist - threshold <= child_dist <= dist + threshold:
                    candidates.append(child_node)

        return sorted(results, key=lambda x: x[1])

class URLRegistry:

    def __init__(self):
        self.seen_urls = set()

    def add(self, url: str):
        if url:
            from db.sqlite_operator import normalize_source_url
            self.seen_urls.add(normalize_source_url(url))

    def exists(self, url: str) -> bool:
        if not url:
            return False
        from db.sqlite_operator import normalize_source_url
        return normalize_source_url(url) in self.seen_urls

    def snapshot(self) -> set:
        return set(self.seen_urls)

    def count(self) -> int:
        return len(self.seen_urls)
