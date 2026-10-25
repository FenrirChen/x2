"""Keep the season task tab from refreshing for ordinary task events."""
import argparse
import hashlib
import json
import struct
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT.parent / '.phase3_deps')]
from tools.savemanager.client import patch_title_voice as native
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

HOOK = 0x14C928C
EXPECTED = bytes.fromhex('e923ba6dfa6701a9f85f02a9f65703a9f44f04a9fd7b05a9fd430191ff4300d1')


def branch_target(data, address):
    word = struct.unpack_from('<I', data, address)[0]
    assert word >> 26 == 5
    offset = word & 0x3ffffff
    if offset & 0x2000000:
        offset -= 0x4000000
    return address + offset * 4


def patch(apk, output):
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(apk) as archive:
        old = archive.read('lib/arm64-v8a/libil2cpp.so')
    assert old[HOOK:HOOK + len(EXPECTED)] == EXPECTED, 'Task Refresh version mismatch'
    reserved = tuple(native.RESERVED) + (
        (branch_target(old, 0x13BDA24), branch_target(old, 0x13BDA24) + native.CAVE_SIZE),
        (branch_target(old, 0x1E497D8), branch_target(old, 0x1E497D8) + 64),)
    cave = native.find_cave(native.parse_elf(old), old, 64, reserved)
    # cmp w1,15; b.eq original; ret; displaced stp d9,d8; b Refresh+4.
    words = [0x71003c3f, 0x54000040, 0xd65f03c0,
             struct.unpack_from('<I', old, HOOK)[0], native.b(cave + 16, HOOK + 4)]
    data = bytearray(old)
    data[cave:cave + 20] = struct.pack('<5I', *words)
    struct.pack_into('<I', data, HOOK, native.b(HOOK, cave))
    assert all(a == b or HOOK <= i < HOOK + 4 or cave <= i < cave + 20
               for i, (a, b) in enumerate(zip(old, data)))
    code = list(Cs(CS_ARCH_ARM64, CS_MODE_ARM).disasm(bytes(data[cave:cave + 20]), cave))
    assert code[0].op_str == 'w1, #0xf' and code[2].mnemonic == 'ret'
    assert code[3].mnemonic == 'stp' and code[3].op_str == 'd9, d8, [sp, #-0x60]!'
    report = {'hook': HOOK, 'cave': cave, 'resume': HOOK + 4,
              'guard': 'GameTaskType.BATTLEPASS == 15 only; ordinary daily/weekly events ignored',
              'source_sha256': hashlib.sha256(old).hexdigest(),
              'output_sha256': hashlib.sha256(data).hexdigest(),
              'reserved_ranges': reserved,
              'disassembly': [f'{i.address:x}: {i.mnemonic} {i.op_str}' for i in code]}
    (output / 'libil2cpp.so').write_bytes(data)
    (output / 'manifest.json').write_text('{}', encoding='utf8')
    (output / 'audit.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(report))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('apk', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    patch(a.apk, a.output)
