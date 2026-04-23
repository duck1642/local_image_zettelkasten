
import re
from utils import QUEUES_DIR

FAILED_FILE = QUEUES_DIR / "failed_links.md"
PENDING_FILE = QUEUES_DIR / "normal_pending_links.md"

def retry_links():
    if not FAILED_FILE.exists():
        print(" No failed_links.md found. Nothing to retry!")
        return

    print(f" Reading failed links from {FAILED_FILE.name}...")


    link_pattern = re.compile(r"\[.*?\]\s+(.*?)\s+\|")

    urls_to_retry = []
    with open(FAILED_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('#') or not line.strip():
                continue

            match = link_pattern.search(line)
            if match:
                urls_to_retry.append(match.group(1).strip())
            else:

                parts = line.split('|')
                if len(parts) > 0:
                    raw = parts[0].split(']')[-1].strip()
                    if raw.startswith('http'):
                        urls_to_retry.append(raw)

    if not urls_to_retry:
        print("  No valid URLs found in failed_links.md.")
        return

    print(f" Found {len(urls_to_retry)} links. Appending to {PENDING_FILE.name}...")


    mode = 'a' if PENDING_FILE.exists() else 'w'
    with open(PENDING_FILE, mode, encoding='utf-8') as f:
        if mode == 'w':
            f.write("# LIZ Pending Links\n")

        f.write("\n# --- Retried Links ---\n")
        for url in urls_to_retry:
            f.write(f"{url}\n")


    with open(FAILED_FILE, 'w', encoding='utf-8') as f:
        f.write("# LIZ Failed Links Log\n")
        f.write("# This file tracks URLs that failed to process correctly.\n\n")

    print(f" Success! {len(urls_to_retry)} links moved. failed_links.md has been cleared.")

if __name__ == "__main__":
    retry_links()
