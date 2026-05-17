import argparse
import json
import subprocess
import sys

from perf_common import ROOT, result_dir_for_config, resolve_config_path, write_json, utc_now


def _run(command: list[str]) -> subprocess.CompletedProcess:
    print(" ".join(command), flush=True)
    return subprocess.run(command, cwd=str(ROOT), text=True, capture_output=True, check=False)


def _last_path(stdout: str) -> str:
    for line in reversed(stdout.splitlines()):
        text = line.strip()
        if text:
            return text
    raise RuntimeError("generator did not print an output path")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate a vault and run the split performance harness.")
    parser.add_argument("--items", type=int, default=800)
    parser.add_argument("--name", default="perf")
    parser.add_argument("--groups", type=int, default=100)
    parser.add_argument("--review", type=int, default=10)
    parser.add_argument("--video-ratio", type=float, default=0.1)
    parser.add_argument("--artists", type=int, default=50)
    parser.add_argument("--platforms", default="pixiv,x,instagram,local")
    parser.add_argument("--topics", type=int, default=25)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-tauri", action="store_true", help="Run only generated-vault/index/backend API perf.")
    args = parser.parse_args(argv)

    generator_command = [
        "cmd",
        "/c",
        str(ROOT / "tests" / "perf-generate-vault.bat"),
        "--items",
        str(args.items),
        "--name",
        args.name,
        "--groups",
        str(args.groups),
        "--review",
        str(args.review),
        "--video-ratio",
        str(args.video_ratio),
        "--artists",
        str(args.artists),
        "--platforms",
        args.platforms,
        "--topics",
        str(args.topics),
        "--seed",
        str(args.seed),
    ]
    if args.force:
        generator_command.append("--force")
    generated = _run(generator_command)
    if generated.returncode != 0:
        print(generated.stdout)
        print(generated.stderr, file=sys.stderr)
        return generated.returncode

    config_path = resolve_config_path(str(_last_path(generated.stdout)) + "/config.yaml")
    steps = {
        "generated_vault": {
            "exit_code": generated.returncode,
            "stdout_tail": generated.stdout[-2000:],
            "stderr_tail": generated.stderr[-2000:],
        }
    }

    for name, script in [
        ("index", ROOT / "tests" / "perf-index.bat"),
        ("backend_api", ROOT / "tests" / "perf-backend-api.bat"),
    ]:
        completed = _run(["cmd", "/c", str(script), str(config_path)])
        steps[name] = {
            "exit_code": completed.returncode,
            "stdout_tail": completed.stdout[-4000:],
            "stderr_tail": completed.stderr[-4000:],
        }
        if completed.returncode != 0:
            break

    if not args.skip_tauri and all(step["exit_code"] == 0 for step in steps.values()):
        completed = _run(["cmd", "/c", str(ROOT / "tests" / "perf-tauri-webview.bat"), str(config_path)])
        steps["tauri_webview"] = {
            "exit_code": completed.returncode,
            "stdout_tail": completed.stdout[-4000:],
            "stderr_tail": completed.stderr[-4000:],
        }

    ok = all(step["exit_code"] == 0 for step in steps.values())
    summary = {
        "kind": "perf-full",
        "run_id": config_path.parent.name,
        "config_path": str(config_path),
        "started_at": utc_now(),
        "ok": ok,
        "steps": steps,
    }
    out_path = result_dir_for_config(config_path) / "summary.json"
    write_json(out_path, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
