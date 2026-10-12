"""Audit obtainable activity boxes and every positive canonical bag outcome.

Only a disposable SQLite database is used. Each grant is rolled back. Nested
boxes are tracked as future usable items, not automatically opened for players.
Run with PYTHONPATH=src;. python tools/analysis/audit_activity_bag_items.py.
"""
from collections import Counter
import json
from pathlib import Path
import tempfile

from x2server.player.bag_items import grant_bag_rewards
from x2server.player.economy import EconomyService
from x2server.player.store import PlayerStore

ROOT = Path(__file__).resolve().parents[2]


def activity_items(economy):
    data = json.loads((ROOT / 'src/x2server/data/activity_rotation_catalog.json').read_text('utf8'))
    exchange = json.loads((ROOT / 'src/x2server/data/activity_exchange_catalog.json').read_text('utf8'))
    tables = data['tables']
    boxes = {r['BoxID']: r for r in tables['ActivityBox']}
    goods = {r['GoodsGroupID']: r for r in tables['ActivityBoxGoods']}
    gifts = economy.gift_contents
    result = {}
    for theme in data['themes']:
        owned = {r['ActivityID'] for r in theme['activities']}
        ids, groups = set(), set()
        for shop in exchange['shops']:
            if shop['group'] == theme['group']:
                ids.update(r['itemId'] for r in shop['goods'])
        for name, field in [('ActivityTask', 'GiftGroup'), ('NewYearFoodTask', 'GiftGroup'), ('ActivityTaskBox', 'GiftID')]:
            groups.update(r[field] for r in tables[name] if r['ActivityID'] in owned
                          and r.get('IsUse', {'value': 1})['value'] == 1)
        for row in tables['SectionTable']:
            if row['SectionID'] in theme['section_ids']:
                for field in ['FirVReward', 'VReward', 'MopReward']:
                    groups.update(row.get(field, []))
                profile = economy.section_rewards.get(row['SectionID']) or {}
                ids.update(profile.get('direct_items', []))
                ids.update(profile.get('nested_drop_items', []))
        for row in tables['POVChapterInfo']:
            if row['UnlockActiviyID'] in owned and row.get('ClearReward'):
                groups.add(row['ClearReward'])
        for row in theme['activities']:
            kind = row['ActivityType']['value']
            if kind in [1, 2]:
                groups.update(row.get('ActivityReward', []))
            elif kind in [15, 24]:
                groups.update(row.get('ActivityParam2', []))
            elif kind == 26:
                for bid in row['ActivityParam1']:
                    ids.update(goods[g]['ItemID'] for g in boxes[bid]['GoodsGroupId'])
            elif kind == 28:
                ids.update(row['ActivityParam4'])
            elif kind == 29:
                groups.update(row['ActivityReward'])
            elif kind == 30:
                groups.update(row['ActivityParam2'])
                groups.update(row['ActivityParam4'])
                for question in tables['AnswerConfig']:
                    if question['QaType'] == row['ActivityReward'][0]:
                        groups.update(question['AnswerReward'])
            elif kind == 50:
                groups.update(row.get('ActivityParam2', []))
            elif kind == 23:
                for extra in tables['ExtraDroop']:
                    if extra['ID'] in row['ActivityParam1']:
                        groups.update(extra['ExtraGiftID'])
        for group in groups:
            if str(group) not in gifts:
                raise ValueError(f"missing activity gift {theme['title']}:{group}")
            ids.update(i for i, n in gifts[str(group)]['items'] if n > 0)
        direct = ids & {int(i) for i in economy.bag_catalog['items']}
        closure, pending = set(direct), list(direct)
        while pending:
            box = pending.pop()
            for gid in economy.bag_catalog['items'][str(box)]['used']:
                for item, n in economy.bag_catalog['gifts'][str(gid)]['items']:
                    if n and str(item) in economy.bag_catalog['items'] and item not in closure:
                        closure.add(item)
                        pending.append(item)
        result[theme['title']] = {'direct': sorted(direct), 'with_nested': sorted(closure)}
    return result


def audit():
    with tempfile.TemporaryDirectory(prefix='x2-bag-audit-') as directory:
        store = PlayerStore(Path(directory) / 'audit.sqlite3')
        p = store.login('audit', 1, 0)
        store.save_snapshot(1, {**p['snapshot'], 'level': 60, 'mobility': {'power': 0}, 'heroes': []}, p['revision'])
        economy = EconomyService(store)
        themes = activity_items(economy)
        checked, errors, zero = 0, [], 0
        kinds = Counter()
        client_items = json.loads((ROOT / 'src/x2server/data/activity_rotation_catalog.json').read_text('utf8'))['tables']['Item']
        links_checked = 0
        for row in client_items:
            if row.get('Used'):
                links_checked += 1
                if economy.bag_catalog['items'].get(str(row['ItemID']), {}).get('used') != row['Used']:
                    errors.append({'box': row['ItemID'], 'error': 'Item.Used differs from client table'})
        for box, link in economy.bag_catalog['items'].items():
            for group in link['used']:
                gift = economy.bag_catalog['gifts'][str(group)]
                kind, weights = gift['awardType'], gift['weights']
                if (kind not in (1, 2, 4, 5)
                        or kind == 1 and weights
                        or kind == 4 and (len(weights) != 1 or not 0 < weights[0] <= len(gift['items']))
                        or kind in (2, 5) and (len(weights) != len(gift['items']) or min(weights) < 0 or sum(weights) <= 0)
                        or any(n < 0 or kind in (1, 4) and n == 0 for _, n in gift['items'])):
                    errors.append({'box': int(box), 'group': group, 'error': 'invalid gift shape'})
                    continue
                for index, (item, count) in enumerate(gift['items']):
                    if kind in (2, 5) and weights[index] == 0:
                        continue
                    if count == 0:
                        zero += 1
                        continue
                    store.db.execute('SAVEPOINT candidate')
                    try:
                        grant_bag_rewards(economy, 1, f'audit:{box}:{group}:{index}', {item: count}, int(box))
                        checked += 1
                        kinds[economy.items[item]['ItemType']['value']] += 1
                    except Exception as exc:
                        errors.append({'box': int(box), 'group': group, 'item': item, 'error': str(exc)})
                    finally:
                        store.db.execute('ROLLBACK TO candidate')
                        store.db.execute('RELEASE candidate')
        report = {'themes': themes, 'all_usable_items': len(economy.bag_catalog['items']),
                  'client_use_links_checked': links_checked,
                  'positive_outcomes_checked': checked, 'intentional_zero_entries': zero,
                  'reward_types': dict(kinds), 'errors': errors,
                  'names': {i: economy.bag_catalog['items'][str(i)]['name']
                            for row in themes.values() for i in row['with_nested']}}
        assert store.db.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
        store.close()
        return report


if __name__ == '__main__':
    report = audit()
    target = ROOT / 'runtime/activity_bag_item_audit_20261012.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', 'utf8')
    print(json.dumps({k: v for k, v in report.items() if k not in ['names', 'themes', 'errors']}, ensure_ascii=False))
    for theme, data in report['themes'].items():
        print(theme, len(data['direct']), len(data['with_nested']))
    print('errors', report['errors'])
    raise SystemExit(bool(report['errors']))
