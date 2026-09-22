"""Create an X2 Revival APK by patching only the packaged GameConfig asset."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import zlib
import zipfile
from pathlib import Path
from typing import Any

ASSET_NAME = "assets/42c44a368fc3544296d1e717a485b306.ab"
REFERENCE_SHA256 = "26a47aa684576549142cf0e4d096a78b90446314506626d2f9e57e6f76450bbe"
OLD_LOGIN_URL = "http://ssl-x2zh1login-release.17m3.com"
NEW_LOGIN_URL = "http://10.0.2.2:18080"
KEY_PREFIX = "x2_GAME_ds"
KEY_MULTIPLIER = 4_289_702_650
LEGACY_SIGNATURE_RENAMES = {
    "META-INF/MANIFEST.MF": "META-INF/MANIFEST.MX",
    "META-INF/COM_SIVA.SF": "META-INF/COM_SIVA.SX",
    "META-INF/COM_SIVA.RSA": "META-INF/COM_SIVA.RSX",
}


class PatchError(RuntimeError):
    """The input is not the confirmed reference asset or cannot be patched safely."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def gameconfig_key(encrypted_length: int) -> bytes:
    material = f"{KEY_PREFIX}{encrypted_length * KEY_MULTIPLIER}".encode("utf-8")
    return hashlib.md5(material).digest()  # noqa: S324 - recovered game format, not security


def _openssl_binary(explicit: str | None = None) -> str:
    binary = explicit or shutil.which("openssl")
    if not binary:
        raise PatchError("OpenSSL was not found; pass --openssl with its executable path")
    return binary


def crypt_asset(data: bytes, *, decrypt: bool, openssl: str | None = None) -> bytes:
    if len(data) % 16:
        raise PatchError("GameConfig ciphertext/plaintext length must be a multiple of 16")
    command = [
        _openssl_binary(openssl),
        "enc",
        "-aes-128-ecb",
        "-nopad",
        "-K",
        gameconfig_key(len(data)).hex(),
    ]
    if decrypt:
        command.append("-d")
    completed = subprocess.run(command, input=data, capture_output=True, check=False)
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise PatchError(f"OpenSSL AES operation failed: {detail}")
    if len(completed.stdout) != len(data):
        raise PatchError("OpenSSL returned an unexpected output length")
    return completed.stdout


def decode_asset(encrypted: bytes, *, openssl: str | None = None) -> tuple[bytes, dict[str, Any]]:
    plaintext = crypt_asset(encrypted, decrypt=True, openssl=openssl)
    try:
        parsed = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PatchError("decrypted GameConfig is not valid UTF-8 JSON") from exc
    if not isinstance(parsed, dict):
        raise PatchError("decrypted GameConfig root must be an object")
    return plaintext, parsed


def effective_row(config: dict[str, Any]) -> dict[str, Any]:
    rows = config.get("configs")
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        raise PatchError("GameConfig does not contain row 0")
    row = rows[0]
    packages = row.get("packageName")
    if not isinstance(packages, list) or "com.siva.project.x2" not in packages:
        raise PatchError("row 0 is not the confirmed com.siva.project.x2 row")
    return row


def patch_plaintext(plaintext: bytes) -> bytes:
    old = OLD_LOGIN_URL.encode("utf-8")
    new = NEW_LOGIN_URL.encode("utf-8")
    if plaintext.count(old) != 1:
        raise PatchError("expected exactly one row-0 Login_Url occurrence")
    patched = plaintext.replace(old, new, 1)
    # Preserve the exact encrypted length and every JSON value. JSON permits trailing
    # whitespace, so this compensates for the shorter development URL without editing
    # the packaged padding field or changing the length-derived AES key.
    patched += b" " * (len(plaintext) - len(patched))
    if len(patched) != len(plaintext):
        raise PatchError("replacement URL is too long for the fixed-length asset")
    return patched


