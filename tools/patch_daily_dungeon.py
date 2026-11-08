"""Open the weekday rotation gate on the client DailyDungeon table.

Build-time only. DailyDungeon.OpenTime is a Monday-relative list read by the
shipped client, not a server value:

    ChapterModule.CheckDailyChapterTime 0x16bad64
      0x16bae84 DateTimeHelper.get_DayOfWeek
      0x16bae88 DailyDungeon.OpenTime
      0x16baed4 return OpenTime[DayOfWeek] > 0

ChapterModule.CheckDailyChapterOpenAndLeftTimes is that check ANDed with
CheckDailyChapterOpenParam, and ChapterModule.OnJump's param1==3 branch (the
chapter-menu 再临试炼 entries, Jump 29147 -> ChapterModule(3, 2030500)) calls the
same pair. L2C_ServerTableConfig only carries string key/values, so no server
field reaches this gate: a server-side always_open schedule leaves the client
blocking 2030500/2030600/2030700/2031200 on their closed weekdays.

Only 2030500 饕餮再临, 2030600 阿波菲斯再临, 2030700 惩罚者再临 and 2031200 天书再临
carry a zero in OpenTime (index 0 = Sunday); every other daily dungeon is already
all-ones. Setting those four rows to 1 (0 -> 1, one byte each) fixes both the
dungeon entry and the chapter-menu jump without touching rewards, counts or the
server contract.

The RSA prefix is retained and the change is length preserving, so the original
encrypted prefix stays valid: re-obfuscating the repaired plaintext with the same
positional XOR reproduces the signed prefix byte for byte. The repaired payload is
spliced back into the reference asset at the offset it was read from, so the
replacement `assets/bin/Data/<hash>` file differs from the reference in exactly
those twelve bytes and nothing else (serialized-file data offset, object table and
the other objects are untouched).

    python tools/patch_daily_dungeon.py --apk <reference.apk> --output <dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS / "analysis"))
from _client_table_wire import (  # noqa: E402
    convert_data_bytes,
    parse_message,
    parse_table_container,
    rsa_public_unpad,
)

# Rows whose OpenTime still carries a weekday gate (index 0 = Sunday).
TARGET_KEYS = (2030500, 2030600, 2030700, 2031200)
TABLE_NAME = "dailydungeon"
DATA_PREFIX = "assets/bin/Data/"


class PatchError(RuntimeError):
    """Raised when the reference APK does not match the expected table layout."""


def varint(n: int) -> bytes:
    out = bytearray()
    while n > 127:
        out.append((n & 127) | 128)
        n >>= 7
    out.append(n)
    return bytes(out)


def xor_table(blob: bytes) -> bytes:
    out = bytearray(blob)
    index, delta = 1, 0
    while index < len(out):
        out[index] ^= (delta + index) & 255
        index <<= 1
        delta -= 1
    index, delta = len(out) - 1, 0
    while index > 0:
        out[index] ^= (delta + index) & 255
        index >>= 1
        delta -= 1
    return bytes(out)


def open_time(record: bytes) -> list[int]:
    values, _ = parse_message(record)
    return [v.value for v in values if v.field == 8 and v.wire == 0]


def open_time_zero_offsets(plain: bytes) -> list[tuple[int, int]]:
    """Absolute offsets in `plain` of every OpenTime byte that must become 1.

    Returns (key, offset) pairs for the target rows only.
    """
    values, _ = parse_message(plain, 4)
    hits: list[tuple[int, int]] = []
    for outer in values:
        if outer.field != 2 or outer.wire != 2:
            continue
        record = outer.value
        record_start = outer.end - len(record)
        inner, _ = parse_message(record)
        key = next((v.value for v in inner if v.field == 1 and v.wire == 0), None)
        if key not in TARGET_KEYS:
            continue
        for value in inner:
            if value.field != 8:
                continue
            if value.wire == 0:
                if value.value == 0:
                    hits.append((key, record_start + value.end - 1))
            elif value.wire == 2:
                # Packed variant: a 0x00 byte inside the payload is always value 0.
                body = value.end - len(value.value)
                for i, byte in enumerate(value.value):
                    if byte == 0:
                        hits.append((key, record_start + body + i))
    return hits


def patch_plaintext(plain: bytes) -> tuple[bytes, list[tuple[int, int]]]:
    hits = open_time_zero_offsets(plain)
    if not hits:
        return plain, []
    repaired = bytearray(plain)
    for _, offset in hits:
        repaired[offset] = 1
    return bytes(repaired), hits


def find_table_entries(apk: Path) -> list[str]:
    """Container entries whose base name is DailyDungeon (primary + override namespaces)."""
    with zipfile.ZipFile(apk) as z:
        try:
            stamp = z.read(DATA_PREFIX + "globalgamemanagers")
        except KeyError as exc:
            raise PatchError("globalgamemanagers missing from %s" % apk) from exc
    import UnityPy  # lazy: keeps the pure functions importable without UnityPy

    env = UnityPy.load(stamp)
    entries = []
    for file in env.files.values():
        objects = list(file.objects.values()) if isinstance(file.objects, dict) else list(file.objects)
        for obj in objects:
            if obj.class_id != 147:
                continue
            for key, value in obj.read_typetree().get("m_Container", []):
                if Path(key).name.lower() != TABLE_NAME:
                    continue
                if value["m_FileID"] <= 0:
                    continue
                name = (getattr(file.externals[value["m_FileID"] - 1], "path", None)
                        or getattr(file.externals[value["m_FileID"] - 1], "name", None))
                if name and (DATA_PREFIX + name) not in entries:
                    entries.append(DATA_PREFIX + name)
    if not entries:
        raise PatchError("no DailyDungeon container entry found in %s" % apk)
    return entries


def patch_entry(encrypted: bytes) -> tuple[bytes, dict]:
    """Repair one table payload; returns (new payload, audit record)."""
    container = parse_table_container(encrypted)
    if container["kind"] != "array":
        raise PatchError("unexpected DailyDungeon framing: %s" % container["kind"])
    repaired, hits = patch_plaintext(container["plain"])
    if not hits:
        return encrypted, {"changed": 0, "keys": []}
    signed_prefix = rsa_public_unpad(encrypted[:128])
    obfuscated = xor_table(repaired)
    if obfuscated[:len(signed_prefix)] != signed_prefix:
        raise PatchError("RSA-covered prefix changed")
    patched = encrypted[:128] + obfuscated[len(signed_prefix):]
    if len(patched) != len(encrypted) or convert_data_bytes(patched) != repaired:
        raise PatchError("re-encryption round trip failed")
    decoded = parse_table_container(patched)
    if decoded["keys"] != container["keys"] or len(decoded["items"]) != len(container["items"]):
        raise PatchError("table framing changed by the patch")
    for key, _ in hits:
        index = container["keys"].index(key)
        if open_time(decoded["items"][index]) != [1] * 7:
            raise PatchError("key %d OpenTime not fully open after patch" % key)
    return patched, {
        "changed": len(hits),
        "keys": sorted({key for key, _ in hits}),
    }


def splice(source: bytes, old: bytes, new: bytes) -> bytes:
    """Replace one occurrence of `old` inside `source`, keeping the length."""
    if old == new:
        return source
    if source.count(old) != 1:
        raise PatchError("m_Script payload is not unique in the reference asset")
    at = source.index(old)
    result = source[:at] + new + source[at + len(old):]
    if len(result) != len(source):
        raise PatchError("asset length changed by the patch")
    return result


def patch(apk: Path, output: Path) -> dict:
    import UnityPy  # lazy: keeps the pure functions importable without UnityPy

    output.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    audit: dict[str, dict] = {}
    with zipfile.ZipFile(apk) as z:
        for entry in find_table_entries(apk):
            source = z.read(entry)
            env = UnityPy.load(source)
            text = next((o for o in env.objects
                         if o.type.name == "TextAsset"
                         and o.read_typetree()["m_Name"].lower() == TABLE_NAME), None)
            if text is None:
                raise PatchError("%s holds no %s TextAsset" % (entry, TABLE_NAME))
            script = text.read_typetree()["m_Script"]
            encrypted = (script.encode("utf-8", "surrogateescape")
                         if isinstance(script, str) else script)
            patched, record = patch_entry(encrypted)
            audit[entry] = record
            if not record["changed"]:
                continue
            result = splice(source, encrypted, patched)
            spread = sum(1 for a, b in zip(source, result) if a != b)
            if spread != record["changed"]:
                raise PatchError("%s: %d asset bytes changed, %d expected"
                                 % (entry, spread, record["changed"]))
            target = output / Path(entry).name
            target.write_bytes(result)
            manifest[entry] = str(target.resolve())
            audit[entry]["sha256"] = hashlib.sha256(source).hexdigest()
    if not manifest:
        raise PatchError("every DailyDungeon copy is already fully open")
    (output / "patches.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    for entry, record in audit.items():
        print("%-52s changed=%d keys=%s" % (entry, record["changed"], record["keys"]))
    print("patched %d entr(ies); RSA prefix and every other record unchanged" % len(manifest))
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apk", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    patch(args.apk, args.output)
