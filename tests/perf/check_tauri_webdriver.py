import argparse
import json
import os
import shutil
import subprocess

from perf_common import write_json, RESULTS_ROOT, utc_now


def _executable(command: str, env_name: str | None = None) -> str | None:
    if env_name and os.environ.get(env_name):
        return os.environ[env_name]
    return shutil.which(command)


def _version(command: str, env_name: str | None = None) -> str | None:
    executable = _executable(command, env_name)
    if not executable:
        return None
    for args in (["--version"], ["--help"]):
        try:
            completed = subprocess.run([executable, *args], text=True, capture_output=True, timeout=10, check=False)
            text = (completed.stdout or completed.stderr).strip()
            if text and (completed.returncode == 0 or args == ["--help"]):
                return text.splitlines()[0]
        except Exception as exc:
            return f"version check failed: {exc}"
    return None


def _exists(command: str, env_name: str | None = None) -> str | None:
    path = _executable(command, env_name)
    if path and os.path.exists(path):
        return path
    path = shutil.which(command)
    return path


def check() -> dict:
    tauri_driver = _exists("tauri-driver", "TAURI_DRIVER")
    edge_driver = _exists("msedgedriver", "MSEDGEDRIVER_PATH")
    return {
        "kind": "tauri-webdriver-readiness",
        "checked_at": utc_now(),
        "ok": bool(tauri_driver and edge_driver),
        "tauri_driver": tauri_driver,
        "tauri_driver_version": _version("tauri-driver", "TAURI_DRIVER"),
        "msedgedriver": edge_driver,
        "msedgedriver_version": _version("msedgedriver", "MSEDGEDRIVER_PATH"),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check Tauri WebDriver dependencies.")
    parser.add_argument("--write", action="store_true", help="Write readiness JSON to tests/perf-results/tauri-webdriver-check.json")
    args = parser.parse_args(argv)
    payload = check()
    if args.write:
        write_json(RESULTS_ROOT / "tauri-webdriver-check.json", payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
