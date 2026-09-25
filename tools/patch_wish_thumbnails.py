"""Build a reversible IL2CPP thumbnail fallback for the confirmed X2 2.4 client.

The packaged Draw atlas lacks several ChouJiang_Tab sprites. Its full-size
pool covers are present, so the fallback loads a cover only when the original
atlas lookup returns no sprite. This script builds a copy; it never edits the
reference library or installs anything on a device.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

REFERENCE_SHA256 = "37f092f117c11d7e0cdae1e9ac9f7123487c97b6d91c4e7ab699d380646a1dca"
LOAD_ADDRESS = 0x1A92120
CALL_ADDRESS = 0x1A92148
CAVE_ADDRESS = 0x429B870
ATLAS_LOOKUP = 0x151DCCC
RESOURCE_LOOKUP = 0x1D4A730
STRING_NEW = 0x3F4DFB8
GENERIC_JEWEL_TAB = b"Draw/ChouJiang_Tab700\0"
GENERIC_JEWEL_COVER = b"UIAltas/Draw/GuangGaoTu_Cover700\0"
MISSING_JEWEL_POOL = 22702
MAIN_CAVE_ADDRESS = 0x429B920
MAIN_IMAGE_CALLS = (0x1A8F844, 0x1A8F880)


def _branch(from_address: int, to_address: int) -> int:
    distance = to_address - from_address
    if distance % 4 or not -(1 << 27) <= distance < 1 << 27:
        raise ValueError("branch target is out of ARM64 range")
    return 0x94000000 | ((distance // 4) & 0x3FFFFFF)


def build(source: Path, output: Path) -> str:
    if source.resolve() == output.resolve():
        raise ValueError("output must be a separate file")
    data = bytearray(source.read_bytes())
    digest = hashlib.sha256(data).hexdigest()
    if digest != REFERENCE_SHA256:
        raise ValueError(f"unexpected client library SHA-256: {digest}")
    if data[LOAD_ADDRESS:LOAD_ADDRESS + 4].hex() != "175d40f9":
        raise ValueError("thumbnail field instruction does not match")
    if data[CALL_ADDRESS:CALL_ADDRESS + 4].hex() != "e12eea97":
        raise ValueError("atlas lookup instruction does not match")

    # The source ELF's executable segment has vaddr == file offset here.
    # The caller saves x24; hold DrawParam there while both managed lookup
    # calls run. Their argument convention is (null, path, null).
    literal_address = CAVE_ADDRESS + 112
    adr_address = CAVE_ADDRESS + 56
    adr_distance = literal_address - adr_address
    if not -(1 << 20) <= adr_distance < 1 << 20:
        raise ValueError("generic thumbnail string is out of ADR range")
    adr_word = (0x10000000 | ((adr_distance & 3) << 29)
                | (((adr_distance >> 2) & 0x7FFFF) << 5))
    words = [
        0xA9BF7BFD,  # stp x29, x30, [sp, #-16]!
        0x52800008 | (MISSING_JEWEL_POOL << 5),  # movz w8, #22702
        0x6B08027F,  # cmp w19, w8
        0x54000000 | (11 << 5),  # b.eq generic
        0xAA1F03E0,  # mov x0, xzr
        0xF9400000 | (23 << 10) | (24 << 5) | 1,  # ldr x1, [x24, #0xb8]
        0xAA1F03E2,  # mov x2, xzr
        _branch(CAVE_ADDRESS + 28, ATLAS_LOOKUP),
        0xB5000000 | (12 << 5),  # cbnz x0, return
        0xAA1F03E0,
        0xF9400000 | (22 << 10) | (24 << 5) | 1,  # ldr x1, [x24, #0xb0]
        0xAA1F03E2,
        _branch(CAVE_ADDRESS + 48, RESOURCE_LOOKUP),
        0xB5000000 | (7 << 5),  # cbnz x0, return
        adr_word,  # adr x0, generic jewel tab path
        _branch(CAVE_ADDRESS + 60, STRING_NEW),
        0xAA0003E1,  # mov x1, x0
        0xAA1F03E0,
        0xAA1F03E2,
        _branch(CAVE_ADDRESS + 76, ATLAS_LOOKUP),
        0xA8C17BFD,  # ldp x29, x30, [sp], #16
        0xD65F03C0,  # ret
    ]
    code = b"".join(word.to_bytes(4, "little") for word in words)
    if data[CAVE_ADDRESS:literal_address + len(GENERIC_JEWEL_TAB)] != bytes(
            literal_address + len(GENERIC_JEWEL_TAB) - CAVE_ADDRESS):
        raise ValueError("expected executable padding is occupied")
    data[CAVE_ADDRESS:CAVE_ADDRESS + len(code)] = code
    data[literal_address:literal_address + len(GENERIC_JEWEL_TAB)] = GENERIC_JEWEL_TAB
    data[LOAD_ADDRESS:LOAD_ADDRESS + 4] = (0xAA0803F8).to_bytes(4, "little")
    data[CALL_ADDRESS:CALL_ADDRESS + 4] = _branch(CALL_ADDRESS, CAVE_ADDRESS).to_bytes(4, "little")

    # Pool 22702 has neither its tab sprite nor its full-size Cover702 in the
    # packaged APK. Substitute a generic jewel cover for the two main images.
    cover_literal = MAIN_CAVE_ADDRESS + 64
    cover_adr_address = MAIN_CAVE_ADDRESS + 20
    cover_delta = cover_literal - cover_adr_address
    cover_adr = (0x10000000 | ((cover_delta & 3) << 29)
                 | (((cover_delta >> 2) & 0x7FFFF) << 5))
    main_words = [
        0xA9BF7BFD,
        0xB9400000 | (4 << 10) | (25 << 5) | 8,  # ldr w8, [x25, #0x10]
        0x52800009 | (MISSING_JEWEL_POOL << 5),  # movz w9, #22702
        0x6B09011F,  # cmp w8, w9
        0x54000001 | (4 << 5),  # b.ne original path
        cover_adr,
        _branch(MAIN_CAVE_ADDRESS + 24, STRING_NEW),
        0xAA0003E1,
        0xAA1F03E0,
        0xAA1F03E2,
        _branch(MAIN_CAVE_ADDRESS + 40, 0x1547498),
        0xA8C17BFD,
        0xD65F03C0,
    ]
    main_code = b"".join(word.to_bytes(4, "little") for word in main_words)
    if data[MAIN_CAVE_ADDRESS:cover_literal + len(GENERIC_JEWEL_COVER)] != bytes(
            cover_literal + len(GENERIC_JEWEL_COVER) - MAIN_CAVE_ADDRESS):
        raise ValueError("main image executable padding is occupied")
    data[MAIN_CAVE_ADDRESS:MAIN_CAVE_ADDRESS + len(main_code)] = main_code
    data[cover_literal:cover_literal + len(GENERIC_JEWEL_COVER)] = GENERIC_JEWEL_COVER
    for address in MAIN_IMAGE_CALLS:
        data[address:address + 4] = _branch(address, MAIN_CAVE_ADDRESS).to_bytes(4, "little")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(build(args.source, args.output))
