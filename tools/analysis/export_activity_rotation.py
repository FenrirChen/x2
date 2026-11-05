"""Recover the enabled activity groups without inventing rewards."""
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from analysis.progression.probe import read_tables

THEMES = (
    (37, '阏逢敛遗', 13430701), (33, '伪生樱之岛', 50009035),
    (15, '斟鄩之邑', 13430301),
    (13, '全景裂隙', 13430231), (7, '冬至万物', 13430091),
    (10, '珠雀绮馔', 13430111), (99, '日月盈仄', 50009023),
)
STATE_SLOTS = {37: 0, 33: 1, 15: 2, 13: 4, 7: 5, 10: 6, 99: 7}


def restore_yuexi_shops(tables):
    """Retained Table_410 has the four shops missing from canonical ShopConfig."""
    from analysis.progression.probe import (
        ROOT as RESOURCE_ROOT, UnityPy, schemas, enums, classes, decode_record,
    )
    from phase3_protobuf import parse_table_container
    source = 'assets/bin/Data/8c8abe333ea043a418a9e14cc63c7c71'
    with zipfile.ZipFile(RESOURCE_ROOT / 'X2_Eclipse_v2_4.apk') as apk:
        asset = next(o.read() for o in UnityPy.load(apk.read(source)).objects
                     if o.type.name == 'TextAsset')
        blob = asset.m_Script
        if isinstance(blob, str):
            blob = blob.encode('utf-8', 'surrogateescape')
    fields = schemas['ShopConfig']['fields']
    recovered = {}
    for raw in parse_table_container(bytes(blob))['items']:
        row = decode_record(raw, fields, enums, classes)[0]
        if row['ShopID'] in range(887, 891):
            row['ShopParam2'] = [(0, 1, 2, 4)[row['ShopID'] - 887]]
            recovered[row['ShopID']] = row
    if len(recovered) != 4:
        raise ValueError('Missing retained YueXi shop configuration')
    existing = {row['ShopID'] for row in tables['ShopConfig']}
    tables['ShopConfig'].extend(recovered[key] for key in sorted(recovered)
                                if key not in existing)


def retire_disabled_theme(data):
    """Remove playable configuration, retaining only IDs needed to deny entry."""
    tables = data['tables']
    retired = [r for r in tables['ActivityReal'] if r['ActivityGroup'] == 17]
    aids = {r['ActivityID'] for r in retired}
    chapters = {r['ID']: r for r in tables['ActivityDungeon'] + tables['DailyDungeon']}
    chapter_ids = {v for r in retired for v in r.get('ActivityParam1', []) if v in chapters}
    section_ids = {v for cid in chapter_ids for key in ('SectionID', 'ChallengeLevel')
                   for v in chapters[cid].get(key, [])}
    section_catalog = {r['SectionID'] for r in tables['SectionTable']}
    section_ids.update(v for r in retired for key in ('ActivityParam1', 'ActivityParam3', 'ActivityParam4')
                       for v in r.get(key, []) if v in section_catalog)
    section_ids.discard(0)
    data['closed_section_ids'] = sorted(set(data.get('closed_section_ids', [])) | section_ids)
    data['state_cycle_size'] = 8
    data['themes'] = [t for t in data['themes'] if t['group'] != 17]
    for theme in data['themes']:
        theme['state_slot'] = STATE_SLOTS[theme['group']]
    for name, rows in tables.items():
        tables[name] = [r for r in rows if r.get('ActivityID') not in aids]
    for name in ('ActivityDungeon', 'DailyDungeon'):
        tables[name] = [r for r in tables[name] if r['ID'] not in chapter_ids]
    tables['SectionTable'] = [r for r in tables['SectionTable'] if r['SectionID'] not in section_ids]
    return data


