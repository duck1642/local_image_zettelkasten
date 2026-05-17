import argparse
import json
import subprocess
import sys
from pathlib import Path

from perf_common import ROOT, result_dir_for_config, resolve_config_path, write_json, utc_now


PROFILES = {
    "800": {"items": 800, "groups": 80, "review": 8, "video_ratio": 0.15, "artists": 50, "platforms": "pixiv,x,instagram,local", "topics": 25, "tauri": True},
    "10k": {"items": 10_000, "groups": 1_000, "review": 20, "video_ratio": 0.15, "artists": 250, "platforms": "pixiv,x,instagram,local", "topics": 100, "tauri": False},
    "50k": {"items": 50_000, "groups": 5_000, "review": 30, "video_ratio": 0.15, "artists": 750, "platforms": "pixiv,x,instagram,local", "topics": 250, "tauri": False},
    "100k": {"items": 100_000, "groups": 10_000, "review": 50, "video_ratio": 0.15, "artists": 1_000, "platforms": "pixiv,x,instagram,local", "topics": 500, "tauri": False},
}


def _run(command: list[str]) -> subprocess.CompletedProcess:
    print(" ".join(command), flush=True)
    return subprocess.run(command, cwd=str(ROOT), text=True, capture_output=True, check=False)


def _generated_config_path(stdout: str) -> str:
    text = stdout.strip()
    if "{" in text and "}" in text:
        try:
            payload = json.loads(text[text.find("{") : text.rfind("}") + 1])
            if payload.get("config_path"):
                return str(payload["config_path"])
        except json.JSONDecodeError:
            pass
    for line in reversed(stdout.splitlines()):
        text = line.strip()
        if text:
            path = Path(text)
            return str(path if path.name == "config.yaml" else path / "config.yaml")
    raise RuntimeError("generator did not print an output path")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate a vault and run the split performance harness.")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="800")
    parser.add_argument("--items", type=int)
    parser.add_argument("--name")
    parser.add_argument("--groups", type=int)
    parser.add_argument("--review", type=int)
    parser.add_argument("--video-ratio", type=float)
    parser.add_argument("--artists", type=int)
    parser.add_argument("--platforms")
    parser.add_argument("--topics", type=int)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--iterations", type=int, default=7)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-tauri", action="store_true", help="Run only generated-vault/index/backend API perf.")
    parser.add_argument("--include-tauri", action="store_true", help="Run Tauri even when the selected profile skips it by default.")
    args = parser.parse_args(argv)
    profile = dict(PROFILES[args.profile])
    for key in ["items", "groups", "review", "artists", "platforms", "topics"]:
        value = getattr(args, key)
        if value is not None:
            profile[key] = value
    if args.video_ratio is not None:
        profile["video_ratio"] = args.video_ratio
    run_name = args.name or f"perf-{args.profile}"
    run_tauri = (args.include_tauri or bool(profile["tauri"])) and not args.skip_tauri

    generator_command = [
        "cmd",
        "/c",
        str(ROOT / "tests" / "perf-generate-vault.bat"),
        "--items",
        str(profile["items"]),
        "--name",
        run_name,
        "--groups",
        str(profile["groups"]),
        "--review",
        str(profile["review"]),
        "--video-ratio",
        str(profile["video_ratio"]),
        "--artists",
        str(profile["artists"]),
        "--platforms",
        str(profile["platforms"]),
        "--topics",
        str(profile["topics"]),
        "--seed",
        str(args.seed),
        "--json",
    ]
    if args.force:
        generator_command.append("--force")
    generated = _run(generator_command)
    if generated.returncode != 0:
        print(generated.stdout)
        print(generated.stderr, file=sys.stderr)
        return generated.returncode

    config_path = resolve_config_path(_generated_config_path(generated.stdout))
    steps = {
        "generated_vault": {
            "exit_code": generated.returncode,
            "stdout_tail": generated.stdout[-2000:],
            "stderr_tail": generated.stderr[-2000:],
        }
    }

    for step_name, script in [
        ("index", ROOT / "tests" / "perf-index.bat"),
        ("backend_api", ROOT / "tests" / "perf-backend-api.bat"),
    ]:
        command = ["cmd", "/c", str(script), str(config_path)]
        if step_name == "backend_api":
            command.extend(["--iterations", str(args.iterations)])
        completed = _run(command)
        steps[step_name] = {
            "exit_code": completed.returncode,
            "stdout_tail": completed.stdout[-4000:],
            "stderr_tail": completed.stderr[-4000:],
        }
        if completed.returncode != 0:
            break

    if run_tauri and all(step["exit_code"] == 0 for step in steps.values()):
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
        "profile": args.profile,
        "parameters": {**profile, "name": run_name, "seed": args.seed, "iterations": args.iterations, "run_tauri": run_tauri},
        "ok": ok,
        "steps": steps,
    }
    out_path = result_dir_for_config(config_path) / "summary.json"
    write_json(out_path, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
