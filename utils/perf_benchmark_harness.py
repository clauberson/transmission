#!/usr/bin/env python3

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

EXIT_INVALID_ARGS = 2
EXIT_SETUP_FAILED = 10
EXIT_WARMUP_FAILED = 20
EXIT_MEASURE_FAILED = 30
EXIT_SUMMARY_FAILED = 40
EXIT_PHASE_TIMEOUT = 50

NETWORK_PROFILES: dict[str, dict[str, Any]] = {
    "lan": {"latency_ms": 2, "jitter_ms": 1, "loss_percent": 0.0, "bandwidth_mbps": 1000},
    "wan": {"latency_ms": 35, "jitter_ms": 8, "loss_percent": 0.2, "bandwidth_mbps": 300},
    "lossy": {"latency_ms": 85, "jitter_ms": 20, "loss_percent": 1.5, "bandwidth_mbps": 120},
}

SCENARIO_FACTORS = {"A": 1, "B": 2, "C": 3, "D": 4}

DEFAULT_PHASE_SECONDS = {
    "smoke": {"warmup": 120, "measure": 480},
    "full": {"warmup": 300, "measure": 1200},
}

METRIC_KEYS = ("download_bps", "upload_bps", "latency_ms", "cpu_avg", "cpu_peak", "rss_avg", "rss_peak")


@dataclasses.dataclass
class PhaseResult:
    phase: str
    duration_seconds: int
    exit_code: int
    metrics: dict[str, Any]


@dataclasses.dataclass
class RunResult:
    scenario: str
    run_id: str
    network_profile: str
    n: int
    seed: int
    phases: list[PhaseResult]
    branch: str
    commit: str
    release: str
    hardware_profile: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reproducible benchmark harness for Transmission scenarios A/B/C/D")
    parser.add_argument("--mode", choices=["smoke", "full"], default="smoke", help="Execution preset")
    parser.add_argument("--scenarios", default="A,B,C,D", help="Comma-separated list, e.g. A,D")
    parser.add_argument("-N", "--n", type=int, default=200, help="Base workload size")
    parser.add_argument("--warmup-seconds", type=int, help="Override warm-up phase duration")
    parser.add_argument("--measure-seconds", type=int, help="Override measurement phase duration")
    parser.add_argument("--network-profile", choices=sorted(NETWORK_PROFILES), default="wan", help="Network profile")
    parser.add_argument("--output-root", default="artifacts", help="Output root")
    parser.add_argument("--run-id", help="Optional stable run id (default: UTC timestamp)")
    parser.add_argument("--seed", type=int, default=7, help="Deterministic seed for synthetic baseline metrics")
    parser.add_argument(
        "--phase-command",
        default=(
            "python3 -c \"import json,time,os,random;"
            "random.seed(int(os.environ['TR_BENCH_SEED'])+int(os.environ['TR_BENCH_SCENARIO_FACTOR']));"
            "d=int(os.environ['TR_BENCH_PHASE_SECONDS']);"
            "f=float(os.environ['TR_BENCH_SCENARIO_FACTOR']);"
            "n=int(os.environ['TR_BENCH_N']);"
            "time.sleep(min(d,2));"
            "m={'download_bps': n*180000*f*(1+random.uniform(-0.03,0.03)),'upload_bps': n*45000*f*(1+random.uniform(-0.03,0.03)),"
            "'latency_ms': 20.0*f*(1+random.uniform(-0.08,0.08)),"
            "'cpu_avg':8.0*f+random.uniform(-0.4,0.4),'cpu_peak':12.0*f+random.uniform(-0.8,0.8),"
            "'rss_avg': n*4000000*f,'rss_peak': n*4600000*f};"
            "print(json.dumps(m))\""
        ),
        help=(
            "Command run for each phase. It must print one JSON object to stdout with keys: "
            "download_bps, upload_bps, latency_ms, cpu_avg, cpu_peak, rss_avg, rss_peak"
        ),
    )
    parser.add_argument("--phase-timeout-seconds", type=int, default=1800, help="Timeout per phase")
    parser.add_argument("--branch", default=os.environ.get("GITHUB_REF_NAME", "unknown"), help="Branch associada ao benchmark")
    parser.add_argument("--commit", default=os.environ.get("GITHUB_SHA", "unknown"), help="Commit associada ao benchmark")
    parser.add_argument("--release", default="", help="Release/tag associada ao benchmark (opcional)")
    parser.add_argument("--hardware-profile", default="default", help="Perfil de hardware usado no benchmark")
    parser.add_argument("--tc-netem-script", default="./utils/tc_netem_profiles.py", help="Script used to apply tc/netem profiles")
    parser.add_argument("--scenario-d-netem-profile", choices=["profile_1", "profile_2", "profile_3"], help="Apply tc/netem profile only for scenario D")
    parser.add_argument("--tc-interface", help="Network interface used by tc/netem when scenario D profile is enabled")
    parser.add_argument("--force", action="store_true", help="Overwrite existing run directories")
    return parser.parse_args()


