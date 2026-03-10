#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

METRIC_KEYS = ("download_bps", "upload_bps", "cpu_avg", "cpu_peak", "rss_avg", "rss_peak")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Atualiza baseline de performance com trilha de auditoria")
    parser.add_argument("--summary", default="artifacts/summary.json", help="Resumo gerado pelo benchmark harness")
    parser.add_argument("--baseline-root", default="perf-baseline", help="Diretório do baseline versionado")
    parser.add_argument("--kind", choices=["release", "moving-average-main"], required=True)
    parser.add_argument("--author", required=True, help="Responsável pela atualização")
    parser.add_argument("--reason", required=True, help="Motivo da atualização")
    parser.add_argument("--release", help="Tag do release quando --kind=release")
    parser.add_argument("--commit", required=True, help="Commit referência para rastreabilidade")
    parser.add_argument("--window", type=int, default=10, help="Janela da média móvel da main")
    parser.add_argument("--source-workflow", default="benchmark-harness", help="Workflow origem dos dados")
    parser.add_argument("--run-id", default="manual", help="Identificador da execução benchmark")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def extract_metrics(summary: dict[str, Any]) -> dict[str, dict[str, float]]:
    runs = summary.get("runs", [])
    metrics: dict[str, dict[str, float]] = {}
    for run in runs:
        scenario = run.get("scenario")
        if not scenario:
            continue
        metrics[scenario] = {key: float(run[key]) for key in METRIC_KEYS if key in run and run[key] is not None}
    if not metrics:
        raise ValueError("summary sem métricas válidas")
    return metrics


def update_release(*, args: argparse.Namespace, baseline_root: Path, summary: dict[str, Any], metrics: dict[str, dict[str, float]]) -> None:
    if not args.release:
        raise ValueError("--release é obrigatório para kind=release")
    release_path = baseline_root / "releases" / f"{args.release}.json"
    release_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema_version": 1,
        "baseline_kind": "release",
        "release": args.release,
        "commit": args.commit,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "source": {
            "workflow": args.source_workflow,
            "run_id": args.run_id,
            "summary_path": str(Path(args.summary)),
            "summary_generated_at": summary.get("generated_at"),
        },
        "audit": {
            "author": args.author,
            "reason": args.reason,
            "date": dt.datetime.now(dt.UTC).isoformat(),
        },
        "metrics": metrics,
    }
    release_path.write_text(json.dumps(payload, indent=2) + "\n")

    manifest_path = baseline_root / "manifest.json"
    manifest = load_json(manifest_path) if manifest_path.exists() else {"schema_version": 1}
    manifest["primary"] = {
        "type": "release",
        "latest_stable": args.release,
        "path": f"releases/{args.release}.json",
    }
    if "secondary" not in manifest:
        manifest["secondary"] = {"type": "moving_average_main", "window": args.window, "path": "main/moving-average.json"}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


def update_moving_average(*, args: argparse.Namespace, baseline_root: Path, summary: dict[str, Any], metrics: dict[str, dict[str, float]]) -> None:
    moving_path = baseline_root / "main" / "moving-average.json"
    moving_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, Any] = load_json(moving_path) if moving_path.exists() else {}
    sampled_commits: list[str] = [args.commit]
    sampled_commits.extend(existing.get("sampled_commits", []))
    sampled_commits = sampled_commits[: args.window]

    payload = {
        "schema_version": 1,
        "baseline_kind": "moving_average_main",
        "branch": "main",
        "window": args.window,
        "updated_at": dt.datetime.now(dt.UTC).isoformat(),
        "sampled_commits": sampled_commits,
        "source": {
            "workflow": args.source_workflow,
            "run_id": args.run_id,
            "summary_path": str(Path(args.summary)),
            "summary_generated_at": summary.get("generated_at"),
        },
        "audit": {
            "author": args.author,
            "reason": args.reason,
            "date": dt.datetime.now(dt.UTC).isoformat(),
        },
        "metrics": metrics,
    }
    moving_path.write_text(json.dumps(payload, indent=2) + "\n")


def main() -> int:
    args = parse_args()
    summary = load_json(Path(args.summary))
    metrics = extract_metrics(summary)
    baseline_root = Path(args.baseline_root)

    if args.kind == "release":
        update_release(args=args, baseline_root=baseline_root, summary=summary, metrics=metrics)
    else:
        update_moving_average(args=args, baseline_root=baseline_root, summary=summary, metrics=metrics)
    print("baseline atualizado com auditoria")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
