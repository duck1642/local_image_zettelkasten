
import subprocess
import sys

def update_tools():

    print("[INFO] LMZ Maintenance - Updating External Tools...")

    tools = ["yt-dlp", "gallery-dl"]

    for tool in tools:
        print(f"[INFO] Updating {tool}...")
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

    print("[INFO] LMZ Maintenance - Regenerating all Markdown files from Database...")
    from db.sqlite_operator import init_database
    from scripts.workspace_select import select_runtime_context
    from utils import note_path_for
    from md_generator import generate_markdown

    ctx = select_runtime_context("markdown regeneration", hydrate=False)
    db_path = ctx.active_vault.db_path
    if not db_path.exists():
        print(f"[ERROR] Database not found at {db_path}")
        return

    conn = init_database(ctx=ctx)
    cursor = conn.cursor()
    cursor.execute("SELECT hash, storage_id FROM items")
    rows = cursor.fetchall()

    print(f"[INFO] Found {len(rows)} items in database.")

    notes_dir = ctx.active_vault.notes_dir
    notes_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for file_hash, storage_id in rows:
        md_content = generate_markdown(conn, file_hash)
        if md_content:
            md_path = note_path_for(file_hash, storage_id, ctx=ctx)
            md_path.parent.mkdir(parents=True, exist_ok=True)
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(md_content)
            count += 1

    conn.close()
    print(f"[OK] Done! Re-generated {count} notes in {notes_dir}")

if __name__ == "__main__":
    update_tools()
    regenerate_markdowns()
