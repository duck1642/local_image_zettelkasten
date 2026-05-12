
import shutil
from db.sqlite_operator import reset_database
from utils import ASSETS_DIR, NOTES_DIR, DB_PATH

def main():

    print("[INFO] LMZ System Reset - Starting")

    if DB_PATH.exists():
        reset_database()
    else:
        print("[INFO] Database file not found, skipping reset.")

    assets_dir = ASSETS_DIR
    notes_dir = NOTES_DIR

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
