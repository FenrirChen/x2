"""Replace the eight empty YueXi hall graphics with existing event branding.

Compatibility binding, not a recovery of the missing human/fox banner artwork.
All other scene objects and the current APK's native patches are preserved.
"""
import argparse
import copy
import json
import struct
import zipfile
from pathlib import Path

import UnityPy

SPRITE_FILE = '8281f30dbfa6b4341b686850c542e747'
BINDINGS = {1924: 15, 2074: 15, 1831: 27, 1949: 27}
HIDE = {1773, 1800, 1875, 2040}


def patch(apk, output):
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(apk) as archive:
        sprite_env = UnityPy.load(archive.read('assets/bin/Data/' + SPRITE_FILE))
        sprites = {o.path_id: o for o in sprite_env.objects if o.type.name == 'Sprite'}
        assert sprites[15].read().m_Name == 'YueXiChuJiu_Icon'
        assert sprites[27].read().m_Name == 'YueXiChuJiu_RiYueYingZe'
        env = UnityPy.load(archive.read('assets/bin/Data/level2'))
        sf = next(iter(env.files.values()))
        originals = {pid: o.get_raw_data() for pid, o in sf.objects.items()}
        external = copy.copy(sf.externals[0])
        external.path, external.guid, external.type = SPRITE_FILE, bytes(16), 0
        external.temp_empty = ''
        sf.externals.append(external)
        fid = len(sf.externals)
        for pid in BINDINGS.keys() | HIDE:
            obj = sf.objects[pid]
            raw = bytearray(obj.get_raw_data())
            assert obj.type.name == 'MonoBehaviour' and len(raw) == 292
            assert struct.unpack_from('<iq', raw, 16) == (1, 1947)  # AdvancedImage
            assert struct.unpack_from('<iq', raw, 196) == (0, 0)
            if pid in BINDINGS:
                struct.pack_into('<iq', raw, 196, fid, BINDINGS[pid])
                raw[212] = 1  # Image.m_PreserveAspect
            else:
                raw[12] = 0  # Disable only the empty graphic, not its GameObject.
            obj.set_raw_data(bytes(raw))
        payload = sf.save()
        reread = next(iter(UnityPy.load(payload).files.values()))
        assert set(reread.objects) == set(originals)
        for pid, raw in originals.items():
            if pid not in BINDINGS.keys() | HIDE:
                assert reread.objects[pid].get_raw_data() == raw
        for pid, sprite in BINDINGS.items():
            raw = reread.objects[pid].get_raw_data()
            assert struct.unpack_from('<iq', raw, 196) == (fid, sprite) and raw[212] == 1
        for pid in HIDE:
            assert reread.objects[pid].get_raw_data()[12] == 0
        target = output / 'level2'
        target.write_bytes(payload)
        (output / 'libil2cpp.so').write_bytes(archive.read('lib/arm64-v8a/libil2cpp.so'))
        (output / 'manifest.json').write_text(json.dumps(
            {'assets/bin/Data/level2': str(target.resolve())}, indent=2), encoding='utf-8')
        (output / 'audit.json').write_text(json.dumps(
            {'bindings': BINDINGS, 'hidden_empty_graphics': sorted(HIDE), 'sprite_file': SPRITE_FILE},
            indent=2), encoding='utf-8')
    print('Validated 8 hall graphics; other scene objects and native code unchanged.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    patch(args.apk, args.output)
