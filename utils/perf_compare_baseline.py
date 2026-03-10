#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

METRIC_KEYS = ("download_bps", "upload_bps", "latency_ms", "cpu_avg", "cpu_peak", "rss_avg", "rss_peak")
DEFAULT_RULES: dict[str, dict[str, Any]] = {
    "download_bps": {"direction": "higher_is_better", "warn_percent": 3.0, "critical_percent": 7.0, "alpha_warn": 0.10, "alpha_critical": 0.05},
    "upload_bps": {"direction": "higher_is_better", "warn_percent": 3.0, "critical_percent": 7.0, "alpha_warn": 0.10, "alpha_critical": 0.05},
    "latency_ms": {"direction": "lower_is_better", "warn_percent": 3.0, "critical_percent": 7.0, "alpha_warn": 0.10, "alpha_critical": 0.05},
    "cpu_avg": {"direction": "lower_is_better", "warn_percent": 3.0, "critical_percent": 7.0, "alpha_warn": 0.10, "alpha_critical": 0.05},
    "cpu_peak": {"direction": "lower_is_better", "warn_percent": 3.0, "critical_percent": 7.0, "alpha_warn": 0.10, "alpha_critical": 0.05},
    "rss_avg": {"direction": "lower_is_better", "warn_percent": 3.0, "critical_percent": 7.0, "alpha_warn": 0.10, "alpha_critical": 0.05},
    "rss_peak": {"direction": "lower_is_better", "warn_percent": 3.0, "critical_percent": 7.0, "alpha_warn": 0.10, "alpha_critical": 0.05},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analisador estatístico para comparação current vs baseline")
    parser.add_argument("--summary", default="artifacts/summary.json")
    parser.add_argument("--baseline-root", default="perf-baseline")
    parser.add_argument("--rules", default="perf-baseline/kpi-rules.json")
    parser.add_argument("--output-json", default="artifacts/baseline-comparison.json")
    parser.add_argument("--output-md", default="artifacts/baseline-comparison.md")
    parser.add_argument("--fail-on", choices=["never", "warn", "critical"], default="never")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def load_baselines(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest = load_json(root / "manifest.json")
    primary = load_json(root / manifest["primary"]["path"])
    secondary = load_json(root / manifest["secondary"]["path"])
    return manifest, primary, secondary


def load_rules(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return DEFAULT_RULES
    payload = load_json(path)
    merged = dict(DEFAULT_RULES)
    for key, value in payload.get("kpis", {}).items():
        base = dict(merged.get(key, {}))
        base.update(value)
        merged[key] = base
    return merged


def make_current_samples(summary: dict[str, Any]) -> dict[str, dict[str, list[float]]]:
    mapped: dict[str, dict[str, list[float]]] = {}
    for run in summary.get("runs", []):
        scenario = run.get("scenario")
        if not scenario:
            continue
        scenario_map = mapped.setdefault(scenario, {})
        for key in METRIC_KEYS:
            value = run.get(key)
            if value is None:
                continue
            scenario_map.setdefault(key, []).append(float(value))
    return mapped


def baseline_samples_for(reference: dict[str, Any], scenario: str, metric: str) -> list[float]:
    value = reference.get("metrics", {}).get(scenario, {}).get(metric)
    if value is None:
        return []
    if isinstance(value, list):
        return [float(v) for v in value]
    return [float(value)]


def median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    m = n // 2
    if n % 2 == 1:
        return ordered[m]
    return (ordered[m - 1] + ordered[m]) / 2.0


def pct_delta(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline in (None, 0):
        return None
    return (current - baseline) / baseline * 100.0


def rankdata(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda p: p[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def mann_whitney_pvalue(x: list[float], y: list[float]) -> float | None:
    if len(x) < 2 or len(y) < 2:
        return None
    combined = x + y
    ranks = rankdata(combined)
    n1 = len(x)
    n2 = len(y)
    r1 = sum(ranks[:n1])
    u1 = r1 - n1 * (n1 + 1) / 2.0
    mean_u = n1 * n2 / 2.0

    tie_counts: dict[float, int] = {}
    for value in combined:
        tie_counts[value] = tie_counts.get(value, 0) + 1
    tie_term = sum((count**3 - count) for count in tie_counts.values())
    n = n1 + n2
    if n <= 1:
        return None
    var_u = (n1 * n2 / 12.0) * (n + 1 - tie_term / (n * (n - 1)))
    if var_u <= 0:
        return None

    z = (u1 - mean_u) / math.sqrt(var_u)
    cdf = 0.5 * (1.0 + math.erf(abs(z) / math.sqrt(2.0)))
    p = 2.0 * (1.0 - cdf)
    return max(0.0, min(1.0, p))


def classify(delta: float | None, pvalue: float | None, rules: dict[str, Any]) -> tuple[str, str]:
    if delta is None or pvalue is None:
        return "Info", "inconclusive"

    direction = rules["direction"]
    regress = delta < 0 if direction == "higher_is_better" else delta > 0
    improve = delta > 0 if direction == "higher_is_better" else delta < 0
    abs_delta = abs(delta)

    if regress and abs_delta >= float(rules["critical_percent"]) and pvalue <= float(rules["alpha_critical"]):
        return "Critical", "regression"
    if regress and abs_delta >= float(rules["warn_percent"]) and pvalue <= float(rules["alpha_warn"]):
        return "Warn", "regression"
    if improve and abs_delta >= float(rules["warn_percent"]) and pvalue <= float(rules["alpha_warn"]):
        return "Info", "improvement"
    return "Info", "inconclusive"


def compare_source(
    *,
    source_name: str,
    current: dict[str, dict[str, list[float]]],
    baseline: dict[str, Any],
    rules: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    totals = {"Info": 0, "Warn": 0, "Critical": 0}

    scenarios = sorted(set(current.keys()) | set(baseline.get("metrics", {}).keys()))
    for scenario in scenarios:
        for metric in METRIC_KEYS:
            current_samples = current.get(scenario, {}).get(metric, [])
            baseline_samples = baseline_samples_for(baseline, scenario, metric)
            current_med = median(current_samples)
            baseline_med = median(baseline_samples)
            delta = pct_delta(current_med, baseline_med)
            pvalue = mann_whitney_pvalue(current_samples, baseline_samples)
            metric_rules = rules.get(metric, DEFAULT_RULES[metric])
            severity, decision = classify(delta, pvalue, metric_rules)
            totals[severity] += 1

            rows.append(
                {
                    "source": source_name,
                    "scenario": scenario,
                    "metric": metric,
                    "current_samples": current_samples,
                    "baseline_samples": baseline_samples,
                    "current_median": current_med,
                    "baseline_median": baseline_med,
                    "delta_percent": delta,
                    "p_value": pvalue,
                    "severity": severity,
                    "decision": decision,
                }
            )

    return {"rows": rows, "totals": totals}


def fmt(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}{suffix}"


def build_markdown(report: dict[str, Any]) -> str:
    lines = ["# Performance Baseline Comparison", ""]
    for name in ("primary", "secondary"):
        section = report["comparison"][name]
        totals = section["totals"]
        lines.extend(
            [
                f"## {name.title()} baseline",
                f"Info: {totals['Info']} | Warn: {totals['Warn']} | Critical: {totals['Critical']}",
                "",
                "| Scenario | KPI | Current (median) | Baseline (median) | Delta % | p-value | Severity | Decision |",
                "|---|---|---:|---:|---:|---:|---|---|",
            ]
        )
        for row in section["rows"]:
            lines.append(
                "| {scenario} | {metric} | {current} | {baseline} | {delta} | {pvalue} | {sev} | {dec} |".format(
                    scenario=row["scenario"],
                    metric=row["metric"],
                    current=fmt(row["current_median"]),
                    baseline=fmt(row["baseline_median"]),
                    delta=fmt(row["delta_percent"], "%"),
                    pvalue=fmt(row["p_value"]),
                    sev=row["severity"],
                    dec=row["decision"],
                )
            )
        lines.append("")
    return "\n".join(lines)


def should_fail(report: dict[str, Any], mode: str) -> bool:
    if mode == "never":
        return False
    for name in ("primary", "secondary"):
        totals = report["comparison"][name]["totals"]
        if mode == "critical" and totals["Critical"] > 0:
            return True
        if mode == "warn" and (totals["Warn"] > 0 or totals["Critical"] > 0):
            return True
    return False


def main() -> int:
    args = parse_args()
    summary = load_json(Path(args.summary))
    manifest, primary, secondary = load_baselines(Path(args.baseline_root))
    rules = load_rules(Path(args.rules))
    current = make_current_samples(summary)

    report = {
        "schema_version": 2,
        "summary_generated_at": summary.get("generated_at"),
        "manifest": manifest,
        "rules": rules,
        "comparison": {
            "primary": compare_source(source_name="primary", current=current, baseline=primary, rules=rules),
            "secondary": compare_source(source_name="secondary", current=current, baseline=secondary, rules=rules),
        },
    }

    markdown = build_markdown(report)
    report["markdown_path"] = args.output_md

    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2) + "\n")
    output_md.write_text(markdown)

    print(json.dumps(report, indent=2))
    return 1 if should_fail(report, args.fail_on) else 0


if __name__ == "__main__":
    raise SystemExit(main())
