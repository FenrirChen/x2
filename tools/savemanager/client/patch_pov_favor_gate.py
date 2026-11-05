"""Open the POV chapter list's 神格默契度 gate.

`PovMapTab_RefreshChapters` / `RefreshSingleChapter` / `ChapterModule_CheckPOVChapterOpen`
decide whether a 前情回顾 (PointOfView) chapter is open with

    GetFavorLevelByHeroId(heroId) >= POVChapterInfo.FavorLevel

where `GetFavorLevelByHeroId` is a thin `ChapterModule` wrapper that tail-calls
`FavorModule.GetFavorLevel_1`. A fresh account has no 默契度 with the POV heroes
(the table asks for level 3, one chapter for 5), so every permanent chapter stays
locked behind a number the player cannot raise without weeks of gift farming.

The server already supplies the real gates - previous stage clears come from the
mission pairs (`ChapterModule` type 4 / mainMission) and the chapter rewards are
settled in `ActivityService.pov_chapter_rewards` - so only this client threshold
has to be opened. The wrapper itself is replaced in place:

    mov  w0, #99        ; 0x52800C60
    ret                 ; 0xD65F03C0

`FavorModule.GetFavorLevel_1` is NOT touched: the 好感/神格 pages, avatars, 纸鹤
and the gift-level checks call it directly and keep their real values, so nothing
is displayed as level 99. A full-library scan of the audited build shows the
wrapper is only referenced by the three POV call sites above.

The entry RVA is per build. The default is the audited 2.4 build (88855552 bytes);
for any other `libil2cpp.so` pass `--entry` with the RVA of
`ChapterModule.GetFavorLevelByHeroId` from your own dump.cs/script.json. The body
is verified instruction by instruction before anything is written, so a wrong RVA
fails loudly instead of corrupting an unrelated method.

Usage:
    python patch_pov_favor_gate.py <libil2cpp.so> <patched.so> [--entry 0x16C7E14]
    python patch_pov_favor_gate.py <libil2cpp.so> <patched.so> --callers
"""
from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT.parent / '.phase2_deps'), str(ROOT.parent / '.phase3_deps')]

from capstone import CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN, Cs

# ChapterModule.GetFavorLevelByHeroId in the audited 2.4 build (the one shipped
# in the APK); the last instruction is the tail call into
# FavorModule.GetFavorLevel_1.
DEFAULT_ENTRY = 0x16C7E14
FAVOR_MAX = 0x63                       # 99, far above every POVChapterInfo.FavorLevel (3/5)
PATCH = (0x52800000 | (FAVOR_MAX << 5), 0xD65F03C0)   # mov w0,#99 ; ret

# First eight words of the audited method, including the PC-relative `adrp` and
# `tbnz` and the static-field load `ldrb w8,[x20,#0xbd0]`. They only match the
# default 2.4 build; with --entry the same 27 instructions are compared
# structurally instead (see BODY).
ORIGINAL = (0xA9BE4FF4, 0xA9017BFD, 0x910043FD, 0xF001F574,
            0x396F4288, 0x2A0103F3, 0x370000E8, 0xB001D9C8)

# (mnemonic, op_str) of the whole method, entry .. tail call. Entries ending in a
# space are prefixes (the PC-relative target or the static-field offset differs
# per build); the empty op_str means "any target" and the two fixed offsets are
# il2cpp object field offsets, which are stable across builds.
BODY = (
    ('stp', 'x20, x19, [sp, #-0x20]!'),
    ('stp', 'x29, x30, [sp, #0x10]'),
    ('add', 'x29, sp, #0x10'),
    ('adrp', 'x20, '),
    ('ldrb', 'w8, [x20'),
    ('mov', 'w19, w1'),
    ('tbnz', 'w8, #0, '),
    ('adrp', 'x8, '),
    ('ldr', 'x8, [x8, '),
    ('ldr', 'w0, [x8]'),
    ('bl', ''),
    ('mov', 'w8, #1'),
    ('strb', 'w8, [x20'),
    ('adrp', 'x8, '),
    ('ldr', 'x8, [x8, '),
    ('ldr', 'x0, [x8]'),
    ('ldrb', 'w8, [x0, #0x10a]'),
    ('tbz', 'w8, #0, '),
    ('ldr', 'w8, [x0, #0xbc]'),
    ('cbnz', 'w8, '),
    ('bl', ''),
    ('ldp', 'x29, x30, [sp, #0x10]'),
    ('mov', 'x0, xzr'),
    ('mov', 'x2, xzr'),
    ('mov', 'w1, w19'),
    ('ldp', 'x20, x19, [sp], #0x20'),
    ('b', ''),
)


