from __future__ import annotations

import json
import socket
from pathlib import Path

from tools.first_contact_preflight import (
    isolation_evidence_valid,
    resolve_exactly,
    runtime_is_clean,
)


def _write_evidence(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "environment_id": "isolated-test-guest",
                "deny_by_default": True,
                "external_route_blocked": True,
                "original_hostname": "bootstrap.example.invalid",
                "hostname_target": "10.0.2.2",
                "validation_method": "guest firewall policy inspection",
                "allowed_destinations": [
                    {"host": "10.0.2.2", "port": 80, "purpose": "bootstrap"},
                    {"host": "10.0.2.2", "port": 29000, "purpose": "game_tcp"},
                ],
            }
        ),
        encoding="utf-8",
    )


def test_missing_isolation_evidence_is_unsafe() -> None:
    result = isolation_evidence_valid(
        None, "bootstrap.example.invalid", "10.0.2.2", 80, "10.0.2.2", 29000
    )
    assert result.passed is False


def test_matching_isolation_evidence_is_accepted(tmp_path: Path) -> None:
    evidence = tmp_path / "isolation.json"
    _write_evidence(evidence)
    result = isolation_evidence_valid(
        evidence, "bootstrap.example.invalid", "10.0.2.2", 80, "10.0.2.2", 29000
    )
    assert result.passed is True


def test_extra_allowed_destination_is_rejected(tmp_path: Path) -> None:
    evidence = tmp_path / "isolation.json"
    _write_evidence(evidence)
    data = json.loads(evidence.read_text(encoding="utf-8"))
    data["allowed_destinations"].append(
        {"host": "8.8.8.8", "port": 53, "purpose": "external_dns"}
    )
    evidence.write_text(json.dumps(data), encoding="utf-8")
    result = isolation_evidence_valid(
        evidence, "bootstrap.example.invalid", "10.0.2.2", 80, "10.0.2.2", 29000
    )
    assert result.passed is False


def test_runtime_cleanliness(tmp_path: Path) -> None:
    (tmp_path / ".gitkeep").touch()
    assert runtime_is_clean(tmp_path).passed is True
    (tmp_path / "server.log").touch()
    assert runtime_is_clean(tmp_path).passed is False


def test_resolution_must_match_exactly(monkeypatch) -> None:
    answers = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.2.2", 0)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("203.0.113.10", 0)),
    ]
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: answers)
    assert resolve_exactly("bootstrap.example.invalid", "10.0.2.2").passed is False
