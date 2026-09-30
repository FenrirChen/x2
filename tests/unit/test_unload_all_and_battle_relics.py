import asyncio
import sqlite3

import pytest

from tests.unit.test_battle import packet, request
from tests.unit.test_economy import env  # noqa: F401
from tests.unit.test_equipment_main_growth import seed
from x2server.messages.battle import BATTLE_SCHEMAS, FIGHT_PROFILE
from x2server.messages.core import HERO_DATA
from x2server.player.battle import BattleService
from x2server.player.equipment import EquipmentService
from x2server.protocol.protobuf import encode_varint


@pytest.mark.parametrize('kind', [1, 2])
def test_client_unload_all_clears_both_sets_before_success_and_persists(env, kind):
    store, economy, ctx = env
    equipment = EquipmentService(store, economy)
    equip_id, _ = seed(store, equipment, 6)
    with store.db:
        store.db.execute('UPDATE equipment_instances SET marker=? WHERE id=?', ('first', equip_id))
    second_id, _ = seed(store, equipment, 5)
    with store.db:
        store.db.execute('UPDATE equipment_instances SET type_id=? WHERE id=?',
            (next(t for t, part in equipment.parts.items() if part == 6), second_id))
    p = store.get(1)
    hero = p['snapshot']['heroes'][0]
    hero['equips'] = [{'position': 0, 'equip_id': equip_id}, {'position': 5, 'equip_id': second_id}]
    hero['season_equips'] = [{'position': 0, 'equip_id': 90}, {'position': 5, 'equip_id': 91}]
    other = dict(hero, id=1004, equips=[{'position': 1, 'equip_id': 92}], season_equips=[])
    p['snapshot']['heroes'].append(other)
    store.save_snapshot(1, p['snapshot'], p['revision'])
    original = store.db.execute('SELECT * FROM equipment_instances').fetchall()
    req = packet({'heroID': 1003, 'posIdx': -1, 'optType': kind}, name='C2L_DoUnEquip')
    for _ in range(2):
        answer = asyncio.run(equipment.handle(ctx, req))
        assert answer.values['code'] == 10
        assert [p.message_name for p in answer.before_response] == ['L2C_HeroUpdate', 'L2C_EquipUpdate']
        wire = HERO_DATA.decode(answer.before_response[0].values['heros'][0])
        assert not wire.get('equips') and not wire.get('seasonEquips')
        current = store.get(1)['snapshot']['heroes']
        assert current[0]['equips'] == current[0]['season_equips'] == []
        assert current[1] == other
        assert store.db.execute('SELECT * FROM equipment_instances').fetchall() == original
    from x2server.player.store import PlayerStore
    reopened = PlayerStore(store.path)
    try:
        hero = reopened.get(1)['snapshot']['heroes'][0]
        assert hero['equips'] == hero['season_equips'] == []
    finally:
        reopened.db.close()


@pytest.mark.parametrize('slot', [-2, 6])
def test_invalid_unload_slot_preserves_db(env, slot):
    store, economy, ctx = env
    equipment = EquipmentService(store, economy)
    before = '\n'.join(store.db.iterdump())
    answer = asyncio.run(equipment.handle(ctx, packet(
        {'heroID': 1003, 'posIdx': slot, 'optType': 1}, name='C2L_DoUnEquip')))
    assert answer.values['code'] == 13
    assert '\n'.join(store.db.iterdump()) == before


def test_native_wire_selected_relics_reach_runtime_response_and_receipt(env):
    store, economy, ctx = env
    battle = BattleService(store, economy)
    relics = [1004024, 1004007]
    with store.db:
        store.db.executemany('INSERT INTO inventory VALUES (1,?,1)', [(r,) for r in relics])
    # Native C2L serializer writes tag 0x50, L2C and profile write 0x48.
    original = packet(request())
    body = original.body + b''.join(b'\x50' + encode_varint(r) for r in relics)
    from dataclasses import replace
    req = replace(original, body=body)
    answer = asyncio.run(battle.enter(ctx, req))
    assert answer.values['result'] == 10
    assert answer.values['selectedRelicList'] == relics
    assert FIGHT_PROFILE.decode(answer.values['fightDataProfile'])['relicList'] == relics
    encoded = BATTLE_SCHEMAS['L2C_FightData'].encode(answer.values)
    for r in relics:
        assert b'\x48' + encode_varint(r) in encoded
    power = store.get(1)['snapshot']['mobility']['power']
    assert asyncio.run(battle.enter(ctx, req)).values == answer.values
    assert store.get(1)['snapshot']['mobility']['power'] == power
    with sqlite3.connect(store.path) as reader:
        response = reader.execute('SELECT response FROM battle_entries').fetchone()[0]
        assert BATTLE_SCHEMAS['L2C_FightData'].decode(response)['selectedRelicList'] == relics
        assert reader.execute('SELECT COUNT(*) FROM economy_runs').fetchone()[0] == 1
        assert reader.execute('SELECT SUM(quantity) FROM inventory').fetchone()[0] == 2


@pytest.mark.parametrize('relics', [[1004007], [1100001], [-1], [1004007, 1004007]])
def test_bad_relics_reject_without_charging_or_abandoning_run(env, relics):
    store, economy, ctx = env
    battle = BattleService(store, economy)
    assert asyncio.run(battle.enter(ctx, packet(request()))).values['result'] == 10
    with store.db:
        store.db.execute('INSERT INTO inventory VALUES (1,1004007,?)', (1 if len(relics)==2 else 0,))
    before = '\n'.join(store.db.iterdump())
    values = request()
    values['selectedRelicList'] = relics
    answer = asyncio.run(battle.enter(ctx, packet(values, request_id=2)))
    assert answer.values['result'] == 13
    assert '\n'.join(store.db.iterdump()) == before


def test_canonical_fixed_relics_are_allowed_without_inventory_grant(env):
    store, economy, ctx = env
    battle = BattleService(store, economy)
    values = request()
    values['selectedRelicList'] = [1004943, 1004948]
    reply = asyncio.run(battle.enter(ctx, packet(values)))
    assert reply.values['result'] == 10
    assert reply.values['selectedRelicList'] == values['selectedRelicList']
    assert store.db.execute('SELECT COUNT(*) FROM inventory').fetchone()[0] == 0


def test_no_selection_does_not_automatically_equip_inventory(env):
    store, economy, ctx = env
    with store.db:
        store.db.execute('INSERT INTO inventory VALUES (1,1004007,1)')
    answer = asyncio.run(BattleService(store, economy).enter(ctx, packet(request())))
    assert answer.values['result'] == 10
    assert not answer.values.get('selectedRelicList')
    assert not FIGHT_PROFILE.decode(answer.values['fightDataProfile']).get('relicList')
