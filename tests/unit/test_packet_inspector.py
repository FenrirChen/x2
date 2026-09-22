import json
import subprocess
import sys
from pathlib import Path


def test_packet_inspector_reads_synthetic_fixture() -> None:
    root = Path(__file__).resolve().parents[2]
    fixture = root / "tests" / "fixtures" / "synthetic_guide_request.bin"
    result = subprocess.run(
        [
            sys.executable,
            str(root / "tools" / "packet_inspector.py"),
            str(fixture),
            "--direction",
            "request",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    output = json.loads(result.stdout)
    assert output["synthetic"] is True
    assert output["messageId"] == 374
    assert output["messageName"] == "C2L_GuideStep"
    assert output["requestId"] == 1
    assert output["crcValid"] is True
    assert output["body"] == {"stepId": 21011, "stepState": 2}

