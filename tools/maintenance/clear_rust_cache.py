import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TAURI_DIR = PROJECT_ROOT / "frontend" / "src-tauri"


def main():
    if not TAURI_DIR.exists():
        print(f"Error: Tauri directory not found at {TAURI_DIR.relative_to(PROJECT_ROOT)}")
        raise SystemExit(1)

    print(f"Running `cargo clean` in {TAURI_DIR.relative_to(PROJECT_ROOT)}...")
    
    try:
        result = subprocess.run(
            ["cargo", "clean"],
            cwd=TAURI_DIR,
            check=True,
            text=True,
            capture_output=True
        )
        print("Successfully cleared Rust cache.")
        if result.stderr:
            # cargo clean outputs to stderr usually
            print(result.stderr)
    except subprocess.CalledProcessError as exc:
        print(f"Failed to clear Rust cache. Exit code: {exc.returncode}")
        if exc.stderr:
            print(exc.stderr)
        raise SystemExit(1)
    except FileNotFoundError:
        print("Error: `cargo` command not found. Ensure Rust is installed and in your PATH.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
