import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from queue_service import QUEUE_LABELS, move_failed_urls, queue_counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["normal", "force"], required=True)
    args = parser.parse_args()
    counts = queue_counts()
    failed_count = counts.get("failed", 0)
    if not failed_count:
        print("No failed URLs found.")
        return 0
    moved = move_failed_urls(args.target)
    print(f"Moved {moved} failed URLs to {QUEUE_LABELS[args.target]}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