def validate_only_login_url_changed(before: dict[str, Any], after: dict[str, Any]) -> None:
    before_copy = json.loads(json.dumps(before, ensure_ascii=False))
    after_copy = json.loads(json.dumps(after, ensure_ascii=False))
    old_row = effective_row(before_copy)
    new_row = effective_row(after_copy)
    if old_row.get("Login_Url") != OLD_LOGIN_URL:
        raise PatchError(f"unexpected old Login_Url: {old_row.get('Login_Url')!r}")
    if new_row.get("Login_Url") != NEW_LOGIN_URL:
        raise PatchError(f"patched Login_Url was not applied: {new_row.get('Login_Url')!r}")
    old_row["Login_Url"] = NEW_LOGIN_URL
    if before_copy != after_copy:
        raise PatchError("a parsed GameConfig value other than row-0 Login_Url changed")


def read_asset(apk: Path) -> tuple[bytes, zipfile.ZipInfo, int]:
    with zipfile.ZipFile(apk) as archive:
        try:
            info = archive.getinfo(ASSET_NAME)
        except KeyError as exc:
            raise PatchError(f"APK is missing {ASSET_NAME}") from exc
        if info.compress_type != zipfile.ZIP_STORED or info.file_size != info.compress_size:
            raise PatchError("target asset is not stored verbatim in the APK")
        return archive.read(info), info, archive.start_dir


def _asset_data_offset(stream: Any, header_offset: int, expected_name: bytes) -> int:
    stream.seek(header_offset)
    header = stream.read(30)
    if len(header) != 30 or header[:4] != b"PK\x03\x04":
        raise PatchError("invalid local ZIP header for target asset")
    name_length, extra_length = struct.unpack_from("<HH", header, 26)
    name = stream.read(name_length)
    if name != expected_name:
        raise PatchError("local ZIP entry name does not match the target asset")
    return header_offset + 30 + name_length + extra_length


def _patch_central_crc(
    stream: Any, start_dir: int, expected_name: bytes, header_offset: int, crc: int
) -> None:
    cursor = start_dir
    while True:
        stream.seek(cursor)
        header = stream.read(46)
        if len(header) < 4 or header[:4] != b"PK\x01\x02":
            break
        if len(header) != 46:
            raise PatchError("truncated central ZIP directory")
        name_length, extra_length, comment_length = struct.unpack_from("<HHH", header, 28)
        relative_offset = struct.unpack_from("<I", header, 42)[0]
        name = stream.read(name_length)
        if name == expected_name and relative_offset == header_offset:
            stream.seek(cursor + 16)
            stream.write(struct.pack("<I", crc))
            return
        cursor += 46 + name_length + extra_length + comment_length
    raise PatchError("target asset central ZIP record was not found")


def _central_record_offset(
    stream: Any, start_dir: int, expected_name: bytes, header_offset: int
) -> int:
    cursor = start_dir
    while True:
        stream.seek(cursor)
        header = stream.read(46)
        if len(header) < 4 or header[:4] != b"PK\x01\x02":
            break
        if len(header) != 46:
            raise PatchError("truncated central ZIP directory")
        name_length, extra_length, comment_length = struct.unpack_from("<HHH", header, 28)
        relative_offset = struct.unpack_from("<I", header, 42)[0]
        name = stream.read(name_length)
        if name == expected_name and relative_offset == header_offset:
            return cursor
        cursor += 46 + name_length + extra_length + comment_length
    raise PatchError(f"central ZIP record was not found for {expected_name!r}")


def neutralize_legacy_v1_signatures(apk: Path) -> None:
    """Rename old v1 signature metadata without shifting any APK entry offsets."""
    with zipfile.ZipFile(apk) as archive:
        start_dir = archive.start_dir
        entries = {
            old: archive.getinfo(old).header_offset for old in LEGACY_SIGNATURE_RENAMES
        }
    with apk.open("r+b") as stream:
        for old, new in LEGACY_SIGNATURE_RENAMES.items():
            old_bytes = old.encode("ascii")
            new_bytes = new.encode("ascii")
            if len(old_bytes) != len(new_bytes):
                raise PatchError("signature metadata rename must preserve filename length")
            header_offset = entries[old]
            stream.seek(header_offset + 26)
            lengths = stream.read(4)
            if len(lengths) != 4:
                raise PatchError("truncated legacy signature local header")
            name_length, _ = struct.unpack("<HH", lengths)
            if name_length != len(old_bytes) or stream.read(name_length) != old_bytes:
                raise PatchError("legacy signature local filename mismatch")
            stream.seek(header_offset + 30)
            stream.write(new_bytes)
            central = _central_record_offset(stream, start_dir, old_bytes, header_offset)
            stream.seek(central + 46)
            stream.write(new_bytes)


