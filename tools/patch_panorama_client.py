"""Restore Rift shop metadata and original logical/physical scene pairing.

Use the current signed APK as baseline. The donor supplies only the four missing
scene registrations, whose compiled level files are already resource supplements.
All other BuildSettings, resource bindings, native patches and data rows remain.
"""
import argparse
import json
from pathlib import Path
import struct
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent), str(ROOT.parent / '.phase2_deps')]
import patch_contract_chujiu as c
from phase3_protobuf import parse_table_container, parse_message, rsa_public_unpad, convert_data_bytes
from tools.analysis.patch_activity_scenes import xor_table, SCENE_ALIASES, MAPINFO_FILE

DATA = 'assets/bin/Data/'
SHOP = '0a5189b8d93663c4aa152623435068da'
CAVE = 0x42B3E00  # after the covenant helper, inside its verified zero area


def table_blob(payload, name):
    sf = c.load_serialized(payload)
    obj = next(o for o in c.objects(sf) if o.class_id == c.TEXT_CLASS)
    head, blob = c.split_raw_text_asset(obj.get_raw_data(), name)
    return sf, obj, head, blob


def save_table(sf, obj, head, blob):
    raw = head + len(blob).to_bytes(4, 'little') + blob
    obj.set_raw_data(raw + bytes(-len(raw) % 4))
    return sf.save()


def shop_config(payload):
    sf, obj, head, blob = table_blob(payload, 'ShopConfig')
    keys, rows = c.parse_table(blob)
    original = dict(zip(keys, rows))
    definitions = json.loads((ROOT / 'src/x2server/data/panorama_shop_configs.json').read_text(encoding='utf-8'))['shops']
    fields = ['ShopID', 'ShopType', 'UnlockType', 'ShopParam1', 'ShopParam2', 'ShopParam3',
              'ShopName', 'ShopNameChina', 'ShopDesc', 'ShopIcon', 'UIPrefabID', 'ShopRank', 'ShopResourceType']
    for row in definitions:
        record = bytearray()
        for number, field in enumerate(fields, 1):
            if field not in row:
                continue
            value = row[field]
            value = value.get('value') if isinstance(value, dict) else value
            for element in value if isinstance(value, list) else [value]:
                record += c.f_str(number, element) if isinstance(element, str) else c.f_int(number, element)
        if row['ShopID'] in original:
            if original[row['ShopID']] != bytes(record):
                raise ValueError('shop already exists with different metadata')
        else:
            c.insert_sorted(keys, rows, [(row['ShopID'], bytes(record))])
    plain = c.serialize_table(keys, rows)
    assert all(dict(zip(keys, rows))[k] == v for k, v in original.items())
    return save_table(sf, obj, head, plain), plain[:16]


def map_info(payload, original_payload):
    sf, obj, head, blob = table_blob(payload, 'MapInfo')
    _, _, _, original_blob = table_blob(original_payload, 'MapInfo')
    old = parse_table_container(blob)
    source = parse_table_container(original_blob)
    def name(row):
        return next(f.value.decode() for f in parse_message(row)[0] if f.field == 9)
    wanted = {k: name(row) for k, row in zip(source['keys'], source['items'])
              if name(row) in SCENE_ALIASES}
    rows, changes = [], []
    for key, row in zip(old['keys'], old['items']):
        fields, _ = parse_message(row)
        if key in wanted and name(row) != wanted[key]:
            assert name(row) == SCENE_ALIASES[wanted[key]], key
            changes.append(key)
        rows.append(b''.join(c.f_str(9, wanted[key]) if f.field == 9 and key in wanted else row[f.start:f.end]
                            for f in fields if not (f.field == 1000 and isinstance(f.value, bytes) and not any(f.value))))
    plain = c.serialize_table(old['keys'], rows)
    if len(plain) < len(old['plain']):
        for size in range(len(old['plain']) - len(plain) + 1):
            candidate = c.serialize_table(old['keys'], rows[:-1] + [rows[-1] + c.f_str(1000, bytes(size))])
            if len(candidate) == len(old['plain']):
                plain = candidate
                break
    assert len(plain) == len(old['plain'])
    signed = rsa_public_unpad(blob[:128])
    obfuscated = xor_table(plain)
    assert obfuscated[:len(signed)] == signed
    encrypted = blob[:128] + obfuscated[len(signed):]
    assert convert_data_bytes(encrypted) == plain
    return save_table(sf, obj, head, encrypted), changes


def native_hook(native, signature):
    before = bytes(native)
    native = bytearray(native)
    target = c.branch_target(struct.unpack_from('<I', native, c.HOOK)[0], c.HOOK)
    old_cave, new_cave = c.OLD_CAVE, c.NEW_CAVE
    try:
        c.OLD_CAVE = target
        prefixes, _ = c.read_existing_signatures(native)
        if signature not in prefixes:
            prefixes.append(signature)
        c.NEW_CAVE = CAVE
        payload = c.build_payload(prefixes)
    finally:
        c.OLD_CAVE, c.NEW_CAVE = old_cave, new_cave
    assert native[CAVE:CAVE + len(payload)] == bytes(len(payload))
    native[CAVE:CAVE + len(payload)] = payload
    struct.pack_into('<I', native, c.HOOK, c.b_insn(c.HOOK, CAVE))
    assert native[:c.HOOK] == before[:c.HOOK]
    assert native[c.HOOK + 4:CAVE] == before[c.HOOK + 4:CAVE]
    assert native[CAVE + len(payload):] == before[CAVE + len(payload):]
    return bytes(native)


