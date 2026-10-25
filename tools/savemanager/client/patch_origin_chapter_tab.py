"""Repair the Origin Paradox title on the chapter screen actually used by WanFa.

UI_BattlePass_Farm is a separate challenge view. OnMBtnWanFaClick opens
ChapterContent (UI_MapChoose), whose BattlePass tab ships with season 2 art.
Only replace that tab's decorative Image components; retain the original
objects, animation targets, scripts, and input bindings.
"""
import argparse
import copy
import json
import struct
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT.parent / '.phase2_deps'))
import UnityPy

PAGE = 'c2688ba506c9bdf469ce1183e197a365'
ORIGIN = '0999fa1dc42cb4d46897892076b8ce2a'
MOON = '350a82e08dde9574196120223d23a89f'
TITLE_PARTS = {3270: 22, 3392: 19, 3396: 23, 3611: 18, 3691: 21,
               3849: 20, 3898: 17, 3917: 20, 4004: 24}
TITLE = 3898


def patch(apk, output, static_background=False):
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(apk) as archive:
        sf = next(iter(UnityPy.load(archive.read('assets/bin/Data/' + PAGE)).files.values()))
        before = {pid: obj.get_raw_data() for pid, obj in sf.objects.items()}
        ext = next((i for i, item in enumerate(sf.externals, 1) if item.path == ORIGIN), None)
        if ext is None:
            item = copy.copy(sf.externals[0])
            item.path = ORIGIN
            item.guid = bytes(16)
            item.type = 0
            item.temp_empty = ''
            sf.externals.append(item)
            ext = len(sf.externals)
        for pid, sprite in TITLE_PARTS.items():
            raw = bytearray(sf.objects[pid].get_raw_data())
            assert len(raw) == 292, (pid, len(raw))
            file_id, path_id = struct.unpack_from('<iq', raw, 196)
            assert sf.externals[file_id - 1].path == MOON and path_id == sprite, pid
            if pid == TITLE:
                struct.pack_into('<iq', raw, 196, ext, 52)
                raw[12] = 1
                raw[60] = 0
            else:
                raw[12] = 0  # Disable Image only; child controls/animation targets survive.
            sf.objects[pid].set_raw_data(bytes(raw))
        # Keep the existing central title position and animation, fitting the
        # complete official Origin logo in its original 380 x 87 title area.
        rect = sf.objects[2427]
        tree = rect.read_typetree()
        assert tree['m_GameObject']['m_PathID'] == 574
        assert tree['m_SizeDelta'] == {'x': 380.0, 'y': 87.0}
        tree['m_SizeDelta']['y'] = 380.0 * 82 / 429
        rect.save_typetree(tree)
        changed = set(TITLE_PARTS) | {2427}
        for rect_id, expected in ((1118, 'ui_yuexiang_hou01 (1)'), (1160, 'ui_yuexiang_qian01 (1)')):
            go_id = sf.objects[rect_id].read_typetree()['m_GameObject']['m_PathID']
            go = sf.objects[go_id].read_typetree()
            assert go['m_Name'] == expected
            go['m_IsActive'] = False
            sf.objects[go_id].save_typetree(go)
            changed.add(go_id)
        assert all(sf.objects[pid].get_raw_data() == data for pid, data in before.items() if pid not in changed)
        payload = sf.save()
        checked = next(iter(UnityPy.load(payload).files.values()))
        assert set(checked.objects) == set(before)
        for pid in TITLE_PARTS:
            raw = checked.objects[pid].get_raw_data()
            assert raw[12] == (1 if pid == TITLE else 0)
        assert struct.unpack_from('<iq', checked.objects[TITLE].get_raw_data(), 196) == (ext, 52)
        assert all(checked.objects[pid].get_raw_data() == data for pid, data in before.items() if pid not in changed)
        target = output / PAGE
        target.write_bytes(payload)
        manifest = {'assets/bin/Data/' + PAGE: str(target.resolve())}
        if static_background:
            # Replace the blank main video surface and the actual tab background.
            # Keep MediaPlayer and its
            # bindings alive; disable its separate DisplayUGUI renderer, which
            # would otherwise cover the static Sprite with a white rectangle.
            for page, image_id, display_id in (
                    ('2edc795102e2597479e3e077aac50714', 387, 326),
                    (PAGE, 3450, None)):
                data = payload if page == PAGE else archive.read('assets/bin/Data/' + page)
                bg = next(iter(UnityPy.load(data).files.values()))
                prior = {pid: obj.get_raw_data() for pid, obj in bg.objects.items()}
                ext_id = next((i for i, item in enumerate(bg.externals, 1)
                               if item.path == 'c00fa480d6831414f9d6dd29d21396c5'), None)
                if ext_id is None:
                    item = copy.copy(bg.externals[0])
                    item.path = 'c00fa480d6831414f9d6dd29d21396c5'
                    item.guid = bytes(16)
                    item.type = 0
                    item.temp_empty = ''
                    bg.externals.append(item)
                    ext_id = len(bg.externals)
                raw = bytearray(bg.objects[image_id].get_raw_data())
                assert len(raw) == 292 and struct.unpack_from('<iq', raw, 196) == (0, 0)
                struct.pack_into('<iq', raw, 196, ext_id, 2)
                raw[60] = 0
                bg.objects[image_id].set_raw_data(bytes(raw))
                if display_id is not None:
                    raw = bytearray(bg.objects[display_id].get_raw_data())
                    assert len(raw) == 252 and raw[12] == 1
                    raw[12] = 0
                    bg.objects[display_id].set_raw_data(bytes(raw))
                saved = bg.save()
                reread = next(iter(UnityPy.load(saved).files.values()))
                assert set(reread.objects) == set(prior)
                assert all(reread.objects[pid].get_raw_data() == data for pid, data in prior.items()
                           if pid not in (image_id, display_id))
                if display_id is not None:
                    assert reread.objects[display_id].get_raw_data()[12] == 0
                assert struct.unpack_from('<iq', reread.objects[image_id].get_raw_data(), 196) == (ext_id, 2)
                target = output / page
                target.write_bytes(saved)
                manifest['assets/bin/Data/' + page] = str(target.resolve())
        # The generic APK verifier checks that the existing native patches survive.
        (output / 'libil2cpp.so').write_bytes(archive.read('lib/arm64-v8a/libil2cpp.so'))
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf8')
    audit = {'page': 'UI_MapChoose/BattlePass', 'source': str(apk),
             'changed_objects': sorted(changed), 'object_count_unchanged': len(before),
             'title': 'SaiJi_Main_ZhuTi3 (Origin Paradox)', 'unrelated_objects_unchanged': True,
             'static_background': static_background,
             'background_objects': {'UI_BattlePass_Main': [387, 326], 'UI_MapChoose': [3450]} if static_background else {},
             'dynamic_cg': 'Video/battlepassMain.mp4 is absent; static fallback is Season0BG when enabled'}
    (output / 'audit.json').write_text(json.dumps(audit, indent=2), encoding='utf8')
    print(json.dumps(audit))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--static-background', action='store_true')
    args = parser.parse_args()
    patch(args.apk, args.output, args.static_background)
