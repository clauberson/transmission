#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

KPI_GROUPS = {
    "throughput": ["download_bps", "upload_bps"],
    "latency": ["latency_ms"],
    "cpu": ["cpu_avg", "cpu_peak"],
    "memory": ["rss_avg", "rss_peak"],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Consolida artefatos de benchmark e gera dashboard estático")
    parser.add_argument("--artifacts-root", default="artifacts", help="Raiz com resumos benchmark")
    parser.add_argument("--comparison", default="artifacts/baseline-comparison.json", help="Resultado de perf_compare_baseline")
    parser.add_argument("--output-json", default="artifacts/perf-dashboard/data.json")
    parser.add_argument("--output-html", default="artifacts/perf-dashboard/index.html")
    return parser.parse_args()


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    pos = (len(ordered) - 1) * pct
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    frac = pos - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def trend(values: list[float]) -> str:
    if len(values) < 2:
        return "stable"
    first = statistics.median(values[: max(1, len(values) // 3)])
    last = statistics.median(values[-max(1, len(values) // 3) :])
    if first == 0:
        return "stable"
    delta = (last - first) / abs(first)
    if delta > 0.03:
        return "up"
    if delta < -0.03:
        return "down"
    return "stable"


def load_summary_files(artifacts_root: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in sorted(artifacts_root.glob("**/summary.json")):
        try:
            results.append(json.loads(path.read_text()))
        except json.JSONDecodeError:
            continue
    return results


def build_dataset(summaries: list[dict[str, Any]], comparison: dict[str, Any] | None) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str, str, str], list[float]] = {}

    for summary in summaries:
        generated_at = summary.get("generated_at")
        for run in summary.get("runs", []):
            branch = run.get("branch") or summary.get("metadata", {}).get("branch", "unknown")
            hardware = run.get("hardware_profile") or summary.get("metadata", {}).get("hardware_profile", "default")
            scenario = run.get("scenario", "unknown")
            commit = run.get("commit") or summary.get("metadata", {}).get("commit", "unknown")
            release = run.get("release") or summary.get("metadata", {}).get("release", "")
            for group_name, kpis in KPI_GROUPS.items():
                for kpi in kpis:
                    value = run.get(kpi)
                    if value is None:
                        continue
                    value = float(value)
                    records.append(
                        {
                            "generated_at": generated_at,
                            "scenario": scenario,
                            "branch": branch,
                            "commit": commit,
                            "release": release,
                            "hardware_profile": hardware,
                            "group": group_name,
                            "kpi": kpi,
                            "value": value,
                        }
                    )
                    grouped.setdefault((branch, hardware, scenario, kpi), []).append(value)

    distributions = []
    for (branch, hardware, scenario, kpi), values in sorted(grouped.items()):
        q1 = percentile(values, 0.25)
        q3 = percentile(values, 0.75)
        distributions.append(
            {
                "branch": branch,
                "hardware_profile": hardware,
                "scenario": scenario,
                "kpi": kpi,
                "median": percentile(values, 0.50),
                "iqr": q3 - q1,
                "p95": percentile(values, 0.95),
                "p99": percentile(values, 0.99),
                "trend": trend(values),
                "samples": len(values),
            }
        )

    severity_totals = {"Info": 0, "Warn": 0, "Critical": 0}
    severity_rows: list[dict[str, Any]] = []
    if comparison:
        for source in ("primary", "secondary"):
            section = comparison.get("comparison", {}).get(source, {})
            for severity in severity_totals:
                severity_totals[severity] += int(section.get("totals", {}).get(severity, 0))
            for row in section.get("rows", []):
                severity_rows.append(
                    {
                        "source": source,
                        "scenario": row.get("scenario"),
                        "kpi": row.get("metric"),
                        "severity": row.get("severity", "Info"),
                        "decision": row.get("decision"),
                        "delta_percent": row.get("delta_percent"),
                    }
                )

    return {
        "schema_version": 1,
        "records": records,
        "distributions": distributions,
        "severity_totals": severity_totals,
        "severity_rows": severity_rows,
    }


HTML = """<!doctype html>
<html lang=\"pt-br\"><head><meta charset=\"utf-8\"><title>Performance Dashboard</title>
<style>body{font-family:Arial,sans-serif;margin:20px}table{border-collapse:collapse;width:100%;margin:8px 0}th,td{border:1px solid #ddd;padding:6px;font-size:12px}.chip{padding:4px 8px;border-radius:8px;color:#fff;margin-right:8px}.Info{background:#3b82f6}.Warn{background:#f59e0b}.Critical{background:#ef4444}</style>
</head><body>
<h1>Dashboard de Performance por Cenário/KPI</h1>
<div>Filtros: Branch <select id=branch></select> Hardware <select id=hw></select></div>
<h2>Alertas</h2><div id=alerts></div>
<h2>Distribuição (mediana, IQR, P95/P99)</h2><table id=dist><thead><tr><th>Painel</th><th>Cenário</th><th>KPI</th><th>Mediana</th><th>IQR</th><th>P95</th><th>P99</th><th>Tendência</th><th>Amostras</th></tr></thead><tbody></tbody></table>
<h2>Regressões por severidade</h2><table id=sev><thead><tr><th>Baseline</th><th>Cenário</th><th>KPI</th><th>Severidade</th><th>Decisão</th><th>Delta %</th></tr></thead><tbody></tbody></table>
<script>
const data=__DATA__;
const branchSel=document.getElementById('branch');
const hwSel=document.getElementById('hw');
function uniq(arr){return [...new Set(arr)]}
function opts(sel,vals){sel.innerHTML='<option value="*">Todos</option>'+vals.map(v=>`<option>${v}</option>`).join('')}
opts(branchSel,uniq(data.records.map(r=>r.branch)).sort());
opts(hwSel,uniq(data.records.map(r=>r.hardware_profile)).sort());
function panelFor(kpi){for (const [g,ks] of Object.entries({throughput:['download_bps','upload_bps'],latency:['latency_ms'],cpu:['cpu_avg','cpu_peak'],memory:['rss_avg','rss_peak']})){if(ks.includes(kpi)) return g;} return 'other';}
function render(){
 const b=branchSel.value,h=hwSel.value;
 const d=data.distributions.filter(r=>(b==='*'||r.branch===b)&&(h==='*'||r.hardware_profile===h));
 document.querySelector('#dist tbody').innerHTML=d.map(r=>`<tr><td>${panelFor(r.kpi)}</td><td>${r.scenario}</td><td>${r.kpi}</td><td>${r.median.toFixed(2)}</td><td>${r.iqr.toFixed(2)}</td><td>${r.p95.toFixed(2)}</td><td>${r.p99.toFixed(2)}</td><td>${r.trend}</td><td>${r.samples}</td></tr>`).join('');
 const sev=data.severity_rows.filter(r=>d.some(x=>x.scenario===r.scenario&&x.kpi===r.kpi));
 document.querySelector('#sev tbody').innerHTML=sev.map(r=>`<tr><td>${r.source}</td><td>${r.scenario}</td><td>${r.kpi}</td><td>${r.severity}</td><td>${r.decision}</td><td>${(r.delta_percent??0).toFixed? r.delta_percent.toFixed(2):'n/a'}</td></tr>`).join('');
 document.getElementById('alerts').innerHTML=['Info','Warn','Critical'].map(s=>`<span class="chip ${s}">${s}: ${data.severity_totals[s]||0}</span>`).join('');
}
branchSel.onchange=render;hwSel.onchange=render;render();
</script></body></html>"""


def main() -> int:
    args = parse_args()
    summaries = load_summary_files(Path(args.artifacts_root))
    comparison_path = Path(args.comparison)
    comparison = json.loads(comparison_path.read_text()) if comparison_path.exists() else None
    dataset = build_dataset(summaries, comparison)

    out_json = Path(args.output_json)
    out_html = Path(args.output_html)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(dataset, indent=2) + "\n")
    out_html.write_text(HTML.replace("__DATA__", json.dumps(dataset)))
    print(json.dumps({"records": len(dataset["records"]), "dist": len(dataset["distributions"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
