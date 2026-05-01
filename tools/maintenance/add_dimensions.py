import shutil
import subprocess
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "backend"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from db.sqlite_operator import init_database
from utils import ASSETS_DIR, PROJECT_ROOT, DB_PATH, asset_path_for

THUMBNAIL_DIR = PROJECT_ROOT / "data" / "ui_cache" / "thumbnails"

def get_image_dimensions(path: Path):
    try:
        from PIL import Image
        with Image.open(path) as img:
            return img.size
    except Exception as e:
        print(f"Error reading image {path}: {e}")
        return None, None

def get_video_dimensions(path: Path):
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=width,height', '-of', 'csv=s=x:p=0',
             str(path)], capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and 'x' in result.stdout.strip():
            parts = result.stdout.strip().split('x')
            return int(parts[0]), int(parts[1])
    except Exception as e:
        print(f"Error reading video {path}: {e}")
    return None, None

def add_dimensions():
    conn = init_database()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT hash, mime_type, file_extension FROM items WHERE width IS NULL OR height IS NULL OR width = 0 OR height = 0')
        items = cursor.fetchall()
        total = len(items)
        print(f"Found {total} items missing dimensions in DB.")
        
        updated = 0
        for i, (file_hash, mime_type, ext) in enumerate(items):
            path = asset_path_for(file_hash, ext, mime_type)
            if not path.exists():
                print(f"File missing on disk: {path}")
                continue
                
            w, h = None, None
            if mime_type and mime_type.startswith('image/'):
                w, h = get_image_dimensions(path)
            elif mime_type and mime_type.startswith('video/'):
                w, h = get_video_dimensions(path)
                
            if w is not None and h is not None:
                cursor.execute('UPDATE items SET width=?, height=? WHERE hash=?', (w, h, file_hash))
                updated += 1
            else:
                print(f"Could not extract dimensions for {file_hash[:8]}... (MIME: {mime_type})")
                
            if (i + 1) % 100 == 0:
                conn.commit()
                print(f"  Processed {i + 1}/{total}, updated {updated}")
                
        conn.commit()
        print(f"[OK] Dimensions added: {updated}/{total}")
    finally:
        conn.close()

def shard_thumbnails():
    if not THUMBNAIL_DIR.exists():
        print("[OK] No thumbnails directory to shard.")
        return

    moved = 0
    for f in list(THUMBNAIL_DIR.iterdir()):
        if not f.is_file():
            continue
        name = f.name
        if len(name) < 2:
            continue
        prefix = name[:2]
        if prefix == f.stem[:2] and len(f.stem) >= 64:
            shard_dir = THUMBNAIL_DIR / prefix
            shard_dir.mkdir(exist_ok=True)
            dest = shard_dir / name
            if not dest.exists():
                shutil.move(str(f), str(dest))
                moved += 1

    print(f"[OK] Shard thumbnails: moved {moved} files into subdirectories")


def main():
    print("--- Adding dimensions to database ---")
    add_dimensions()
    print()
    print("--- Sharding flat thumbnails ---")
    shard_thumbnails()


if __name__ == "__main__":
    main()
