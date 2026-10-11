"""Bind missing activity prefab backgrounds to existing packaged sprites.

Compatibility art selections, not claims of recovered official bindings. Only
audited Image PPtrs and zero-size background RectTransforms are changed. Never
patch masks, control graphics, or already populated references.
Requires UnityPy and an audited ResourceManager index (path -> [file, pathID]).
"""
import argparse
import copy
import json
import struct
import zipfile
from pathlib import Path

import UnityPy

# Explicit object IDs from the 2.4 APK; no heuristic mutation of white images.
PAGES = {
    "chunjiebg2": {
        "ui_newyear2_main": [790, 964], "ui_newyear2_section": [1684, 1972],
        "ui_newyear2_shop": [808, 817], "ui_newyear2_task": [719],
        "ui_newyear2_lantern_main": [760], "ui_newyear2_lantern_drawlots": [80],
        "ui_newyear2_lantern_yearlabel": [97], "ui_newyear2_lantern_question": [109],
        "ui_newyear_main": [491], "ui_newyear_section": [382, 457],
        "ui_newyear_shop": [663, 670], "ui_newyearchieftask": [553],
        "ui_newyear_lantern_main": [685], "ui_newyear_lantern_drawlots": [61],
        "ui_newyear_lantern_yearlabel": [93], "ui_newyear_pov": [1061],
    },
    "chunjiebg3": {
        "ui_newyear2_foodfight_main": [1886], "ui_newyear2_foodfight_store": [348],
        "ui_newyear_foodfight_main": [1843], "ui_newyear_foodfight_store": [348],
    },
    "yinghu": {"ui_sakura_main": [306, 313]},
    "zhenxun1": {"ui_zhenxun_main": [345], "ui_zhenxun_section": [906, 909],
                  "ui_zhenxun_shop": [703], "ui_zhenxun_task": [755]},
    "ann1": {"ui_anniversary_main": [652, 841], "ui_anniversary_section": [386, 403],
             "ui_anniversary_task": [843], "ui_anniversary_poolshop": [962, 1144],
             "ui_anniversary_tower_section": [490, 589]},
    "osirisbg": {"ui_osiris_main": [374, 449], "ui_osiris_section": [977, 1012],
                  "ui_osiris_shop": [322], "ui_osiris_task": [692, 771],
                  "ui_osiris_towerdata": [418, 448]},
    "gonggong_scene": {"ui_gonggong_main": [260], "ui_gonggong_section": [637],
                        "ui_gonggong_shop": [379], "ui_gonggong_task": [675, 851]},
}


def patch(apk, index, output):
    output.mkdir(parents=True, exist_ok=True)
    manifest, audit = {}, []
    with zipfile.ZipFile(apk) as z:
        for art, pages in PAGES.items():
            sprite_file, sprite_id = index['uialtas/cg/' + art]
            sprite_env = UnityPy.load(z.read('assets/bin/Data/' + sprite_file))
            sprite = next(o for o in sprite_env.objects if o.path_id == sprite_id)
            assert sprite.type.name == 'Sprite', art
            sprite.read()  # validate the referenced sprite's serialized structure
            for page, ids in pages.items():
                source, _ = index['ui/' + page]
                entry = 'assets/bin/Data/' + source
                env = UnityPy.load(z.read(entry))
                sf = next(iter(env.files.values()))
                original = {o.path_id: o.get_raw_data() for o in env.objects}
                changed = set()
                external = copy.copy(sf.externals[0])
                external.path, external.guid, external.type = sprite_file, bytes(16), 0
                external.temp_empty = ''
                sf.externals.append(external)
                file_id = len(sf.externals)
                for image_id in ids:
                    obj = sf.objects[image_id]
                    raw = bytearray(obj.get_raw_data())
                    assert obj.type.name == 'MonoBehaviour' and len(raw) == 292, (page, image_id)
                    assert struct.unpack_from('<ii', raw, 64) == (0, 123), (page, image_id)
                    assert struct.unpack_from('<iq', raw, 196) == (0, 0), (page, image_id)
                    struct.pack_into('<iq', raw, 196, file_id, sprite_id)
                    # Full-scene background should not consume clicks.
                    raw[60] = 0
                    obj.set_raw_data(bytes(raw)); changed.add(image_id)
                    go_id = struct.unpack_from('<q', raw, 4)[0]
                    rect_obj = next(o for o in env.objects if o.type.name == 'RectTransform'
                                    and o.read_typetree()['m_GameObject']['m_PathID'] == go_id)
                    rect = rect_obj.read_typetree()
                    size = rect['m_SizeDelta']
                    if size['x'] == 0 and size['y'] == 0 and rect['m_AnchorMin'] == rect['m_AnchorMax']:
                        # Missing Sprite also left SetNativeSize backgrounds at zero.
                        rect['m_AnchorMin'] = rect['m_AnchorMax'] = {'x': .5, 'y': .5}
                        rect['m_SizeDelta'] = {'x': 1336., 'y': 752.}
                        rect['m_AnchoredPosition'] = {'x': 0., 'y': 0.}
                        rect_obj.save_typetree(rect); changed.add(rect_obj.path_id)
                    audit.append(dict(page=page, image=image_id, sprite=art, file=sprite_file))
                payload = sf.save()
                verified = UnityPy.load(payload)
                reread = next(iter(verified.files.values()))
                assert set(original) == set(reread.objects)
                for pid, raw in original.items():
                    if pid not in changed:
                        assert reread.objects[pid].get_raw_data() == raw, (page, pid)
                for pid in ids:
                    assert struct.unpack_from('<iq', reread.objects[pid].get_raw_data(), 196) == (file_id, sprite_id)
                assert reread.externals[file_id - 1].path == sprite_file
                target = output / source
                target.write_bytes(payload)
                manifest[entry] = str(target.resolve())
    (output / 'background-audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'patches.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f'Validated {len(audit)} background references in {len(manifest)} prefabs')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('apk', type=Path); p.add_argument('index', type=Path); p.add_argument('output', type=Path)
    args = p.parse_args()
    patch(args.apk, json.loads(args.index.read_text(encoding='utf-8')), args.output)
