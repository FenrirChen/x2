import asyncio
from contextlib import closing

import pytest

from x2server.messages.battle import FIGHT_DATA, FIGHT_HERO, HERO_ATTR, HERO_ATTR_ADD, PROFILE_HERO
from x2server.messages.core import HERO_GOD_EQUIP
from x2server.network.dispatcher import DispatchContext
from x2server.network.session import SessionState
from x2server.player.battle import BattleService
from x2server.player.battle_bonuses import artifact_attributes, other_attributes, GOD_EQUIP_ATTR, LONG_PAIR, JEWEL_ATTR
from x2server.player.college import CollegeStateRepository
from x2server.player.store import PlayerStore
from tests.unit.test_battle import packet, request


def hero(**changes):
    return dict(id=1028, state=2, level=60, star=46,
        god_equip={'id': 1528, 'level': 100, 'star': 6, 'jewels': {'4': 1250083}},
        favor_fetters={'3': 3}, **changes)


def god_values(h):
    attrs = GOD_EQUIP_ATTR.decode(artifact_attributes(h))
    return {v['Key']: v['Value'] for v in map(LONG_PAIR.decode, attrs['godAttr'])}, attrs


@pytest.mark.parametrize('star,level,attack,percent', [(1, 0, 28, 0), (1, 100, 56, 0),
    (3, 0, 156, 300), (6, 0, 700, 1200), (6, 100, 1008, 1200)])
def test_native_weapon_growth_and_senior_star_index(star, level, attack, percent):
    h = hero()
    h['god_equip'].update(star=star, level=level)
    stats, attrs = god_values(h)
    assert stats[100] == attack
    assert stats.get(101, 0) == percent
    assert LONG_PAIR.decode(JEWEL_ATTR.decode(attrs['jewelAttr'][0])['effect1']) == {'Key': 125, 'Value': 168}


def test_special_jewel_keeps_passives_and_removal_removes_effects():
    h = hero()
    h['god_equip']['jewels'] = {'0': 1251004}
    _, attrs = god_values(h)
    jewel = JEWEL_ATTR.decode(attrs['jewelAttr'][0])
    assert LONG_PAIR.decode(jewel['effect1']) == {'Key': 102, 'Value': 176}
    assert jewel['effect2'] == [241211, 241210]
    h['god_equip']['jewels'] = {}
    assert not god_values(h)[1].get('jewelAttr')
    h.pop('god_equip')
    assert artifact_attributes(h) == b''


def test_inversion_civilization_uses_native_global_rule_without_buildings(tmp_path):
    with closing(PlayerStore(tmp_path / 'inversion.db')) as store:
        assert other_attributes(store, 1, {'id': 1039}) == {
            100: 1685, 104: 10670, 102: 1272, 108: 1750, 103: 1750, 101: 1750}


@pytest.mark.parametrize('field,value', [('star', -1), ('star', 7), ('level', -1), ('level', 101)])
def test_corrupt_artifact_growth_is_rejected(field, value):
    h = hero()
    h['god_equip'][field] = value
    with pytest.raises(ValueError):
        artifact_attributes(h)


def test_fetters_and_civilization_use_saved_progress_and_origin(tmp_path):
    with closing(PlayerStore(tmp_path / 'bonuses.db')) as store:
        store.login('bonuses', 1, 0)
        repo = CollegeStateRepository(store)
        state = repo.load(1)
        assert other_attributes(store, 1, hero()) == {108: 240}
        state['wonders'][0].update(buildingStar=2, buildingLevel=7)
        # A foreign civilization must never apply to this Chinese hero.
        state['wonders'][1].update(buildingStar=6, buildingLevel=35)
        repo.save(1, state)
        assert other_attributes(store, 1, hero()) == {108: 240, 100: 189, 104: 425}
        h = hero()
        h['favor_fetters'] = {'1': 1, '3': 0, '4': 10, '2': 100}
        assert other_attributes(store, 1, h) == {101: 100, 100: 189, 104: 425}
        assert other_attributes(store, 2, hero()) == {108: 240}


def test_entry_snapshots_all_bonuses_without_changing_save_or_double_counting(tmp_path):
    store = PlayerStore(tmp_path / 'entry.db')
    player = store.login('bonus-entry', 1, 0)
    h = hero()
    store.save_snapshot(1, dict(player['snapshot'], level=60, heroes=[h]), player['revision'])
    ctx = DispatchContext('test', 'local', SessionState('test', 'bonus-entry', player_id=1))
    service = BattleService(store)
    values = request()
    values['heros'] = [PROFILE_HERO.encode({'heroId': 1028, 'leader': 1})]
    before = store.get(1)
    first = asyncio.run(service.enter(ctx, packet(values)))
    assert first.values['result'] == 10
    wire = FIGHT_HERO.decode(FIGHT_DATA.decode(first.values['data'])['fightHeros'][0])
    assert HERO_ATTR.decode(wire['heroAttrCount'])['atk'] == 1563
    # Gear and artifact are separate additive carriers, never baked into bare ATK.
    assert not wire.get('heroEquip')
    god = HERO_GOD_EQUIP.decode(wire['heroGodEquip'])
    attrs = GOD_EQUIP_ATTR.decode(god['godEquipAttr'])
    assert LONG_PAIR.decode(attrs['godAttr'][0]) == {'Key': 100, 'Value': 1008}
    other = {r['attrId']: r['attrValue'] for r in map(HERO_ATTR_ADD.decode, wire['attrAdd'])}
    assert other[108] == 240 and other[162] == 69
    assert store.get(1) == before
    h['god_equip']['jewels'] = {}
    h['favor_fetters'] = {}
    store.save_snapshot(1, dict(before['snapshot'], heroes=[h]), before['revision'])
    assert asyncio.run(service.enter(ctx, packet(values))).values == first.values
    second = asyncio.run(service.enter(ctx, packet(values, 2)))
    wire = FIGHT_HERO.decode(FIGHT_DATA.decode(second.values['data'])['fightHeros'][0])
    god = HERO_GOD_EQUIP.decode(wire['heroGodEquip'])
    assert not GOD_EQUIP_ATTR.decode(god['godEquipAttr']).get('jewelAttr')
    assert 108 not in {HERO_ATTR_ADD.decode(r)['attrId'] for r in wire['attrAdd']}
    store.close()
