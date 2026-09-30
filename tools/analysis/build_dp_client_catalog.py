"""Build DP catalogs from fully decrypted, strictly framed canonical APK tables.

Run extract_dp_client_evidence.py first. No byte repairs or sibling-row guesses.
"""
from collections import Counter, defaultdict
import json
import re
from pathlib import Path
from _client_table_wire import parse_message, parse_table_container

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / 'analysis/dp_client/raw'
DATA = ROOT / 'src/x2server/data'
TYPES = {1: 'E_KillMonster', 26: 'E_ShopBuyItem', 27: 'E_NPCInteraction',
         32: 'E_ShopSpendMoney', 34: 'E_BeatSection', 35: 'E_GetItemID',
         36: 'E_GetItemQuality', 37: 'E_GetItemQualityPer', 39: 'E_GetMoneyPer',
         95: 'E_KillMonsterInSan'}


def table(name):
    parsed = parse_table_container((RAW / (name + '.bytes')).read_bytes())
    assert parsed['kind'] == 'array' and not parsed['unknown_wrapper_fields']
    rows = {}
    for key, blob in zip(parsed['keys'], parsed['items'], strict=True):
        values, consumed = parse_message(blob)
        assert consumed == len(blob)
        row = defaultdict(list)
        for value in values:
            row[value.field].append(value.value)
        assert row[1] == [key] and key not in rows
        rows[key] = row
    return rows


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')


def build():
    tables = {name: table(name) for name in
              ('chapterinfo', 'taskchapter', 'taskcondition', 'taskconditionline', 'item', 'language', 'gift')}
    def text(key):
        row = tables['language'].get(key)
        return row[2][0].decode('utf-8') if row and row[2] else None
    def first(row, field, default=0):
        return row[field][0] if row[field] else default
    def signed(values):
        return [v - 2**64 if v >= 2**63 else v for v in values]
    manifest = json.loads((RAW / 'manifest.json').read_text(encoding='utf-8'))
    provenance = {'source': 'canonical APK ResourceManager; Resources.ConvertDataBytes; strict array framing',
                  'tables': {name: len(rows) for name, rows in tables.items()}, 'byteRepairs': [],
                  'manifest': 'analysis/dp_client/manifest.json'}
    chapters = {}
    used_conditions = {}
    for task_id, row in tables['taskchapter'].items():
        chapter, condition_id, condition_type = first(row, 8), first(row, 3), first(row, 4)
        source = 'taskconditionline' if condition_type == 1 else 'taskcondition'
        condition = tables[source][condition_id]
        kind = TYPES[first(condition, 2)]
        targets, points = condition[5], row[10]
        assert len(targets) == len(points) and targets == sorted(targets)
        values1, values2 = signed(condition[3]), signed(condition[4])
        task = {'taskId': task_id, 'describeId': first(row, 2), 'text': text(first(row, 2)),
                'conditionId': condition_id, 'conditionType': condition_type,
                'completionLimit': first(row, 9), 'dp': points[0], 'dpPoints': points,
                'lastTask': first(row, 6), 'nextTask': first(row, 7), 'giftGroup': first(row, 11),
                'acceptLevel': first(row, 5), 'completeType': kind,
                'completeValue1': values1[0], 'completeValue2': values2[0], 'completeNum': targets[0],
                'completeValues1': values1, 'completeValues2': values2, 'completeNums': targets}
        chapters.setdefault(str(chapter), {'chapterId': chapter, 'tasks': []})['tasks'].append(task)
        used_conditions[f'{source}:{condition_id}'] = {str(k): v for k, v in condition.items()}
    for row in chapters.values():
        row['totalDp'] = sum(sum(t['dpPoints']) for t in row['tasks'])
    gates = {str(key): {'chapterId': key, 'dpThresholds': row[15], 'dpRewards': row[16],
                       'unlockMapTypeId': first(row, 17), 'unlockDpRequest': first(row, 18)}
             for key, row in tables['chapterinfo'].items()}
    # Gift rows are authoritative executable contents. Item descriptions are only labels.
    boxes, used_gifts, used_items = {}, {}, {}
    for chapter, gate in gates.items():
        for item_id in gate['dpRewards']:
            row = tables['item'][item_id]
            assert first(row, 6) == 18 and row[16]
            rewards = Counter()
            equip_show = []
            for gift_id in row[16]:
                gift = tables['gift'][gift_id]
                assert first(gift, 2) == 1 and len(gift[4]) == len(gift[5])
                used_gifts[str(gift_id)] = {str(k): v for k, v in gift.items()}
                for key, num in zip(gift[4], gift[5], strict=True):
                    assert num > 0
                    rewards[key] += num
                if first(gift, 8):
                    equip_show.extend(gift[6])
            equip = {key: rewards.pop(key) for key in list(rewards) if 1240000 <= key < 1245000}
            box = {'name': text(first(row, 2)), 'chapterId': int(chapter), 'contentsText': text(first(row, 3)),
                   'giftGroups': row[16], 'contents': [{'itemId': key, 'num': num,
                       'name': text(first(tables['item'][key], 2))} for key, num in sorted(rewards.items())],
                   'supported': True}
            if equip:
                # GiftShow references the client item explicitly named N★套装.
                suits = {400 + (key - 1240000) // 10 for key in equip}
                assert len(suits) == 1 and len(equip) == 6 and set(equip.values()) == {1}
                stars = {int(re.search(r'(\d)★套装', text(first(tables['item'][key], 2)))[1]) for key in equip_show}
                assert len(stars) == 1
                for key in equip_show:
                    show = tables['item'][key]
                    used_items[str(key)] = {'nameId': first(show, 2), 'name': text(first(show, 2)),
                                            'itemQuality': first(show, 7)}
                box['equib'] = {'suit': suits.pop(), 'star': stars.pop(), 'count': 6,
                                 'parts': sorted((key - 1240000) % 10 for key in equip),
                                 'typeIds': sorted(equip),
                                 'giftShowIds': equip_show,
                                 'starEvidence': 'Gift.GiftShow -> Item.NameID -> Language: N★套装'}
            boxes[str(item_id)] = box
            # Bytes only matter for supported fields; avoid unrelated Item strings.
            used_items[str(item_id)] = {'nameId': first(row, 2), 'descId': first(row, 3), 'Used': row[16]}
    write(DATA / 'chapter_dp_tasks.json', {'provenance': provenance, 'chapters': chapters})
    write(DATA / 'chapter_dp.json', {'provenance': provenance, 'chapters': gates})
    write(DATA / 'dp_box_contents.json', {'provenance': provenance, 'boxes': boxes})
    evidence = ROOT / 'analysis/dp_client'
    write(evidence / 'manifest.json', manifest)
    write(evidence / 'used_rows.json', {'conditions': used_conditions, 'items': used_items, 'gifts': used_gifts})
    print('tasks', sum(len(r['tasks']) for r in chapters.values()), 'boxes', len(boxes))
    print('chapter totals', {key: row['totalDp'] for key, row in chapters.items()})


if __name__ == '__main__':
    build()
