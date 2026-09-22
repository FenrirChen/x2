"""Inspect one local X2 packet fixture. This tool never opens a network connection."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from x2server.config.logging import configure_logging  # noqa: E402
from x2server.protocol.codec import ProtocolCodec  # noqa: E402
from x2server.protocol.errors import ProtocolError  # noqa: E402
from x2server.protocol.headers import RequestHeader, ResponseHeader  # noqa: E402

LOGGER = logging.getLogger("x2.packet_inspector")
_SENSITIVE_NAMES = {"token", "password", "secret", "privatekey", "private_key"}


def _safe_json(value: Any, field_name: str = "") -> Any:
    if field_name.lower() in _SENSITIVE_NAMES:
        return "<redacted>"
    if isinstance(value, bytes):
        return {"encoding": "hex", "value": value.hex()}
    if isinstance(value, dict):
        return {key: _safe_json(item, key) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe_json(item) for item in value]
    return value


def inspect_packet(path: Path, direction: str) -> dict[str, Any]:
    """Decode a local fixture and return non-sensitive inspection metadata."""
    header_type = RequestHeader if direction == "request" else ResponseHeader
    decoded = ProtocolCodec().decode(path.read_bytes(), header_type)
    header = decoded.packet.header
    return {
        "fixture": path.name,
        "synthetic": path.name.startswith("synthetic_"),
        "totalLen": decoded.packet.total_length,
        "headLen": decoded.packet.header_length,
        "messageId": decoded.packet.message_id,
        "messageName": decoded.message_name,
        "requestId": header.request_id,
        "sessionId": header.session_id,
        "crcValid": True if isinstance(header, RequestHeader) else None,
        "bodyLength": len(decoded.packet.body),
        "body": _safe_json(decoded.values),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path, help="local binary packet fixture")
    parser.add_argument("--direction", required=True, choices=("request", "response"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging("WARNING")
    try:
        result = inspect_packet(args.fixture, args.direction)
    except (OSError, ProtocolError, ValueError) as exc:
        LOGGER.error("unable to inspect local fixture: %s", exc)
        return 2
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

