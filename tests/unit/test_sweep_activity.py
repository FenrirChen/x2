import asyncio
import sqlite3

import pytest

from tests.unit.test_battle import packet
from tests.unit.test_economy import env, rewards  # noqa: F401
from x2server.messages.lobby import ACTIVITY_DATA, LOBBY_SCHEMAS, MISSION_PAIR
from x2server.player.battle import BattleService
from x2server.player.lobby import LobbyService


def test_activity_directory_contains_native_sweep_tab_without_other_events(env):
    store, economy, ctx = env
    before = '\n'.join(store.db.iterdump())
    reply = asyncio.run(LobbyService(sweep_enabled=True).query(ctx, packet({}, name='C2L_QueryActivity')))
    wire = LOBBY_SCHEMAS['L2C_QueryActivity'].encode(reply.values)
    values = LOBBY_SCHEMAS['L2C_QueryActivity'].decode(wire)
    assert len(values['activityData']) == 1
    data = ACTIVITY_DATA.decode(values['activityData'][0])
    assert (data['actId'], data['actType'], data['state']) == (73010, 71, 1)
    assert (data['activityParentType'], data['activityGroup'], data['openLever']) == (2, 24, 10)
    assert data['activityShow'] == 1 and data['param1'] == [3]
    assert data['startTime'] < 1790817334 < data['endTime']
    assert data['activityTaps'] == 'UIAltas/Activity/SaiJiSaoDang'
    # Native serializer tags for actType and param1, not an arbitrary UI flag.
    assert b'\x20\x47' in values['activityData'][0] and b'\x58\x03' in values['activityData'][0]
    assert '\n'.join(store.db.iterdump()) == before


def test_activity_entry_disabled_by_user_decision(env):
    store, _, ctx = env
    before = '\n'.join(store.db.iterdump())
    lobby = LobbyService()
    assert asyncio.run(lobby.query(ctx, packet({}, name='C2L_QueryActivity'))).values == {'code': 10}
    status = asyncio.run(lobby.query(ctx, packet({}, name='C2L_EntryidStatus'))).values
    assert [MISSION_PAIR.decode(v) for v in status['entryidStatus']] == [{'Key': 19, 'Value': 2}]
    assert '\n'.join(store.db.iterdump()) == before


@pytest.mark.parametrize('section', [2131301, 2130501, 2130601, 2130701, 2131201])
def test_client_sweep_material_chapters_grant_reward_and_replay_once(env, section):
    store, economy, ctx = env
    battle = BattleService(store, economy)
    with store.db:
        store.db.execute('INSERT INTO economy_clears VALUES (1,?,?)', (section, 'cleared-test'))
    req = packet({'sectionId': section, 'sweepCount': 2}, name='C2L_SecSweep')
    before = store.get(1)['snapshot']['mobility']['power']
    reply = asyncio.run(battle.sweep(ctx, req))
    assert reply.values['code'] == 10
    assert rewards(reply.values['rewardData'])
    after = store.get(1)
    assert after['snapshot']['mobility']['power'] == before - economy.reward_sections[section]['ManualValue']*2
    assert asyncio.run(battle.sweep(ctx, req)).values == reply.values
    assert store.get(1)['snapshot'] == after['snapshot']
    with sqlite3.connect(store.path) as reader:
        assert reader.execute('SELECT COUNT(*) FROM sweep_receipts').fetchone()[0] == 1
        assert reader.execute('SELECT COUNT(*) FROM pending_rewards').fetchone()[0] == 0


def test_client_99_sweep_limit_and_stamina_validation(env):
    store, economy, ctx = env
    battle = BattleService(store, economy)
    with store.db:
        store.db.execute("INSERT INTO economy_clears VALUES (1,2130501,'clear')")
    economy.refresh_stamina(1)
    p = store.get(1)
    cost = economy.reward_sections[2130501]['ManualValue']
    power = cost * 100
    store.save_snapshot(1, dict(p['snapshot'], mobility={**p['snapshot']['mobility'], 'power': power}), p['revision'])
    req = packet({'sectionId': 2130501, 'sweepCount': 99}, name='C2L_SecSweep')
    reply = asyncio.run(battle.sweep(ctx, req))
    assert reply.values['code'] == 10 and reply.values['sweepCount'] == 99
    assert store.get(1)['snapshot']['mobility']['power'] == cost
    for count in (0, -1, 100):
        before = '\n'.join(store.db.iterdump())
        rejected = asyncio.run(battle.sweep(ctx, packet({'sectionId': 2130501, 'sweepCount': count},
            request_id=100+count, name='C2L_SecSweep')))
        assert rejected.values['code'] == 13
        assert '\n'.join(store.db.iterdump()) == before
    before = '\n'.join(store.db.iterdump())
    assert asyncio.run(battle.sweep(ctx, packet({'sectionId': 2130501, 'sweepCount': 99},
        request_id=500, name='C2L_SecSweep'))).values['code'] == 13
    assert '\n'.join(store.db.iterdump()) == before


def test_uncleared_stage_is_not_made_clear_by_opening_activity(env):
    store, economy, ctx = env
    battle = BattleService(store, economy)
    asyncio.run(LobbyService().query(ctx, packet({}, name='C2L_QueryActivity')))
    before = '\n'.join(store.db.iterdump())
    reply = asyncio.run(battle.sweep(ctx, packet({'sectionId': 2130501, 'sweepCount': 1}, name='C2L_SecSweep')))
    assert reply.values['code'] == 13
    assert '\n'.join(store.db.iterdump()) == before
