"""Ephemeral trial loadouts recovered from the canonical client's TrialUnitBase."""
import json
from functools import lru_cache
from importlib.resources import files


@lru_cache(maxsize=1)
def catalog():
    return json.loads(files('x2server').joinpath('data/trial_units.json').read_text(encoding='utf-8'))


def section_trial(row, selected_ids):
    """Canonical trial sections, plus the requested chapter-seven story trial.

    2.4 labels 2110607 as E_Friend. The user explicitly requests a Behemoth
    trial there; only its solo normal/trial alias gets the canonical 1303
    loadout. Other selected teams retain their account growth and equipment.
    This compatibility exception must not rewrite the client's SectionTable.
    """
    if row.get('AssistType', {}).get('value') == 1:
        return next((unit for unit in row.get('AssistParam', []) if unit > 0), None)
    if (row.get('SectionID') == 2110607 and row.get('ChapterID') == 2010700
            and len(selected_ids) == 1 and selected_ids[0] in (1003, 1303)):
        return 1303
    return None


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
    # A skin replaces ActionFileID. Thetis must keep its independent trial
    # attacks (normal skin halves their range). Behemoth's original trial skin
    # is required: action_1303 contains invalid SkillID 10057 in ultimate
    # transitions, while its prescribed regular action file checks 10033.
    allowed_skin_units = {unit_id}
    if unit_id == 1303:
        allowed_skin_units.add(row['UnitID'])
    if skin and catalog()['appearance_units'].get(str(skin)) not in allowed_skin_units:
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


def chapter7_equipment(section, hero, equipped, artifact_bonus):
    """User-approved attack compensation, only on this ephemeral story loadout.

    Account gear and the shared canonical trial plates are never modified.
    Fixed damage and dynamic client buffs can still differ from an exact damage
    multiplier; the pre-buff attack subtotal is multiplied by ten.
    """
    if section != 2110607 or hero.get('trial_unit') != 1303:
        return equipped
    from x2server.messages.equipment import HERO_EQUIP, EQUIP_PARAM
    from .battle_bonuses import GOD_EQUIP_ATTR, JEWEL_ATTR, LONG_PAIR
    from .progression import hero_attributes
    rows = [HERO_EQUIP.decode(raw) for raw in equipped]
    params = [EQUIP_PARAM.decode(row['param']) for row in rows]
    attack = hero_attributes({**hero, 'id': hero.get('battle_base_id', hero['id'])})['atk']
    attack += sum(p.get(f'av{s}', 0) for p in params for s in range(1, 7)
                  if p.get(f'at{s}') == 100)
    bonus = GOD_EQUIP_ATTR.decode(artifact_bonus)
    pairs = [LONG_PAIR.decode(raw) for raw in bonus.get('godAttr', [])]
    for raw in bonus.get('jewelAttr', []):
        jewel = JEWEL_ATTR.decode(raw)
        if jewel.get('effect1'):
            pairs.append(LONG_PAIR.decode(jewel['effect1']))
    attack += sum(p.get('Value', 0) for p in pairs if p.get('Key') == 100)
    target = next((i, s) for i, p in enumerate(params) for s in range(1, 7)
                  if p.get(f'at{s}') == 100)
    index, slot = target
    params[index][f'av{slot}'] += 9 * attack
    rows[index]['param'] = EQUIP_PARAM.encode(params[index])
    return [HERO_EQUIP.encode(row) for row in rows]
