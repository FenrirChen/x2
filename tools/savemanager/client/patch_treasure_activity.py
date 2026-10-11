"""Preserve ordinary rooms, add retained tower rooms, embed anniversary CG."""
import copy
import json
import struct
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT.parent), str(ROOT.parent / '.phase2_deps')]
import UnityPy
from phase3_protobuf import parse_message
from tools.analysis.patch_activity_scenes import ld
from tools.savemanager.client.patch_activity_ui import branch, adrp, ldr, str_


def entries(blob):
    fields, _ = parse_message(blob)
    result = {}
    for field in fields:
        assert field.field == 1 and field.wire == 2
        children, _ = parse_message(field.value)
        key = next(c.value for c in children if c.field == 1)
        assert key not in result
        result[key] = field.value
    return result


def text_asset(env):
    obj = next(o for o in env.objects if o.type.name == 'TextAsset')
    tree = obj.read_typetree()
    blob = tree['m_Script']
    return obj, tree, blob.encode('utf-8', 'surrogateescape') if isinstance(blob, str) else blob


def patch(apk, output):
    output.mkdir(parents=True, exist_ok=True)
    index = json.loads((ROOT / 'tools/savemanager/client/activity_resource_index.json').read_text(encoding='utf-8'))
    manifest, audit = {}, []
    with zipfile.ZipFile(apk) as z:
        native = bytearray(z.read('lib/arm64-v8a/libil2cpp.so'))
        cave, hook = 0x42B0900, 0x1E5B6B8
        assert native[hook:hook + 8] == bytes.fromhex('003440f9c0035fd6')
        words = [ldr(8, 0, 0x68), 0xB4000068, 0xAA0803E0, 0xD65F03C0,
                 0xA9BE7BF3, 0xAA0003F3]  # preserve x19/lr; x19 = room
        def emit(word):
            words.append(word)
        def reference(address, rd):
            emit(adrp(8, cave + 4 * len(words), address))
            emit(ldr(8, 8, address & 0xFFF))
            emit(ldr(rd, 8))
        reference(0x5288938, 0)  # List<TriggerGroup>, SceneData constructor
        emit(branch(cave + 4 * len(words), 0x3F6452C, True))
        emit(str_(0, 19, 0x68))
        emit(str_(0, 31, 0x10))
        reference(0x523A508, 1)
        emit(branch(cave + 4 * len(words), 0x3D4E3A8, True))
        emit(ldr(0, 31, 0x10))
        emit(0xA8C27BF3)
        emit(0xD65F03C0)
        blob = struct.pack('<' + 'I' * len(words), *words)
        assert native[cave:cave + len(blob)] == bytes(len(blob))
        native[cave:cave + len(blob)] = blob
        native[hook:hook + 4] = struct.pack('<I', branch(hook, cave))
        target = output / 'libil2cpp.treasure.so'
        target.write_bytes(native)
        audit.append({'native_hook': hex(hook), 'cave': hex(cave),
                      'purpose': 'initialize absent room trigger list, preserve real triggers',
                      'instructions': blob.hex()})
        # SceneMap aliases also select scenelogic. Add only missing room keys:
        # shared door/boss geometry must remain byte-identical for ordinary maps.
        for base, tower in [('46ebaa628637ace419252edac8d0d39d', '7470463322250fa4092ed34864a317fe'),
                            ('ad71ec8efa62eff4db92f94b1aaeb0f0', 'd42e07006f351a34a9d81e411e686434')]:
            env = UnityPy.load(z.read('assets/bin/Data/' + base))
            obj, tree, original = text_asset(env)
            _, _, extra = text_asset(UnityPy.load(z.read('assets/bin/Data/' + tower)))
            existing, additions = entries(original), entries(extra)
            missing = {k: v for k, v in additions.items() if k not in existing}
            assert missing
            patched = original + b''.join(ld(1, value) for value in missing.values())
            assert all(entries(patched)[k] == v for k, v in existing.items())
            tree['m_Script'] = patched.decode('utf-8', 'surrogateescape')
            obj.save_typetree(tree)
            target = output / base
            target.write_bytes(env.file.save())
            assert text_asset(UnityPy.load(target.read_bytes()))[2] == patched
            manifest['assets/bin/Data/' + base] = str(target.resolve())
            audit.append({'scene_logic': base, 'added_rooms': [k.decode() for k in missing]})

        sprite_file, sprite_id = index['uialtas/cg/ann1']
        art = UnityPy.load(z.read('assets/bin/Data/' + sprite_file))
        sprite_source = next(o for o in art.objects if o.path_id == sprite_id)
        sprite_tree = sprite_source.read_typetree()
        texture_source = next(o for o in art.objects if o.path_id == sprite_tree['m_RD']['texture']['m_PathID'])
        assert texture_source.read().image.size == (1336, 752)
        pages = {'ui_anniversary_main': [652, 841], 'ui_anniversary_section': [386, 403],
                 'ui_anniversary_task': [843], 'ui_anniversary_poolshop': [962, 1144],
                 'ui_anniversary_tower_section': [490, 589]}
        for page, images in pages.items():
            file, _ = index['ui/' + page]
            env = UnityPy.load(z.read('assets/bin/Data/' + file))
            sf = next(iter(env.files.values()))
            originals = {pid: o.get_raw_data() for pid, o in sf.objects.items()}
            first_id = max(sf.objects) + 1
            clones = []
            for source, pid in [(texture_source, first_id), (sprite_source, first_id + 1)]:
                clone = copy.copy(source)
                clone.assets_file, clone.path_id = sf, pid
                clone.serialized_type = copy.deepcopy(source.serialized_type)
                sf.types.append(clone.serialized_type)
                clone.type_id = len(sf.types) - 1
                clone.set_raw_data(source.get_raw_data())
                sf.objects[pid] = clone
                clones.append(clone)
            tree = copy.deepcopy(sprite_tree)
            tree['m_RD']['texture'] = {'m_FileID': 0, 'm_PathID': first_id}
            clones[1].save_typetree(tree)
            changed = set(images)
            for pid in images:
                raw = bytearray(sf.objects[pid].get_raw_data())
                assert len(raw) == 292
                struct.pack_into('<iq', raw, 196, 0, first_id + 1)
                # Use the standard UI material rather than a stripped custom shader.
                struct.pack_into('<iq', raw, 32, 0, 0)
                raw[60] = 0
                sf.objects[pid].set_raw_data(bytes(raw))
                go = struct.unpack_from('<q', raw, 4)[0]
                rect_obj = next(o for o in sf.objects.values() if o.type.name == 'RectTransform'
                                and o.read_typetree()['m_GameObject']['m_PathID'] == go)
                rect = rect_obj.read_typetree()
                if rect['m_SizeDelta'] == {'x': 0., 'y': 0.} and rect['m_AnchorMin'] == rect['m_AnchorMax']:
                    rect['m_SizeDelta'] = {'x': 1336., 'y': 752.}
                    rect_obj.save_typetree(rect)
                    changed.add(rect_obj.path_id)
            payload = sf.save()
            verified = UnityPy.load(payload)
            reread = next(iter(verified.files.values()))
            for pid, raw in originals.items():
                if pid not in changed:
                    assert reread.objects[pid].get_raw_data() == raw
            for pid in images:
                assert struct.unpack_from('<iq', reread.objects[pid].get_raw_data(), 196) == (0, first_id + 1)
            assert reread.objects[first_id].read().image.size == (1336, 752)
            target = output / file
            target.write_bytes(payload)
            manifest['assets/bin/Data/' + file] = str(target.resolve())
            audit.append({'page': page, 'images': images, 'embedded_cg': 'ann1'})
    (output / 'patches.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    (output / 'audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Verified', len(manifest), 'resource patches')


if __name__ == '__main__':
    patch(sys.argv[1], Path(sys.argv[2]))