def now_run_id() -> str:
    return dt.datetime.now(dt.UTC).strftime("run-%Y%m%dT%H%M%SZ")


def parse_scenarios(raw: str) -> list[str]:
    scenarios = [value.strip().upper() for value in raw.split(",") if value.strip()]
    unknown = [value for value in scenarios if value not in SCENARIO_FACTORS]
    if unknown:
        raise ValueError(f"Unknown scenarios: {', '.join(unknown)}")
    if not scenarios:
        raise ValueError("At least one scenario is required")
    return scenarios


def run_phase(*, cmd: str, env: dict[str, str], timeout_seconds: int, cwd: Path) -> tuple[int, dict[str, Any], str, str]:
    completed = subprocess.run(
        cmd,
        cwd=cwd,
        shell=True,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    payload = {}
    for line in completed.stdout.splitlines()[::-1]:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
            break
        except json.JSONDecodeError:
            continue
    return completed.returncode, payload, completed.stdout, completed.stderr



def run_netem_script(*, script: str, command: str, profile: str | None, interface: str, cwd: Path) -> tuple[int, str, str]:
    args = [script, command, "--interface", interface]
    if profile is not None:
        args.extend(["--profile", profile])
    completed = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr

def aggregate(run_results: list[RunResult], output_root: Path) -> dict[str, Any]:
    summary_runs: list[dict[str, Any]] = []
    for run in run_results:
        measure = next((phase for phase in run.phases if phase.phase == "measurement"), None)
        metrics = measure.metrics if measure is not None else {}
        summary_runs.append(
            {
                "scenario": run.scenario,
                "run_id": run.run_id,
                "network_profile": run.network_profile,
                "branch": run.branch,
                "commit": run.commit,
                "release": run.release,
                "hardware_profile": run.hardware_profile,
                "N": run.n,
                "seed": run.seed,
                **{key: metrics.get(key) for key in METRIC_KEYS},
            }
        )
    return {
        "schema_version": 1,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "output_root": str(output_root),
        "metadata": {
            "branch": run_results[0].branch if run_results else "unknown",
            "commit": run_results[0].commit if run_results else "unknown",
            "release": run_results[0].release if run_results else "",
            "hardware_profile": run_results[0].hardware_profile if run_results else "default",
        },
        "runs": summary_runs,
    }


def main() -> int:
    try:
        args = parse_args()
        scenarios = parse_scenarios(args.scenarios)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INVALID_ARGS

    if args.n <= 0:
        print("error: N must be > 0", file=sys.stderr)
        return EXIT_INVALID_ARGS
    if args.scenario_d_netem_profile and not args.tc_interface:
        print("error: --tc-interface is required when --scenario-d-netem-profile is set", file=sys.stderr)
        return EXIT_INVALID_ARGS

    output_root = Path(args.output_root)
    run_id = args.run_id or now_run_id()
    warmup_seconds = args.warmup_seconds or DEFAULT_PHASE_SECONDS[args.mode]["warmup"]
    measure_seconds = args.measure_seconds or DEFAULT_PHASE_SECONDS[args.mode]["measure"]

    try:
        output_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"error: cannot create output root: {exc}", file=sys.stderr)
        return EXIT_SETUP_FAILED

    run_results: list[RunResult] = []

    for scenario in scenarios:
        scenario_dir = output_root / scenario / run_id
        if scenario_dir.exists() and args.force:
            shutil.rmtree(scenario_dir)
        try:
            scenario_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            print(f"error: run directory already exists: {scenario_dir} (use --force)", file=sys.stderr)
            return EXIT_SETUP_FAILED
        except OSError as exc:
            print(f"error: cannot create scenario dir {scenario_dir}: {exc}", file=sys.stderr)
            return EXIT_SETUP_FAILED

        factor = SCENARIO_FACTORS[scenario]
        scenario_n = args.n * factor
        profile = NETWORK_PROFILES[args.network_profile]
        phases: list[PhaseResult] = []
        netem_applied = False

        try:
            if scenario == "D" and args.scenario_d_netem_profile:
                apply_code, netem_stdout, netem_stderr = run_netem_script(
                    script=args.tc_netem_script,
                    command="apply",
                    profile=args.scenario_d_netem_profile,
                    interface=args.tc_interface,
                    cwd=Path.cwd(),
                )
                (scenario_dir / "netem-setup.log").write_text(netem_stdout)
                (scenario_dir / "netem-setup.err").write_text(netem_stderr)
                if apply_code != 0:
                    print(f"error: failed to apply netem for scenario D (exit={apply_code})", file=sys.stderr)
                    return EXIT_SETUP_FAILED
                netem_applied = True

            for phase_name, phase_seconds in (("warmup", warmup_seconds), ("measurement", measure_seconds)):
                env = os.environ.copy()
                env.update(
                    {
                        "TR_BENCH_MODE": args.mode,
                        "TR_BENCH_SCENARIO": scenario,
                        "TR_BENCH_SCENARIO_FACTOR": str(factor),
                        "TR_BENCH_NETWORK_PROFILE": args.network_profile,
                        "TR_BENCH_NETWORK_PROFILE_JSON": json.dumps(profile),
                        "TR_BENCH_PHASE": phase_name,
                        "TR_BENCH_PHASE_SECONDS": str(phase_seconds),
                        "TR_BENCH_N": str(scenario_n),
                        "TR_BENCH_RUN_ID": run_id,
                        "TR_BENCH_OUTPUT_DIR": str(scenario_dir),
                        "TR_BENCH_SEED": str(args.seed),
                    }
                )

                try:
                    code, payload, stdout, stderr = run_phase(
                        cmd=args.phase_command,
                        env=env,
                        timeout_seconds=args.phase_timeout_seconds,
                        cwd=Path.cwd(),
                    )
                except subprocess.TimeoutExpired:
                    print(f"error: {scenario} {phase_name} timed out after {args.phase_timeout_seconds}s", file=sys.stderr)
                    return EXIT_PHASE_TIMEOUT

                phase_metrics = payload if isinstance(payload, dict) else {}
                phases.append(PhaseResult(phase=phase_name, duration_seconds=phase_seconds, exit_code=code, metrics=phase_metrics))

                log_path = scenario_dir / f"{phase_name}.log"
                err_path = scenario_dir / f"{phase_name}.err"
                log_path.write_text(stdout)
                err_path.write_text(stderr)

                if code != 0:
                    print(f"error: scenario {scenario} failed during {phase_name} (exit={code})", file=sys.stderr)
                    return EXIT_WARMUP_FAILED if phase_name == "warmup" else EXIT_MEASURE_FAILED
        finally:
            if scenario == "D" and args.scenario_d_netem_profile and args.tc_interface and netem_applied:
                teardown_code, td_stdout, td_stderr = run_netem_script(
                    script=args.tc_netem_script,
                    command="teardown",
                    profile=None,
                    interface=args.tc_interface,
                    cwd=Path.cwd(),
                )
                (scenario_dir / "netem-teardown.log").write_text(td_stdout)
                (scenario_dir / "netem-teardown.err").write_text(td_stderr)
                if teardown_code != 0:
                    print(f"error: failed to teardown netem for scenario D (exit={teardown_code})", file=sys.stderr)
                    return EXIT_SETUP_FAILED

        metrics_doc = {
            "schema_version": 1,
            "scenario": scenario,
            "run_id": run_id,
            "network_profile": args.network_profile,
            "branch": args.branch,
            "commit": args.commit,
            "release": args.release,
            "hardware_profile": args.hardware_profile,
            "N": scenario_n,
            "seed": args.seed,
            "phases": [dataclasses.asdict(phase) for phase in phases],
            "netem_profile": args.scenario_d_netem_profile if scenario == "D" else None,
            "netem_interface": args.tc_interface if scenario == "D" else None,
        }
        (scenario_dir / "metrics.json").write_text(json.dumps(metrics_doc, indent=2) + "\n")

        run_results.append(
            RunResult(
                scenario=scenario,
                run_id=run_id,
                network_profile=args.network_profile,
                n=scenario_n,
                seed=args.seed,
                phases=phases,
                branch=args.branch,
                commit=args.commit,
                release=args.release,
                hardware_profile=args.hardware_profile,
            )
        )

    try:
        summary = aggregate(run_results, output_root)
        (output_root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    except OSError as exc:
        print(f"error: failed writing summary: {exc}", file=sys.stderr)
        return EXIT_SUMMARY_FAILED

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
