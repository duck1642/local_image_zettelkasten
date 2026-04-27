import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from db.sqlite_operator import init_database
from utils import ASSETS_DIR, PROJECT_ROOT


THUMBNAIL_DIR = PROJECT_ROOT / "data" / "ui_cache" / "thumbnails"


def get_image_dimensions(path: Path) -> tuple[int | None, int | None]:
    try:
        from PIL import Image
        with Image.open(path) as img:
            w, h = img.size
            return w, h
    except Exception:
        return None, None


def get_video_dimensions(path: Path) -> tuple[int | None, int | None]:
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=width,height', '-of', 'csv=s=x:p=0',
             str(path)], capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and 'x' in result.stdout.strip():
            parts = result.stdout.strip().split('x')
            return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return None, None


def add_dimensions():
    conn = init_database()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT hash, file_extension, mime_type FROM items WHERE width IS NULL OR height IS NULL")
        rows = cursor.fetchall()
        total = len(rows)
        updated = 0
        print(f"Found {total} items missing dimensions.")

        for i, (file_hash, extension, mime_type) in enumerate(rows):
            ext = extension or ""
            asset_path = ASSETS_DIR / file_hash[:2] / f"{file_hash}{ext}"
            if not asset_path.exists():
                continue

            w, h = None, None
            if (mime_type or "").startswith("video/"):
                w, h = get_video_dimensions(asset_path)
            elif (mime_type or "").startswith("image/"):
                w, h = get_image_dimensions(asset_path)

            if w and h:
                cursor.execute("UPDATE items SET width = ?, height = ? WHERE hash = ?", (w, h, file_hash))
                updated += 1

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
