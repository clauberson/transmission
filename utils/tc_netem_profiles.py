#!/usr/bin/env python3

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

PROFILES: dict[str, dict[str, float | int]] = {
    "profile_1": {"bandwidth_mbit": 80, "rtt_ms": 70, "jitter_ms": 6, "loss_percent": 0.2},
    "profile_2": {"bandwidth_mbit": 25, "rtt_ms": 140, "jitter_ms": 16, "loss_percent": 1.0},
    "profile_3": {"bandwidth_mbit": 8, "rtt_ms": 260, "jitter_ms": 35, "loss_percent": 2.2},
}

STATE_DIR = Path("/tmp/transmission-netem")
DEFAULT_SAFE_QDISCS = {"noqueue", "fq_codel", "fq", "pfifo_fast", "pfifo"}
EPSILON = {"bandwidth_mbit": 0.1, "rtt_ms": 1.0, "jitter_ms": 1.0, "loss_percent": 0.05}


@dataclasses.dataclass
class NetemApplied:
    bandwidth_mbit: float | None
    rtt_ms: float | None
    jitter_ms: float | None
    loss_percent: float | None
    raw_line: str


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=check)


def has_tc() -> bool:
    return shutil.which("tc") is not None


def fail(msg: str, code: int = 1) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return code


def state_path(interface: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", interface)
    return STATE_DIR / f"{safe}.json"


def parse_netem_line(line: str) -> NetemApplied | None:
    if "qdisc netem" not in line:
        return None

    rate_match = re.search(r"\brate\s+([0-9.]+)([KMG]?)bit\b", line)
    delay_match = re.search(r"\bdelay\s+([0-9.]+)ms(?:\s+([0-9.]+)ms)?", line)
    loss_match = re.search(r"\bloss\s+([0-9.]+)%", line)

    scale = {"": 1e-6, "K": 1e-3, "M": 1.0, "G": 1e3}
    bandwidth_mbit = None
    if rate_match:
        value = float(rate_match.group(1))
        unit = rate_match.group(2)
        bandwidth_mbit = value * scale[unit]

    rtt_ms = float(delay_match.group(1)) if delay_match else None
    jitter_ms = float(delay_match.group(2)) if delay_match and delay_match.group(2) else 0.0
    loss_percent = float(loss_match.group(1)) if loss_match else 0.0

    return NetemApplied(
        bandwidth_mbit=bandwidth_mbit,
        rtt_ms=rtt_ms,
        jitter_ms=jitter_ms,
        loss_percent=loss_percent,
        raw_line=line.strip(),
    )


def show_qdisc(interface: str, stats: bool = False) -> str:
    if not has_tc():
        return ""
    cmd = ["tc", "-s", "qdisc", "show", "dev", interface] if stats else ["tc", "qdisc", "show", "dev", interface]
    completed = run(cmd, check=False)
    return completed.stdout if completed.returncode == 0 else ""


def extract_netem(interface: str) -> NetemApplied | None:
    for line in show_qdisc(interface).splitlines():
        parsed = parse_netem_line(line)
        if parsed:
            return parsed
    return None


def current_root_kinds(interface: str) -> list[str]:
    if not has_tc():
        return []
    completed = run(["tc", "-j", "qdisc", "show", "dev", interface], check=False)
    if completed.returncode != 0:
        return []
    data = completed.stdout
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return []
    kinds: list[str] = []
    for item in payload:
        kind = item.get("kind")
        parent = item.get("parent", "")
        if kind and parent == "root":
            kinds.append(str(kind))
    return kinds


def require_prerequisites(interface: str) -> int | None:
    if not has_tc():
        return fail("`tc` não está disponível (pacote iproute2 ausente). Use fallback sem netem.", code=3)
    if os.geteuid() != 0:
        return fail("execução sem privilégios de root/CAP_NET_ADMIN. Consulte o guia de troubleshooting.", code=4)
    probe = run(["tc", "qdisc", "help"], check=False)
    if "netem" not in (probe.stdout + probe.stderr):
        return fail("módulo/ação netem não disponível no kernel deste runner.", code=5)
    link = run(["ip", "link", "show", "dev", interface], check=False)
    if link.returncode != 0:
        return fail(f"interface `{interface}` não encontrada", code=6)
    return None


def cmd_apply(args: argparse.Namespace) -> int:
    prereq_error = require_prerequisites(args.interface)
    if prereq_error is not None:
        return prereq_error

    profile = PROFILES[args.profile]
    kinds = current_root_kinds(args.interface)
    if any(kind not in DEFAULT_SAFE_QDISCS for kind in kinds):
        return fail(
            "interface possui qdisc root não-padrão; abortando para evitar sobrescrever configuração preexistente "
            f"({', '.join(kinds)}).",
            code=7,
        )

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state = {
        "interface": args.interface,
        "profile": args.profile,
        "baseline_root_kinds": kinds,
        "expected": profile,
    }
    state_path(args.interface).write_text(json.dumps(state, indent=2) + "\n")

    run(["tc", "qdisc", "replace", "dev", args.interface, "root", "netem",
         "rate", f"{profile['bandwidth_mbit']}mbit",
         "delay", f"{profile['rtt_ms']}ms", f"{profile['jitter_ms']}ms",
         "loss", f"{profile['loss_percent']}%"])

    measured = extract_netem(args.interface)
    if measured is None:
        return fail("perfil aplicado, mas qdisc netem não foi encontrado na interface", code=8)

    print(json.dumps({"event": "apply", "interface": args.interface, "profile": args.profile,
                      "expected": profile, "measured": dataclasses.asdict(measured)}, indent=2))
    print(show_qdisc(args.interface, stats=True).strip())
    return cmd_validate(args)


def cmd_teardown(args: argparse.Namespace) -> int:
    if not has_tc():
        return fail("`tc` não está disponível para teardown", code=3)
    if os.geteuid() != 0:
        return fail("teardown sem privilégios de root/CAP_NET_ADMIN", code=4)

    existing = extract_netem(args.interface)
    if existing is not None:
        run(["tc", "qdisc", "del", "dev", args.interface, "root"], check=False)

    residual = extract_netem(args.interface)
    if residual is not None:
        return fail(f"teardown incompleto: netem residual detectado: {residual.raw_line}", code=9)

    st = state_path(args.interface)
    if st.exists():
        st.unlink()

    print(json.dumps({"event": "teardown", "interface": args.interface, "residual_netem": False}, indent=2))
    return 0


def within(expected: float | int, got: float | None, key: str) -> bool:
    if got is None:
        return False
    return abs(float(expected) - float(got)) <= EPSILON[key]


def cmd_validate(args: argparse.Namespace) -> int:
    if not has_tc():
        return fail("`tc` não está disponível (iproute2 ausente)", code=3)
    profile = PROFILES[args.profile]
    measured = extract_netem(args.interface)
    if measured is None:
        return fail("nenhum qdisc netem ativo para validar", code=10)

    checks = {
        "bandwidth_mbit": within(profile["bandwidth_mbit"], measured.bandwidth_mbit, "bandwidth_mbit"),
        "rtt_ms": within(profile["rtt_ms"], measured.rtt_ms, "rtt_ms"),
        "jitter_ms": within(profile["jitter_ms"], measured.jitter_ms, "jitter_ms"),
        "loss_percent": within(profile["loss_percent"], measured.loss_percent, "loss_percent"),
    }
    ok = all(checks.values())

    payload = {
        "event": "validate",
        "interface": args.interface,
        "profile": args.profile,
        "expected": profile,
        "measured": dataclasses.asdict(measured),
        "checks": checks,
        "stats": show_qdisc(args.interface, stats=True).strip(),
    }
    print(json.dumps(payload, indent=2))
    return 0 if ok else 11


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gerencia perfis tc/netem para cenários D")
    parser.add_argument("command", choices=["apply", "teardown", "validate", "status"])
    parser.add_argument("--profile", choices=sorted(PROFILES), required=False, default="profile_1")
    parser.add_argument("--interface", default="eth0")
    return parser


def cmd_status(args: argparse.Namespace) -> int:
    if not has_tc():
        return fail("`tc` não está disponível (iproute2 ausente)", code=3)
    measured = extract_netem(args.interface)
    print(json.dumps({
        "event": "status",
        "interface": args.interface,
        "active": measured is not None,
        "measured": dataclasses.asdict(measured) if measured else None,
        "stats": show_qdisc(args.interface, stats=True).strip(),
    }, indent=2))
    return 0


def main() -> int:
    args = build_parser().parse_args()
    if args.command in {"apply", "validate"} and not args.profile:
        return fail("--profile é obrigatório para apply/validate")
    if args.command == "apply":
        return cmd_apply(args)
    if args.command == "teardown":
        return cmd_teardown(args)
    if args.command == "validate":
        return cmd_validate(args)
    return cmd_status(args)


if __name__ == "__main__":
    raise SystemExit(main())
