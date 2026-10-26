"""Allow the favor gift button after the client reach the level limit.

`FavorSendGift_CheckAttchLevelMax` decides the gift button state with:

    cmp  w0, w21      ; w0 = Favor.FavorLevel, w21 = FavorabilityHero.LevelLimit
    cset w23, lt      ; w23 = (FavorLevel < LevelLimit)

`w23` is later ANDed with `Favor.GiftsTimes < SendGiftControl.ReceiveNumber`
and written to `Selectable.set_interactable` / `UIImageGray.set_gray`, so a max
level hero can no longer send gifts.  The server already accepts them -- its
`_advance()` caps the level at `LevelLimit` and keeps accumulating `exp` -- so
only this client gate has to be opened.

The two instructions are replaced in place with the same length:

    cmp  w0, w21
    mov  w23, #1

The site is found by the exact byte pattern rather than a fixed RVA: the APK's
`libil2cpp.so` (88855552 bytes) and the copy under `work/apk` (88872784 bytes)
are different builds whose `.text` starts 0x7B0 apart.  Only a unique match is
accepted, and the result is re-disassembled with capstone before it is written.

Usage:
    python patch_favor_gift_gate.py <libil2cpp.so> <patched.so>
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".phase3_deps"))

from capstone import CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN, Cs

NEEDLE = bytes.fromhex("1f00156bf7a79f1a")   # cmp w0, w21 ; cset w23, lt
PATCH = bytes.fromhex("1f00156b37008052")    # cmp w0, w21 ; mov w23, #1


def find_gate(data: bytes) -> int:
    hits = []
    start = 0
    while True:
        at = data.find(NEEDLE, start)
        if at < 0:
            break
        hits.append(at)
        start = at + 1
    if len(hits) != 1:
        raise SystemExit("favor gift gate matched %d sites (expected exactly 1): %s"
                         % (len(hits), [hex(h) for h in hits]))
    return hits[0]


def verify(data: bytes, at: int) -> None:
    md = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
    instructions = list(md.disasm(data[at:at + 8], at))
    if len(instructions) != 2:
        raise SystemExit("capstone did not decode two instructions")
    first, second = instructions
    if (first.mnemonic, first.op_str) != ("cmp", "w0, w21"):
        raise SystemExit("unexpected first instruction: %s %s" % (first.mnemonic, first.op_str))
    if (second.mnemonic, second.op_str) != ("mov", "w23, #1"):
        raise SystemExit("unexpected second instruction: %s %s"
                         % (second.mnemonic, second.op_str))


def patch(data: bytes) -> bytes:
    at = find_gate(data)
    patched = bytearray(data)
    patched[at:at + 8] = PATCH
    verify(bytes(patched), at)
    print("  gate @ 0x%X: %s -> %s" % (at, NEEDLE.hex(), PATCH.hex()))
    return bytes(patched)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("output")
    args = parser.parse_args()

    data = open(args.source, "rb").read()
    print("source=%s size=%d sha256=%s"
          % (args.source, len(data), hashlib.sha256(data).hexdigest()))
    if data.find(NEEDLE) < 0:
        raise SystemExit("favor gift gate pattern not found")
    open(args.output, "wb").write(patch(data))
    print("patched -> %s" % args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