def prepare(baseline, donor, original, output):
    output.mkdir(parents=True, exist_ok=True)
    patches = {}
    with zipfile.ZipFile(baseline) as a, zipfile.ZipFile(donor) as b, zipfile.ZipFile(original) as source:
        payload, signature = shop_config(a.read(DATA + SHOP))
        patches[DATA + SHOP] = payload
        payload, maps = map_info(a.read(DATA + MAPINFO_FILE), source.read(DATA + MAPINFO_FILE))
        patches[DATA + MAPINFO_FILE] = payload
        sf = c.load_serialized(a.read(DATA + 'globalgamemanagers'))
        obj = next(o for o in c.objects(sf) if o.class_id == 141)  # BuildSettings
        tree = obj.read_typetree()
        donor_sf = c.load_serialized(b.read(DATA + 'globalgamemanagers'))
        scenes = next(o.read_typetree()['scenes'] for o in c.objects(donor_sf) if o.class_id == 141)
        assert scenes[:len(tree['scenes'])] == tree['scenes']
        for index in range(len(tree['scenes']), len(scenes)):
            entry = DATA + 'level' + str(index)
            assert a.read(entry) == b.read(entry), entry
        tree['scenes'] = scenes
        obj.save_typetree(tree)
        patches[DATA + 'globalgamemanagers'] = sf.save()
        patches[c.NATIVE] = native_hook(a.read(c.NATIVE), signature)
        assert next(o for o in c.objects(sf) if o.class_id == c.RESOURCE_CLASS).get_raw_data() == next(
            o for o in c.objects(c.load_serialized(a.read(DATA + 'globalgamemanagers')))
            if o.class_id == c.RESOURCE_CLASS).get_raw_data()
    manifest = {}
    for name, payload in patches.items():
        target = output / (Path(name).name + '.bin')
        target.write_bytes(payload)
        manifest[name] = str(target.resolve())
    plan = output / 'manifest.json'
    plan.write_text(json.dumps({'patches': manifest, 'additions': {}, 'images': []}, indent=2), encoding='utf-8')
    (output / 'audit.json').write_text(json.dumps({'restored_scene_count': len(scenes),
        'restored_maps': maps, 'shop_ids': [876, 877, 878, 879], 'native_prefix': signature.hex()}, indent=2), encoding='utf-8')
    return plan


def validate(baseline, release, plan):
    """Check signed output against the exact four-entry patch boundary."""
    manifest = json.loads(plan.read_text(encoding='utf-8'))['patches']
    with zipfile.ZipFile(baseline) as old, zipfile.ZipFile(release) as new:
        def entries(z):
            return {i.filename: i for i in z.infolist()
                    if not i.filename.upper().startswith('META-INF/')}
        a, b = entries(old), entries(new)
        assert set(a) == set(b), 'unexpected APK entries'
        for name, item in a.items():
            if name in manifest:
                assert new.read(name) == Path(manifest[name]).read_bytes(), name
            else:
                assert (item.CRC, item.file_size) == (b[name].CRC, b[name].file_size), name
        native = new.read(c.NATIVE)
        previous = old.read(c.NATIVE)
        changed = [i for i, (x, y) in enumerate(zip(native, previous)) if x != y]
        assert len(native) == len(previous)
        assert all(c.HOOK <= i < c.HOOK + 4 or CAVE <= i < CAVE + 0x300 for i in changed)
        _, _, _, blob = table_blob(new.read(DATA + SHOP), 'ShopConfig')
        keys, rows = c.parse_table(blob)
        _, _, _, old_blob = table_blob(old.read(DATA + SHOP), 'ShopConfig')
        old_keys, old_rows = c.parse_table(old_blob)
        assert set(keys) - set(old_keys) == {876, 877, 878, 879}
        assert all(dict(zip(keys, rows))[k] == v for k, v in zip(old_keys, old_rows))
        before = c.load_serialized(old.read(DATA + 'globalgamemanagers'))
        after = c.load_serialized(new.read(DATA + 'globalgamemanagers'))
        before_objs, after_objs = list(c.objects(before)), list(c.objects(after))
        assert len(before_objs) == len(after_objs)
        for x, y in zip(before_objs, after_objs):
            assert (x.path_id, x.class_id) == (y.path_id, y.class_id)
            if x.class_id != 141:
                assert x.get_raw_data() == y.get_raw_data()
            else:
                t1, t2 = x.read_typetree(), y.read_typetree()
                assert t2['scenes'][:len(t1['scenes'])] == t1['scenes']
                assert len(t2['scenes']) == 32 and len(t1['scenes']) == 28
                t2['scenes'] = t1['scenes']
                assert t1 == t2
        assert new.testzip() is None
    return {'validated': str(release), 'modified_entries': list(manifest),
            'shops': len(keys), 'scenes': 32, 'native_changed_bytes': len(changed)}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ['baseline', 'donor', 'original', 'work', 'output']:
        p.add_argument('--' + flag, required=True, type=Path)
    args = p.parse_args()
    plan = prepare(args.baseline, args.donor, args.original, args.work)
    from savemanager.client.supplement_reference_resources import assemble
    assemble(args.baseline, plan, args.output)
