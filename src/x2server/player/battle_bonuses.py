"""Native lobby bonuses that combat consumes through precomputed attributes.

Keep beastlords in heroEquip/equipSuitAttr. HeroAttrCount is the grown bare
hero base, not the final total; combat adds artifact/fetter/college wrappers.
"""
import json
import struct
from collections import Counter
from functools import lru_cache
from importlib.resources import files

from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema

LONG_PAIR = ProtoSchema('KeyValuePair_Int32_Int64', (F(1, 'Key', K.INT32), F(2, 'Value', K.INT64)))
JEWEL_ATTR = ProtoSchema('JewelAttr', (F(1, 'effect1', K.MESSAGE), F(2, 'effect2', K.INT32, repeated=True)))
GOD_EQUIP_ATTR = ProtoSchema('HeroGodEquipAttr', (
    F(1, 'godAttr', K.MESSAGE, repeated=True), F(2, 'jewelAttr', K.MESSAGE, repeated=True)))


@lru_cache(maxsize=1)
def catalog():
    return json.loads(files('x2server').joinpath('data/battle_bonuses.json').read_text(encoding='utf-8'))


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def artifact_attributes(hero):
    artifact = hero.get('god_equip')
    if not artifact:
        return b''
    data = catalog()
    identity = data['heroes'][str(hero['id'])]
    base = data['artifacts'][str(artifact['id'])]
    star, level = artifact.get('star', 0), artifact.get('level', 0)
    if not isinstance(star, int) or not isinstance(level, int) or star not in range(7) or level not in range(101):
        raise ValueError('invalid artifact growth state')
    fuse = data['fuses'][f"{star}:{identity['profession']}"]
    # ARM64 ClientProperty uses float32 at every operation, then int32 truncation.
    delta = level * (fuse['MaxAttrRate'] - fuse['AttrRate'])
    factor = f32(f32(f32(delta) * f32(.01)) + f32(fuse['AttrRate']))
    factor = f32(factor * f32(.001))
    attrs = []
    for i in range(1, 4):
        if base.get(f'ArtifactAttr{i}'):
            attrs.append(LONG_PAIR.encode({'Key': base[f'ArtifactAttr{i}'],
                'Value': int(f32(factor * f32(base.get(f'AttrValue{i}', 0))))}))
    for i in range(1, 3):
        values = base.get(f'SenAttrValue{i}', [])
        if base.get(f'SeniorAttr{i}') and star < len(values):
            attrs.append(LONG_PAIR.encode({'Key': base[f'SeniorAttr{i}'], 'Value': values[star]}))
    jewels = []
    for slot, item in sorted(artifact.get('jewels', {}).items(), key=lambda pair: int(pair[0])):
        if int(slot) not in range(6):
            raise ValueError('invalid jewel socket')
        if not item:
            continue
        jewel = data['jewels'][str(item)]
        values = {'effect2': jewel['JewelEffect2']}
        if jewel['JewelEffect1']:
            values['effect1'] = LONG_PAIR.encode({'Key': jewel['JewelEffect1'], 'Value': jewel['EffectValue1']})
        jewels.append(JEWEL_ATTR.encode(values))
    return GOD_EQUIP_ATTR.encode({'godAttr': attrs, 'jewelAttr': jewels})


def other_attributes(store, player_id, hero):
    data, attrs = catalog(), Counter()
    for position, level in hero.get('favor_fetters', {}).items():
        row = data['fetters'].get(f"{hero['id']}:{position}")
        if row and row['IsOpen'] and isinstance(level, int) and 1 <= level <= len(row['AttribValue']):
            attrs[row['Attribid']] += row['AttribValue'][level - 1]
    origin = data['heroes'][str(hero['id'])]['origin']
    if origin == 9:
        # Inversion heroes use the GlobalParamString list's terminal values,
        # independent of building progress (ClientProperty 0x1492674).
        for skill in data['inversion_skills']:
            row = data['wonder_skills'][str(skill)]
            attrs[row['attribute']] += row['values'][-1]
    elif store.db.execute("SELECT 1 FROM sqlite_master WHERE name='college_state'").fetchone():
        state = store.db.execute('SELECT state_json FROM college_state WHERE player_id=?', (player_id,)).fetchone()
        for wonder in json.loads(state[0]).get('wonders', []) if state else []:
            row = data['wonders'].get(str(wonder['buildingId']))
            star, level = wonder.get('buildingStar', 0), wonder.get('buildingLevel', 0)
            if not row or row['origin'] != origin or star == 0:
                continue
            if not isinstance(star, int) or not 1 <= star <= len(row['stars']):
                raise ValueError('invalid civilization star')
            for skill in data['wonder_stars'][str(row['stars'][star - 1])]:
                bonus = data['wonder_skills'][str(skill)]
                if not isinstance(level, int) or not 1 <= level <= len(bonus['values']):
                    raise ValueError('invalid civilization level')
                attrs[bonus['attribute']] += bonus['values'][level - 1]
    return dict(attrs)