def replace_stored_asset(
    reference_apk: Path,
    output_apk: Path,
    encrypted: bytes,
    info: zipfile.ZipInfo,
    start_dir: int,
) -> None:
    if reference_apk.resolve() == output_apk.resolve():
        raise PatchError("output APK must not overwrite the Reference APK")
    output_apk.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(reference_apk, output_apk)
    expected_name = ASSET_NAME.encode("ascii")
    crc = zlib.crc32(encrypted) & 0xFFFFFFFF
    with output_apk.open("r+b") as stream:
        data_offset = _asset_data_offset(stream, info.header_offset, expected_name)
        stream.seek(data_offset)
        stream.write(encrypted)
        stream.seek(info.header_offset + 14)
        stream.write(struct.pack("<I", crc))
        _patch_central_crc(stream, start_dir, expected_name, info.header_offset, crc)
    neutralize_legacy_v1_signatures(output_apk)
    with zipfile.ZipFile(output_apk) as archive:
        if archive.read(ASSET_NAME) != encrypted:
            raise PatchError("patched APK asset verification failed")
        if any(name in archive.namelist() for name in LEGACY_SIGNATURE_RENAMES):
            raise PatchError("legacy v1 signature metadata was not neutralized")


def build_revival_apk(
    reference_apk: Path,
    output_apk: Path,
    *,
    patched_asset: Path | None = None,
    openssl: str | None = None,
    verify_reference_hash: bool = True,
) -> tuple[str, str]:
    reference_hash = sha256_file(reference_apk)
    if verify_reference_hash and reference_hash != REFERENCE_SHA256:
        raise PatchError(f"Reference APK SHA-256 mismatch: {reference_hash}")
    encrypted, info, start_dir = read_asset(reference_apk)
    plaintext, before = decode_asset(encrypted, openssl=openssl)
    row = effective_row(before)
    print(f"old Login_Url: {row.get('Login_Url')}")

    roundtrip = crypt_asset(plaintext, decrypt=False, openssl=openssl)
    if roundtrip != encrypted:
        raise PatchError("no-change GameConfig round-trip is not byte-identical")
    print("round-trip: byte-identical")

    patched_plaintext = patch_plaintext(plaintext)
    patched_encrypted = crypt_asset(patched_plaintext, decrypt=False, openssl=openssl)
    _, after = decode_asset(patched_encrypted, openssl=openssl)
    validate_only_login_url_changed(before, after)
    print(f"new Login_Url: {effective_row(after)['Login_Url']}")
    print("semantic verification: only row-0 Login_Url changed")

    if patched_asset is not None:
        patched_asset.parent.mkdir(parents=True, exist_ok=True)
        patched_asset.write_bytes(patched_encrypted)
    replace_stored_asset(reference_apk, output_apk, patched_encrypted, info, start_dir)
    revival_hash = sha256_file(output_apk)
    return reference_hash, revival_hash


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference_apk", type=Path)
    parser.add_argument("output_apk", type=Path)
    parser.add_argument("--patched-asset", type=Path)
    parser.add_argument("--openssl", help="path to the OpenSSL executable")
    parser.add_argument(
        "--allow-nonreference-hash",
        action="store_true",
        help="test-only: skip the known Reference APK SHA-256 check",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        reference_hash, revival_hash = build_revival_apk(
            args.reference_apk,
            args.output_apk,
            patched_asset=args.patched_asset,
            openssl=args.openssl,
            verify_reference_hash=not args.allow_nonreference_hash,
        )
    except (OSError, PatchError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Reference SHA-256: {reference_hash}")
    print(f"Revival SHA-256:  {revival_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
