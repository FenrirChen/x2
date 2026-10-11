"""2.4 arm64: enable activity entry immediately and initialize cafe lists.

CafeStoreInfo's three native stream readers initialize lists only when a
repeated element is present. Empty cooking queues must remain empty: fake
entries block both cooking and staff selection. Add empty List instances
after each reader initializes its metadata, before its first wire field.
Keep the existing scene, authentication and save-manager patches unchanged.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / '.phase3_deps'))
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN

CAVE = 0x42B0600
READERS = ((0x38E123C, 0x38E1254), (0x38E16B0, 0x38E16C8),
           (0x38E1B80, 0x38E1B98))


def branch(pc, target, link=False):
    delta = target - pc
    assert delta % 4 == 0 and -(1 << 27) <= delta < (1 << 27)
    return (0x94000000 if link else 0x14000000) | ((delta >> 2) & 0x3FFFFFF)


def adrp(rd, pc, target):
    imm = (target >> 12) - (pc >> 12)
    return 0x90000000 | ((imm & 3) << 29) | (((imm >> 2) & 0x7FFFF) << 5) | rd


def ldr(rd, rn, offset=0):
    assert offset % 8 == 0
    return 0xF9400000 | ((offset // 8) << 10) | (rn << 5) | rd


def str_(rd, rn, offset=0):
    return 0xF9000000 | ((offset // 8) << 10) | (rn << 5) | rd


def trampoline(start, resume):
    words = []

    def emit(word):
        words.append(word)

    def call(target):
        emit(branch(start + 4 * len(words), target, True))

    def reference(address, rd):
        emit(adrp(8, start + 4 * len(words), address))
        emit(ldr(8, 8, address & 0xFFF))
        emit(ldr(rd, 8))

    # Preserve every register touched, including stream position/length in
    # x0/x21 and the enclosing reader's return address. x19 = target object.
    emit(0xA9BD07E0)  # stp x0,x1,[sp,#-0x30]!
    emit(0xA90157E8)  # stp x8,x21,[sp,#0x10]
    emit(str_(30, 31, 0x20))
    for offset, class_ref, ctor_ref in (
            (0x18, 0x522A3A8, 0x522B3A0),
            (0x20, 0x52D8AB0, 0x52E98E0)):
        emit(ldr(8, 19, offset))
        skip = len(words)
        emit(0)
        reference(class_ref, 0)
        call(0x3F6452C)  # il2cpp object allocation
        emit(0xAA0003F5)  # mov x21,x0
        reference(ctor_ref, 1)
        call(0x3D4E3A8)  # shared List<T> constructor with correct MethodInfo
        emit(str_(21, 19, offset))
        words[skip] = 0xB5000008 | (((len(words) - skip) & 0x7FFFF) << 5)
    emit(ldr(30, 31, 0x20))
    emit(0xA94157E8)  # ldp x8,x21,[sp,#0x10]
    emit(0xA8C307E0)  # ldp x0,x1,[sp],#0x30
    emit(branch(start + 4 * len(words), resume))
    return struct.pack('<' + 'I' * len(words), *words)


def patch(source, output):
    original = source.read_bytes()
    result = bytearray(original)
    audit = []
    decoder = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)

    def change(offset, expected, blob, purpose):
        assert original[offset:offset + len(blob)] == expected, hex(offset)
        result[offset:offset + len(blob)] = blob
        audit.append({'offset': hex(offset), 'purpose': purpose,
                      'before': expected.hex(), 'after': blob.hex(),
                      'disassembly': [f'{i.address:x} {i.mnemonic} {i.op_str}'
                                      for i in decoder.disasm(blob, offset)]})

    for index, (hook, resume) in enumerate(READERS):
        start = CAVE + index * 0x100
        blob = trampoline(start, resume)
        assert len(blob) <= 0x100
        change(start, bytes(len(blob)), blob, 'initialize absent cafe lists')
        change(hook, struct.pack('<I', branch(hook, resume)),
               struct.pack('<I', branch(hook, start)), 'CafeStoreInfo reader hook')
    # StartEffect hides these two objects until an ElectronicEffect callback;
    # DelayShowDes later activates precisely the same objects. Enable them
    # immediately so a missing/delayed decorative callback cannot block input.
    for offset in (0x1415008, 0x141501C):
        change(offset, bytes.fromhex('e2031f2a'), bytes.fromhex('22008052'),
               'enable activity entry without waiting for animation')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(result)
    output.with_suffix('.audit.json').write_text(json.dumps({
        'source_sha256': hashlib.sha256(original).hexdigest(),
        'output_sha256': hashlib.sha256(result).hexdigest(), 'patches': audit}, indent=2),
        encoding='utf-8')
    print('Patched', len(audit), 'ranges:', output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    patch(args.source, args.output)
