"""Snapshot persistent beastlords into the native FightHero combat contract."""
import json
from collections import Counter
from functools import lru_cache
from importlib.resources import files

from x2server.messages.battle import EQUIP_SUIT_ATTR
from x2server.messages.equipment import HERO_EQUIP, EQUIP_PARAM
from .equipment_factory import load_equipment_tables


@lru_cache(maxsize=1)
def catalogs():
    suits = json.loads(files('x2server').joinpath('data/battle_equipment_suits.json').read_text(encoding='utf-8'))['suits']
    return load_equipment_tables()['equib_base'], suits


def battle_equipment(store, player_id, hero):
    """Use stored affixes verbatim. The client adds these to bare hero stats.

    Property.AddEqtsAttributes applies every supplied suit attribute; therefore
    only send suits with >=2 pieces. Four-piece passives activate at >=4 pieces.
    """
    worn = hero.get('equips', [])
    if not worn:
        return [], []
    bases, suits = catalogs()
    if len(worn) > 6 or not store.db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='equipment_instances'").fetchone():
        raise ValueError('invalid equipment wearing state')
    slots, ids, counts, encoded = set(), set(), Counter(), []
    for entry in sorted(worn, key=lambda e: e['position']):
        equip_id, slot = entry['equip_id'], entry['position']
        row = store.db.execute('SELECT id,type_id,level,exp,star,param,locked FROM equipment_instances '
                               'WHERE player_id=? AND id=?', (player_id, equip_id)).fetchone()
        base = bases.get(str(row['type_id'])) if row else None
        if (not base or slot not in range(6) or slot in slots or equip_id in ids
                or base['part'] != slot + 1):
            raise ValueError('missing/unowned/duplicate/misplaced beastlord')
        slots.add(slot)
        ids.add(equip_id)
        counts[base['suit']] += 1
        encoded.append(HERO_EQUIP.encode({'id': row['id'], 'typeId': row['type_id'],
            'level': row['level'], 'exp': row['exp'], 'star': row['star'], 'status': 1,
            'param': EQUIP_PARAM.encode(json.loads(row['param'])), 'lockState': row['locked'],
            'timeSec': 0, 'seasonId': 0}))
    effects = []
    for suit_id, count in sorted(counts.items()):
        if count < 2:
            continue
        suit = suits.get(str(suit_id))
        if not suit:
            raise ValueError('missing canonical beastlord suit')
        effects.append(EQUIP_SUIT_ATTR.encode({'suitId': suit_id, 'suitNum': count,
            'attribType1': suit['attribute'], 'value1': suit['value'],
            'passiveID': suit['passives'] if count >= 4 else []}))
    return encoded, effects
