import argparse
import importlib.util
import platform
import subprocess
import sys
from pathlib import Path


def default_triple() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    arch = "aarch64" if machine in {"arm64", "aarch64"} else "x86_64"
    if system == "windows":
        return f"{arch}-pc-windows-msvc"
    if system == "darwin":
        return f"{arch}-apple-darwin"
    return f"{arch}-unknown-linux-gnu"


def pyinstaller_python(root: Path) -> str:
    candidates = [
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        probe = subprocess.run(
            [str(candidate), "-c", "import PyInstaller, fastapi"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if probe.returncode == 0:
            return str(candidate)
    if importlib.util.find_spec("PyInstaller") is not None:
        return sys.executable
    raise RuntimeError("PyInstaller is unavailable; install the project with the 'tauri' extra")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-triple", default=default_triple())
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    entry = root / "backend" / "web_api.py"
    bin_dir = root / "frontend" / "src-tauri" / "bin"
    work_dir = root / "build" / "tauri-sidecar"
    target_name = f"lmz-api-{args.target_triple}"

    if not entry.exists():
        print(f"missing backend entry: {entry}", file=sys.stderr)
        return 1

    bin_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        builder_python = pyinstaller_python(root)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    cmd = [
        builder_python,
        "-m",
        "PyInstaller",
        "--onefile",
        "--name",
        target_name,
        "--distpath",
        str(bin_dir),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(work_dir),
    ]
    if args.clean:
        cmd.append("--clean")
    cmd.append(str(entry))

    result = subprocess.run(cmd, cwd=str(root))
    if result.returncode != 0:
        return result.returncode

    suffix = ".exe" if platform.system().lower() == "windows" else ""
    output = bin_dir / f"{target_name}{suffix}"
    if not output.exists():
        print(f"sidecar build finished but output is missing: {output}", file=sys.stderr)
        return 1

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
