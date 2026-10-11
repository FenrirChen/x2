"""Repair unavailable activity SceneMap names while preserving original map logic.

Build-time only: MapInfo IDs, stages, preloads and monster levels are unchanged.
The original RSA prefix is retained. A protobuf unknown-field pad preserves
payload length, so its original encrypted prefix remains valid.
"""
import argparse, hashlib, json, struct, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT.parent), str(ROOT.parent / '.phase2_deps')]
import UnityPy
from phase3_protobuf import convert_data_bytes, parse_table_container, parse_message, rsa_public_unpad

SCENE_ALIASES = {
    'LevelMap_SiShenXueYuan_NY': 'LevelMap_SiShenXueYuan',
    'LevelMap_ZhenXunZhiYi': 'LevelMap_SiShenXueYuan',
    'LevelMap_BaiYeXueYuan_tafang': 'LevelMap_BaiYeXueYuan',
    'LevelMap_Pyramid_Tower': 'TestPyramidMap',
}
MAPINFO_FILE = '192c1f2b873c253499869d5dd6c8fb05'

def varint(n):
    out = bytearray()
    while n > 127:
        out.append((n & 127) | 128); n >>= 7
    out.append(n)
    return bytes(out)

def ld(number, blob):
    return varint(number << 3 | 2) + varint(len(blob)) + blob

def xor_table(blob):
    out = bytearray(blob)
    index, delta = 1, 0
    while index < len(out):
        out[index] ^= (delta + index) & 255
        index <<= 1; delta -= 1
    index, delta = len(out) - 1, 0
    while index > 0:
        out[index] ^= (delta + index) & 255
        index >>= 1; delta -= 1
    return bytes(out)

def patch(apk, output):
    entry = 'assets/bin/Data/' + MAPINFO_FILE
    calendar = json.loads((ROOT / 'src/x2server/data/activity_rotation_catalog.json').read_text(encoding='utf-8'))
    sections = {r['SectionID']: r for r in json.loads((ROOT / 'src/x2server/data/battle_entry_catalog.json').read_text(encoding='utf-8'))['sections']}
    maps = {mid for theme in calendar['themes'] for sid in theme['section_ids'] for mid in sections[sid]['Maps']}
    with zipfile.ZipFile(apk) as z:
        build = next(o.read_typetree() for o in UnityPy.load(z.read('assets/bin/Data/globalgamemanagers')).objects if o.type.name == 'BuildSettings')
        available = {Path(p).stem for p in build['scenes']}
        assert set(SCENE_ALIASES.values()) <= available
        assert not set(SCENE_ALIASES) & available
        source = z.read(entry)
    env = UnityPy.load(source)
    text = next(o for o in env.objects if o.type.name == 'TextAsset' and o.read_typetree()['m_Name'].lower() == 'mapinfo')
    tree = text.read_typetree(); script = tree['m_Script']
    encrypted = script.encode('utf-8', 'surrogateescape') if isinstance(script, str) else script
    container = parse_table_container(encrypted); assert container['kind'] == 'array'
    plain = container['plain']; fields, _ = parse_message(plain, 4)
    chunks = [plain[:4]]; changed = []; records = []
    for field in fields:
        if field.field != 2 or field.wire != 2:
            chunks.append(plain[field.start:field.end]); continue
        record = field.value; values, _ = parse_message(record)
        mid = next(v.value for v in values if v.field == 1)
        old = next(v.value.decode() for v in values if v.field == 9)
        if mid in maps and old in SCENE_ALIASES:
            new = SCENE_ALIASES[old]
            record = b''.join(ld(9, new.encode()) if v.field == 9 else record[v.start:v.end] for v in values)
            changed.append({'map_id': mid, 'old_scene': old, 'scene': new})
        records.append((mid, record)); chunks.append(ld(2, record))
    assert changed
    # Add padding to the last (otherwise untouched) record, outside the RSA prefix.
    assert records[-1][0] not in maps
    prefix = b''.join(chunks[:-1]); tail = records[-1][1]
    repaired = None
    for n in range(len(plain) - len(prefix) - len(tail)):
        candidate = prefix + ld(2, tail + ld(1000, bytes(n)))
        if len(candidate) == len(plain):
            repaired = candidate; break
    assert repaired is not None, 'cannot preserve signed table length'
    signed_prefix = rsa_public_unpad(encrypted[:128]); obfuscated = xor_table(repaired)
    assert obfuscated[:len(signed_prefix)] == signed_prefix, 'RSA-covered prefix changed'
    patched = encrypted[:128] + obfuscated[len(signed_prefix):]
    assert len(patched) == len(encrypted) and convert_data_bytes(patched) == repaired
    decoded = parse_table_container(patched)
    assert decoded['keys'] == container['keys'] and len(decoded['items']) == len(container['items'])
    for old_record, new_record in zip(container['items'], decoded['items']):
        a, _ = parse_message(old_record); b, _ = parse_message(new_record)
        assert [(v.field,v.wire,v.value) for v in a if v.field != 9] == [(v.field,v.wire,v.value) for v in b if v.field not in (9,1000)]
        mid = next(v.value for v in b if v.field == 1)
        name = next(v.value.decode() for v in b if v.field == 9)
        if mid in maps: assert name in available, (mid,name)
    original = {o.path_id: o.get_raw_data() for o in env.objects}
    tree['m_Script'] = patched.decode('utf-8','surrogateescape'); text.save_typetree(tree)
    result = env.file.save(); reread = UnityPy.load(result)
    for o in reread.objects:
        if o.path_id != text.path_id: assert o.get_raw_data() == original[o.path_id]
    raw = next(o.read_typetree()['m_Script'] for o in reread.objects if o.path_id == text.path_id).encode('utf-8','surrogateescape')
    assert raw == patched
    output.mkdir(parents=True, exist_ok=True); target=output/MAPINFO_FILE; target.write_bytes(result)
    manifest={entry:str(target.resolve())};(output/'patches.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    audit={'source_sha256':hashlib.sha256(source).hexdigest(),'available_scenes':sorted(available),'activity_sections':sum(len(t['section_ids']) for t in calendar['themes']),'activity_maps':len(maps),'changes':changed,'padding_record':records[-1][0]}
    (output/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print('activity sections',audit['activity_sections'],'maps',len(maps),'repaired',len(changed),'RSA prefix and original gameplay fields unchanged')

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--apk',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();patch(a.apk,a.output)
