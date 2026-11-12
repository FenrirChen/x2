"""Make the quantity popup's 最多 button toggle back to the minimum.

`ShopCheckWnd_OnInit` wires exactly three buttons into `InputItemNum`: `-`, `+`
and `最多`. `InputItemNum_SetMin(1)` only writes `mMinNum` in memory - the
dialog has no 最小 button - so once 最多 is pressed the value sits at the cap
(923/999 in the report) and the only way back to 1 is pressing `-` hundreds of
times or killing the app. The client prefab is not touched here; the 最多
handler becomes a toggle instead:

Original `InputItemNum_ToMax`:

    mMaxNum = min(mMaxNum, 999)
    SetNum(mMaxNum)

Patched:

    if (_ItemNum >= mMaxNum) SetNum(mMinNum)      # 已经在上限 -> 一键回到 1
    else                     original clamp-999    # 否则一键到上限

Offsets (InputItemNum, the same object `SetNum` / `ToMin` receive):
`_ItemNum 0x10, mDefaultNum 0x1c, mMaxNum 0x20, mMinNum 0x24`.

The site is found by its 8-word prologue + cap comparison pattern, never by a
fixed RVA: this APK's `libil2cpp.so` and the `work/apk` copy are different
builds whose `.text` starts 0x7B0 apart, so a hardcoded address would patch the
wrong build. Only a unique match is accepted. The two PC-relative targets the
cave needs - the null guard called when `this == null` and `SetNum` - are
decoded from the build's own instructions, and the cave is located with
`patch_title_voice.find_cave`, so neither address is assumed either.

Usage:
    python patch_quantity_max_toggle.py <libil2cpp.so> <patched.so>
"""
from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT.parent / '.phase2_deps'), str(ROOT.parent / '.phase3_deps')]

from capstone import CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN, Cs

from tools.savemanager.client import patch_title_voice as voice

# stp x20,x19 / stp x29,x30 / add x29,sp / mov x19,x0 / ldr w8,[x19,#0x20] /
# mov w9,#999 / cmp w8,#999 / csel w20,w9,w8,gt  - i.e. ToMax's prologue and its
# min(mMaxNum, 999) clamp. Unique in the audited build.
NEEDLE = bytes.fromhex('f44fbea9fd7b01a9fd430091f30300aa'
                       '682240b9e97c80521f9d0f7134c1881a')

# words 4..7 / 10..14 of the original function are position independent and are
# copied verbatim into the cave; pin them so a changed build fails loudly.
CLAMP = (0xB9402268, 0x52807CE9, 0x710F9D1F, 0x1A88C134)
STORE_AND_RETURN = (0xB9002274, 0xA9417BFD, 0xAA1303E0, 0x2A1403E1, 0xA8C24FF4)

ITEM_NUM = 0x10
MAX_NUM = 0x20
MIN_NUM = 0x24

CAVE_SIZE = 512
# Trampolines of the rest of this toolchain that already sit in the executable
# segment; never reuse them.
#   * 0x42B02C0 - save-manager login button (patch_il2cpp.py, CAVE)
#   * 0x429B870 - main hall title voice (patch_title_voice.py, autolocated cave)
# The title voice blob is the first 1024-byte zero run of the 2.4 build, so
# without reserving it this patch would push that trampoline 4 bytes further and
# invalidate the address recorded in analysis/client_release_20261024. The next
# aligned 512-byte run behind it (0x429BC70) is the tail of the same audited
# zero gap, which is where this patch lands.
RESERVED = ((0x42B02C0, 0x42B02C0 + 1024), (0x429B870, 0x429B870 + 1024))


def b(pc: int, target: int) -> int:
    delta = target - pc
    assert delta % 4 == 0 and -(1 << 27) <= delta < (1 << 27), (hex(pc), hex(target))
    return 0x14000000 | ((delta >> 2) & 0x03FFFFFF)


def bl(pc: int, target: int) -> int:
    return 0x14000000 | 0x80000000 | (((target - pc) >> 2) & 0x03FFFFFF)


def b_cond(pc: int, target: int, cond: int = 0xA) -> int:
    """cond 0xA = GE (signed >=)."""
    delta = target - pc
    assert delta % 4 == 0 and -(1 << 20) <= delta < (1 << 20), (hex(pc), hex(target))
    return 0x54000000 | (((delta >> 2) & 0x7FFFF) << 5) | cond


def cbnz(pc: int, target: int, rt: int = 19) -> int:
    delta = target - pc
    assert delta % 4 == 0 and -(1 << 20) <= delta < (1 << 20), (hex(pc), hex(target))
    return 0xB5000000 | (((delta >> 2) & 0x7FFFF) << 5) | rt


def find_site(data: bytes) -> int:
    hits = []
    pos = 0
    while True:
        at = data.find(NEEDLE, pos)
        if at < 0:
            break
        hits.append(at)
        pos = at + 1
    if len(hits) != 1:
        raise SystemExit('ToMax pattern matched %d sites (expected exactly 1): %s'
                         % (len(hits), [hex(h) for h in hits]))
    return hits[0]


def decode_target(data: bytes, at: int, mnemonic: str) -> int:
    md = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
    instruction = next(iter(md.disasm(data[at:at + 4], at)))
    if instruction.mnemonic != mnemonic or not instruction.op_str.startswith('#0x'):
        raise SystemExit('expected %s at 0x%X, found %s %s'
                         % (mnemonic, at, instruction.mnemonic, instruction.op_str))
    return int(instruction.op_str[1:], 16)


