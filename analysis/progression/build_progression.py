"""Build compact progression evidence from named, already-indexed client tables."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from probe import read_tables

OUT = Path(__file__).resolve().parent
data, meta, missing = read_tables()
items = {r['ItemID']: r for r in data['Item']}
language = {r['Key']: r.get('Chinese') for table in ('Language', 'LanguageUI') for r in data[table] if r.get('Chinese')}
gifts = {r['GiftGroup']: r for r in data['Gift']}
skills = {r['ID']: r for r in data['SkillBase']}
attribs = {r['ID']: r for r in data['PlayerAttrib']}


def item(item_id: int):
    rec = items.get(item_id)
    return {'material_item_id': item_id,
            'material_name': language.get(rec.get('NameID')) if rec else None,
            'item_type': (rec.get('ItemType') or {}).get('enum') if rec else None,
            'confidence': 'CONFIRMED' if rec else 'PARTIAL'}


def materials(ids, nums):
    return [{**item(i), 'material_num': nums[n] if n < len(nums) else None}
            for n, i in enumerate(ids)]


def put(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


# ExpLevel is the next-level requirement in the same RoleLevel row. ExpSum is
# the cumulative threshold for that row, as verified by all adjacent rows.
player = []
for r in data['RoleExp']:
    level = r['RoleLevel']
    gift = gifts.get(r.get('GiftID'))
    player.append({'source_table': 'RoleExp', 'source_id': level, 'level': level,
                   **({'next_level': level + 1, 'exp_required': r['ExpLevel']} if r.get('ExpLevel') else {}),
                   'cumulative_exp': r.get('ExpSum', 0), 'power_cap': r.get('PowerNum'),
                   'reward_group_id': r.get('GiftID'),
                   'reward': materials(gift.get('GiftValue', []), gift.get('Num', [])) if gift else [],
                   'unlock': [{'function_id': f['ID'], 'name': language.get(f.get('ChineseNameID'))}
                              for f in data['FunctionOpen'] if f.get('OpenLevel') == level],
                   'confidence': 'CONFIRMED'})
put('player_level.json', {'sources': {k: meta[k] for k in ('RoleExp', 'FunctionOpen', 'Gift', 'Item', 'Language')},
                          'rows': player, 'interpretation': 'ExpLevel at current level is next-level requirement; ExpSum is threshold at current level; level 120 has no next requirement. Post-cap overflow is unknown.'})

hero_levels = []
for r in data['PlayerLevelBonus']:
    level = r['HeroLevel']
    hero_levels.append({'source_table': 'PlayerLevelBonus', 'source_id': level, 'level': level,
                        **({'next_level': level + 1, 'exp_required': r['HeroExp']} if r.get('HeroExp') else {}),
                        'cumulative_exp_to_next': r.get('ExpSum'),
                        'attribute_bonus': {k: r.get(k, 0) for k in ('DamageLevelBonus', 'DefenseLevelBonus', 'HPMaxLevelBonus', 'SPMaxLevelBonus')},
                        'material': item(1237907), 'gold_cost': 0,
                        'confidence': 'CONFIRMED'})
hero1003 = attribs[1003]
put('hero_level.json', {'sources': {k: meta[k] for k in ('PlayerAttrib', 'PlayerLevelBonus', 'Item', 'Language')},
                        'resource_evidence': 'HeroLevelUP.RefreshConsume RVA 0x14003FC calls GetCurrencyNum(7) and sets item 1237907; RefreshLevel RVA 0x1400084 reads PlayerLevelBonus.HeroExp.',
                        'hero_1003': {'source_table': 'PlayerAttrib', 'source_id': 1003, 'name': '贝黑莫斯',
                                      'initial_level': hero1003.get('Level'), 'initial_stage': hero1003.get('DefaultStage'),
                                      'base_hp': hero1003.get('HPMax'), 'base_damage': hero1003.get('Damage'), 'base_defense': hero1003.get('Defense'),
                                      'weapon_id': hero1003.get('WeapenId'), 'chip_item': item(hero1003.get('ChipPropID')),
                                      'runtime_current_level_and_star': 'SERVER_STATE_NOT_READ', 'confidence': 'CONFIRMED'},
                        'rows': hero_levels,
                        'interpretation': 'HeroExp on current HeroLevel is the next level requirement; ExpSum is inclusive sum through that transition. No separate gold cost appears in this client UI path; post-cap behavior and any stage-level restriction are unresolved.'})

stages = []
for r in data['PlayerStage']:
    stage = r['HeroStage']
    stages.append({'source_table': 'PlayerStage', 'source_id': stage, 'star': stage,
                   **({'next_star': stage + 1} if stage < 46 else {}),
                   'big_star': r.get('BigStarNum', 0), 'small_star': r.get('SmallStarNum', 0),
                   'fragment_count_field': r.get('ChipNum'),
                   'specific_fragment_for_hero_1003': item(hero1003['ChipPropID']),
                   'universal_fragment_option': materials(r.get('UniversalChip', [])[:1], r.get('UniversalChip', [])[1:2]),
                   'attribute_bonus': {k: r.get(k, 0) for k in ('DamageStageBonus', 'DefenseStageBonus', 'HPMaxStageBonus', 'SPMaxStageBonus')},
                   'relic_ids': r.get('RelicID', []), 'confidence': 'PARTIAL'})
put('hero_star.json', {'sources': {k: meta[k] for k in ('PlayerAttrib', 'PlayerStage', 'Item', 'Language')},
                       'protocol_evidence': 'C2L_HeroOpt OPT_UPSTAR=2 carries upstarConsumeItemId; HeroStarUP.OnClickUpLevel RVA 0x1927868 calls PlayerStageManager.GetItem then HeroModule.UpStar.',
                       'hero_1003_default_stage': hero1003.get('DefaultStage'), 'rows': stages,
                       'caveat': 'ChipNum is the stage-row fragment quantity; exact choice between specific and universal fragments, terminal-row cost, and any other server checks need validation. No independent gold field is present.'})
put('hero_breakthrough.json', {'status': 'NOT_FOUND', 'evidence': 'No separate hero limit-break table or protocol operation located in targeted canonical progression index. PlayerStage is star progression; PlayerLevelBonus has no stage cap field.',
                               'distinct_from_star': True, 'confidence': 'PARTIAL'})

weapon = next(r for r in data['ArtifactBase'] if r['ArtifactID'] == hero1003['WeapenId'])
profession = hero1003['Profession']
fuse_rows = []
for r in data['ArtifactFuse']:
    fuse_rows.append({'source_table': 'ArtifactFuse', 'source_id': f"{r.get('ProfEnum')}:{r.get('FuseID', 0)}",
                      'profession': r.get('ProfEnum'), 'rank': r.get('FuseID', 0), 'required_hero_stage': r.get('HeroStage'),
                      'fuse_value': r.get('FuseValue', 0),
                      'level_up_materials': materials(r.get('AdvancedItem', []), r.get('AdvancedItemNum', [])),
                      'level_up_gold_cost': r.get('AdvancedConsume', 0),
                      'fuse_materials': materials(r.get('FuseItem', []), r.get('FuseItemNum', [])),
                      'fuse_gold_cost': r.get('FuseConsume', 0),
                      'attribute_rate': r.get('AttrRate', 0), 'max_attribute_rate': r.get('MaxAttrRate', 0),
                      'jewel_hole_state': r.get('HoleIsOpen', []), 'confidence': 'PARTIAL'})
put('weapon_progression.json', {'sources': {k: meta[k] for k in ('PlayerAttrib', 'ArtifactBase', 'ArtifactFuse', 'Item', 'Language')},
                                'hero_1003_weapon': {'source_table': 'PlayerAttrib/ArtifactBase', 'source_id': weapon['ArtifactID'],
                                                     'hero_id': 1003, 'profession': profession,
                                                     'name': language.get(weapon.get('NameID')), 'fuse_levels': weapon.get('FuseLevel'),
                                                     'base_attributes': {k: weapon.get(k) for k in ('ArtifactAttr1', 'AttrValue1', 'ArtifactAttr2', 'AttrValue2', 'ArtifactAttr3', 'AttrValue3')},
                                                     'senior_attributes': {k: weapon.get(k) for k in ('SeniorAttr1', 'SenAttrValue1', 'SeniorAttr2', 'SenAttrValue2')},
                                                     'confidence': 'CONFIRMED'},
                                'rows': fuse_rows, 'client_operations': ['ArtifactOpt.JO_LevelUP=0', 'ArtifactOpt.JO_Fuse=1'],
                                'caveat': 'Weapon is hero-bound Artifact. ArtifactFuse gives profession/stage-specific level-up and fusion ingredients; exact rank transition and attribute arithmetic need server or further handler evidence.'})

equip_rows = []
for r in data['EquibExp']:
    level = r.get('EquibLevel', 0)
    equip_rows.append({'source_table': 'EquibExp', 'source_id': level, 'level': level,
                       **({'next_level': level + 1, 'exp_required': r['NeedExp']} if r.get('NeedExp') else {}),
                       'cumulative_exp': r.get('SumExp', 0),
                       **({'gold_cost': r['NeedGlod']} if r.get('NeedGlod') else {}),
                       'cumulative_gold': r.get('SumGold', 0), 'event_flag': r.get('IsEvent', 0),
                       'loss_exp': r.get('LossExp', 0), 'unknown_field_8': r.get('unknown_field_8'),
                       'confidence': 'PARTIAL'})
equip = next(r for r in data['EquibBase'] if r['EquibId'] == 1240001)
equip_item = item(1240001)
put('equipment_progression.json', {'sources': {k: meta[k] for k in ('EquibBase', 'EquibExp', 'EquibStage', 'EquibAttrib', 'EquibAttribBD', 'EquibSuit', 'Item', 'Language')},
                                   'example': {'source_table': 'EquibBase', 'source_id': 1240001, **equip_item,
                                               'position': equip.get('EquibPart'), 'suit_id': equip.get('EquibSuit'),
                                               'main_attribute_candidates': equip.get('MainAttrType'),
                                               'minor_attribute_candidates': equip.get('MinorAttrType'),
                                               'confidence': 'CONFIRMED'},
                                   'level_rows': equip_rows,
                                   'stage_rows': [{'source_table': 'EquibStage', 'source_id': r['Stage'], **r, 'confidence': 'PARTIAL'} for r in data['EquibStage']],
                                   'quality_preset_count': len(data['EquibAttribBD']),
                                   'quality_preset_levels': {str(k): sorted(set(x.get('EquibLevel', 0) for x in data['EquibAttribBD'] if x.get('EquibQuality') == k)) for k in range(1, 7)},
                                   'runtime_state': ['HeroEquip.id', 'typeId', 'level', 'exp', 'star', 'param'],
                                   'caveat': 'Equib is equipment/兽主 by Item.E_Equip and suit/position schema. Attribute candidate weights and quality presets are static, but actual instance rolls and upgrade feed formula are not proven.'})

skill_rows = []
for r in data['SkillLevel']:
    skill_id, level = r['SkillID'], r.get('Level', 0)
    base = skills.get(skill_id, {})
    entry = {'source_table': 'SkillLevel', 'source_id': f'{skill_id}:{level}', 'skill_id': skill_id,
             'skill_name': language.get(base.get('NameID')), 'level': level,
             **({'next_level': level + 1} if r.get('Item') or r.get('GoldConsume') else {}),
             'gold_cost': r.get('GoldConsume', 0), 'materials': materials(r.get('Item', []), r.get('ItemNum', [])),
             'skill_base_unlock_raw': base.get('SkillUnlock'),
             'unlock_condition': {'type': (r.get('SKillGrowCond') or {}).get('enum'), 'value': r.get('GrowCond')},
             'prerequisite_skills': [{'skill_id': i, 'level': r.get('PreSkillLevel', [None]*len(r['PreSkillID']))[n] if n < len(r.get('PreSkillLevel', [])) else None} for n, i in enumerate(r.get('PreSkillID', []))],
             'confidence': 'PARTIAL'}
    skill_rows.append(entry)
put('skill_progression.json', {'sources': {k: meta[k] for k in ('SkillBase', 'SkillLevel', 'Item', 'Language')},
                               'hero_1003_skill_ids': [r['ID'] for r in data['SkillBase'] if str(r['ID']).startswith('1003')],
                               'hero_1003_god_hole': [{**r, 'material': item(r['ItemID'])} for r in data['GodHole'] if r.get('HeroID') == 1003],
                               'rows': skill_rows,
                               'caveat': 'SkillLevel row is keyed by SkillID/current Level; terminal rows have no cost. All GoldConsume fields decode as zero in this version. SkillBase unlock arrays require independent interpretation; server remains authoritative.'})

used_ids = set()
for r in data['SkillLevel']:
    used_ids.update(r.get('Item', []))
for r in data['ArtifactFuse']:
    used_ids.update(r.get('AdvancedItem', []))
    used_ids.update(r.get('FuseItem', []))
for r in data['PlayerAttrib']:
    if r.get('ChipPropID'):
        used_ids.add(r['ChipPropID'])
for r in data['PlayerStage']:
    if r.get('UniversalChip'):
        used_ids.add(r['UniversalChip'][0])
for r in data['GodHole']:
    if r.get('ItemID'):
        used_ids.add(r['ItemID'])
used_ids.add(1237907)
used_ids.add(1237901)
put('material_links.json', {'sources': {k: meta[k] for k in ('Item', 'Language')},
                            'rows': [item(i) for i in sorted(used_ids)],
                            'unresolved_item_ids': sorted(used_ids - items.keys())})

summary = {
    'table_sources': meta, 'missing_tables': missing,
    'counts': {k: len(v) for k, v in data.items()},
    'systems': {
        'player_level': {'status': 'PARTIAL', 'static_rule': '120 RoleExp rows, next-level ExpLevel, cumulative ExpSum, power cap, Gift and FunctionOpen references', 'runtime_state': 'account level and experience', 'server_only': 'overflow and actual grant timing', 'revival_ready': False},
        'hero_level': {'status': 'PARTIAL', 'static_rule': '120 PlayerLevelBonus rows, HeroExp currency and level attribute bonuses', 'runtime_state': 'HeroData.level/exp and currency balance', 'server_only': 'server validation and cap behavior', 'revival_ready': False},
        'hero_star': {'status': 'PARTIAL', 'static_rule': '46 PlayerStage rows, chip costs, universal option, star display and attributes', 'runtime_state': 'HeroData.star and chip balances', 'server_only': 'fragment choice and transition validation', 'revival_ready': False},
        'hero_breakthrough': {'status': 'NOT_FOUND', 'static_rule': 'no independent hero limit-break table or operation in targeted index', 'runtime_state': None, 'server_only': 'unknown', 'revival_ready': False},
        'weapon_level': {'status': 'PARTIAL', 'static_rule': 'hero-bound ArtifactBase and ArtifactFuse level-up ingredients and gold by profession', 'runtime_state': 'HeroGodEquip level/star', 'server_only': 'exact rank transition and attribute computation', 'revival_ready': False},
        'weapon_star_break': {'status': 'PARTIAL', 'static_rule': 'ArtifactFuse fusion costs and HeroStage gates', 'runtime_state': 'HeroGodEquip star', 'server_only': 'transition validation', 'revival_ready': False},
        'equipment_enhancement': {'status': 'PARTIAL', 'static_rule': 'EquibExp 0–15 and quality/attribute tables', 'runtime_state': 'HeroEquip id/typeId/level/exp/star/param', 'server_only': 'instance rolls and feed formula', 'revival_ready': False},
        'equipment_star_quality': {'status': 'PARTIAL', 'static_rule': 'EquibStage 1–6 and quality presets', 'runtime_state': 'HeroEquip.star/param', 'server_only': 'star operation and instance generation', 'revival_ready': False},
        'skill_upgrade': {'status': 'PARTIAL', 'static_rule': 'SkillLevel 2155 rows with hero-level gates, materials, prerequisites; GoldConsume zero', 'runtime_state': 'HeroData.heroSkills', 'server_only': 'upgrade validation and unlock state', 'revival_ready': False},
        'attribute_growth': {'status': 'PARTIAL', 'static_rule': 'HeroModule.GetBaseAttr confirms base*(1+stage_bonus/1000)*(1+level_bonus/1000)+COR for damage, defense and HP, truncated to int; Artifact/Equib modifiers are additional', 'runtime_state': 'hero level/star and equip instance', 'server_only': 'full equipment stacking and dynamic rolls', 'revival_ready': False},
    },
    'material_item_links': {'resolved': len(used_ids & items.keys()), 'unresolved': len(used_ids - items.keys())},
    'adjacent_tables': ['GodHole', 'JewelBase', 'EquibSuit', 'FunctionOpen'],
}
put('progression_summary.json', summary)
print('wrote progression summaries:', ', '.join(sorted(p.name for p in OUT.glob('*.json'))))
