from pathlib import Path
import shutil


PROJECT_ROOT = Path(__file__).resolve().parents[2]

LOG_DIRS_TO_CLEAN = [
    PROJECT_ROOT / "logs",
    PROJECT_ROOT / "frontend" / "logs",
]

LOG_GLOBS_TO_CLEAN = [
    PROJECT_ROOT.glob("*.log"),
    (PROJECT_ROOT / "frontend").glob("*.log"),
    (PROJECT_ROOT / "frontend").glob("npm-debug.log*"),
    (PROJECT_ROOT / "frontend").glob("yarn-debug.log*"),
    (PROJECT_ROOT / "frontend").glob("yarn-error.log*"),
    (PROJECT_ROOT / "frontend").glob("pnpm-debug.log*"),
    (PROJECT_ROOT / "frontend").glob("lerna-debug.log*"),
]


def main():
    removed_items = 0
    failed = []

    # 1. Clean log directories
    for log_dir in LOG_DIRS_TO_CLEAN:
        if not log_dir.exists() or not log_dir.is_dir():
            continue

        for item in log_dir.iterdir():
            try:
                if item.is_file() or item.is_symlink():
                    item.unlink()
                    print(f"removed: {item.relative_to(PROJECT_ROOT)}")
                elif item.is_dir():
                    shutil.rmtree(item)
                    print(f"removed directory: {item.relative_to(PROJECT_ROOT)}")
                removed_items += 1
            except OSError as exc:
                failed.append((item, exc))
                print(f"failed to remove: {item.relative_to(PROJECT_ROOT)} - {exc}")

    # 2. Clean standalone log files
    for glob_iter in LOG_GLOBS_TO_CLEAN:
        for file_path in glob_iter:
            if file_path.is_file() or file_path.is_symlink():
                try:
                    file_path.unlink()
                    print(f"removed: {file_path.relative_to(PROJECT_ROOT)}")
                    removed_items += 1
                except OSError as exc:
                    failed.append((file_path, exc))
                    print(f"failed to remove: {file_path.relative_to(PROJECT_ROOT)} - {exc}")

    if removed_items == 0:
        print("No log files found to remove.")
    else:
        print(f"done: {removed_items} log items removed.")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