def disassemble(data: bytes, rva: int, count: int):
    md = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
    return list(md.disasm(data[rva:rva + count * 4], rva))


def verify_body(data: bytes, entry: int, exact: bool) -> str:
    """Prove `entry` really is ChapterModule.GetFavorLevelByHeroId."""
    if exact:
        found = struct.unpack_from('<' + 'I' * len(ORIGINAL), data, entry)
        if tuple(found) != ORIGINAL:
            raise SystemExit('GetFavorLevelByHeroId prologue differs from the audited 2.4 build '
                             'at 0x%X:\n  found    %s\n  expected %s\n'
                             'pass --entry with the RVA from this build\'s dump.cs'
                             % (entry, ' '.join('%08X' % w for w in found),
                                ' '.join('%08X' % w for w in ORIGINAL)))
    instructions = disassemble(data, entry, len(BODY))
    if len(instructions) != len(BODY):
        raise SystemExit('could not disassemble %d instructions at 0x%X' % (len(BODY), entry))
    for instruction, (mnemonic, op_str) in zip(instructions, BODY):
        if instruction.mnemonic != mnemonic:
            raise SystemExit('0x%X: expected %s, found %s %s'
                             % (instruction.address, mnemonic, instruction.mnemonic,
                                instruction.op_str))
        if not op_str or instruction.op_str == op_str or instruction.op_str.startswith(op_str):
            continue
        raise SystemExit('0x%X: expected %s %s, found %s %s'
                         % (instruction.address, mnemonic, op_str,
                            instruction.mnemonic, instruction.op_str))
    return 'exact' if exact else 'structural'


def patch(data: bytes, entry: int, exact: bool) -> tuple[bytes, str]:
    mode = verify_body(data, entry, exact)
    patched = bytearray(data)
    struct.pack_into('<2I', patched, entry, *PATCH)
    instructions = disassemble(bytes(patched), entry, 2)
    if ([(i.mnemonic, i.op_str) for i in instructions]
            != [('mov', 'w0, #0x63'), ('ret', '')]):
        raise SystemExit('patched entry does not decode to mov w0,#0x63 ; ret: %s'
                         % [(i.mnemonic, i.op_str) for i in instructions])
    # Everything behind the first two instructions must stay byte-identical so the
    # disassembly in the audit keeps matching the shipped method.
    tail = data[entry + 8:entry + len(BODY) * 4]
    if bytes(patched[entry + 8:entry + len(BODY) * 4]) != tail:
        raise SystemExit('bytes behind the patched prologue changed')
    changed = [i for i, (a, b) in enumerate(zip(data, bytes(patched))) if a != b]
    if any(not entry <= i < entry + 8 for i in changed):
        raise SystemExit('patch touched bytes outside the entry')
    return bytes(patched), mode


def callers(data: bytes, entry: int) -> list[int]:
    """Every `bl <entry>` in the file (4-byte aligned), for re-auditing a build."""
    words = array('I')
    words.frombytes(data[:len(data) // 4 * 4])
    if sys.byteorder != 'little':
        words.byteswap()
    found = []
    for address, word in enumerate(words):
        if word & 0xFC000000 != 0x94000000:
            continue
        delta = word & 0x03FFFFFF
        if delta & 0x02000000:
            delta -= 0x04000000
        if address * 4 + delta * 4 == entry:
            found.append(address * 4)
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('source')
    parser.add_argument('output')
    parser.add_argument('--entry', type=lambda value: int(value, 0), default=DEFAULT_ENTRY,
                        help='RVA of ChapterModule.GetFavorLevelByHeroId (default: 0x16C7E14, '
                             'the audited 2.4 build); pass your own for any other build')
    parser.add_argument('--callers', action='store_true',
                        help='only list the bl call sites of the entry, do not patch')
    args = parser.parse_args()

    data = open(args.source, 'rb').read()
    exact = args.entry == DEFAULT_ENTRY
    print('source=%s size=%d sha256=%s'
          % (args.source, len(data), hashlib.sha256(data).hexdigest()))
    if args.callers:
        verify_body(data, args.entry, exact)
        print('callers of 0x%X: %s' % (args.entry, [hex(a) for a in callers(data, args.entry)]))
        return 0
    patched, mode = patch(data, args.entry, exact)
    print('GetFavorLevelByHeroId @ 0x%X (%s body) -> mov w0,#0x63 ; ret' % (args.entry, mode))
    open(args.output, 'wb').write(patched)
    print('patched -> %s sha256=%s' % (args.output, hashlib.sha256(patched).hexdigest()))
    return 0


if __name__ == '__main__':
    sys.exit(main())
