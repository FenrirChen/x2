"""Recover achievement rows from the APK's ResourceManager-selected tables.

Rule bindings are explicit Revival interpretations of the client's Chinese
descriptions. AchievementCondition is NOT TaskCondition: their numeric ids
overlap but refer to different rules.
"""
import json
import re
from pathlib import Path
from analysis.progression.probe import read_tables


def export():
    names = ['Achievement', 'AchievementCondition', 'AchievementConditionLine',
             'TaskControl', 'Language', 'UnitBase', 'Item', 'JewelBase',
             'ChapterInfo', 'CollegeBuilding', 'EquibSuit', 'EquibBase', 'SectionTable']
    data, meta, missing = read_tables(names)
    if missing:
        raise ValueError(missing)
    # These achievement tables have no active-version override in the probe;
    # refuse an unrelated cached table if a future extraction adds one.
    for name in names[:3]:
        assert meta[name]['source'].startswith('assets/bin/Data/')
    language = {r['Key']: r.get('Chinese', '') for r in data['Language']}
    # UnitBase also contains same-name combat/assist variants. Only the
    # favorability catalog's account heroes can own persistent favor levels.
    favor = json.loads(Path('src/x2server/data/favor_catalog.json').read_text(encoding='utf-8'))
    account_ids = {row['HeroID'] for row in favor['favorabilityhero']}
    heroes = {language.get(r.get('Name')): r['ID'] for r in data['UnitBase']
              if r['ID'] in account_ids}
    heroes['朱雀'] = heroes['陵光']
    item_names = {r['ItemID']: language.get(r.get('NameID'), '') for r in data['Item']}
    buildings = {language.get(r['NameID']): r['ID'] for r in data['CollegeBuilding']}
    chapters = {language.get(r.get('ChapterName')): r for r in data['ChapterInfo']}
    single = {r['AchievementConditionID']: [r['CompleteNum']] for r in data['AchievementCondition']}
    line = {r['AchievementConditionID']: r['CompleteNum'] for r in data['AchievementConditionLine']}
    rows = {}
    for row in data['Achievement']:
        if row.get('IsUse', {}).get('value') != 1:
            continue
        desc = language[row['AchievementDescribe']]
        rule = {'kind': 'unsupported'}
        if desc == '解神者等级达到 {0} 级':
            rule = {'kind': 'account_level'}
        elif desc == '累计登录 {0} 天':
            rule = {'kind': 'login_days'}
        elif re.fullmatch(r'拥有 \d+ 位神格', desc):
            rule = {'kind': 'hero_count'}
        elif match := re.fullmatch(r'拥有\d+名 (\d+) 级及以上的神格', desc):
            rule = {'kind': 'hero_level', 'minimum': int(match[1])}
        elif match := re.fullmatch(r'拥有 \d+ 名(\d+)(?:★及以上的神格|★神格)', desc):
            rule = {'kind': 'hero_star', 'minimum': int(match[1])}
        elif desc in ('拥有 6 件兽主', '拥有 12 件兽主', '拥有 18 件兽主'):
            rule = {'kind': 'equipment_count'}
        elif match := re.fullmatch(r'拥有 \d+ 件(\d+)级(?:及以上兽主|兽主)', desc):
            rule = {'kind': 'equipment_level', 'minimum': int(match[1])}
        elif match := re.fullmatch(r'拥有 \d+ 件(\d+)(?:★及以上兽主|星兽主|★兽主)', desc):
            rule = {'kind': 'equipment_star', 'minimum': int(match[1])}
        elif match := re.fullmatch(r'\d+ 名神格的魂器达到(\d+)星(?:及以上)?', desc):
            rule = {'kind': 'artifact_star', 'minimum': int(match[1])}
        elif match := re.fullmatch(r'拥有 \d+ 个默契度达到(\d+)级的神格', desc):
            rule = {'kind': 'favor_count', 'minimum': int(match[1])}
        elif desc.endswith('默契度达到 {0} 级') and desc.split('默契度')[0] in heroes:
            rule = {'kind': 'hero_favor', 'hero': heroes[desc.split('默契度')[0]]}
        elif desc.startswith('通关剧情章节'):
            chapter = chapters[desc.split('：')[-1]]
            rule = {'kind': 'sections_clear', 'ids': [chapter['StageID'][-1]]}
        elif desc.startswith('通关现世复刻（血月难度）：'):
            chapter = chapters[desc.split('：')[-1]]
            ids = [r['SectionID'] for r in data['SectionTable']
                   if r['SectionID'] in chapter['ChallengeLevel'] and language.get(r.get('ChallengeName')) == '血月']
            assert len(ids) == 1
            rule = {'kind': 'sections_clear', 'ids': ids}
        elif desc.startswith('6 分钟内通关现世复刻：'):
            chapter = chapters[desc.split('：')[-1].split('（')[0]]
            ids = [r['SectionID'] for r in data['SectionTable']
                   if r['SectionID'] in chapter['ChallengeLevel'] and language.get(r.get('ChallengeName')) == '新月']
            assert len(ids) == 1
            rule = {'kind': 'timed_clear', 'ids': ids, 'seconds': 360}
        elif desc.endswith('等级达到 {0} 级') and desc.split('等级')[0] in buildings:
            rule = {'kind': 'building_level', 'id': buildings[desc.split('等级')[0]]}
        elif re.fullmatch(r'(?:拥有1件|收集1套)6星兽主：.+', desc):
            name = desc.split('：')[-1]
            suits = [r['SuitId'] for r in data['EquibSuit'] if language.get(r['NameID']) == name + '套装']
            if suits:
                rule = {'kind': 'equipment_set' if desc.startswith('收集') else 'equipment_named',
                    'parts': {str(r['EquibId']): r['EquibPart'] for r in data['EquibBase'] if r['EquibSuit'] in suits}}
        elif desc == '与神格点击交谈 {0} 次':
            rule = {'kind': 'event', 'event': 19}
        elif desc == '累计赠送神格礼物达到 {0} 次':
            rule = {'kind': 'event', 'event': 18}
        elif match := re.fullmatch(r'拥有 \d+ 颗(\d+)★普通宝石', desc):
            rule = {'kind': 'item_count', 'ids': [r['JewelID'] for r in data['JewelBase']
                if r['StarLevel'] == int(match[1]) and '★' in item_names.get(r['JewelID'], '')]}
        # Specific named jewels use canonical Item + JewelBase, never id arithmetic.
        elif '宝石姬：' in desc or desc.startswith('收集 1 颗 '):
            star_match = re.search(r'(\d+) 星|★(\d+)', desc)
            star = int(next(v for v in star_match.groups() if v)) if star_match else 0
            name = desc.split('宝石姬：')[-1] if '宝石姬：' in desc else desc.split('颗 ')[-1].split('★')[0]
            ids = [r['JewelID'] for r in data['JewelBase']
                   if name == item_names.get(r['JewelID'], '').split('★')[0] and (not star or r['StarLevel'] == star)]
            if ids:
                rule = {'kind': 'item_count', 'ids': ids}
        targets = (line if row['AchievementConditionType']['value'] == 1 else single)[row['AchievementConditionID']]
        assert len(targets) == len(row['GiftGroup'])
        rows[str(row['AchievementID'])] = {'group': row['AchievementGroup']['value'],
            'previous': row.get('LastAchievement', 0), 'targets': targets,
            'gifts': row['GiftGroup'], 'description': desc, 'rule': rule}
    control = data['TaskControl'][0]
    output = {'source': meta, 'binding_policy': 'Revival interpretation of client descriptions; unknown conditions remain incomplete',
              'achievements': rows, 'point_targets': control['CompleteAchievementNumber'],
              'point_gifts': control['CompleteAchievementNumberGiftGroup']}
    path = Path('src/x2server/data/achievements.json')
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('exported', len(rows), 'supported', sum(r['rule']['kind'] != 'unsupported' for r in rows.values()))


if __name__ == '__main__':
    export()
