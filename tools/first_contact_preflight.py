"""Read-only safety checks required before an X2 First Contact run.

The tool never changes DNS, hosts files, firewall rules, certificates, or
listeners. Missing isolation evidence is a hard failure.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import socket
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_HOSTNAME = "ssl-x2zh1login-release.17m3.com"


@dataclass(frozen=True, slots=True)
class Check:
    """One non-mutating preflight result."""

    name: str
    passed: bool
    detail: str


def resolve_exactly(hostname: str, expected_ip: str) -> Check:
    """Require every resolved address to equal the controlled target."""
    try:
        expected = ipaddress.ip_address(expected_ip)
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        resolved = {ipaddress.ip_address(item[4][0]) for item in infos}
    except (OSError, ValueError) as exc:
        return Check("hostname_resolution", False, f"resolution failed: {exc}")
    passed = bool(resolved) and resolved == {expected}
    rendered = ",".join(sorted(str(item) for item in resolved)) or "none"
    return Check("hostname_resolution", passed, f"resolved={rendered}; expected={expected}")


def listener_reachable(name: str, host: str, port: int, timeout: float = 0.5) -> Check:
    """Try one short TCP connection to an explicitly supplied local target."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except OSError as exc:
        return Check(name, False, f"not reachable: {exc}")
    return Check(name, True, f"reachable at {host}:{port}")


def runtime_is_clean(path: Path) -> Check:
    """Allow only the tracked placeholder in the runtime directory."""
    try:
        unexpected = sorted(item.name for item in path.iterdir() if item.name != ".gitkeep")
    except OSError as exc:
        return Check("runtime_clean", False, f"unable to inspect: {exc}")
    return Check(
        "runtime_clean",
        not unexpected,
        "clean" if not unexpected else "unexpected entries: " + ",".join(unexpected),
    )


def git_state_known(repository: Path) -> Check:
    """Confirm Git can report the tree; a dirty tree is reported, not concealed."""
    result = subprocess.run(
        ["git", "status", "--short", "--branch"],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return Check("git_state", False, result.stderr.strip() or "git status failed")
    lines = result.stdout.splitlines()
    dirty = max(0, len(lines) - 1)
    return Check("git_state", True, f"known; uncommitted_entries={dirty}")


def isolation_evidence_valid(
    path: Path | None,
    hostname: str,
    bootstrap_ip: str,
    bootstrap_port: int,
    tcp_ip: str,
    tcp_port: int,
) -> Check:
    """Validate an operator-supplied record of externally enforced isolation."""
    if path is None:
        return Check("external_isolation", False, "no isolation evidence supplied")
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Check("external_isolation", False, f"invalid evidence: {exc}")
    if not isinstance(data, dict):
        return Check("external_isolation", False, "evidence root must be an object")
    expected_destinations = {
        (bootstrap_ip, bootstrap_port, "bootstrap"),
        (tcp_ip, tcp_port, "game_tcp"),
    }
    raw_destinations = data.get("allowed_destinations")
    try:
        actual_destinations = {
            (str(item["host"]), int(item["port"]), str(item["purpose"]))
            for item in raw_destinations
        }
    except (KeyError, TypeError, ValueError):
        return Check("external_isolation", False, "allowed_destinations is invalid")
    required = (
        data.get("deny_by_default") is True
        and data.get("external_route_blocked") is True
        and data.get("original_hostname") == hostname
        and data.get("hostname_target") == bootstrap_ip
        and isinstance(data.get("environment_id"), str)
        and bool(data.get("environment_id"))
        and isinstance(data.get("validation_method"), str)
        and bool(data.get("validation_method"))
        and actual_destinations == expected_destinations
    )
    return Check(
        "external_isolation",
        required,
        "deny-by-default evidence matches targets" if required else "evidence does not match",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hostname", default=PRODUCTION_HOSTNAME)
    parser.add_argument("--bootstrap-target-ip", required=True)
    parser.add_argument("--bootstrap-port", type=int, default=80)
    parser.add_argument("--tcp-target-ip", required=True)
    parser.add_argument("--tcp-port", type=int, required=True)
    parser.add_argument("--isolation-evidence", type=Path)
    parser.add_argument("--runtime-dir", type=Path, default=REPOSITORY_ROOT / "runtime")
    parser.add_argument("--repository", type=Path, default=REPOSITORY_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    checks = [
        resolve_exactly(args.hostname, args.bootstrap_target_ip),
        listener_reachable(
            "bootstrap_listener", args.bootstrap_target_ip, args.bootstrap_port
        ),
        listener_reachable("tcp_listener", args.tcp_target_ip, args.tcp_port),
        isolation_evidence_valid(
            args.isolation_evidence,
            args.hostname,
            args.bootstrap_target_ip,
            args.bootstrap_port,
            args.tcp_target_ip,
            args.tcp_port,
        ),
        runtime_is_clean(args.runtime_dir),
        git_state_known(args.repository),
    ]
    safe = all(check.passed for check in checks)
    result = {
        "SAFE_TO_RUN": safe,
        "checks": [asdict(check) for check in checks],
    }
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 0 if safe else 2


if __name__ == "__main__":
    raise SystemExit(main())
