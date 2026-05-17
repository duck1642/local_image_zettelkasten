import argparse
import json
import sys
import time

from perf_common import ROOT, env_for_config, ms_since, resolve_config_path, result_dir_for_config, run_subprocess, utc_now, write_json


def _parse_json_output(stdout: str) -> dict:
    text = stdout.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def run_index_perf(config_arg: str) -> dict:
    config_path = resolve_config_path(config_arg)
    started = time.perf_counter()
    completed = run_subprocess(
        [sys.executable, str(ROOT / "tools" / "maintenance" / "rebuild_metadata_index.py"), "--full", "--json"],
        env=env_for_config(config_path),
        cwd=ROOT,
    )
    duration_ms = ms_since(started)
    report = {}
    parse_error = None
    if completed.stdout.strip():
        try:
            report = _parse_json_output(completed.stdout)
        except Exception as exc:
            parse_error = str(exc)
    payload = {
        "kind": "index",
        "run_id": config_path.parent.name,
        "config_path": str(config_path),
        "started_at": utc_now(),
        "duration_ms": duration_ms,
        "exit_code": completed.returncode,
        "report": report,
        "stdout_tail": completed.stdout[-2000:],
        "stderr_tail": completed.stderr[-2000:],
    }
    if parse_error:
        payload["parse_error"] = parse_error
    out_path = result_dir_for_config(config_path) / "index.json"
    write_json(out_path, payload)
    payload["result_path"] = str(out_path)
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Measure full metadata index rebuild performance.")
    parser.add_argument("config_path")
    args = parser.parse_args(argv)
    payload = run_index_perf(args.config_path)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["exit_code"] == 0 else payload["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
