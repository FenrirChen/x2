"""Regenerate deterministic local fixtures from the recovered M1 specification."""

from __future__ import annotations

import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from x2server.protocol.codec import ProtocolCodec  # noqa: E402
from x2server.protocol.headers import RequestHeader  # noqa: E402


def main() -> None:
    """Write only explicitly synthetic, credential-free fixtures."""
    target = REPOSITORY_ROOT / "tests" / "fixtures" / "synthetic_guide_request.bin"
    packet = ProtocolCodec().encode(
        "C2L_GuideStep",
        {"stepId": 21011, "stepState": 2},
        RequestHeader(
            request_id=1,
            session_id="synthetic-session",
            ack_data_version=1,
            unit_id=100,
        ),
    )
    target.write_bytes(packet)


if __name__ == "__main__":
    main()

