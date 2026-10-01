import asyncio
import json

import pytest

from x2server.messages.battle import FIGHT_DATA, FIGHT_HERO, HERO_ATTR, EQUIP_SUIT_ATTR
from x2server.messages.equipment import HERO_EQUIP, EQUIP_PARAM
from x2server.network.dispatcher import DispatchContext
from x2server.network.session import SessionState
from x2server.player.battle import BattleService
from x2server.player.battle_equipment import battle_equipment, catalogs
from x2server.player.equipment import EquipmentService
from x2server.player.store import PlayerStore
from tests.unit.test_battle import packet, request


@pytest.fixture
def equipment_env(tmp_path):
    store = PlayerStore(tmp_path / 'battle-equipment.db')
    store.login('beastlord-battle', 1, 0)
    EquipmentService(store)
    bases, _ = catalogs()
    worn = []
    for type_id, base in sorted(bases.items()):
        if base['suit'] != 400:
            continue
        slot = base['part'] - 1
        param = {'at1': 100, 'av1': 9876, 'at2': 101, 'av2': 135,
                 'at3': 105, 'av3': 271, 'at6': 108, 'av6': 123, 'lock1': 1}
        with store.db:
            cursor = store.db.execute('INSERT INTO equipment_instances '
                '(player_id,type_id,level,exp,star,param,marker) VALUES (1,?,15,0,6,?,?)',
                (int(type_id), json.dumps(param), f'test-{slot}'))
        worn.append({'position': slot, 'equip_id': cursor.lastrowid})
    assert len(worn) == 6
    yield store, {'id': 1003, 'level': 1, 'star': 1, 'state': 2, 'equips': worn}
    store.close()


@pytest.mark.parametrize('count', [0, 1, 2, 3, 4, 6])
def test_native_affixes_and_two_four_piece_thresholds(equipment_env, count):
    store, hero = equipment_env
    equipped, effects = battle_equipment(store, 1, dict(hero, equips=hero['equips'][:count]))
    assert len(equipped) == count
    for blob in equipped:
        row = HERO_EQUIP.decode(blob)
        assert row['level'] == 15 and row['star'] == 6 and row['status'] == 1
        params = EQUIP_PARAM.decode(row['param'])
        assert params['av1'] == 9876 and params['av2'] == 135 and params['av6'] == 123
    assert len(effects) == int(count >= 2)
    if effects:
        effect = EQUIP_SUIT_ATTR.decode(effects[0])
        assert effect['suitId'] == 400 and effect['suitNum'] == count
        assert effect['attribType1'] == 108 and effect['value1'] == 300
        assert effect.get('passiveID', []) == ([241000, 241006] if count >= 4 else [])


def test_entry_persists_equipment_and_replay_does_not_refresh_gear(equipment_env):
    store, hero = equipment_env
    player = store.get(1)
    store.save_snapshot(1, dict(player['snapshot'], level=60, heroes=[hero]), player['revision'])
    ctx = DispatchContext('test', 'local', SessionState('test', 'equipment', player_id=1))
    service = BattleService(store)
    result = asyncio.run(service.enter(ctx, packet(request())))
    assert result.values['result'] == 10
    wire = FIGHT_HERO.decode(FIGHT_DATA.decode(result.values['data'])['fightHeros'][0])
    assert len(wire['heroEquip']) == 6 and len(wire['equipSuitAttr']) == 1
    # Combat Property.AddEqtsAttributes adds affixes and suit bonuses itself.
    assert HERO_ATTR.decode(wire['heroAttrCount'])['hp'] == 720
    player = store.get(1)
    hero['equips'] = []
    store.save_snapshot(1, dict(player['snapshot'], heroes=[hero]), player['revision'])
    assert asyncio.run(service.enter(ctx, packet(request()))).values == result.values
    next_entry = asyncio.run(service.enter(ctx, packet(request(), 2)))
    wire = FIGHT_HERO.decode(FIGHT_DATA.decode(next_entry.values['data'])['fightHeros'][0])
    assert not wire.get('heroEquip') and not wire.get('equipSuitAttr')


def test_bad_wearing_state_rejected_without_borrowing_other_player_equipment(equipment_env):
    store, hero = equipment_env
    with pytest.raises(ValueError):
        battle_equipment(store, 2, hero)
    with pytest.raises(ValueError):
        battle_equipment(store, 1, dict(hero, equips=[hero['equips'][0]] * 2))
    wrong = dict(hero['equips'][0], position=5)
    with pytest.raises(ValueError):
        battle_equipment(store, 1, dict(hero, equips=[wrong]))
