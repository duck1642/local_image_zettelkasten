import argparse
import subprocess
import sys
from pathlib import Path


def _run_command(cmd: list[str]) -> int:
    result = subprocess.run(cmd, text=True)
    return int(result.returncode)


def check() -> int:
    script_path = Path(__file__).resolve().with_name("lmz_readiness_check.py")
    if not script_path.exists():
        print(f"[ERROR] Readiness script not found: {script_path}")
        return 1
    return _run_command([sys.executable, str(script_path), "--non-interactive"])


def _update_single_tool(tool: str) -> bool:
    cmd = [sys.executable, "-m", "pip", "install", "-U", tool, "--break-system-packages"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"[OK] {tool} updated successfully.")
        return True

    fallback = cmd[:-1]
    fallback_result = subprocess.run(fallback, capture_output=True, text=True)
    if fallback_result.returncode == 0:
        print(f"[OK] {tool} updated successfully.")
        return True

    stderr = (fallback_result.stderr or result.stderr or "").strip()
    print(f"[ERROR] Failed to update {tool}: {stderr}")
    return False


def update_downloaders() -> int:
    print("[INFO] Updating downloader dependencies...")
    ok = True
    for tool in ("yt-dlp", "gallery-dl"):
        print(f"[INFO] Updating {tool}...")
        if not _update_single_tool(tool):
            ok = False
    return 0 if ok else 1


def install_playwright_browser() -> int:
    print("[INFO] Installing Playwright Chromium browser...")
    return _run_command([sys.executable, "-m", "playwright", "install", "chromium"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LMZ maintenance CLI")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("check", help="Run environment readiness checks")
    subparsers.add_parser("update-downloaders", help="Update yt-dlp and gallery-dl")
    subparsers.add_parser("install-playwright-browser", help="Install Playwright Chromium browser")
    subparsers.add_parser("update", help="Alias for update-downloaders")
    subparsers.add_parser("update-tools", help="Alias for update-downloaders")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command or "update-downloaders"

    if command == "check":
        return check()
    if command in {"update-downloaders", "update", "update-tools"}:
        return update_downloaders()
    if command == "install-playwright-browser":
        return install_playwright_browser()

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
