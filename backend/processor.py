
import shutil
import json
import time
from pathlib import Path
from typing import Tuple, Optional
from datetime import datetime
from utils import (
    ASSETS_DIR, REVIEW_DIR, calculate_file_hash, calculate_phash,
    flatten_image, get_normalization_color, note_path_for
)
from fingerprint import (
    get_audio_fingerprint, get_visual_embedding,
    compare_embeddings, compare_audio_fingerprints
)
from validators import get_mime_type, is_allowed_mime
from db.sqlite_operator import (
    init_database, check_duplicate_hash, insert_to_database,
    get_all_video_signatures, insert_tiles
)
from db.search_manager import search_manager
from md_generator import generate_markdown
from logger import log_activity, log_system
from tagging import tag_media

def calculate_tiles(filepath: Path, ratio_threshold: float = 3.0) -> list:

    try:
        from PIL import Image
        import imagehash
        from utils import get_config

        config = get_config()
        proc_config = config.get('processing', {})
        do_flatten = proc_config.get('flatten_transparency', False)
        bg_color = get_normalization_color(proc_config)

        tiles = []
        with Image.open(filepath) as img:
            if do_flatten:
                img = flatten_image(img, bg_color)

            w, h = img.size

            if w == 0 or h == 0:
                from logger import log_system
                log_system("WARNING", "Degenerate image with 0-pixel dimension", file=str(filepath), width=w, height=h)
                return []
            ratio = max(w, h) / min(w, h)

            if ratio < ratio_threshold:
                return []


            if h > w:
                num_tiles = h // w
                for i in range(num_tiles):
                    top = i * w
                    bottom = top + w
                    tile = img.crop((0, top, w, bottom))
                    tiles.append((i, str(imagehash.phash(tile))))
            else:
                num_tiles = w // h
                for i in range(num_tiles):
                    left = i * h
                    right = left + h
                    tile = img.crop((left, 0, right, h))
                    tiles.append((i, str(imagehash.phash(tile))))
        return tiles
    except Exception:
        return []

def find_visual_duplicate(new_phash: str, threshold: int = 5, new_tiles: list = None) -> Tuple[Optional[str], Optional[str], int, Optional[int]]:

    best_match = None
    match_type = None
    min_distance = None
    total_conflicts = 0

    try:


        matches = search_manager.query_image(new_phash, threshold)

        for f_hash, dist, m_type in matches:
            total_conflicts += 1
            if min_distance is None or dist < min_distance:
                min_distance = dist
                best_match = f_hash
                match_type = f"{m_type} (Dist: {dist})"


        if not best_match and new_tiles:
            for t_index, t_phash in new_tiles:

                tile_matches = search_manager.query_global_only(t_phash, threshold)
                if tile_matches:
                    f_hash, dist = tile_matches[0]
                    total_conflicts += len(tile_matches)
                    if not best_match:
                        best_match = f_hash
                        min_distance = dist
                        match_type = f"Whole-to-Fragment (Tile #{t_index})"

    except Exception as e:
        log_system("ERROR", f"Search error in find_visual_duplicate: {e}")

    return best_match, match_type, total_conflicts, min_distance

def find_video_duplicate(audio_hash: bytes, visual_embedding: bytes, ai_threshold: float = 0.08) -> Tuple[Optional[str], Optional[str], int, Optional[float]]:

    best_match = None
    match_type = None
    max_similarity = 0.0
    total_conflicts = 0

    try:

        matches = search_manager.query_video(audio_hash, visual_embedding, ai_threshold)


        conflict_map = {}
        for f_hash, similarity, m_type in matches:
            total_conflicts += 1
            if f_hash not in conflict_map:
                conflict_map[f_hash] = {"similarity": similarity, "types": [m_type]}
            else:
                conflict_map[f_hash]["types"].append(m_type)
                if similarity > conflict_map[f_hash]["similarity"]:
                    conflict_map[f_hash]["similarity"] = similarity


        for f_hash, data in conflict_map.items():
            if len(data["types"]) > 1:
                best_match = f_hash
                max_similarity = data["similarity"]
                match_type = f"High Confidence (Double-Match: {', '.join(data['types'])})"
                break


        if not best_match and conflict_map:
            sorted_conflicts = sorted(conflict_map.items(), key=lambda x: x[1]["similarity"], reverse=True)
            best_match, data = sorted_conflicts[0]
            max_similarity = data["similarity"]
            match_type = f"{data['types'][0]} Match"

    except Exception as e:
        log_system("ERROR", f"Search error in find_video_duplicate: {e}")

    return best_match, match_type, total_conflicts, max_similarity if best_match else None

