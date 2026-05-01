import argparse
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import sysconfig
from importlib import metadata
from pathlib import Path


IS_WINDOWS = os.name == "nt"
PLATFORM_STR = platform.system()

OK = "[OK]"
MISS = "[MISSING]"
WARN = "[WARN]"


def check_binary(name):
    path_entries = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    local_appdata = os.environ.get("LOCALAPPDATA")
    extra_entries = [
        sysconfig.get_path("scripts"),
        str(Path(sys.executable).resolve().parent / "Scripts"),
        str(Path(sys.executable).resolve().parent),
    ]
    if local_appdata:
        extra_entries.extend(
            [
                str(Path(local_appdata) / "Microsoft" / "WinGet" / "Links"),
                str(Path(local_appdata) / "Python" / "bin"),
            ]
        )

    merged_path = os.pathsep.join([p for p in path_entries + extra_entries if p])
    return shutil.which(name, path=merged_path)


def get_version(package_name):
    try:
        return metadata.version(package_name)
    except metadata.PackageNotFoundError:
        return None


def generate_fix_script(missing_bins, missing_libs):

    script_lines = ["# LMZ Windows Fix Script", "Write-Host 'Checking for Winget...'"]

    if missing_bins:
        script_lines.append("\n# --- System Binaries ---")
        unique_bins = list(dict.fromkeys(missing_bins))
        if any(bin_name in {"ffmpeg", "ffprobe"} for bin_name in unique_bins):
            script_lines.append("winget install ffmpeg")
        for bin_name in unique_bins:
            if bin_name in {"ffmpeg", "ffprobe"}:
                continue
            if bin_name in {"gallery-dl", "yt-dlp"}:
                script_lines.append(f"pip install {bin_name}")
            elif bin_name == "fpcalc":
                script_lines.append("# fpcalc usually comes with Chromaprint. Suggesting manual download or scoop.")
                script_lines.append("Write-Host 'Please download fpcalc from https://acoustid.org/chromaprint' -ForegroundColor Yellow")

    if missing_libs:
        script_lines.append("\n# --- Python Libraries ---")
        for lib in dict.fromkeys(missing_libs):
            pkg = "python-magic-bin" if lib == "python-magic" and IS_WINDOWS else lib
            script_lines.append(f"pip install {pkg}")

        if "playwright" in missing_libs:
            script_lines.append("playwright install chromium")

    return "\n".join(script_lines)


def print_line(message=""):
    print(message.encode("ascii", "replace").decode("ascii"))


def should_prompt(non_interactive: bool) -> bool:
    return not non_interactive and sys.stdin.isatty()


def install_missing_python_libs(missing_libs):
    for lib in missing_libs:
        pkg = "python-magic-bin" if lib == "python-magic" and IS_WINDOWS else lib
        print_line(f"Installing {pkg}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

    if "playwright" in missing_libs:
        print_line("Installing Playwright browsers...")
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])


def main():
    parser = argparse.ArgumentParser(description="Check LMZ system readiness.")
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Never prompt for installation.",
    )
    parser.add_argument(
        "--install-python-libs",
        action="store_true",
        help="Install missing Python packages after the report.",
    )
    args = parser.parse_args()

    print_line(f"--- LMZ SYSTEM READINESS REPORT ({PLATFORM_STR}) ---")

    missing_bins = []
    missing_libs = []

    print_line("\n[SYSTEM BINARIES]")
    for binary in ["ffmpeg", "ffprobe", "gallery-dl", "yt-dlp", "fpcalc"]:
        path = check_binary(binary)
        if path:
            print_line(f"{OK} {binary:12}: Found at {path}")
        else:
            print_line(f"{MISS} {binary:12}: NOT FOUND")
            missing_bins.append(binary)

    print_line("\n[DATABASE]")
    try:
        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()
        cursor.execute("PRAGMA compile_options;")
        options = [row[0] for row in cursor.fetchall()]
        fts5 = "ENABLE_FTS5" in options
        print_line(f"{OK if fts5 else MISS} SQLite FTS5 Support: {'Enabled' if fts5 else 'Disabled'}")
        conn.close()
    except Exception as exc:
        print_line(f"{MISS} SQLite Check Error: {exc}")

    print_line("\n[FIREWALL]")
    try:
        import magic

        magic.Magic()
        print_line(f"{OK} libmagic: Binary loaded and working")
    except Exception as exc:
        print_line(f"{MISS} libmagic: Error loading ({exc})")
        missing_libs.append("python-magic")

    print_line("\n[PYTHON LIBRARIES]")
    libraries = {
        "Pillow": "Pillow",
        "PyYAML": "PyYAML",
        "ImageHash": "ImageHash",
        "Torch": "torch",
        "SentenceTransformers": "sentence-transformers",
        "Playwright": "playwright",
        "Numpy": "numpy",
        "Flet": "flet",
        "Flet Desktop": "flet-desktop",
        "Watchdog": "watchdog",
    }

    for label, package_name in libraries.items():
        version = get_version(package_name)
        if version:
            print_line(f"{OK} {label:20}: v{version}")
        else:
            print_line(f"{MISS} {label:20}: NOT FOUND")
            missing_libs.append(package_name)

    print_line("\n" + "=" * 40)
    if not missing_bins and not missing_libs:
        print_line("[READY] LMZ is ready to launch.")
    else:
        print_line(f"{WARN} Found {len(missing_bins) + len(missing_libs)} missing components.")

        if IS_WINDOWS:
            print_line("\n[WINDOWS QUICK-FIX COMMANDS]")
            print_line("Copy and paste these into PowerShell:")
            print_line("-" * 30)
            print_line(generate_fix_script(missing_bins, missing_libs))
            print_line("-" * 30)

            should_install = args.install_python_libs
            if not should_install and should_prompt(args.non_interactive):
                choice = input("\nInstall missing Python libraries now? (y/n): ").strip().lower()
                should_install = choice == "y"

            if should_install and missing_libs:
                install_missing_python_libs(missing_libs)
                print_line("\nDone. Re-run this script to verify.")
        else:
            print_line("\nLinux/Mac users: use your package manager for binaries and pip for Python libraries.")

    print_line("\n--- REPORT COMPLETE ---")


if __name__ == "__main__":
    main()
