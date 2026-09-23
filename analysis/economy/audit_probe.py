from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from phase3_analyze import build_schema, decode_record
from phase3_output.phase3_parsers.x2_table_parser import parse_table_container

WANTED = ('SectionTable', 'ShopConfig', 'ShopGoodsGroup', 'MissionTable',
          'TaskCondition', 'Item', 'Achievement', 'DrawRules', 'DrawParam',
          'Language', 'LanguageUI')
schemas, classes, enums, _ = build_schema((ROOT / 'tools/Il2CppDumper-bin/dump.cs').read_text(encoding='utf-8'))
rows = list(csv.DictReader((ROOT / 'phase3_output/phase3_active_table_versions.csv').open(encoding='utf-8-sig')))
data = {}
meta = {}
for name in WANTED:
    row = next(r for r in rows if r['asset_name'] == name and r['selected_as_active'] == 'true')
    blob = ROOT / 'phase3_output/raw_tables' / f'{name}__{row["hash"]}.bin'
    container = parse_table_container(blob.read_bytes())
    records = [decode_record(item, schemas[name]['fields'], enums, classes)[0] for item in container['items']]
    data[name] = records
    meta[name] = {'file': str(blob.relative_to(ROOT)).replace('\\', '/'), 'count': len(records)}

lang = {}
for name in ('Language', 'LanguageUI'):
    for rec in data[name]:
        lang[rec.get('Key')] = rec.get('Chinese') or rec.get('LanguageCH') or rec.get('LanguageCN')

def show(name, count=5):
    print('\n###', name, meta[name])
    for rec in data[name][:count]:
        print(json.dumps(rec, ensure_ascii=False))

if __name__ == '__main__':
    for n in ('ShopConfig', 'ShopGoodsGroup', 'MissionTable', 'TaskCondition', 'Item', 'Achievement'):
        show(n, 5)
    for n in ('SectionTable',):
        print('\n###', n)
        for sid in (2110001, 2110801, 2160561):
            rec = next((r for r in data[n] if r.get('SectionID') == sid), None)
            print(json.dumps(rec, ensure_ascii=False))
    print('\nLANG SAMPLE', data['Language'][0], data['LanguageUI'][0])
