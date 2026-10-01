"""Ephemeral trial loadouts recovered from the canonical client's TrialUnitBase."""
import json
from functools import lru_cache
from importlib.resources import files


@lru_cache(maxsize=1)
def catalog():
    return json.loads(files('x2server').joinpath('data/trial_units.json').read_text(encoding='utf-8'))


def trial_hero(unit_id, wire_id):
    from .progression import catalog as progression
    row = next((r for r in catalog()['units'] if r['TrialHeroID'] == unit_id), None)
    if not row or wire_id not in (unit_id, row['UnitID']):
        return None
    prototype = next((r for r in progression()['hero_unlock'] if r['hero_id'] == row['UnitID']), {})
    levels = row.get('SkillLevel', [])
    return {'id': wire_id, 'battle_base_id': row['UnitID'], 'trial_unit': unit_id,
        'state': 2, 'level': row['HeroLevel'], 'star': row['HeroStars'], 'exp': 0,
        'skills': [{'id': skill, 'level': levels[i] if i < len(levels) else 1}
                   for i, skill in enumerate(prototype.get('initial_skills', []))],
        'god_equip': ({'id': prototype['artifact_id'], 'star': row.get('ArtifactStar', 0),
                      'level': row.get('ArtifactLevel', 0)} if prototype.get('artifact_id') else None),
        'trial_skin': row.get('AppearanceID', 0)}


def equipment(hero):
    from x2server.messages.equipment import HERO_EQUIP, EQUIP_PARAM
    from x2server.messages.battle import EQUIP_SUIT_ATTR
    from .battle_equipment import catalogs
    from collections import Counter
    row = next(r for r in catalog()['units'] if r['TrialHeroID'] == hero['trial_unit'])
    plates = {r['AttrbdID']: r for r in catalog()['equipment_attributes']}
    bases, suits = catalogs()
    encoded, counts = [], Counter()
    for slot, (type_id, plate_id) in enumerate(zip(row.get('EquipGroupID', []), row.get('EquipAttrID', []))):
        plate = plates[plate_id]
        main = plate['MainAttr']
        param = {'at1': main[0], 'av1': main[1] + main[2] * main[3]}
        for i, (kind, value, times, growth) in enumerate(zip(plate['MinorAttrType'],
                plate['MinorAttrValue'], plate['MinorAttrStreNum'], plate['MinorAttrStreValue']), 2):
            param.update({f'at{i}': kind, f'av{i}': value + times * growth})
        counts[bases[str(type_id)]['suit']] += 1
        encoded.append(HERO_EQUIP.encode({'id': slot + 1, 'typeId': type_id,
            'level': plate.get('EquibLevel', 0), 'star': plate['EquibQuality'], 'status': 1,
            'param': EQUIP_PARAM.encode(param)}))
    effects = [EQUIP_SUIT_ATTR.encode({'suitId': suit, 'suitNum': count,
        'attribType1': suits[str(suit)]['attribute'], 'value1': suits[str(suit)]['value'],
        'passiveID': suits[str(suit)]['passives'] if count >= 4 else []})
        for suit, count in counts.items() if count >= 2]
    return encoded, effects
