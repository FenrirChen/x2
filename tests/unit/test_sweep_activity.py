import asyncio
import sqlite3

import pytest

from tests.unit.test_battle import packet
from tests.unit.test_economy import env, rewards  # noqa: F401
from x2server.messages.lobby import ACTIVITY_DATA, LOBBY_SCHEMAS, MISSION_PAIR
from x2server.player.activity import ActivityService
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


def test_activity_entry_can_be_explicitly_disabled(env):
    store, _, ctx = env
    before = '\n'.join(store.db.iterdump())
    lobby = LobbyService(sweep_enabled=False)
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


def test_shared_15_sweep_limit_and_stamina_validation(env):
    store, economy, ctx = env
    battle = BattleService(store, economy)
    with store.db:
        store.db.execute("INSERT INTO economy_clears VALUES (1,2130501,'clear')")
    economy.refresh_stamina(1)
    p = store.get(1)
    cost = economy.reward_sections[2130501]['ManualValue']
    power = cost * 100
    store.save_snapshot(1, dict(p['snapshot'], mobility={**p['snapshot']['mobility'], 'power': power}), p['revision'])
    req = packet({'sectionId': 2130501, 'sweepCount': 15}, name='C2L_SecSweep')
    reply = asyncio.run(battle.sweep(ctx, req))
    assert reply.values['code'] == 10 and reply.values['sweepCount'] == 15
    assert store.get(1)['snapshot']['mobility']['power'] == cost * 85
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


def test_activity_directory_keeps_recovered_sweep_tab_by_default(env):
    # ActivityRuntime answers C2L_QueryActivity in production; the sweep entry
    # must survive the rebuilt directory instead of only living in the lobby's
    # overridden standalone branch.
    store, economy, ctx = env
    activity = ActivityService(economy, lobby=LobbyService())
    reply = activity.query_activity(ctx.session.player_id)
    values = LOBBY_SCHEMAS['L2C_QueryActivity'].decode(LOBBY_SCHEMAS['L2C_QueryActivity'].encode(reply))
    assert values['activityData']
    data = ACTIVITY_DATA.decode(values['activityData'][0])
    assert (data['actId'], data['actType'], data['state']) == (73010, 71, 1)


def test_activity_directory_omits_sweep_tab_when_explicitly_disabled(env):
    store, economy, ctx = env
    activity = ActivityService(economy, lobby=LobbyService(sweep_enabled=False))
    reply = activity.query_activity(ctx.session.player_id)
    values = LOBBY_SCHEMAS['L2C_QueryActivity'].decode(LOBBY_SCHEMAS['L2C_QueryActivity'].encode(reply))
    assert 73010 not in [ACTIVITY_DATA.decode(row)['actId'] for row in values['activityData']]


def test_uncleared_stage_is_not_made_clear_by_opening_activity(env):
    store, economy, ctx = env
    battle = BattleService(store, economy)
    asyncio.run(LobbyService().query(ctx, packet({}, name='C2L_QueryActivity')))
    before = '\n'.join(store.db.iterdump())
    reply = asyncio.run(battle.sweep(ctx, packet({'sectionId': 2130501, 'sweepCount': 1}, name='C2L_SecSweep')))
    assert reply.values['code'] == 13
    assert '\n'.join(store.db.iterdump()) == before


def test_production_default_sweep_survives_runtime_dispatch_and_calendar(env):
    from x2server.player.activity_runtime import ActivityRuntime
    from x2server.player.activity_rotation import ActivityRotation
    from x2server.player.mail import MailService
    from x2server.messages.activity import ACTIVITY_SCHEMAS
    _, economy, ctx = env
    now=[ActivityRotation.ANCHOR+1]
    economy.clock=lambda:now[0]
    lobby=LobbyService()
    activity=ActivityService(economy,lobby=lobby)
    runtime=ActivityRuntime(activity,MailService(economy.store,economy,economy.clock))
    handlers={**lobby.handlers(),**runtime.handlers()}
    for index,timestamp in enumerate((ActivityRotation.ANCHOR+1,ActivityRotation.FIRST_END+1,ActivityRotation.ANCHOR-1)):
        now[0]=timestamp
        reply=asyncio.run(handlers['C2L_QueryActivity'](ctx,packet({},800+index,'C2L_QueryActivity')))
        data=ACTIVITY_SCHEMAS['L2C_QueryActivity'].decode(ACTIVITY_SCHEMAS['L2C_QueryActivity'].encode(reply.values))
        rows=[ACTIVITY_DATA.decode(raw) for raw in data['activityData']]
        sweep=[r for r in rows if r['actType']==71]
        assert len(sweep)==1 and sweep[0]['actId']==73010 and sweep[0]['state']==1
    status=asyncio.run(handlers['C2L_EntryidStatus'](ctx,packet({},810,'C2L_EntryidStatus')))
    assert {'Key':19,'Value':1} in [MISSION_PAIR.decode(raw) for raw in status.values['entryidStatus']]


def test_sweep_quota_is_shared_rolls_at_midnight_and_retries_are_free(env):
    store,e,ctx=env
    battle=BattleService(store,e)
    now=[1792598399]  # 2026-10-21 23:59:59 Beijing
    e.clock=lambda:now[0]
    with store.db:
        for sid in (2130501,2130601):
            store.db.execute("INSERT INTO economy_clears VALUES (1,?,'clear')",(sid,))
    e.refresh_stamina(1)
    p=store.get(1)
    store.save_snapshot(1,dict(p['snapshot'],mobility={**p['snapshot']['mobility'],'power':10000}),p['revision'])
    def sweep(sid,n,rid):
        return asyncio.run(battle.sweep(ctx,packet({'sectionId':sid,'sweepCount':n},rid,'C2L_SecSweep')))
    first=sweep(2130501,10,900)
    assert first.values['code']==10
    assert sweep(2130501,10,900).values==first.values
    assert store.db.execute('SELECT used FROM server_sweep_limits WHERE player_id=1').fetchone()[0]==10
    assert sweep(2130601,6,901).values['code']==13
    assert sweep(2130601,5,902).values['code']==10
    before=store.get(1)
    assert sweep(2130501,1,903).values['code']==13
    assert store.get(1)==before
    now[0]+=1
    assert sweep(2130601,15,904).values['code']==10
    # A previous day's receipt cannot charge the fresh day's quota.
    assert sweep(2130501,10,900).values==first.values
    assert store.db.execute('SELECT used FROM server_sweep_limits WHERE player_id=1').fetchone()[0]==15


def test_failed_sweep_rolls_back_quota_and_rewards(env,monkeypatch):
    from x2server.player.economy import UnresolvedEconomy
    store,e,ctx=env
    battle=BattleService(store,e)
    with store.db:
        store.db.execute("INSERT INTO economy_clears VALUES (1,2130501,'clear')")
    before='\n'.join(store.db.iterdump())
    def fail(*args,**kwargs):
        raise UnresolvedEconomy('test delivery failure')
    monkeypatch.setattr(e,'_grant',fail)
    assert asyncio.run(battle.sweep(ctx,packet({'sectionId':2130501,'sweepCount':1},950,'C2L_SecSweep'))).values['code']==13
    assert '\n'.join(store.db.iterdump())==before
