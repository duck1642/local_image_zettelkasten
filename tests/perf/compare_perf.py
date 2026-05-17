import argparse
import json
from pathlib import Path


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _metric(result: dict, key: str, value):
    if isinstance(value, (int, float)):
        result[key] = float(value)


def _flatten_run(run_dir: Path) -> dict[str, float]:
    values: dict[str, float] = {}
    index = _load(run_dir / "index.json")
    backend = _load(run_dir / "backend-api.json")
    tauri = _load(run_dir / "tauri-webview.json")

    report = index.get("report") if isinstance(index.get("report"), dict) else {}
    _metric(values, "index.duration_ms", report.get("duration_ms") or index.get("duration_ms"))
    _metric(values, "index.items", report.get("items"))
    _metric(values, "index.errors", report.get("errors"))

    for endpoint in backend.get("endpoints") or []:
        name = endpoint.get("name")
        if not name:
            continue
        _metric(values, f"backend.{name}.p50_ms", endpoint.get("p50_ms"))
        _metric(values, f"backend.{name}.p95_ms", endpoint.get("p95_ms"))
        _metric(values, f"backend.{name}.max_ms", endpoint.get("max_ms"))
    for sample in backend.get("memory") or []:
        label = sample.get("label")
        if label:
            _metric(values, f"backend.memory.{label}.backend_mb", sample.get("backend_mb"))

    for metric in tauri.get("metrics") or []:
        name = metric.get("name")
        if not name:
            continue
        _metric(values, f"tauri.{name}.duration_ms", metric.get("duration_ms"))
        for key in ["max_tiles", "max_images", "max_videos", "max_dom_nodes"]:
            _metric(values, f"tauri.{name}.{key}", metric.get(key))
    for sample in tauri.get("memory") or []:
        label = sample.get("label")
        if label:
            for key in ["backend_mb", "frontend_mb", "total_mb"]:
                _metric(values, f"tauri.memory.{label}.{key}", sample.get(key))
    if tauri.get("dom"):
        _metric(values, "tauri.dom.max_tiles", max((sample.get("tiles") or 0) for sample in tauri["dom"]))
        _metric(values, "tauri.dom.max_videos", max((sample.get("videos") or 0) for sample in tauri["dom"]))
        _metric(values, "tauri.dom.max_nodes", max((sample.get("dom_nodes") or 0) for sample in tauri["dom"]))
    return values


def compare_runs(baseline_dir: Path, latest_dir: Path, warn_pct: float) -> dict:
    baseline = _flatten_run(baseline_dir)
    latest = _flatten_run(latest_dir)
    comparisons = []
    warnings = []
    for key in sorted(set(baseline) & set(latest)):
        before = baseline[key]
        after = latest[key]
        delta = after - before
        delta_pct = None if before == 0 else round((delta / before) * 100, 2)
        row = {
            "metric": key,
            "baseline": round(before, 2),
            "latest": round(after, 2),
            "delta": round(delta, 2),
            "delta_pct": delta_pct,
        }
        comparisons.append(row)
        if delta_pct is not None and delta_pct > warn_pct:
            warnings.append(row)
    return {
        "kind": "perf-compare",
        "baseline_dir": str(baseline_dir),
        "latest_dir": str(latest_dir),
        "warn_pct": warn_pct,
        "ok": True,
        "warnings": warnings,
        "comparisons": comparisons,
        "missing_in_latest": sorted(set(baseline) - set(latest)),
        "new_in_latest": sorted(set(latest) - set(baseline)),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Compare two LMZ perf result directories. Warn only; never fails on regressions.")
    parser.add_argument("baseline_dir", type=Path)
    parser.add_argument("latest_dir", type=Path)
    parser.add_argument("--warn-pct", type=float, default=20.0)
    args = parser.parse_args(argv)
    payload = compare_runs(args.baseline_dir, args.latest_dir, args.warn_pct)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
