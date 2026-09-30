"""Decode only named progression tables from the existing canonical resource index."""
from __future__ import annotations

import csv
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / '.phase2_deps')]
import UnityPy
from phase3_analyze import build_schema, class_blocks, parse_fields, decode_record, resource_map
from phase3_protobuf import parse_table_container

NAMES = (
    'RoleExp', 'PlayerLevelBonus', 'PlayerStage', 'PlayerAttrib',
    'ArtifactBase', 'ArtifactFuse', 'EquibBase', 'EquibAttrib',
    'EquibAttribBD', 'EquibExp', 'EquibStage', 'EquibSuit',
    'SkillBase', 'SkillLevel', 'UnitBase', 'Item', 'FunctionOpen',
    'GodHole', 'JewelBase', 'Gift', 'Language', 'LanguageUI',
)

dump = (ROOT / 'tools/Il2CppDumper-bin/dump.cs').read_text(encoding='utf-8')
schemas, classes, enums, _ = build_schema(dump)
for (namespace, name), block in class_blocks(dump).items():
    if namespace == 'Example' and name not in classes:
        classes[name] = parse_fields(block)
active_versions = ROOT / 'phase3_output/phase3_active_table_versions.csv'
active = ({r['asset_name']: r for r in csv.DictReader(active_versions.open(encoding='utf-8-sig'))
           if r['selected_as_active'] == 'true'} if active_versions.exists() else {})
resources = {r['resource_path'].lower(): r for r in resource_map()}


def read_tables(names=NAMES):
    data, meta = {}, {}
    missing = []
    with zipfile.ZipFile(ROOT / 'X2_Eclipse_v2_4.apk') as apk:
        for name in names:
            if name in active:
                digest = active[name]['hash']
                blob = (ROOT / 'phase3_output/raw_tables' / f'{name}__{digest}.bin').read_bytes()
                source = f'phase3_output/raw_tables/{name}__{digest}.bin'
            else:
                entry = resources.get('table/' + name.lower())
                if not entry:
                    missing.append(name)
                    continue
                digest = entry['source_hash']
                source = 'assets/bin/Data/' + digest
                env = UnityPy.load(apk.read(source))
                objects = [o.read() for o in env.objects if o.type.name == 'TextAsset']
                obj = next((o for o in objects if getattr(o, 'm_Name', '').lower() == name.lower()), None)
                if obj is None:
                    missing.append(name)
                    continue
                blob = obj.m_Script
                if isinstance(blob, str):
                    blob = blob.encode('utf-8', 'surrogateescape')
            container = parse_table_container(bytes(blob))
            fields = schemas.get(name, {}).get('fields') or classes.get(name)
            if not fields:
                missing.append(name + ': schema')
                continue
            records = [decode_record(item, fields, enums, classes)[0] for item in container['items']]
            data[name] = records
            meta[name] = {'source': source, 'record_count': len(records), 'fields': [x['name'] for x in fields]}
    return data, meta, missing


if __name__ == '__main__':
    selected = sys.argv[1:] or NAMES
    data, meta, missing = read_tables(selected)
    for name in selected:
        if name not in data:
            continue
        print(name, json.dumps(meta[name], ensure_ascii=False))
        for rec in data[name][:3]:
            print(json.dumps(rec, ensure_ascii=False))
    print('missing', missing)
