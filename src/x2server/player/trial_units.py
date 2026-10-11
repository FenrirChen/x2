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
    # TrialHeroID is a distinct UnitBase/PlayerAttrib combat identity. UnitID
    # identifies the normal hero for presentation/artifact lookup only.
    skill_ids = catalog()['unit_skills'][str(unit_id)]
    skin = row.get('AppearanceID', 0)
    # A battle skin replaces ActionFileID through Appearance.UnitBaseID.
    # Normal default skins would replace trial-specific attacks with the
    # normal hero's actions (Thetis projectile range 1600 -> 800).
    if skin and catalog()['appearance_units'].get(str(skin)) != unit_id:
        skin = 0
    return {'id': unit_id, 'battle_base_id': unit_id, 'trial_unit': unit_id,
        'state': 2, 'level': row['HeroLevel'], 'star': row['HeroStars'], 'exp': 0,
        'skills': [{'id': skill, 'level': levels[i]}
                   for i, skill in enumerate(skill_ids[:len(levels)]) if skill > 0],
        'god_equip': ({'id': prototype['artifact_id'], 'star': row.get('ArtifactStar', 0),
                      'level': row.get('ArtifactLevel', 0),
                      'jewels': {str(slot): item for slot, item in enumerate(row.get('WeaponGems', [])) if item > 0}}
                     if prototype.get('artifact_id') else None),
        'trial_skin': skin}


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