def main():
    names = ['ActivityReal', 'ActivityDungeon', 'DailyDungeon', 'ActivityTask',
             'ActivityTaskBox', 'TaskCondition', 'NewYearCafe', 'NewYearCafeBuff',
             'NewYearFood', 'NewYearFoodTask', 'NewYearCook', 'NewYearCookTask',
             'ActivityBox', 'ActivityBoxGoods', 'ActivityBuilding', 'ShopConfig',
             'ShopGoodsGroup', 'Gift', 'AnswerConfig', 'Tower', 'TowerBase',
             'TowerController', 'TowerGrid', 'TowerRank', 'TowerEffect', 'Item',
             'ExtraDroop', 'SectionTable', 'MapInfo', 'Language', 'AccountBuff', 'POVChapterInfo']
    tables, meta, missing = read_tables(names)
    if missing:
        raise ValueError(f'Missing required tables: {missing}')
    restore_yuexi_shops(tables)
    # Only the 70010 chapters are reachable by an activity; the 17 permanent
    # chapters (no UnlockActiviyID) are restored from data/activity_rotation_extra.json
    # so a regeneration cannot drop their whole-chapter ClearReward again.
    tables['POVChapterInfo'] = [r for r in tables['POVChapterInfo']
                               if r.get('UnlockActiviyID') == 70010]
    from tools.analysis.export_world_boss import mail_templates
    tables['MailInfo'], meta['MailInfo'] = mail_templates(set(range(1325044, 1325054)))
    sections = {r['SectionID']: r for r in tables['SectionTable']}
    chapters = {r['ID']: r for r in tables['ActivityDungeon'] + tables['DailyDungeon']}
    themes = []
    for group, title, title_key in THEMES:
        activities = [r for r in tables['ActivityReal'] if r.get('ActivityGroup') == group
                      and (group != 7 or r['ActivityID'] in (70049, 70050, 70051))]
        chapter_ids = sorted({x for r in activities for x in r.get('ActivityParam1', [])
                              if x in chapters})
        owned = {sid for cid in chapter_ids for key in ('SectionID', 'ChallengeLevel')
                 for sid in chapters[cid].get(key, [])}
        # Some gameplay lists are ChapterIDs, others contain direct SectionIDs.
        for r in activities:
            for key in ('ActivityParam1', 'ActivityParam3', 'ActivityParam4'):
                owned.update(x for x in r.get(key, []) if x in sections)
        # Zero is the client's placeholder, never a playable section.
        owned.discard(0)
        themes.append({'group': group, 'title': title, 'title_key': title_key,
                       'activities': activities, 'chapter_ids': chapter_ids,
                       'section_ids': sorted(owned)})
    selected_ids = {r['ActivityID'] for t in themes for r in t['activities']}
    section_ids = {s for t in themes for s in t['section_ids']}
    tables['ActivityReal'] = [r for r in tables['ActivityReal'] if r['ActivityID'] in selected_ids]
    tables['SectionTable'] = [r for r in tables['SectionTable'] if r['SectionID'] in section_ids]
    tables['Language'] = []  # Native texts remain in the APK; no duplicate full dictionary.
    data = {'anchor': '2026-10-10T00:00:00+08:00', 'period_days': 5,
            'reset_each_period': True, 'themes': themes, 'source': meta, 'tables': tables}
    # Collect closed sections before narrowing ActivityReal/SectionTable on export.
    full_tables, _, _ = read_tables(['ActivityReal', 'SectionTable'])
    data['tables']['ActivityReal'] = full_tables['ActivityReal']
    data['tables']['SectionTable'] = full_tables['SectionTable']
    retire_disabled_theme(data)
    data['tables']['ActivityReal'] = [r for r in data['tables']['ActivityReal'] if r['ActivityID'] in selected_ids]
    data['tables']['SectionTable'] = [r for r in data['tables']['SectionTable'] if r['SectionID'] in section_ids]
    path = ROOT / 'src/x2server/data/activity_rotation_catalog.json'
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    print('Themes:', [(t['title'], len(t['section_ids'])) for t in themes])
    print('Tables:', {k: len(v) for k, v in tables.items()})


if __name__ == '__main__':
    main()
