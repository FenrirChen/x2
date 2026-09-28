"""Patch the verified Revival v0.2 GameConfig login URL for the public host.

Output is unsigned. Run zipalign and sign with an approved key separately.
No commercial APK or signing material belongs in the source repository.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import zlib
import zipfile
from pathlib import Path

from patch_gameconfig import (
    ASSET_NAME, PatchError, _asset_data_offset, _central_record_offset,
    _patch_central_crc, crypt_asset, decode_asset, effective_row,
    read_asset, sha256_file,
)

INPUT_SHA256 = "460dc657a8fb1b5410a4c0eaa5fac9433b45ecc54b7f3845afc626420946276d"
OLD_URL = "http://10.0.2.2:18080"
NEW_URL = "http://fenrirchen.com:18080"
OLD_SIGNATURES = {
    "META-INF/MANIFEST.MF": "META-INF/MANIFEST.MZ",
    "META-INF/X2-REVIV.SF": "META-INF/X2-REVIV.SX",
    "META-INF/X2-REVIV.RSA": "META-INF/X2-REVIV.RSX",
}


def patch_config(plaintext: bytes) -> bytes:
    before = json.loads(plaintext)
    row = effective_row(before)
    if row.get("Login_Url") != OLD_URL or row.get("packageType") != "testpackage":
        raise PatchError("input is not the confirmed Revival Account configuration")
    old, new = OLD_URL.encode(), NEW_URL.encode()
    if plaintext.count(old) != 1:
        raise PatchError("expected one Login_Url in GameConfig")
    trailing = len(plaintext) - len(plaintext.rstrip(b" \t\r\n"))
    updated = plaintext.rstrip(b" \t\r\n").replace(old, new, 1)
    if len(updated) > len(plaintext) or trailing < len(new) - len(old):
        raise PatchError("insufficient GameConfig padding for longer public URL")
    updated = updated.ljust(len(plaintext), b" ")
    after = json.loads(updated)
    effective_row(after)["Login_Url"] = OLD_URL
    if after != before:
        raise PatchError("a GameConfig field other than Login_Url changed")
    return updated


def neutralize_old_signature(apk: Path) -> None:
    with zipfile.ZipFile(apk) as archive:
        start_dir = archive.start_dir
        offsets = {name: archive.getinfo(name).header_offset for name in OLD_SIGNATURES}
        if any(new in archive.namelist() for new in OLD_SIGNATURES.values()):
            raise PatchError("signature placeholder already exists")
    with apk.open("r+b") as stream:
        for old, new in OLD_SIGNATURES.items():
            original, replacement = old.encode(), new.encode()
            assert len(original) == len(replacement)
            offset = offsets[old]
            stream.seek(offset + 26)
            name_length, _ = struct.unpack("<HH", stream.read(4))
            if name_length != len(original) or stream.read(name_length) != original:
                raise PatchError("old signature ZIP entry changed")
            stream.seek(offset + 30)
            stream.write(replacement)
            central = _central_record_offset(stream, start_dir, original, offset)
            stream.seek(central + 46)
            stream.write(replacement)


def build(input_apk: Path, output_apk: Path) -> None:
    if input_apk.resolve() == output_apk.resolve():
        raise PatchError("output must differ from input")
    if sha256_file(input_apk).lower() != INPUT_SHA256:
        raise PatchError("input APK SHA-256 is not the approved Revival v0.2 build")
    encrypted, info, start_dir = read_asset(input_apk)
    plaintext, _ = decode_asset(encrypted)
    if crypt_asset(plaintext, decrypt=False) != encrypted:
        raise PatchError("GameConfig no-change round-trip failed")
    patched = crypt_asset(patch_config(plaintext), decrypt=False)
    output_apk.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(input_apk, output_apk)
    name = ASSET_NAME.encode()
    crc = zlib.crc32(patched) & 0xffffffff
    with output_apk.open("r+b") as stream:
        stream.seek(_asset_data_offset(stream, info.header_offset, name))
        stream.write(patched)
        stream.seek(info.header_offset + 14)
        stream.write(struct.pack("<I", crc))
        _patch_central_crc(stream, start_dir, name, info.header_offset, crc)
    neutralize_old_signature(output_apk)
    with zipfile.ZipFile(output_apk) as archive:
        if archive.read(ASSET_NAME) != patched or archive.testzip() is not None:
            raise PatchError("output APK ZIP verification failed")
    _, parsed = decode_asset(patched)
    if effective_row(parsed)["Login_Url"] != NEW_URL:
        raise PatchError("output endpoint verification failed")
    print(f"Input SHA-256: {INPUT_SHA256}")
    print(f"Login endpoint: {NEW_URL}")
    print(f"Unsigned APK SHA-256: {sha256_file(output_apk)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_apk", type=Path)
    parser.add_argument("output_apk", type=Path)
    args = parser.parse_args()
    build(args.input_apk, args.output_apk)


if __name__ == "__main__":
    main()
