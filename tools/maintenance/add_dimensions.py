import subprocess
import sys
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "backend"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from db.sqlite_operator import init_database
from utils import asset_path_for
import utils

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
        cursor.execute('SELECT hash, mime_type, file_extension, storage_id FROM items WHERE width IS NULL OR height IS NULL OR width = 0 OR height = 0')
        items = cursor.fetchall()
        total = len(items)
        print(f"Found {total} items missing dimensions in DB.")
        
        updated = 0
        for i, (file_hash, mime_type, ext, storage_id) in enumerate(items):
            path = asset_path_for(file_hash, ext, mime_type, storage_id=storage_id)
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

def main():
    parser = argparse.ArgumentParser(description="Populate missing media dimensions in the active vault DB.")
    parser.parse_args()

    from runtime_context import has_runtime_context
    if not has_runtime_context():
        from scripts.workspace_select import select_runtime_context
        select_runtime_context("add_dimensions")

    print("--- Adding dimensions to database ---")
    add_dimensions()


if __name__ == "__main__":
    main()
