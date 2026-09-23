from __future__ import annotations

import json
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / '.phase2_deps'))
import UnityPy
from phase3_analyze import class_blocks, enum_blocks, parse_fields, decode_record, resource_map
from phase3_output.phase3_parsers.x2_table_parser import parse_table_container

NAMES = ('Gift', 'DropProp', 'DailyTask', 'TaskEndlessWeek', 'TaskControl',
         'TaskConditionLine', 'DailyDungeon', 'ActivityBoxGoods',
         'ActivityTask', 'ActivityExchange', 'FavorabilityDailyTask',
         'TaskChapter', 'TaskHappy', 'TaskSeven', 'AchievementCondition',
         'ChapterInfo')

dump = (ROOT / 'tools/Il2CppDumper-bin/dump.cs').read_text(encoding='utf-8')
blocks = class_blocks(dump)
classes = {name: parse_fields(block) for (ns, name), block in blocks.items() if ns == 'Example'}
enums = enum_blocks(dump)
resources = {r['resource_path'].lower(): r for r in resource_map()}
chosen = {}
for name in NAMES:
    match = resources.get('table/' + name.lower())
    if match:
        chosen[match['source_hash']] = name

data = {}
meta = {}
with zipfile.ZipFile(ROOT / 'X2_Eclipse_v2_4.apk') as apk:
    for digest, name in chosen.items():
        source = 'assets/bin/Data/' + digest
        env = UnityPy.load(apk.read(source))
        objects = [o.read() for o in env.objects if o.type.name == 'TextAsset']
        obj = next((o for o in objects if getattr(o, 'm_Name', '') == name), None)
        if obj is None:
            continue
        payload = getattr(obj, 'm_Script')
        if isinstance(payload, str):
            payload = payload.encode('utf-8', 'surrogateescape')
        parsed = parse_table_container(bytes(payload))
        fields = classes.get(name)
        if fields:
            records = [decode_record(item, fields, enums, classes)[0] for item in parsed['items']]
        else:
            records = []
        data[name] = records
        meta[name] = {'source': source, 'count': len(parsed['items']),
                      'decoded': len(records), 'fields': [f['name'] for f in fields or []]}

if __name__ == '__main__':
    for name in NAMES:
        if name in meta:
            print('\n###', name, json.dumps(meta[name], ensure_ascii=False))
            for rec in data[name][:3]:
                print(json.dumps(rec, ensure_ascii=False))
        else:
            print('\n###', name, 'NO CANONICAL RESOURCE')
