

import json
import shutil
from pathlib import Path
from utils import REVIEW_DIR, get_config
from processor import process_file

def review_sidecar_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + '.json')

def get_review_items():
    if not REVIEW_DIR.exists():
        return []
    return sorted([f for f in REVIEW_DIR.iterdir() if f.is_file() and f.suffix != '.json'])

def interactive_menu():
    while True:
        items = get_review_items()

        print("\n" + "="*50)
        print("Y LMZ VISUAL DUPLICATE REVIEW")
        print("="*50)

        if not items:
            print("Y The review folder is empty. Everything is clean!")
            break

        print(f"Found {len(items)} items awaiting your decision:\n")

        for i, f in enumerate(items, 1):
            json_path = review_sidecar_path(f)
            info = ""
            if json_path.exists():
                try:
                    with open(json_path, 'r', encoding='utf-8') as jf:
                        data = json.load(jf)

                        best = data.get('best_match') or ''
                        info = f" [Best Match: {best[:8]}... | Dist: {data.get('distance')} | Total: {data.get('total_conflicts')}]"
                except Exception:
                    pass
            print(f"  {i}. {f.name}{info}")

        print("\nCommands:")
        print("  #      - Enter a number to manage that file")
        print("  a      - Approve ALL items")
        print("  r      - Reject ALL items")
        print("  q      - Quit")

        choice = input("\nAction: ").strip().lower()

        if choice == 'q':
            break
        elif choice == 'a':
            confirm = input("Are you sure you want to approve ALL? (y/n): ")
            if confirm.lower() == 'y':
                for item in items:
                    approve_file(item.name)
        elif choice == 'r':
            confirm = input("Are you sure you want to reject ALL? (y/n): ")
            if confirm.lower() == 'y':
                for item in items:
                    reject_file(item.name)
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(items):
                manage_single_item(items[idx])
            else:
                print("[ERROR] Invalid number.")
        else:
            print("[ERROR] Invalid command.")

def manage_single_item(item_path):
    json_path = review_sidecar_path(item_path)
    best_match = "Unknown"
    distance = "?"
    new_phash = "Unknown"
    total_conflicts = 0

    if json_path.exists():
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                best_match = data.get('best_match', "Unknown")
                distance = data.get('distance', "?")
                new_phash = data.get('phash', "Unknown")
                total_conflicts = data.get('total_conflicts', 0)
        except Exception:
            pass

    print(f"\n" + "-"*60)
    print(f"Y REVIEWING: {item_path.name}")
    print(f"YZ  New pHash:      {new_phash}")
    print(f"Y Best Match:     {best_match}")
    print(f"Y Min Distance:   {distance}")
    print(f"as i   Total Conflicts: {total_conflicts} items in vault")
    print("-"*60)
    print("\nActions:")
    print("1. Approve (Keep and move to Vault)")
    print("2. Reject (Delete forever)")
    print("3. Back")

    choice = input("\nChoice: ").strip()

    if choice == '1':
        approve_file(item_path.name)
    elif choice == '2':
        reject_file(item_path.name)

def approve_file(filename):
    file_path = REVIEW_DIR / filename
    json_path = review_sidecar_path(file_path)

    if not file_path.exists():
        return

    print(f"[OK] Approving: {filename}")

    metadata = {}
    if json_path.exists():
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                metadata = data.get('metadata', {})
        except Exception:
            pass

    config = get_config()
    success, message, _ = process_file(file_path, config, metadata=metadata, delete_source=True, skip_similarity=True)

    if success:
        print(f"   {message}")
        if json_path.exists():
            json_path.unlink()
    else:
        print(f"   [ERROR] Error: {message}")

def reject_file(filename):
    file_path = REVIEW_DIR / filename
    json_path = review_sidecar_path(file_path)

    if file_path.exists():
        file_path.unlink()
        print(f"Yi   Deleted: {filename}")

    if json_path.exists():
        json_path.unlink()

if __name__ == "__main__":
    try:
        interactive_menu()
    except KeyboardInterrupt:
        print("\nY Exiting Review Manager.")
