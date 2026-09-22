"""Read-only Android-side safety gate for an X2 First Contact run."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_PACKAGE = "com.siva.project.x2"
EXPECTED_APK_SHA256 = "26a47aa684576549142cf0e4d096a78b90446314506626d2f9e57e6f76450bbe"
EXPECTED_HOSTNAME = "ssl-x2zh1login-release.17m3.com"


@dataclass(frozen=True, slots=True)
class Check:
    """One fail-closed Android lab check."""

    name: str
    passed: bool
    detail: str


def parse_adb_devices(output: str) -> dict[str, str]:
    """Return serial-to-state entries from ``adb devices`` output."""
    devices: dict[str, str] = {}
    for line in output.splitlines():
        fields = line.strip().split()
        if len(fields) >= 2 and not line.startswith("List of devices"):
            devices[fields[0]] = fields[1]
    return devices


def run_adb(adb: Path, serial: str, *args: str, timeout: float = 5.0) -> tuple[int, str]:
    """Run one bounded ADB command without shell expansion."""
    try:
        completed = subprocess.run(
            [str(adb), "-s", serial, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    output = (completed.stdout + completed.stderr).strip()
    return completed.returncode, output


def validate_isolation_evidence(
    path: Path | None,
    *,
    avd_name: str,
    serial: str,
    hostname: str,
    redirect_ip: str,
    bootstrap_port: int,
    tcp_ip: str,
    tcp_port: int,
) -> Check:
    """Require exact runtime evidence for the restricted emulator network."""
    if path is None:
        return Check("isolation_evidence", False, "not supplied")
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Check("isolation_evidence", False, f"invalid JSON: {exc}")
    if not isinstance(data, dict):
        return Check("isolation_evidence", False, "root must be an object")
    expected = {
        "avd_name": avd_name,
        "serial": serial,
        "expected_hostname": hostname,
        "resolved_address": redirect_ip,
        "bootstrap_endpoint": {"host": redirect_ip, "port": bootstrap_port},
        "tcp_endpoint": {"host": tcp_ip, "port": tcp_port},
        "egress_policy": "qemu_slirp_restrict",
        "deny_by_default": True,
        "external_route_blocked": True,
        "verification_result": True,
        "package_data_clean": True,
        "apk_sha256": EXPECTED_APK_SHA256,
    }
    mismatches = [key for key, value in expected.items() if data.get(key) != value]
    required_text = ("run_scope", "timestamp", "verification_method")
    mismatches.extend(
        key for key in required_text if not isinstance(data.get(key), str) or not data[key]
    )
    return Check(
        "isolation_evidence",
        not mismatches,
        "matches expected lab" if not mismatches else "mismatch: " + ",".join(mismatches),
    )


def check_adb(adb: Path, serial: str) -> Check:
    """Require exactly the expected online emulator."""
    try:
        completed = subprocess.run(
            [str(adb), "devices"],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check("adb_device", False, str(exc))
    devices = parse_adb_devices(completed.stdout)
    passed = devices == {serial: "device"}
    return Check("adb_device", passed, json.dumps(devices, sort_keys=True))


def check_shell_equals(adb: Path, serial: str, name: str, command: str, expected: str) -> Check:
    """Require a bounded shell command to return one exact value."""
    code, output = run_adb(adb, serial, "shell", command)
    passed = code == 0 and output.strip() == expected
    return Check(name, passed, f"value={output.strip()!r}; expected={expected!r}")


def check_package(adb: Path, serial: str, package: str) -> Check:
    """Require the package to be installed but not running."""
    path_code, package_path = run_adb(adb, serial, "shell", "pm", "path", package)
    pid_code, pid = run_adb(adb, serial, "shell", "pidof", package)
    installed = path_code == 0 and package_path.startswith("package:")
    stopped = pid_code != 0 or not pid.strip()
    return Check(
        "package_installed_stopped",
        installed and stopped,
        f"installed={installed}; stopped={stopped}",
    )


def check_hosts(adb: Path, serial: str, hostname: str, expected_ip: str) -> Check:
    """Verify the disposable guest's exact hosts override without DNS traffic."""
    code, output = run_adb(adb, serial, "shell", "cat", "/etc/hosts")
    matches = []
    for line in output.splitlines():
        fields = line.split("#", 1)[0].split()
        if len(fields) >= 2 and hostname in fields[1:]:
            matches.append(fields[0])
    passed = code == 0 and matches == [expected_ip]
    return Check("guest_hostname_override", passed, f"matches={matches}")


def check_listener(name: str, host: str, port: int) -> Check:
    """Reuse the host-only TCP reachability check."""
    import socket

    try:
        with socket.create_connection((host, port), timeout=0.5):
            pass
    except OSError as exc:
        return Check(name, False, str(exc))
    return Check(name, True, f"reachable={host}:{port}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", required=True, type=Path)
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--avd-name", default="X2-Recovery-Lab")
    parser.add_argument("--package", default=EXPECTED_PACKAGE)
    parser.add_argument("--hostname", default=EXPECTED_HOSTNAME)
    parser.add_argument("--redirect-ip", default="10.0.2.100")
    parser.add_argument("--bootstrap-host", default="127.0.0.1")
    parser.add_argument("--bootstrap-port", type=int, default=18080)
    parser.add_argument("--tcp-host", default="127.0.0.1")
    parser.add_argument("--tcp-guest-ip", default="10.0.2.101")
    parser.add_argument("--tcp-port", type=int, default=29000)
    parser.add_argument("--isolation-evidence", type=Path)
    parser.add_argument("--runtime-dir", type=Path, default=REPOSITORY_ROOT / "runtime")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    checks = [
        Check("adb_binary", args.adb.is_file(), str(args.adb)),
        check_adb(args.adb, args.serial),
        check_shell_equals(
            args.adb, args.serial, "avd_name", "getprop ro.kernel.qemu.avd_name", args.avd_name
        ),
        check_shell_equals(
            args.adb, args.serial, "api_level", "getprop ro.build.version.sdk", "27"
        ),
        check_package(args.adb, args.serial, args.package),
        check_hosts(args.adb, args.serial, args.hostname, args.redirect_ip),
        check_listener("bootstrap_listener", args.bootstrap_host, args.bootstrap_port),
        check_listener("tcp_listener", args.tcp_host, args.tcp_port),
        validate_isolation_evidence(
            args.isolation_evidence,
            avd_name=args.avd_name,
            serial=args.serial,
            hostname=args.hostname,
            redirect_ip=args.redirect_ip,
            bootstrap_port=80,
            tcp_ip=args.tcp_guest_ip,
            tcp_port=args.tcp_port,
        ),
        Check("runtime_directory", args.runtime_dir.is_dir(), str(args.runtime_dir)),
    ]
    safe = all(check.passed for check in checks)
    sys.stdout.write(
        json.dumps(
            {"SAFE_TO_RUN": safe, "checks": [asdict(check) for check in checks]},
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    return 0 if safe else 2


if __name__ == "__main__":
    raise SystemExit(main())
