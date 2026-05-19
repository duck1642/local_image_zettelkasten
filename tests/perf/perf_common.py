import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = ROOT / "tests"
GENERATED_ROOT = TESTS_DIR / "generated"
RESULTS_ROOT = TESTS_DIR / "perf-results"
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
TAURI_DIR = FRONTEND_DIR / "src-tauri"
DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def ms_since(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 2)
    rank = (len(ordered) - 1) * pct
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 2)


def summarize_durations(samples: list[float]) -> dict:
    values = [float(value) for value in samples if value is not None]
    if not values:
        return {
            "samples": 0,
            "min_ms": None,
            "p50_ms": None,
            "p95_ms": None,
            "max_ms": None,
            "mean_ms": None,
        }
    return {
        "samples": len(values),
        "min_ms": round(min(values), 2),
        "p50_ms": percentile(values, 0.50),
        "p95_ms": percentile(values, 0.95),
        "max_ms": round(max(values), 2),
        "mean_ms": round(sum(values) / len(values), 2),
    }


def resolve_config_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(f"config not found: {path}")
    if path.name != "config.yaml":
        raise ValueError(f"expected config.yaml path, got: {path}")
    return path


def vault_dir_for_config(config_path: Path) -> Path:
    return config_path.resolve().parent


def run_id_for_config(config_path: Path) -> str:
    return vault_dir_for_config(config_path).name


def result_dir_for_config(config_path: Path) -> Path:
    result_dir = RESULTS_ROOT / run_id_for_config(config_path)
    result_dir.mkdir(parents=True, exist_ok=True)
    return result_dir


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_manifest(config_path: Path) -> dict:
    manifest_path = vault_dir_for_config(config_path) / "manifest.json"
    if not manifest_path.exists():
        return {}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def python_executable() -> str:
    return sys.executable or "python"


def env_for_config(config_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["LMZ_CONFIG_PATH"] = str(config_path)
    backend_path = str(BACKEND_DIR)
    current = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = backend_path if not current else backend_path + os.pathsep + current
    return env


def http_json(url: str, timeout: float = 30.0) -> tuple[int, dict | list | str | None]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()
        status = int(response.status)
        if not data:
            return status, None
        text = data.decode("utf-8", errors="replace")
        content_type = response.headers.get("content-type", "")
        if "json" in content_type:
            return status, json.loads(text)
        try:
            return status, json.loads(text)
        except json.JSONDecodeError:
            return status, text


def wait_for_backend(base_url: str, timeout_s: float = 45.0) -> float:
    started = time.perf_counter()
    deadline = started + timeout_s
    last_error = None
    while time.perf_counter() < deadline:
        try:
            status, _ = http_json(f"{base_url.rstrip('/')}/api/session-key", timeout=2.0)
            if status == 200:
                return ms_since(started)
        except Exception as exc:
            last_error = exc
        time.sleep(0.35)
    raise TimeoutError(f"backend did not become ready at {base_url}: {last_error}")


def backend_memory_snapshot(base_url: str, label: str) -> dict:
    try:
        status, payload = http_json(f"{base_url.rstrip('/')}/api/system/memory", timeout=10.0)
        backend_mb = None
        if isinstance(payload, dict):
            backend_mb = payload.get("backend_mb")
        return {
            "label": label,
            "ok": 200 <= status < 300,
            "backend_mb": backend_mb if isinstance(backend_mb, (int, float)) else None,
            "status": status,
        }
    except Exception as exc:
        return {
            "label": label,
            "ok": False,
            "backend_mb": None,
            "error": str(exc),
        }


def start_backend(config_path: Path, base_url: str = DEFAULT_BACKEND_URL, log_path: Path | None = None) -> tuple[subprocess.Popen, float]:
    env = env_for_config(config_path)
    env["LMZ_DISABLE_RELOAD"] = "1"
    started = time.perf_counter()
    log_file = None
    stdout = subprocess.DEVNULL
    stderr = subprocess.DEVNULL
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = log_path.open("a", encoding="utf-8", errors="replace")
        stdout = log_file
        stderr = subprocess.STDOUT
    process = subprocess.Popen(
        [python_executable(), str(BACKEND_DIR / "web_api.py")],
        cwd=str(BACKEND_DIR),
        env=env,
        stdout=stdout,
        stderr=stderr,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    if log_file:
        log_file.close()
    try:
        ready_ms = wait_for_backend(base_url)
    except Exception:
        stop_process_tree(process)
        raise
    return process, max(ready_ms, ms_since(started))


def stop_process_tree(process: subprocess.Popen | None) -> None:
    if not process or process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def url_with_params(base_url: str, path: str, params: dict[str, str | int] | list[tuple[str, str | int]] | None = None) -> str:
    url = base_url.rstrip("/") + path
    if not params:
        return url
    if isinstance(params, dict):
        query = urllib.parse.urlencode(params)
    else:
        query = urllib.parse.urlencode(params)
    return url + "?" + query


def compact_response_stats(payload) -> dict:
    if isinstance(payload, dict):
        result = {}
        if isinstance(payload.get("items"), list):
            result["items"] = len(payload["items"])
        for key in ["has_more", "next_cursor", "total_items", "indexed", "errors", "stale", "items"]:
            if key in payload and key not in result:
                value = payload[key]
                if isinstance(value, (str, int, float, bool)) or value is None:
                    result[key] = value
        return result
    if isinstance(payload, list):
        return {"items": len(payload)}
    return {}


def run_subprocess(command: list[str], env: dict[str, str] | None = None, cwd: Path | None = None, timeout_s: int | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=str(cwd or ROOT),
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout_s,
        check=False,
    )
