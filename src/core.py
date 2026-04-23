
from utils import setup_directories, get_config, INPUT_DIR, VAULT_DIR, DB_PATH, REVIEW_DIR, QUEUES_DIR
from processor import process_file
from external_ingestion import ExternalIngestor
from db.sqlite_operator import init_database
from db.search_manager import search_manager

def main():

    setup_directories()
    config = get_config()


    conn = init_database()
    search_manager.hydrate(conn)
    conn.close()

    print(f"\nY LIZ Unified System - Starting")
    print(f"   Input: {INPUT_DIR}")
    print(f"   Vault: {VAULT_DIR}")
    print(f"   DB: {DB_PATH}\n")

    stats = {"processed": 0, "skipped": 0, "errors": 0}


    ingestion_targets = [
        ("normal_pending_links.md", False),
        ("force_pending_links.md", True)
    ]

    for filename, skip_val in ingestion_targets:
        links_file = QUEUES_DIR / filename
        if links_file.exists():
            mode_str = "FORCE (No Size Check)" if skip_val else "NORMAL"
            print(f"Y Found {filename} [{mode_str}]. Starting Ingestion...")
            ingestor = ExternalIngestor(str(links_file), skip_validation=skip_val)
            ext_stats = ingestor.run()
            stats["processed"] += ext_stats["processed"]
            stats["skipped"] += ext_stats.get("skipped", 0)
            stats["errors"] += ext_stats["errors"]
        else:
            print(f"a1i   No {filename} found. Skipping.")

    print(f"\nY Scanning local input folder for remaining files...")

    if not INPUT_DIR.exists():
        INPUT_DIR.mkdir(parents=True, exist_ok=True)

    local_index_queue = []
    for filepath in sorted(INPUT_DIR.rglob('*')):
        if not filepath.is_file() or filepath.suffix.lower() in ['.md', '.json', '.txt']:
            continue

        if REVIEW_DIR in filepath.parents or filepath.parent == REVIEW_DIR:
            continue


        success, message, idx_data = process_file(filepath, config, delete_source=True, sync_index=False)

        if success:
            print(f"   {message}")
            stats["processed"] += 1
            if idx_data:
                local_index_queue.append(idx_data)

            parent = filepath.parent
            if parent != INPUT_DIR and parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
        elif "Duplicate ignored" in message:
            print(f"   {message}")
            stats["skipped"] += 1
        else:
            print(f"   {message}")
            stats["errors"] += 1


    if local_index_queue:
        print(f"Y Syncing RAM indexes for {len(local_index_queue)} local items...")
        for item in local_index_queue:
            search_manager.update_indexes(**item)

    print(f"\nYS FINAL SUMMARY: {stats['processed']} Added | {stats['skipped']} Skipped/Duplicates | {stats['errors']} Errors")
