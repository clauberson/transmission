#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

METRIC_KEYS = ("download_bps", "upload_bps", "cpu_avg", "cpu_peak", "rss_avg", "rss_peak")
LOWER_IS_BETTER = {"cpu_avg", "cpu_peak", "rss_avg", "rss_peak"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compara summary benchmark com baseline primário/secundário")
    parser.add_argument("--summary", default="artifacts/summary.json")
    parser.add_argument("--baseline-root", default="perf-baseline")
    parser.add_argument("--output", default="artifacts/baseline-comparison.json")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def load_baselines(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest = load_json(root / "manifest.json")
    primary = load_json(root / manifest["primary"]["path"])
    secondary = load_json(root / manifest["secondary"]["path"])
    return manifest, primary, secondary


def make_map(summary: dict[str, Any]) -> dict[str, dict[str, float]]:
    mapped: dict[str, dict[str, float]] = {}
    for run in summary.get("runs", []):
        scenario = run.get("scenario")
        if not scenario:
            continue
        mapped[scenario] = {key: float(run[key]) for key in METRIC_KEYS if run.get(key) is not None}
    return mapped


def pct_delta(current: float, reference: float) -> float | None:
    if reference == 0:
        return None
    return (current - reference) / reference * 100.0


def compare(current: dict[str, dict[str, float]], baseline: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    base_metrics = baseline.get("metrics", {})
    for scenario, metrics in current.items():
        reference = base_metrics.get(scenario, {})
        scenario_result: dict[str, Any] = {}
        for key, value in metrics.items():
            ref_value = reference.get(key)
            if ref_value is None:
                scenario_result[key] = {"current": value, "baseline": None, "delta_percent": None, "status": "missing"}
                continue
            delta = pct_delta(value, float(ref_value))
            regressed = value > ref_value if key in LOWER_IS_BETTER else value < ref_value
            scenario_result[key] = {
                "current": value,
                "baseline": float(ref_value),
                "delta_percent": delta,
                "status": "regression" if regressed else "ok",
            }
        result[scenario] = scenario_result
    return result


def main() -> int:
    args = parse_args()
    summary = load_json(Path(args.summary))
    manifest, primary, secondary = load_baselines(Path(args.baseline_root))
    current = make_map(summary)

    payload = {
        "schema_version": 1,
        "manifest": manifest,
        "summary_generated_at": summary.get("generated_at"),
        "comparison": {
            "primary": {
                "reference": manifest["primary"],
                "result": compare(current, primary),
            },
            "secondary": {
                "reference": manifest["secondary"],
                "result": compare(current, secondary),
            },
        },
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
