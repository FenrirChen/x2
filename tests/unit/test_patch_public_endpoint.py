import importlib.util
import json
from pathlib import Path

import pytest


TOOL = Path(__file__).resolve().parents[2] / "tools" / "patch_public_endpoint.py"
SPEC = importlib.util.spec_from_file_location("patch_public_endpoint", TOOL)
assert SPEC is not None and SPEC.loader is not None
import sys
sys.path.insert(0, str(TOOL.parent))
patch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(patch)


def test_public_patch_changes_only_login_url():
    config = {"configs": [{"packageName": ["com.siva.project.x2"],
                           "packageType": "testpackage", "Login_Url": patch.OLD_URL,
                           "client_Type": "product"}], "other": [1, 2]}
    raw = json.dumps(config).encode() + b" " * 160
    changed = patch.patch_config(raw)
    assert len(changed) == len(raw)
    result = json.loads(changed)
    assert result["configs"][0]["Login_Url"] == patch.NEW_URL
    result["configs"][0]["Login_Url"] = patch.OLD_URL
    assert result == config


def test_public_patch_rejects_other_source():
    raw = json.dumps({"configs": [{"packageName": ["com.siva.project.x2"],
                                    "packageType": "product", "Login_Url": patch.OLD_URL}]}).encode()
    with pytest.raises(patch.PatchError):
        patch.patch_config(raw)
