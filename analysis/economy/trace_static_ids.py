"""Search exact numeric IDs in the already extracted canonical tables and targeted small tables."""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from phase3_analyze import build_schema, decode_record
from phase3_output.phase3_parsers.x2_table_parser import parse_table_container
from targeted_probe import data as targeted

IDS = (2001501, 2006901, 1933001, 1933002, 1933003, 1900101,
       10610001, 10610801, 10630101)
schemas, classes, enums, _ = build_schema((ROOT/'tools/Il2CppDumper-bin/dump.cs').read_text(encoding='utf-8'))
rows = list(csv.DictReader((ROOT/'phase3_output/phase3_active_table_versions.csv').open(encoding='utf-8-sig')))
hits = defaultdict(list)

def walk(obj, path, table):
    if isinstance(obj, dict):
        for k, v in obj.items(): walk(v, f'{path}.{k}', table)
    elif isinstance(obj, list):
        for n, v in enumerate(obj): walk(v, f'{path}[{n}]', table)
    elif type(obj) is int and obj in IDS:
        hits[obj].append((table,path))

for row in rows:
    if row['selected_as_active'] != 'true': continue
    name = row['asset_name']
    fields = schemas.get(name, {}).get('fields')
    if not fields: continue
    payload = ROOT/'phase3_output/raw_tables'/f'{name}__{row["hash"]}.bin'
    parsed = parse_table_container(payload.read_bytes())
    for i, blob in enumerate(parsed['items']):
        rec, _ = decode_record(blob, fields, enums, classes)
        walk(rec, f'record[{i}]', name)

for name in ('Gift','DropProp','DailyTask','TaskControl','ActivityBoxGoods',
             'ActivityTask','TaskEndlessWeek','DailyDungeon','ChapterInfo'):
    for i, rec in enumerate(targeted.get(name,[])):
        walk(rec,f'record[{i}]',name)

if __name__ == '__main__':
    for value in IDS:
        print(value, json.dumps(hits[value][:20],ensure_ascii=False), 'total',len(hits[value]))
