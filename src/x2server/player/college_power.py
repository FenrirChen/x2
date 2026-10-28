"""Exploration ability: native combat/survival plus four damage channels."""
from collections import Counter
from functools import lru_cache
from importlib.resources import files
import json

from .battle_bonuses import (artifact_attributes, other_attributes, GOD_EQUIP_ATTR,
                             JEWEL_ATTR, LONG_PAIR, f32)
from .battle_equipment import battle_equipment
from .progression import hero_attributes, hero_skills
from x2server.messages.equipment import HERO_EQUIP, EQUIP_PARAM
from x2server.messages.battle import EQUIP_SUIT_ATTR


@lru_cache(maxsize=1)
def rules():
    data = json.loads(files('x2server').joinpath('data/college_power_rules.json').read_text(encoding='utf8'))
    return ({r['AttribId']: r for r in data['attributes']},
            {r['ID']: r for r in data['heroes']}, data['params'])


def hero_power(store, player_id, hero, clock=None, season=None):
    """Use server-owned stats/equipment; requests never supply their own power."""
    attributes, prototypes, params = rules()
    prototype = prototypes[hero['id']]
    bonus = Counter(other_attributes(store, player_id, hero, clock))
    if season:
        # 赛季天赋与魂器蚀化对普通战斗同样生效 (见 player/battle.py enter), 探索
        # 战力必须用同一口径, 否则沿用旧战力会低估、把够门槛的探索挡在外面。
        bonus.update(season.attributes(player_id))
        bonus.update(season.artifact.attributes(player_id, hero))
    artifact = GOD_EQUIP_ATTR.decode(artifact_attributes(hero))
    for raw in artifact.get('godAttr', []):
        pair = LONG_PAIR.decode(raw)
        bonus[pair['Key']] += pair['Value']
    for raw in artifact.get('jewelAttr', []):
        jewel = JEWEL_ATTR.decode(raw)
        if jewel.get('effect1'):
            pair = LONG_PAIR.decode(jewel['effect1'])
            bonus[pair['Key']] += pair['Value']
    worn, suits = battle_equipment(store, player_id, hero)
    for raw in worn:
        values = EQUIP_PARAM.decode(HERO_EQUIP.decode(raw)['param'])
        for index in range(1, 7):
            if values.get(f'At{index}'):
                bonus[values[f'At{index}']] += values.get(f'Av{index}', 0)
    for raw in suits:
        suit = EQUIP_SUIT_ATTR.decode(raw)
        bonus[suit['attribType1']] += suit['value1']

    def value(key, base=0):
        row = attributes.get(key, {})
        total = base + bonus[key]
        if 'ValueMax' in row:
            total = min(row['ValueMax'], total)
        if 'ValueMin' in row:
            total = max(row['ValueMin'], total)
        return total

    def rate(key):
        return f32(attributes.get(key, {}).get('AbilityRate', 0) * f32(.001))

    grown = hero_attributes(hero)
    atk = int(f32(f32(grown['atk'] + bonus[100]) * f32(1 + bonus[101] * f32(.001))))
    defense = int(f32(f32(grown['def'] + bonus[102]) * f32(1 + bonus[103] * f32(.001))))
    hp = int(f32(f32(grown['hp'] + bonus[104]) * f32(1 + bonus[105] * f32(.001))))
    skill_factor = f32(1)
    for index, skill in enumerate(hero_skills(hero)[:4], 1):
        skill_factor = f32(skill_factor + f32((skill['level'] - 1)
            * f32(int(params[f'Skill{index}Ability']) * f32(.001))))
    combat = int(f32(f32(f32(atk * rate(174))
                    * f32(prototype['SkillAbility'] * f32(.001))) * skill_factor))
    survival = int(f32(f32(hp * rate(176)) + f32(defense * rate(175))))
    critical = min(1, f32(value(112, prototype.get('Critical', int(params['CRI']))) * f32(.001)))
    # 113 是加算: 行内 CriticalDamage 叠在 GlobalParamString.CRI_Dmg 的 150% 基数上
    # (Property_AddBaseProperty 用 add 合成同一个 CriticalDamage 属性), 不是替换。
    critical_damage = f32(value(113, int(params['CRI_Dmg'])
                                + (prototype.get('CriticalDamage') or 0)) * f32(.001))
    # GetBaseAbilty 0x1495aec literal is -0.001; positive DR raises survival.
    reduction = f32(value(119) * f32(.001))
    critical_factor = f32(f32(1 - critical) + f32(f32(critical * critical_damage) * rate(113)))
    base = int(f32(f32(combat * critical_factor) + f32(survival / f32(1 - f32(reduction * rate(119))))))
    total = base
    for damage, extra, resist, resistance_cap, status in (
            (122, 146, 121, 157, 145), (125, 148, 124, 158, 147),
            (128, 150, 127, 159, 149), (131, 152, 130, 159, 151)):
        resistance = min(f32((value(resist) + value(116)) * f32(.001)),
                         f32((value(resistance_cap) + int(params['SR_Max'])) * f32(.001)))
        correction = min(1, f32(value(status) * f32(.001)))
        # Physical differs from the other channels in the native reciprocal.
        correction_gain = (f32(3 / f32(f32(1 / f32(correction * rate(status))) + 3))
                           if correction and rate(status) and damage == 122 else
                           f32(3 / f32(f32(f32(1 / correction) * rate(status)) + 3))
                           if correction else 0)
        offensive = f32(combat * f32(f32(f32(value(damage) * f32(.001)) * rate(damage))
                                  + f32(f32(value(extra) * f32(.001)) * rate(extra))))
        defensive = f32(survival * f32(f32(f32(1 / f32(1 - f32(rate(resist) * resistance)))
                                                  + correction_gain) - 1))
        total += int(f32(offensive + defensive))
    return max(0, total)
