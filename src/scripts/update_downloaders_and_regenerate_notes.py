
import subprocess
import sys
import os
import sqlite3
from pathlib import Path

def update_tools():

    print("Y i   LIZ Maintenance - Updating External Tools...")

    tools = ["yt-dlp", "gallery-dl"]

    for tool in tools:
        print(f"Y Updating {tool}...")
        cmd = [sys.executable, "-m", "pip", "install", "-U", tool, "--break-system-packages"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                print(f"   [OK] {tool} updated successfully.")
            else:

                cmd.pop()
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    print(f"   [OK] {tool} updated successfully.")
                else:
                    print(f"   [ERROR] Failed to update {tool}: {res.stderr}")
        except Exception as e:
            print(f"   [ERROR] Error updating {tool}: {str(e)}")

def regenerate_markdowns():

    print("Y LIZ Maintenance - Regenerating all Markdown files from Database...")
    from db.sqlite_operator import init_database
    from utils import DB_PATH, NOTES_DIR, note_path_for
    from md_generator import generate_markdown

    if not os.path.exists(DB_PATH):
        print(f"[ERROR] Database not found at {DB_PATH}")
        return

    conn = init_database()
    cursor = conn.cursor()
    cursor.execute("SELECT hash FROM items")
    rows = cursor.fetchall()

    print(f"Y Found {len(rows)} items in database.")

    notes_dir = NOTES_DIR
    notes_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for (file_hash,) in rows:
        md_content = generate_markdown(conn, file_hash)
        if md_content:
            md_path = note_path_for(file_hash)
            md_path.parent.mkdir(parents=True, exist_ok=True)
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(md_content)
            count += 1

    conn.close()
    print(f"[OK] Done! Re-generated {count} notes in {notes_dir}")

if __name__ == "__main__":
    update_tools()
    regenerate_markdowns()
