
import sqlite3
import os
from pathlib import Path
from tqdm import tqdm

from db.sqlite_operator import init_database
from fingerprint import get_audio_fingerprint, get_visual_embedding
from utils import ASSETS_DIR, DB_PATH

def migrate():
    print(f"[INFO] LMZ Signature Migration - Target: {DB_PATH}")
    conn = init_database()
    cursor = conn.cursor()


    cursor.execute("SELECT hash, file_extension, mime_type FROM items WHERE mime_type LIKE 'video/%'")
    videos = cursor.fetchall()

    if not videos:
        print("[INFO] No videos found in database for migration.")
        conn.close()
        return

    print(f"[INFO] Found {len(videos)} videos. Starting re-calculation...")

    updates = 0
    errors = 0

    for f_hash, ext, mime in tqdm(videos, desc="Migrating", unit="file"):
        shard = f_hash[:2]
        file_path = ASSETS_DIR / shard / f"{f_hash}{ext}"

        if not file_path.exists():
            print(f"[WARN] File missing in vault: {file_path.name}")
            errors += 1
            continue

        try:

            audio_hash = get_audio_fingerprint(file_path)
            visual_emb = get_visual_embedding(file_path)

            cursor.execute('''
                UPDATE items
                SET audio_hash = ?, visual_embedding = ?
                WHERE hash = ?
            ''', (audio_hash, visual_emb, f_hash))

            updates += 1

            if updates % 10 == 0:
                conn.commit()

        except Exception as e:
            print(f"[ERROR] Error migrating {f_hash}: {e}")
            errors += 1

    conn.commit()
    conn.close()

    print(f"\n[OK] Migration Complete!")
    print(f"   - Updated: {updates}")
    print(f"   - Errors/Missing: {errors}")
    print(f"   - Total Processed: {len(videos)}")

if __name__ == "__main__":
    migrate()
