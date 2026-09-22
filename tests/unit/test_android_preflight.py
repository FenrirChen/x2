from __future__ import annotations

import json
from pathlib import Path

from tools.android.android_preflight import (
    EXPECTED_APK_SHA256,
    parse_adb_devices,
    validate_isolation_evidence,
)


def test_parse_adb_devices() -> None:
    output = "List of devices attached\nemulator-5554\tdevice product:sdk model:sdk\n"
    assert parse_adb_devices(output) == {"emulator-5554": "device"}


def test_empty_adb_devices() -> None:
    assert parse_adb_devices("List of devices attached\n\n") == {}


def _evidence() -> dict[str, object]:
    return {
        "run_scope": "X2 First Contact",
        "timestamp": "2026-09-22T15:00:00+08:00",
        "verification_method": "QEMU restrict plus exact guestfwd",
        "avd_name": "X2-Recovery-Lab",
        "serial": "emulator-5554",
        "expected_hostname": "ssl-x2zh1login-release.17m3.com",
        "resolved_address": "10.0.2.100",
        "bootstrap_endpoint": {"host": "10.0.2.100", "port": 80},
        "tcp_endpoint": {"host": "10.0.2.101", "port": 29000},
        "egress_policy": "qemu_slirp_restrict",
        "deny_by_default": True,
        "external_route_blocked": True,
        "verification_result": True,
        "package_data_clean": True,
        "apk_sha256": EXPECTED_APK_SHA256,
    }


def test_matching_android_isolation_evidence(tmp_path: Path) -> None:
    path = tmp_path / "isolation.json"
    path.write_text(json.dumps(_evidence()), encoding="utf-8")
    result = validate_isolation_evidence(
        path,
        avd_name="X2-Recovery-Lab",
        serial="emulator-5554",
        hostname="ssl-x2zh1login-release.17m3.com",
        redirect_ip="10.0.2.100",
        bootstrap_port=80,
        tcp_ip="10.0.2.101",
        tcp_port=29000,
    )
    assert result.passed is True


def test_android_isolation_evidence_fails_closed(tmp_path: Path) -> None:
    data = _evidence()
    data["external_route_blocked"] = False
    path = tmp_path / "isolation.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    result = validate_isolation_evidence(
        path,
        avd_name="X2-Recovery-Lab",
        serial="emulator-5554",
        hostname="ssl-x2zh1login-release.17m3.com",
        redirect_ip="10.0.2.100",
        bootstrap_port=80,
        tcp_ip="10.0.2.101",
        tcp_port=29000,
    )
    assert result.passed is False
