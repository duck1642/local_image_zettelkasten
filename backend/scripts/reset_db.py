
import shutil
from db.sqlite_operator import reset_database
from scripts.workspace_select import select_runtime_context

def main():

    print("[INFO] LMZ System Reset - Starting")
    ctx = select_runtime_context("system reset", hydrate=False)
    db_path = ctx.active_vault.db_path

    confirm = input(f"Reset DB and clear assets/notes for vault '{ctx.active_vault.id}'? Type RESET to continue: ").strip()
    if confirm != "RESET":
        print("[INFO] Reset cancelled.")
        return

    if db_path.exists():
        reset_database()
    else:
        print("[INFO] Database file not found, skipping reset.")

    assets_dir = ctx.active_vault.assets_dir
    notes_dir = ctx.active_vault.notes_dir

    for folder in [assets_dir, notes_dir]:
        if folder.exists():
            print(f"[INFO] Clearing folder: {folder}")
            for item in folder.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
        else:
            print(f"[WARN] Folder not found, skipping: {folder}")

    print("\n[OK] LMZ System is now clean and ready for a fresh start.")

if __name__ == "__main__":
    main()