def process_file(filepath: Path, config: dict, metadata: dict = None, delete_source: bool = False, skip_similarity: bool = False, sync_index: bool = True) -> Tuple[bool, str, Optional[dict]]:

    metadata = metadata or {}
    index_data = None

    firewall_config = config.get('firewall', {})
    allowed_mimes = firewall_config.get('allowed_mimes', [])


    mime_type = get_mime_type(filepath) or "unknown"
    if not is_allowed_mime(mime_type, allowed_mimes):
        log_system("WARNING", f"Skipped: Invalid MIME type", file=filepath.name, mime=mime_type)
        return False, f"Invalid MIME: {mime_type}", None


    allowed_exts_config = firewall_config.get('allowed_extensions', [])
    allowed_exts = {ext.lstrip('.').lower() for ext in allowed_exts_config}

    if filepath.suffix.lstrip('.').lower() not in allowed_exts:
        log_system("WARNING", f"Skipped: Invalid extension", file=filepath.name, extension=filepath.suffix)
        return False, f"Invalid extension: {filepath.suffix}", None

    file_hash = calculate_file_hash(filepath)
    conn = init_database()
    if check_duplicate_hash(conn, file_hash):
        conn.close()
        log_system("INFO", f"Skipped: Duplicate hash", hash=file_hash, file=filepath.name)
        return False, f"Duplicate ignored: {file_hash[:8]}...", None


    phash = None
    audio_hash = None
    visual_embedding = None
    tiles = []
    width = None
    height = None

    if mime_type.startswith('image/'):
        phash = calculate_phash(filepath)
        tiles = calculate_tiles(filepath)
        try:
            from PIL import Image as PILImage
            with PILImage.open(filepath) as img:
                width, height = img.size
        except Exception:
            pass

        if phash and not skip_similarity:
            conflict_hash, match_type, total_conflicts, distance = find_visual_duplicate(phash, threshold=5, new_tiles=tiles)
            if conflict_hash:

                conn.close()

                REVIEW_DIR.mkdir(parents=True, exist_ok=True)
                dest_path = REVIEW_DIR / filepath.name
                shutil.move(filepath, dest_path)


                sidecar = {
                    "original_name": filepath.name,
                    "phash": phash,
                    "match_type": match_type,
                    "best_match": conflict_hash,
                    "distance": distance,
                    "total_conflicts": total_conflicts,
                    "is_tiled": bool(tiles),
                    "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "metadata": metadata
                }
                with open(dest_path.with_suffix(dest_path.suffix + '.json'), 'w', encoding='utf-8') as f:
                    json.dump(sidecar, f, indent=4)

                log_system("WARNING", f"Quarantined: Visual match detected ({match_type})", file=filepath.name, match_type=match_type, conflicts=total_conflicts)
                return False, f"asi   Visual Match ({match_type}, Total: {total_conflicts}) -> Moved to review/", None

    elif mime_type.startswith('video/'):

        audio_hash = get_audio_fingerprint(filepath)
        visual_embedding = get_visual_embedding(filepath)
        try:
            import subprocess
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                 '-show_entries', 'stream=width,height', '-of', 'csv=s=x:p=0',
                 str(filepath)], capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and 'x' in result.stdout.strip():
                parts = result.stdout.strip().split('x')
                width, height = int(parts[0]), int(parts[1])
        except Exception:
            pass

        if (audio_hash or visual_embedding) and not skip_similarity:
            conflict_hash, match_type, total_conflicts, similarity = find_video_duplicate(audio_hash, visual_embedding, ai_threshold=0.08)
            if conflict_hash:

                conn.close()

                REVIEW_DIR.mkdir(parents=True, exist_ok=True)
                dest_path = REVIEW_DIR / filepath.name
                shutil.move(filepath, dest_path)


                sidecar = {
                    "original_name": filepath.name,
                    "match_type": match_type,
                    "best_match": conflict_hash,
                    "similarity": round(float(similarity), 4) if similarity else 0.0,
                    "total_conflicts": total_conflicts,
                    "audio_present": bool(audio_hash),
                    "visual_embedding_present": bool(visual_embedding),
                    "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "metadata": metadata
                }
                with open(dest_path.with_suffix(dest_path.suffix + '.json'), 'w', encoding='utf-8') as f:
                    json.dump(sidecar, f, indent=4)

                log_system("WARNING", f"Quarantined: Video duplicate detected ({match_type})", file=filepath.name, match_type=match_type, conflicts=total_conflicts)
                return False, f"asi   Video Duplicate ({match_type}, Total: {total_conflicts}) -> Moved to review/", None

    orig_ext = filepath.suffix.lower()
    target_ext = orig_ext
    if orig_ext in ['.jfif', '.jpeg']:
        target_ext = '.jpg'

    master_timestamp = datetime.now()
    master_timestamp_str = master_timestamp.strftime('%Y-%m-%d %H:%M:%S')

    vault_path = None
    md_path = None

    try:
        shard_folder = file_hash[:2]
        new_filename = f"{file_hash}{target_ext}"

        shard_path = ASSETS_DIR / shard_folder
        shard_path.mkdir(parents=True, exist_ok=True)

        vault_path = shard_path / new_filename
        asset_rel_path = f"../../assets/{shard_folder}/{new_filename}"

        file_size = filepath.stat().st_size

        shutil.copy2(filepath, vault_path)

        insert_to_database(conn, filepath, file_hash, mime_type, target_ext, metadata, file_size=file_size, timestamp=master_timestamp, phash=phash, audio_hash=audio_hash, visual_embedding=visual_embedding, width=width, height=height)

        if tiles:
            insert_tiles(conn, file_hash, tiles)


        title = metadata.get('title', '')

        md_content = generate_markdown(conn, file_hash, asset_rel_path, title=title)
        if md_content:
            md_path = note_path_for(file_hash)
            md_path.parent.mkdir(parents=True, exist_ok=True)
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(md_content)


        source_url = metadata.get('source_url', '')
        index_data = {
            "file_hash": file_hash,
            "phash": phash,
            "url": source_url,
            "tiles": tiles,
            "audio_hash": audio_hash,
            "visual_embedding": visual_embedding
        }

        try:
            tag_result = tag_media(vault_path, item_hash=file_hash, config=config)
            if tag_result.status != "ok":
                log_system("WARNING", "Tagging enrichment did not complete", hash=file_hash, status=tag_result.status, error=tag_result.error)
                if config.get('tagging', {}).get('fail_ingestion_on_error', False):
                    raise RuntimeError(tag_result.error or f"tagging ended with status {tag_result.status}")
            else:
                md_content = generate_markdown(conn, file_hash, asset_rel_path, title=title)
                if md_content:
                    md_path = note_path_for(file_hash)
                    md_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(md_path, 'w', encoding='utf-8') as f:
                        f.write(md_content)
        except Exception as tag_exc:
            log_system("WARNING", "Tagging enrichment crashed", hash=file_hash, error=str(tag_exc))
            if config.get('tagging', {}).get('fail_ingestion_on_error', False):
                raise

        conn.commit()


        if sync_index:
            search_manager.update_indexes(**index_data)

        if delete_source:
            cleanup_error = None
            for _ in range(5):
                try:
                    filepath.unlink()
                    cleanup_error = None
                    break
                except OSError as exc:
                    cleanup_error = exc
                    time.sleep(0.2)
            if cleanup_error is not None:
                # Ingest has already committed at this point; treat source cleanup as non-fatal.
                log_system("WARNING", "Ingest succeeded but source cleanup failed", file=str(filepath), error=str(cleanup_error))

        artist = metadata.get('artist', 'Local')
        platform = metadata.get('platform', 'Local')

        log_activity(
            original_name=filepath.name,
            vault_id=file_hash,
            platform=platform,
            artist=artist,
            source_url=source_url,
            timestamp_str=master_timestamp_str
        )

        return True, f"Success: {filepath.name} -> {new_filename}", index_data

    except Exception as e:

        try:
            conn.rollback()
        except Exception:
            pass

        try:
            if vault_path and vault_path.exists():
                vault_path.unlink()
            if md_path and md_path.exists():
                md_path.unlink()
        except Exception:
            pass

        log_system("ERROR", f"Pipeline crash during processing", file=filepath.name, error=str(e))
        return False, f"System Error (Rolled back): {str(e)}", None

    finally:
        if 'conn' in locals():
            try:
                conn.close()
            except Exception:
                pass
