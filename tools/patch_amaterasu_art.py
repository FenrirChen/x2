"""Route 大御神 天照 (Appearance 1222601) off the broken Live2D branch.

Build-time only. 天照's Live2D model (`Live2dModle/L2D_1026`) renders as a solid
black silhouette in the current client and its additive meshes flash white when
the portrait is tapped ("圣光"). The static resources are intact: 字段 13
`ShowDrawing` points at `ExpressionAnim/1026/ExpressionAnim1026` (the full
`Hero_drawing_1026` art with eye/mouth expressions) and 字段 12 `FullDrawing`
points at `UIAltas/Hero_F/Hero_F_drawing_1026`.

`ExpressionAnimatorManager_AddModleByHeroID` (0x1EEB2C0) takes the Live2D branch
whenever `Appearance.Live2DShow` (offset +0x58) is non-empty, then SpineShow
(+0x60), and returns 0 when both are empty. `AddHeroAnimByID` (0x1EEB0C0) maps
that 0 to `AddExpressionAnimByHeroID_RawImage` (0x1EEB260). Clearing 字段 14 makes
the 神格详情 and 主城 use the colored expression portrait again, and removes the
additive layer that shows up as "圣光" on tap.

This is a client-table workaround, not a repair of the L2D assets: the original
model and texture stay untouched in the APK, so a future model fix can simply
restore the value. No server data changes.

    python tools/patch_amaterasu_art.py --apk <reference.apk> --output <dir>

The output directory receives a replacement `assets/bin/Data/2c6eecbf...` plus
`patches.json` / `audit.json`. The APK has to be rebuilt and re-signed with the
local dev key before it can be installed; this tool does neither.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from patch_izanagi_skin import (
    APPEARANCE_TABLE,
    DATA_PREFIX,
    PatchError,
    build_array,
    field_span,
    parse_table_container,
    rebuild_table,
    reencrypt,
    rsa_public_unpad,
    split_array,
)

APPEARANCE_ID = 1222601
LIVE2D_SHOW = b"Live2dModle/L2D_1026"
SHOW_DRAWING = b"ExpressionAnim/1026/ExpressionAnim1026"

# Protobuf tag for 字段 14 wire type 2 (length-delimited), value length 0.
EMPTY_LIVE2D_FIELD = b"\x72\x00"


def patch_appearance(encrypted: bytes) -> tuple[bytes, dict]:
    table = parse_table_container(encrypted)
    if table["kind"] != "array":
        raise PatchError("Appearance is not a key/row array")
    plain, prefix = table["plain"], rsa_public_unpad(encrypted[:128])
    count, keys, rows, spans, keys_end = split_array(plain)
    index = keys.index(APPEARANCE_ID)
    if spans[index] < len(prefix):
        raise PatchError("the 1222601 row sits inside the RSA-covered prefix")
    row = rows[index]

    start, end, value = field_span(row, 14, 2)
    if value != LIVE2D_SHOW:
        raise PatchError(f"Appearance 1222601 Live2DShow is {value!r}")
    rows[index] = row[:start] + EMPTY_LIVE2D_FIELD + row[end:]

    repaired = build_array(plain, keys_end, rows)
    patched = reencrypt(encrypted, repaired, prefix)
    decoded = parse_table_container(patched)
    row = decoded["items"][decoded["keys"].index(APPEARANCE_ID)]
    if field_span(row, 14, 2)[2] not in (b"", None):
        raise PatchError("Live2DShow was not cleared")
    if field_span(row, 13, 2)[2] != SHOW_DRAWING:
        raise PatchError("ShowDrawing changed; the ExpressionAnim fallback would break")
    return patched, {"live2d_show": [LIVE2D_SHOW.decode(), ""],
                     "show_drawing": SHOW_DRAWING.decode()}


def patch(apk: Path, output: Path) -> dict[str, str]:
    output.mkdir(parents=True, exist_ok=True)
    payload, audit = rebuild_table(apk, APPEARANCE_TABLE, "Appearance", patch_appearance)
    target = output / (APPEARANCE_TABLE + ".bin")
    target.write_bytes(payload)
    manifest = {DATA_PREFIX + APPEARANCE_TABLE: str(target.resolve())}
    (output / "patches.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output / "audit.json").write_text(
        json.dumps({DATA_PREFIX + APPEARANCE_TABLE: audit}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"{APPEARANCE_TABLE:<52} {len(payload):>8} B")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apk", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    patch(arguments.apk, arguments.output)