def build_cave(data: bytes, site: int, cave: int) -> tuple[bytes, dict]:
    words = struct.unpack_from('<16I', data, site)
    if tuple(words[4:8]) != CLAMP or tuple(words[10:15]) != STORE_AND_RETURN:
        raise SystemExit('ToMax body differs from the audited build: %s'
                         % ' '.join(f'{w:08X}' for w in words))
    if words[8] != 0xB5000053:
        raise SystemExit('ToMax null check differs from the audited build')
    guard = decode_target(data, site + 4 * 9, 'bl')
    set_num = decode_target(data, site + 4 * 15, 'b')

    plan: list[int | None] = [
        words[0], words[1], words[2], words[3],                  # displaced prologue
        0xB9401268,                                              # ldr w8, [x19, _ItemNum]
        0xB9402269,                                              # ldr w9, [x19, mMaxNum]
        0x6B09011F,                                              # cmp w8, w9
        None,                                                    # b.ge -> to_min
        *CLAMP,                                                  # clamp-999
        None,                                                    # cbnz x19, skip guard
        None,                                                    # bl null guard
        *STORE_AND_RETURN,
        None,                                                    # b SetNum
        0xB9402661, 0xA9417BFD, 0xAA1303E0, 0xA8C24FF4,           # to_min: SetNum(mMinNum)
        None,                                                    # b SetNum
    ]
    # plan[7]  b.ge   -> 20      (已经在上限, 走 to_min)
    # plan[12] cbnz   -> 14      (this != null, 跳过 null guard 调用)
    # plan[13] bl     -> guard
    # plan[19] b      -> SetNum  (clamp-999 路径)
    # plan[24] b      -> SetNum  (to_min 路径)
    to_min = 20
    tail_max = 19
    tail_min = len(plan) - 1
    guard_branch = 12
    plan[7] = b_cond(cave + 4 * 7, cave + 4 * to_min)
    plan[guard_branch] = cbnz(cave + 4 * guard_branch, cave + 4 * (guard_branch + 2))
    plan[guard_branch + 1] = bl(cave + 4 * (guard_branch + 1), guard)
    plan[tail_max] = b(cave + 4 * tail_max, set_num)
    plan[tail_min] = b(cave + 4 * tail_min, set_num)

    blob = b''.join(struct.pack('<I', word & 0xFFFFFFFF) for word in plan)
    meta = dict(site=site, cave=cave, guard=guard, set_num=set_num,
                words=[f'{w & 0xFFFFFFFF:08X}' for w in plan])
    return blob, meta


def verify(patched: bytes, meta: dict) -> None:
    cave, site = meta['cave'], meta['site']
    md = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
    hook = next(iter(md.disasm(patched[site:site + 4], site)))
    if hook.mnemonic != 'b' or int(hook.op_str[1:], 16) != cave:
        raise SystemExit('hook does not branch to the cave: %s %s' % (hook.mnemonic, hook.op_str))
    instructions = list(md.disasm(patched[cave:cave + len(meta['words']) * 4], cave))
    if len(instructions) != len(meta['words']):
        raise SystemExit('cave does not decode into %d instructions' % len(meta['words']))
    if (instructions[0].mnemonic, instructions[0].op_str) != ('stp', 'x20, x19, [sp, #-0x20]!'):
        raise SystemExit('cave does not start with the displaced prologue')
    if (instructions[4].mnemonic, instructions[4].op_str) != ('ldr', 'w8, [x19, #0x10]'):
        raise SystemExit('cave does not read _ItemNum')
    if (instructions[7].mnemonic, instructions[7].op_str) != ('b.ge', '#0x%x' % (cave + 4 * 20)):
        raise SystemExit('cave does not fall back to the minimum at the cap')
    if (instructions[20].mnemonic, instructions[20].op_str) != ('ldr', 'w1, [x19, #0x24]'):
        raise SystemExit('cave minimum block does not read mMinNum')
    if not all(i.mnemonic == 'b' and int(i.op_str[1:], 16) == meta['set_num']
               for i in (instructions[19], instructions[24])):
        raise SystemExit('cave does not tail-call SetNum(0x%X)' % meta['set_num'])


def patch(data: bytes) -> tuple[bytes, dict]:
    site = find_site(data)
    elf = voice.parse_elf(data)
    cave = voice.find_cave(elf, data, CAVE_SIZE, RESERVED)
    blob, meta = build_cave(data, site, cave)
    patched = bytearray(data)
    patched[cave:cave + len(blob)] = blob
    struct.pack_into('<I', patched, site, b(site, cave))
    changed = {i for i, (a, c) in enumerate(zip(data, bytes(patched))) if a != c}
    if any(not (site <= i < site + 4 or cave <= i < cave + len(blob)) for i in changed):
        raise SystemExit('patch touched bytes outside the hook and the cave')
    verify(bytes(patched), meta)
    return bytes(patched), meta


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('source')
    parser.add_argument('output')
    args = parser.parse_args()

    data = open(args.source, 'rb').read()
    print('source=%s size=%d sha256=%s'
          % (args.source, len(data), hashlib.sha256(data).hexdigest()))
    patched, meta = patch(data)
    print('ToMax @ 0x%X -> cave 0x%X (guard 0x%X, SetNum 0x%X)'
          % (meta['site'], meta['cave'], meta['guard'], meta['set_num']))
    for word in meta['words']:
        print('  ', word)
    open(args.output, 'wb').write(patched)
    print('patched -> %s sha256=%s' % (args.output, hashlib.sha256(patched).hexdigest()))
    return 0


if __name__ == '__main__':
    sys.exit(main())
