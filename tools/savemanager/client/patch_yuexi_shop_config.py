"""Restore missing YueXi shops without replacing any existing shop record.

The current ShopConfig table omits 887-890; Table_410 retains their 2.4 schema.
A narrow native loader branch accepts only this merged plaintext table prefix.
All encrypted tables retain the original RSA/XOR loader, and all original shop
records (including battle passes) are byte-for-byte preserved.
"""
import argparse
import json
import struct
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT.parent), str(ROOT.parent / '.phase2_deps')]
import UnityPy
from phase3_protobuf import parse_table_container, parse_table_array, parse_message
from tools.analysis.patch_activity_scenes import ld, varint
from tools.savemanager.client.patch_treasure_activity import text_asset
from tools.savemanager.client.patch_activity_ui import branch, ldr

BASE = '0a5189b8d93663c4aa152623435068da'
RECOVERED = '8c8abe333ea043a418a9e14cc63c7c71'
HOOK, CAVE = 0x1B4A0C4, 0x42B0D00


def patch(apk, output):
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(apk) as archive:
        env = UnityPy.load(archive.read('assets/bin/Data/' + BASE))
        obj, tree, blob = text_asset(env)
        base = parse_table_container(blob)
        recovered = parse_table_container(text_asset(UnityPy.load(
            archive.read('assets/bin/Data/' + RECOVERED)))[2])
        assert base['kind'] == recovered['kind'] == 'array'
        records = dict(zip(base['keys'], base['items']))
        extra = dict(zip(recovered['keys'], recovered['items']))
        assert len(records) == 25 and all(i not in records for i in range(887, 891))
        for stage, key in enumerate(range(887, 891), 1):
            fields, _ = parse_message(extra[key])
            assert any(f.field == 5 for f in fields)
            records[key] = b''.join(varint(5 << 3) + varint(stage * 6)
                if f.field == 5 else extra[key][f.start:f.end] for f in fields)
        plain = struct.pack('<I', len(records)) + b''.join(
            varint(1 << 3) + varint(key) for key in records) + b''.join(
            ld(2, record) for record in records.values())
        keys, items, unknown, used = parse_table_array(plain[4:])
        assert not unknown and used == len(plain) - 4 and len(keys) == len(items) == 29
        checked = dict(zip(keys, items))
        assert all(checked[k] == v for k, v in zip(base['keys'], base['items']))
        for stage, key in enumerate(range(887, 891), 1):
            fields, _ = parse_message(checked[key])
            assert [f.value for f in fields if f.field == 5] == [stage * 6]
        tree['m_Script'] = plain.decode('utf-8', 'surrogateescape')
        obj.save_typetree(tree)
        target = output / BASE
        target.write_bytes(env.file.save())
        assert text_asset(UnityPy.load(target.read_bytes()))[2] == plain
        native = bytearray(archive.read('lib/arm64-v8a/libil2cpp.so'))
        original = struct.unpack_from('<I', native, HOOK)[0]
        assert original == 0xA9BC5FF8  # displaced stp x24,x23,[sp,#-64]!
        # ConvertDataBytes is void(ref byte[]); x1 points to the byte[] slot.
        # Validate length and both first 64-bit words; never read past an array.
        words = [0, ldr(8, 1), 0, 0xB9401909, 0x7100413F, 0,
                 ldr(9, 8, 0x20), 0, 0xEB0A013F, 0,
                 ldr(9, 8, 0x28), 0, 0xEB0A013F, 0, 0xD65F03C0,
                 original, branch(CAVE + 64, HOOK + 4), 0xD503201F]
        fallback = CAVE + 60
        words[0] = 0xB4000001 | (((fallback - CAVE) // 4) << 5)  # cbz x1
        words[2] = 0xB4000008 | (((fallback - (CAVE + 8)) // 4) << 5)
        words[5] = 0x54000003 | (((fallback - (CAVE + 20)) // 4) << 5)  # b.lo
        words[9] = 0x54000001 | (((fallback - (CAVE + 36)) // 4) << 5)
        words[13] = 0x54000001 | (((fallback - (CAVE + 52)) // 4) << 5)
        for index, literal in [(7, CAVE + 72), (11, CAVE + 80)]:
            words[index] = 0x5800000A | (((literal - (CAVE + index * 4)) // 4) << 5)
        payload = struct.pack('<18I', *words) + plain[:16]
        assert native[CAVE:CAVE + len(payload)] == bytes(len(payload))
        native[CAVE:CAVE + len(payload)] = payload
        struct.pack_into('<I', native, HOOK, branch(HOOK, CAVE))
        (output / 'libil2cpp.so').write_bytes(native)
        (output / 'manifest.json').write_text(json.dumps(
            {'assets/bin/Data/' + BASE: str(target.resolve())}, indent=2), encoding='utf-8')
        (output / 'audit.json').write_text(json.dumps({'source': RECOVERED,
            'restored_shops': list(range(887, 891)), 'thresholds': [6, 12, 18, 24],
            'preserved_original_records': base['keys'], 'hook': HOOK, 'cave': CAVE,
            'loader_prefix': plain[:16].hex()}, indent=2), encoding='utf-8')
    print('Validated 29 shops, 25 untouched original records, four restored stages.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    patch(args.apk, args.output)
