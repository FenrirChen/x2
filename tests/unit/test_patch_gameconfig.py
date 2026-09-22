from __future__ import annotations

import importlib.util
import json
import shutil
import zipfile
from pathlib import Path

import pytest

TOOL_PATH = Path(__file__).resolve().parents[2] / "tools" / "patch_gameconfig.py"
SPEC = importlib.util.spec_from_file_location("patch_gameconfig", TOOL_PATH)
assert SPEC is not None and SPEC.loader is not None
patch_gameconfig = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(patch_gameconfig)


def padded_config() -> bytes:
    config = {
        "configs": [
            {
                "packageName": ["com.siva.project.x2"],
                "client_Type": "product",
                "packageType": "product",
                "gameServerName": "TAP_BiliBili_Server",
                "Login_Url": patch_gameconfig.OLD_LOGIN_URL,
                "language": "CN",
            },
            {"Login_Url": "http://unchanged.example"},
        ],
        "a": "padding-value",
    }
    raw = json.dumps(config, ensure_ascii=False, separators=(",", ":")).encode()
    return raw + b" " * (-len(raw) % 16)


@pytest.mark.skipif(shutil.which("openssl") is None, reason="OpenSSL is required")
def test_gameconfig_round_trip_and_minimal_patch() -> None:
    plaintext = padded_config()
    encrypted = patch_gameconfig.crypt_asset(plaintext, decrypt=False)
    decoded, before = patch_gameconfig.decode_asset(encrypted)

    assert decoded == plaintext
    assert patch_gameconfig.crypt_asset(decoded, decrypt=False) == encrypted

    patched_plaintext = patch_gameconfig.patch_plaintext(decoded)
    patched_encrypted = patch_gameconfig.crypt_asset(patched_plaintext, decrypt=False)
    _, after = patch_gameconfig.decode_asset(patched_encrypted)
    patch_gameconfig.validate_only_login_url_changed(before, after)

    assert patch_gameconfig.effective_row(after)["Login_Url"] == patch_gameconfig.NEW_LOGIN_URL
    assert after["configs"][1] == before["configs"][1]
    assert len(patched_encrypted) == len(encrypted)


def test_patch_rejects_missing_original_url() -> None:
    with pytest.raises(patch_gameconfig.PatchError, match="exactly one"):
        patch_gameconfig.patch_plaintext(b'{"configs": []}' + b" " * 1)


def test_neutralize_legacy_v1_signature_names_preserves_payloads(tmp_path: Path) -> None:
    apk = tmp_path / "sample.apk"
    payloads = {
        "META-INF/MANIFEST.MF": b"manifest",
        "META-INF/COM_SIVA.SF": b"signature file",
        "META-INF/COM_SIVA.RSA": b"signature block",
        "assets/kept.bin": b"kept",
    }
    with zipfile.ZipFile(apk, "w") as archive:
        for name, payload in payloads.items():
            archive.writestr(name, payload)

    patch_gameconfig.neutralize_legacy_v1_signatures(apk)

    with zipfile.ZipFile(apk) as archive:
        names = set(archive.namelist())
        assert not names.intersection(patch_gameconfig.LEGACY_SIGNATURE_RENAMES)
        for old, new in patch_gameconfig.LEGACY_SIGNATURE_RENAMES.items():
            assert archive.read(new) == payloads[old]
        assert archive.read("assets/kept.bin") == b"kept"
