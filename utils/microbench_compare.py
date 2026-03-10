#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compare microbench summary against thresholds and optional baseline commit")
    p.add_argument("--current", default="artifacts/microbench-summary.json")
    p.add_argument("--baseline", default="", help="Optional baseline microbench summary")
    p.add_argument("--thresholds", default="perf-baseline/microbench-thresholds.json")
    p.add_argument("--output-json", default="artifacts/microbench-comparison.json")
    p.add_argument("--output-md", default="artifacts/microbench-comparison.md")
    p.add_argument("--fail-on-regression", action="store_true")
    return p.parse_args()


def load(path: str) -> dict:
    return json.loads(Path(path).read_text())


def to_map(summary: dict) -> dict[str, dict]:
    return {b["name"]: b for b in summary.get("benchmarks", [])}


def main() -> int:
    args = parse_args()
    current = load(args.current)
    baseline = load(args.baseline) if args.baseline else {"benchmarks": []}
    thresholds = load(args.thresholds)

    cur = to_map(current)
    base = to_map(baseline)
    rows: list[dict] = []
    has_regression = False

    for name, entry in cur.items():
        limits = thresholds.get("benchmarks", {}).get(name, {})
        ns = float(entry["ns_per_op"]["mean"])
        allocs = float(entry["allocations_per_op"]["mean"])
        bytes_ = float(entry["bytes_per_op"]["mean"])

        base_entry = base.get(name)
        base_ns = float(base_entry["ns_per_op"]["mean"]) if base_entry else None
        delta_pct = (((ns - base_ns) / base_ns) * 100.0) if base_ns not in (None, 0.0) else None

        ns_limit = limits.get("max_ns_per_op")
        allocs_limit = limits.get("max_allocations_per_op")
        bytes_limit = limits.get("max_bytes_per_op")
        max_commit_delta = limits.get("max_commit_delta_pct")

        fails = []
        if ns_limit is not None and ns > float(ns_limit):
            fails.append(f"ns>{ns_limit}")
        if allocs_limit is not None and allocs > float(allocs_limit):
            fails.append(f"allocs>{allocs_limit}")
        if bytes_limit is not None and bytes_ > float(bytes_limit):
            fails.append(f"bytes>{bytes_limit}")
        if delta_pct is not None and max_commit_delta is not None and delta_pct > float(max_commit_delta):
            fails.append(f"delta>{max_commit_delta}%")

        if fails:
            has_regression = True

        rows.append(
            {
                "name": name,
                "ns_per_op": ns,
                "allocations_per_op": allocs,
                "bytes_per_op": bytes_,
                "baseline_ns_per_op": base_ns,
                "delta_pct": delta_pct,
                "failures": fails,
                "status": "regression" if fails else "ok",
            }
        )

    out = {
        "current_commit": current.get("commit"),
        "baseline_commit": baseline.get("commit"),
        "rows": sorted(rows, key=lambda r: r["name"]),
        "has_regression": has_regression,
    }

    Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_json).write_text(json.dumps(out, indent=2) + "\n")

    lines = [
        "# Microbench Comparison",
        "",
        f"Current commit: `{out['current_commit']}`",
        f"Baseline commit: `{out['baseline_commit']}`" if out["baseline_commit"] else "Baseline commit: `n/a`",
        "",
        "| Benchmark | ns/op | alloc/op | bytes/op | delta vs baseline | status |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in out["rows"]:
        delta = "n/a" if row["delta_pct"] is None else f"{row['delta_pct']:.2f}%"
        status = row["status"] if not row["failures"] else f"regression ({', '.join(row['failures'])})"
        lines.append(
            f"| {row['name']} | {row['ns_per_op']:.2f} | {row['allocations_per_op']:.4f} | {row['bytes_per_op']:.2f} | {delta} | {status} |"
        )
    Path(args.output_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_md).write_text("\n".join(lines) + "\n")

    if args.fail_on_regression and has_regression:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
