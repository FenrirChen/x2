"""Set the native purchase selector stock cap before any item/resource lookup.

The ActivityUI baseline is preserved, including the rollback of Treasure patches.
ShopCheckWnd.ResetData has several early exits before InputItemNum.SetMax.
The shared popup must not reuse its table default or a previous item's maximum.
"""
import argparse
import hashlib
import json
import struct
import zipfile
from pathlib import Path
from patch_activity_ui import branch, ldr

ENTRY = 0x1795E48
CAVE = 0x42B0B00


def patch(apk, output):
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(apk) as archive:
        native = bytearray(archive.read('lib/arm64-v8a/libil2cpp.so'))
    original = struct.unpack_from('<I', native, ENTRY)[0]
    assert original == 0xA9BA6FFC  # stp x28,x27,[sp,#-0x60]!
    words = [ldr(8, 0, 0x108), 0, ldr(9, 0, 0x118), 0,
             0xB940290A, 0x7100015F, 0,  # canBuyTimes; cmp w10,#0
             0xB9402D0B, 0x4B0B014A, 0x7100015F,
             0x1A9FC14A, 0xB900212A]  # max(0,cap-bought) -> InputItemNum.mMaxNum
    skip = len(words)
    for index, register in ((1, 8), (3, 9)):
        words[index] = 0xB4000000 | ((skip-index) << 5) | register
    words[6] = 0x5400000D | ((skip-6) << 5)  # b.le: unlimited offers retain original behavior
    words += [original, branch(CAVE + (skip+1)*4, ENTRY+4)]
    code = struct.pack('<'+'I'*len(words), *words)
    assert not any(native[CAVE:CAVE+len(code)])
    native[CAVE:CAVE+len(code)] = code
    struct.pack_into('<I', native, ENTRY, branch(ENTRY, CAVE))
    path = output / 'libil2cpp.so'
    path.write_bytes(native)
    (output / 'manifest.json').write_text('{}', encoding='utf-8')
    audit = {'baseline': str(apk), 'entry': hex(ENTRY), 'cave': hex(CAVE),
             'native_sha256': hashlib.sha256(native).hexdigest(), 'instructions': len(words)}
    (output / 'audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
    print(json.dumps(audit))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    patch(args.apk, args.output)
