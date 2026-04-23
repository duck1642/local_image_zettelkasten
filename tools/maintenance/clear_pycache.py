from pathlib import Path
import shutil


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main():
    removed = 0
    failed = []

    for path in PROJECT_ROOT.rglob("__pycache__"):
        if not path.is_dir():
            continue
        try:
            shutil.rmtree(path)
            removed += 1
            print(f"removed: {path.relative_to(PROJECT_ROOT)}")
        except OSError as exc:
            failed.append((path, exc))
            print(f"failed: {path.relative_to(PROJECT_ROOT)} - {exc}")

    print(f"done: {removed} __pycache__ folders removed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
