
from pathlib import Path
from typing import List, Optional, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time
import shutil
import re

from utils import get_config, QUEUES_DIR, ASSETS_DIR, NOTES_DIR
from db.sqlite_operator import init_database
from db.search_manager import search_manager
from processor import process_file
from logs.logger import log_system

from downloaders.gallery_dl_wrapper import download_gallery, inspect_gallery
from downloaders.yt_dlp_wrapper import download_video, inspect_youtube_community
import random


GLOBAL_WORKER_LIMIT: Optional[threading.Semaphore] = None

class ExternalIngestor:
    def __init__(self, links_file: str, skip_validation: bool = False):
        self.links_file = Path(links_file)
        self.config = get_config()
        self.fail_log_lock = threading.Lock()
        self.skip_validation = skip_validation


        global GLOBAL_WORKER_LIMIT
        max_global = self.config.get("ingestion_concurrency", {}).get("global_max_workers", 10)
        if GLOBAL_WORKER_LIMIT is None or GLOBAL_WORKER_LIMIT._value != max_global:
            GLOBAL_WORKER_LIMIT = threading.Semaphore(max_global)
            log_system("INFO", f"Global Ingestion Semaphore initialized with {max_global} slots.")

    def run(self) -> dict:

        stats = {"processed": 0, "skipped": 0, "errors": 0}
        batch_index_queue = []

        if not self.links_file.exists():
            print(f"[ERROR] Links file not found: {self.links_file}")
            log_system("WARNING", f"Ingestion skipped: {self.links_file.name} not found")
            return stats

        try:
            print(f"Y Reading links from: {self.links_file}")
            links = self._parse_links()

            if not links:
                print(f"Y No valid links found in {self.links_file.name}.")
                log_system("INFO", f"Ingestion finished: {self.links_file.name} is empty")
                return stats


            buckets = self._bucket_links(links)
            print(f"Y Bucketed {len(links)} links into {len(buckets)} platform queues.")


            all_remaining = []

            with ThreadPoolExecutor(max_workers=len(buckets)) as platform_executor:
                futures = {platform_executor.submit(self._manage_platform_queue, plat, urls): plat for plat, urls in buckets.items()}

                for future in as_completed(futures):
                    platform = futures[future]
                    try:
                        worker_stats, worker_remaining, worker_index_data = future.result()

                        stats["processed"] += worker_stats["processed"]
                        stats["skipped"] += worker_stats["skipped"]
                        stats["errors"] += worker_stats["errors"]
                        all_remaining.extend(worker_remaining)
                        batch_index_queue.extend(worker_index_data)
                    except Exception as e:
                        print(f"[ERROR] Platform manager for {platform} crashed: {e}")
                        log_system("ERROR", f"Platform manager crash", platform=platform, error=str(e))


            if batch_index_queue:
                print(f"Y Syncing RAM indexes for {len(batch_index_queue)} new items...")
                try:
                    for item in batch_index_queue:
                        search_manager.update_indexes(**item)
                except Exception as sync_e:
                    print(f"as i   RAM Index Sync error (Batch): {sync_e}")
                    log_system("ERROR", "RAM Sync failed during batch finalization", error=str(sync_e))


            self._write_back(all_remaining)
            print(f"\n[OK] Ingestion cycle complete. {len(all_remaining)} links remaining in file.")

        except Exception as e:
            print(f"[ERROR] Critical Error in ExternalIngestor: {e}")
            log_system("ERROR", "ExternalIngestor failed", error=str(e))

        return stats

    def _manage_platform_queue(self, platform: str, urls: List[str]) -> Tuple[dict, List[str], List[dict]]:

        plat_config = self.config.get("ingestion_concurrency", {}).get("platforms", {}).get(platform,
                      self.config.get("ingestion_concurrency", {}).get("platforms", {}).get("default", {}))

        num_workers = plat_config.get("workers", 1)
        jitter = plat_config.get("jitter_range", [2.0, 4.0])

        plat_stats = {"processed": 0, "skipped": 0, "errors": 0}
        plat_remaining = []
        plat_index_data = []

        print(f"[INFO] [{platform.upper()}] Starting queue with {num_workers} workers.")

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(self._worker_item, platform, url, jitter) for url in urls]

            for future in as_completed(futures):
                success, url_out, stats_out, index_list = future.result()


                plat_stats["processed"] += stats_out["processed"]
                plat_stats["skipped"] += stats_out["skipped"]
                plat_stats["errors"] += stats_out["errors"]

                if index_list:
                    plat_index_data.extend(index_list)

                if not success:
                    plat_remaining.append(url_out)

        return plat_stats, plat_remaining, plat_index_data

    def _worker_item(self, platform: str, url: str, jitter_range: list) -> Tuple[bool, str, dict, List[dict]]:

        item_stats = {"processed": 0, "skipped": 0, "errors": 0}


        downloader_type = self._get_downloader_type(url)
        if not downloader_type:
            print(f"as i   [{platform.upper()}] Unsupported platform: {url}")
            log_system("WARNING", "URL skipped: Unsupported platform", url=url)
            return False, url, item_stats, []

        is_pixiv = self._is_pixiv_url(url)
        is_x = self._is_x_url(url)
        is_instagram = self._is_instagram_url(url)
        is_pinterest = self._is_pinterest_url(url)
        is_youtube_community = self._is_youtube_community_url(url)
        batch_protected = is_pixiv or is_x or is_instagram or is_pinterest or is_youtube_community
        metadata_info = None

        if is_pixiv or is_instagram or is_pinterest or is_youtube_community:
            if is_youtube_community:
                meta_success, metadata_info = inspect_youtube_community(url)
            else:
                meta_success, metadata_info = inspect_gallery(url)
            if not meta_success:
                platform_label = "YouTube community" if is_youtube_community else "Pinterest" if is_pinterest else "Instagram" if is_instagram else "Pixiv"
                error_msg = metadata_info.get('error', f'{platform_label} metadata failed')
                print(f"   [ERROR] [{platform.upper()}] Metadata failed: {error_msg}")
                log_system("ERROR", f"{platform_label} metadata failed", url=url, error=error_msg)
                self._log_failure(url, f"{platform_label} metadata failed: {error_msg}")
                item_stats["errors"] += 1
                return False, url, item_stats, []

            expected_count = metadata_info.get("expected_count", 0)
            if is_instagram:
                shortcode = self._instagram_shortcode(url)
                if self._instagram_complete(url, expected_count):
                    print(f"[OK] [{platform.upper()}] URL already complete, skipping: {url}")
                    log_system("INFO", "Instagram URL skipped: Complete in database", url=url, shortcode=shortcode, expected_count=expected_count)
                    item_stats["skipped"] += 1
                    return True, url, item_stats, []
            elif is_pinterest:
                if self._url_complete(url):
                    print(f"[OK] [{platform.upper()}] URL already ingested, skipping: {url}")
                    log_system("INFO", "Pinterest URL skipped: Complete in database", url=url)
                    item_stats["skipped"] += 1
                    return True, url, item_stats, []
            elif is_youtube_community:
                if self._url_complete(url, expected_count):
                    print(f"[OK] [{platform.upper()}] Community post already complete, skipping: {url}")
                    log_system("INFO", "YouTube community post skipped: Complete in database", url=url, expected_count=expected_count)
                    item_stats["skipped"] += 1
                    return True, url, item_stats, []
            elif self._url_complete(url, expected_count):
                print(f"[OK] [{platform.upper()}] URL already complete, skipping: {url}")
                log_system("INFO", "Pixiv URL skipped: Complete in database", url=url, expected_count=expected_count)
                item_stats["skipped"] += 1
                return True, url, item_stats, []
        elif self._url_complete(url):
            print(f"[OK] [{platform.upper()}] URL already ingested, skipping: {url}")
            if is_x:
                log_system("INFO", "X URL skipped: Complete in database", url=url)
            else:
                log_system("INFO", "URL skipped: Complete in database", url=url)
            item_stats["skipped"] += 1
            return True, url, item_stats, []


        with GLOBAL_WORKER_LIMIT:

            wait_time = random.uniform(jitter_range[0], jitter_range[1])
            time.sleep(wait_time)


            max_attempts = 2
            attempt = 0
            success = False
            result = {}

            while attempt < max_attempts and not success:
                attempt += 1
                print(f"Y [{platform.upper()}] Processing: {url} (Attempt {attempt}/{max_attempts})")

                if downloader_type == 'gallery-dl':
                    success, result = download_gallery(url, metadata_info=metadata_info)
                elif downloader_type == 'yt-dlp':
                    success, result = download_video(url, metadata_info=metadata_info)

                if not success and attempt < max_attempts:
                    print(f"   a3 [{platform.upper()}] Attempt {attempt} failed. Retrying in 2 seconds...")
                    log_system("WARNING", f"Download attempt {attempt} failed", url=url, platform=platform)
                    time.sleep(2)

            if success:

                if is_pixiv:
                    expected_count = result.get("expected_count", 0)
                    downloaded_count = result.get("downloaded_count", len(result.get("file_paths", [])))
                    log_system("INFO", "Pixiv download verified", url=url, expected_count=expected_count, downloaded_count=downloaded_count)
                elif is_x:
                    log_system(
                        "INFO",
                        "X download completed",
                        url=url,
                        download_url=result.get("download_url", ""),
                        downloaded_count=result.get("downloaded_count", len(result.get("file_paths", [])))
                    )
                elif is_instagram:
                    log_system(
                        "INFO",
                        "Instagram download verified",
                        url=url,
                        shortcode=self._instagram_shortcode(url),
                        expected_count=result.get("expected_count", 0),
                        downloaded_count=result.get("downloaded_count", len(result.get("file_paths", [])))
                    )
                elif is_pinterest:
                    log_system(
                        "INFO",
                        "Pinterest download verified",
                        url=url,
                        expected_count=result.get("expected_count", 0),
                        downloaded_count=result.get("downloaded_count", len(result.get("file_paths", [])))
                    )
                elif is_youtube_community:
                    log_system(
                        "INFO",
                        "YouTube community download verified",
                        url=url,
                        expected_count=result.get("expected_count", 0),
                        downloaded_count=result.get("downloaded_count", len(result.get("file_paths", [])))
                    )

                validation_failed = False
                validation_error = ""

                if not self.skip_validation:
                    expected_size = result.get('expected_size')
                    expected_sizes = result.get('expected_sizes', {})

                    for f_path in result['file_paths']:
                        p = Path(f_path)
                        if not p.exists(): continue

                        actual_size = p.stat().st_size
                        target_expected = None

                        if expected_size:
                            target_expected = expected_size
                        elif expected_sizes:

                            target_expected = expected_sizes.get(p.stem)

                        if target_expected:
                            if downloader_type == 'gallery-dl':

                                if actual_size != target_expected:
                                    validation_failed = True
                                    validation_error = f"Size mismatch for {p.name}: Expected {target_expected}, got {actual_size} (STRICT)"
                                    break
                            else:

                                diff = abs(actual_size - target_expected)
                                if diff > (target_expected * 0.01) and diff > 102400:
                                    validation_failed = True
                                    validation_error = f"Size mismatch for {p.name}: Expected {target_expected}, got {actual_size} (RELAXED)"
                                    break

                if validation_failed:
                    print(f"   [ERROR] [{platform.upper()}] Integrity Check Failed: {validation_error}")
                    log_system("ERROR", "Integrity check failed", url=url, error=validation_error)
                    self._log_failure(url, f"Integrity check failed: {validation_error}")


                    if 'session_dir' in result:
                        shutil.rmtree(result['session_dir'], ignore_errors=True)

                    item_stats["errors"] += 1
                    return False, url, item_stats, []


                processed_all = True
                batch_data = []

                for f_path in result['file_paths']:
                    target_file = Path(f_path)

                    process_success, msg, idx_data = process_file(
                        target_file,
                        self.config,
                        metadata=result['metadata'],
                        delete_source=True,
                        sync_index=False
                    )

                    if process_success:
                        print(f"   [{platform.upper()}] {msg}")
                        item_stats["processed"] += 1
                        if idx_data:
                            batch_data.append(idx_data)
                    else:
                        print(f"   [{platform.upper()}] [ERROR] Pipeline Error: {msg}")
                        item_stats["errors"] += 1
                        processed_all = False


                if 'session_dir' in result:
                    session_dir_path = Path(result['session_dir'])
                    if session_dir_path.exists():
                        shutil.rmtree(session_dir_path, ignore_errors=True)

                if not processed_all:

                    if batch_data and batch_protected:
                        rolled_back = self._rollback_batch(batch_data)
                        item_stats["processed"] = max(0, item_stats["processed"] - rolled_back)
                        log_system("WARNING", "Rolled back partial URL ingest", url=url, platform=platform, rolled_back=rolled_back)
                    self._log_failure(url, "Pipeline Error during file processing")
                    return False, url, item_stats, [] if batch_protected else batch_data

                if is_pixiv:
                    log_system("INFO", "Pixiv URL processed successfully", url=url, processed=len(batch_data))
                elif is_x:
                    log_system("INFO", "X URL processed successfully", url=url, processed=len(batch_data))
                elif is_instagram:
                    log_system("INFO", "Instagram URL processed successfully", url=url, shortcode=self._instagram_shortcode(url), processed=len(batch_data))
                elif is_pinterest:
                    log_system("INFO", "Pinterest URL processed successfully", url=url, processed=len(batch_data))
                elif is_youtube_community:
                    log_system("INFO", "YouTube community post processed successfully", url=url, processed=len(batch_data))
                return True, url, item_stats, batch_data
            else:
                error_msg = result.get('error', f"Failed after {max_attempts} attempts")
                print(f"   [ERROR] [{platform.upper()}] Download failed: {error_msg}")
                log_system("ERROR", f"Download permanently failed", url=url, platform=platform, error=error_msg)

                self._log_failure(url, f"Download failed: {error_msg}")
                item_stats["errors"] += 1
                return False, url, item_stats, []

    def _is_pixiv_url(self, url: str) -> bool:
        return 'pixiv.net' in url.lower()

    def _is_x_url(self, url: str) -> bool:
        u = url.lower()
        return 'twitter.com' in u or 'x.com' in u

    def _is_instagram_url(self, url: str) -> bool:
        return 'instagram.com' in url.lower()

    def _is_pinterest_url(self, url: str) -> bool:
        u = url.lower()
        return 'pinterest' in u or 'pin.it' in u

    def _is_youtube_community_url(self, url: str) -> bool:
        u = url.lower()
        return 'youtube.com/post/' in u or ('youtube.com/' in u and '/community' in u and 'lb=' in u)

    def _instagram_shortcode(self, url: str) -> str:
        match = re.search(r'instagram\.com/(?:p|reel|tv)/([^/?#]+)', url, re.IGNORECASE)
        return match.group(1) if match else ""

    def _instagram_complete(self, url: str, expected_count: int = None) -> bool:
        shortcode = self._instagram_shortcode(url)
        if not shortcode:
            return self._url_complete(url, expected_count)

        conn = init_database()
        try:
            rows = conn.execute(
                'SELECT hash, file_extension FROM items WHERE LOWER(source_url) LIKE LOWER(?)',
                (f"%/{shortcode}%",)
            ).fetchall()

            if not rows:
                return False

            missing_assets = []
            for file_hash, file_extension in rows:
                asset_path = ASSETS_DIR / file_hash[:2] / f"{file_hash}{file_extension}"
                if not asset_path.exists():
                    missing_assets.append(file_hash)

            if missing_assets:
                log_system("WARNING", "Instagram URL has DB rows with missing assets", url=url, shortcode=shortcode, missing_count=len(missing_assets))
                return False

            if expected_count and len(rows) != expected_count:
                log_system("WARNING", "Instagram URL has incomplete DB row count", url=url, shortcode=shortcode, expected_count=expected_count, db_count=len(rows))
                return False

            return True
        finally:
            conn.close()

    def _url_complete(self, url: str, expected_count: int = None) -> bool:
        conn = init_database()
        try:
            rows = conn.execute(
                'SELECT hash, file_extension FROM items WHERE LOWER(source_url) = LOWER(?)',
                (url.strip(),)
            ).fetchall()

            if not rows:
                return False

            missing_assets = []
            for file_hash, file_extension in rows:
                asset_path = ASSETS_DIR / file_hash[:2] / f"{file_hash}{file_extension}"
                if not asset_path.exists():
                    missing_assets.append(file_hash)

            if missing_assets:
                log_system("WARNING", "URL has DB rows with missing assets", url=url, missing_count=len(missing_assets))
                return False

            if expected_count is not None and len(rows) != expected_count:
                log_system("WARNING", "URL has incomplete DB row count", url=url, expected_count=expected_count, db_count=len(rows))
                return False

            return True
        finally:
            conn.close()

    def _rollback_batch(self, batch_data: List[dict]) -> int:
        conn = init_database()
        rolled_back = 0
        try:
            for item in batch_data:
                file_hash = item.get("file_hash")
                if not file_hash:
                    continue

                row = conn.execute(
                    'SELECT file_extension FROM items WHERE hash = ?',
                    (file_hash,)
                ).fetchone()

                file_extension = row[0] if row else ""
                conn.execute('DELETE FROM items WHERE hash = ?', (file_hash,))

                if file_extension:
                    asset_path = ASSETS_DIR / file_hash[:2] / f"{file_hash}{file_extension}"
                    if asset_path.exists():
                        asset_path.unlink()

                note_path = NOTES_DIR / f"{file_hash}.md"
                if note_path.exists():
                    note_path.unlink()

                rolled_back += 1

            conn.commit()
            return rolled_back
        except Exception as e:
            conn.rollback()
            log_system("ERROR", "Rollback failed", error=str(e))
            return rolled_back
        finally:
            conn.close()

    def _log_failure(self, url: str, reason: str):

        failure_file = QUEUES_DIR / "failed_links.md"
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")


        with self.fail_log_lock:
            mode = 'a' if failure_file.exists() else 'w'
            with open(failure_file, mode, encoding='utf-8') as f:
                if mode == 'w':
                    f.write("# LIZ Failed Links Log\n")
                    f.write("# This file tracks URLs that failed to process correctly.\n\n")
                f.write(f"[{timestamp}] {url} | Reason: {reason}\n")


    def _bucket_links(self, links: List[str]) -> Dict[str, List[str]]:

        buckets = {}
        for url in links:
            platform = self._get_platform_name(url)
            if platform not in buckets:
                buckets[platform] = []
            buckets[platform].append(url)
        return buckets

    def _get_platform_name(self, url: str) -> str:

        u = url.lower()
        if 'pixiv.net' in u: return 'pixiv'
        if 'pinterest' in u or 'pin.it' in u: return 'pinterest'
        if 'instagram.com' in u: return 'instagram'
        if 'twitter.com' in u or 'x.com' in u: return 'x'
        if 'youtube.com' in u or 'youtu.be' in u: return 'youtube'
        return 'generic'

    def _parse_links(self) -> List[str]:

        links = []
        import re
        list_marker_pattern = re.compile(r'^(\s*[-*+]|\s*\d+\.)\s+')

        md_link_pattern = re.compile(r'\[.*?\]\((.*?)\)')

        with open(self.links_file, 'r', encoding='utf-8') as f:
            for line in f:
                raw_line = line.strip()
                if not raw_line or raw_line.startswith('#'): continue
                processed_line = list_marker_pattern.sub('', raw_line)

                md_match = md_link_pattern.search(processed_line)
                if md_match:
                    url = md_match.group(1).strip()
                else:
                    url = processed_line

                if 'http' in url.lower():
                    links.append(url.strip())
        return links

    def _get_downloader_type(self, url: str) -> Optional[str]:

        u = url.lower()
        if any(x in u for x in ['pixiv.net', 'pinterest.com', 'pin.it', 'instagram.com', 'twitter.com', 'x.com']):
            return 'gallery-dl'
        if any(x in u for x in ['youtube.com', 'youtu.be']):
            return 'yt-dlp'
        return None

    def _write_back(self, links: List[str]):

        with open(self.links_file, 'w', encoding='utf-8') as f:
            if links:
                f.write("# Remaining links for LIZ Ingestion\n")
                for link in links:
                    f.write(f"{link}\n")
            else:
                f.write("# All links processed. \n")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        ingestor = ExternalIngestor(sys.argv[1])
        ingestor.run()
