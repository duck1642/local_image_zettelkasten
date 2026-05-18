import argparse
import json
import shutil
from pathlib import Path

from perf_common import GENERATED_ROOT, RESULTS_ROOT, ROOT


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _safe_artifact(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    resolved_root = root.resolve()
    if resolved == resolved_root or not _is_inside(resolved, resolved_root):
        raise ValueError(f"refusing unsafe path: {resolved}")
    return resolved


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            try:
                total += child.stat().st_size
            except OSError:
                pass
    return total


def _artifact(run_id: str, include_generated: bool = True, include_results: bool = True) -> list[Path]:
    paths = []
    if include_generated:
        generated = GENERATED_ROOT / run_id
        if generated.exists():
            paths.append(generated)
    if include_results:
        result = RESULTS_ROOT / run_id
        if result.exists():
            paths.append(result)
    return paths


def _selected_run_ids(args) -> list[str]:
    run_ids = set(args.run_id or [])
    generated_dirs = sorted([path for path in GENERATED_ROOT.glob("*") if path.is_dir()], key=lambda path: path.name)

    if args.all:
        run_ids.update(path.name for path in generated_dirs)

    if args.keep_latest is not None:
        keep = max(0, int(args.keep_latest))
        stale = generated_dirs[:-keep] if keep else generated_dirs
        run_ids.update(path.name for path in stale)

    return sorted(run_ids)


def cleanup(args) -> dict:
    if not args.all and args.keep_latest is None and not args.run_id:
        raise ValueError("select artifacts with --run-id, --keep-latest, or --all")

    include_generated = not args.results_only
    include_results = not args.generated_only
    if not include_generated and not include_results:
        raise ValueError("--generated-only and --results-only cannot be used together")

    selected = _selected_run_ids(args)
    artifacts = []
    for run_id in selected:
        for path in _artifact(run_id, include_generated=include_generated, include_results=include_results):
            root = GENERATED_ROOT if _is_inside(path, GENERATED_ROOT) else RESULTS_ROOT
            safe_path = _safe_artifact(path, root)
            artifacts.append(
                {
                    "run_id": run_id,
                    "path": str(safe_path),
                    "kind": "generated" if root == GENERATED_ROOT else "perf-results",
                    "bytes": _dir_size(safe_path) if args.with_size else None,
                }
            )

    total_bytes = sum(int(item["bytes"] or 0) for item in artifacts)
    payload = {
        "apply": bool(args.apply),
        "selected_run_ids": selected,
        "artifact_count": len(artifacts),
        "total_bytes": total_bytes,
        "artifacts": artifacts,
    }

    if args.apply:
        for item in artifacts:
            shutil.rmtree(item["path"])

    return payload


def _print_summary(payload: dict):
    mode = "DELETE" if payload["apply"] else "DRY-RUN"
    print(f"{mode} artifacts={payload['artifact_count']} bytes={payload['total_bytes']}")
    for item in payload["artifacts"]:
        size = item["bytes"] if item["bytes"] is not None else "size-skipped"
        print(f"{item['kind']} {size} {item['path']}")
    if not payload["apply"]:
        print("Add --apply to delete these artifacts.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Safely clean generated perf vaults and perf result folders.")
    parser.add_argument("--run-id", action="append", help="Generated run id, e.g. 028-pass3b2-50k. Can be repeated.")
    parser.add_argument("--keep-latest", type=int, help="Delete generated vaults older than the latest N by folder name.")
    parser.add_argument("--all", action="store_true", help="Select all generated vaults.")
    parser.add_argument("--generated-only", action="store_true", help="Delete only tests/generated artifacts.")
    parser.add_argument("--results-only", action="store_true", help="Delete only tests/perf-results artifacts.")
    parser.add_argument("--with-size", action="store_true", help="Recursively calculate artifact sizes. Slower on large vaults.")
    parser.add_argument("--apply", action="store_true", help="Actually delete selected artifacts. Without this, dry-run only.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        payload = cleanup(args)
    except Exception as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        else:
            print(f"ERROR {exc}")
        return 2

    payload["ok"] = True
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_summary(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
