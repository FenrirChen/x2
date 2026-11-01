import asyncio
import pytest
from types import SimpleNamespace
import time
from datetime import datetime, timedelta, timezone

from tests.unit.test_economy import env
from tests.unit.test_battle import packet, request
from x2server.messages.battle import FIGHT_PROFILE, CHECKOUT
from x2server.messages.core import INT_PAIR
from x2server.player.battle import BattleService
from x2server.player.economy import EconomyService
from x2server.player.endless import weekly_values, WEEKLY
from x2server.player.login import LoginService
from x2server.player.element_compose import cumulative_values


@pytest.fixture(autouse=True)
def entry_and_scenario_share_a_clock(monkeypatch):
    # Production uses the same wall clock. Keep injected scenario times on
    # entry rows and expiry checks without modifying Python's global time module.
    monkeypatch.setattr('x2server.player.battle.time', SimpleNamespace(time=time.time))


def enter(battle, ctx, rid, resume=False):
    import x2server.player.battle as module
    module.time.time = battle.economy.clock
    values = request()
    values.update(missionId=2110291, chapter=2060101, sceneId=2210191, isFromProfile=resume)
    result = asyncio.run(battle.enter(ctx, packet(values, rid)))
    assert result.values['result'] == 10
    return result


def compose(e, ctx, rid=10, fid=420501, count=1):
    return asyncio.run(e.element_compose.compose(ctx, packet(
        {'elementID': fid, 'count': count}, rid, 'C2L_ElementCompose')))


def counts(values):
    return {p['Key']: p['Value'] for raw in values['FormulaComposeAll']
            if (p := INT_PAIR.decode(raw)).get('Key')}


def test_cumulative_history_checkout_new_run_monday_restart_login(env):
    store, e, ctx = env
    now = [int(datetime(2026, 10, 18, 23, 59, 50, tzinfo=timezone(timedelta(hours=8))).timestamp())]
    e.clock = lambda: now[0]
    b = BattleService(store, e)
    first = enter(b, ctx, 1)
    assert WEEKLY.decode(first.before_response[0].values['Weekly'])['ElementExpAll'] == 0
    answer = compose(e, ctx)
    assert answer.values['code'] == 10
    weekly = WEEKLY.decode(answer.pushes[0].values['Weekly'])
    assert weekly['ElementExpAll'] == 30 and counts(weekly) == {420501: 1}
    assert compose(e, ctx).values == answer.values
    checkout = packet({'checkout': CHECKOUT.encode({'sectionId': 2110291, 'chapterId': 2060101,
        'success': True, 'fightTime': 120})}, 11, 'C2L_CheckoutMainMissionSign')
    assert asyncio.run(b.checkout(ctx, checkout)).values['result'] == 10
    second = enter(b, ctx, 12)
    assert second.values['uuid'] != first.values['uuid']
    weekly = WEEKLY.decode(second.before_response[0].values['Weekly'])
    assert weekly['ElementExpAll'] == 30 and counts(weekly) == {420501: 1}
    # New runs must not inherit old run products/counts, or restore old map state.
    new_profile = FIGHT_PROFILE.decode(second.values['fightDataProfile'])
    assert not new_profile.get('formulaCompose') and not new_profile.get('elementExp', 0)
    assert not new_profile['isProfileValid']
    assert compose(e, ctx, 13, 420502, 2).values['code'] == 10
    now[0] += 10
    weekly = WEEKLY.decode(e.endless.refresh_week(1).values['Weekly'])
    assert weekly['ElementExpAll'] == 90 and counts(weekly) == {}
    assert not e.endless.active_run(second.values['uuid'], 1)
    assert compose(e, ctx, 14).values['code'] == 13
    rebuilt = EconomyService(store, clock=e.clock)
    login = LoginService.snapshot_push(store.get(1), store, now=now[0])
    assert WEEKLY.decode(login.values['Weekly'])['ElementExpAll'] == 90
    third = enter(BattleService(store, rebuilt), ctx, 15)
    weekly = WEEKLY.decode(third.before_response[0].values['Weekly'])
    assert counts(weekly) == {}
    assert weekly['ElementExpAll'] == 90
    assert compose(rebuilt, ctx, 16, 420502, 1).values['code'] == 10
    assert cumulative_values(store, 1, e.clock())['ElementExpAll'] == 120


def test_history_resume_counts_current_run_once_and_preserves_profile(env):
    store, e, ctx = env
    b = BattleService(store, e)
    first = enter(b, ctx, 1)
    assert compose(e, ctx).values['code'] == 10
    drop = packet({'missionId': 2110291, 'chapterId': 2060101, 'sceneId': 2210191,
                   'layer': 3}, 11, 'C2L_FightDropData')
    assert asyncio.run(b.drop_data(ctx, drop)).values['result'] == 10
    resumed = enter(b, ctx, 12, True)
    assert resumed.values['uuid'] == first.values['uuid']
    assert FIGHT_PROFILE.decode(resumed.values['fightDataProfile'])['elementExp'] == 30
    assert counts(WEEKLY.decode(resumed.before_response[0].values['Weekly'])) == {420501: 1}
    assert cumulative_values(store, 1, e.clock())['ElementExpAll'] == 30
    assert compose(e, ctx, 13).values['code'] == 10
    assert cumulative_values(store, 1, e.clock())['ElementExpAll'] == 60


def test_history_legacy_rows_invalid_data_other_players_and_non_element_runs(env):
    store, e, ctx = env
    # The half-month tally dates a run by its entry, so legacy ledger rows need
    # their entry rows too (BattleService is what creates that table).
    BattleService(store, e)
    now = e.clock()
    with store.db:
        for uid, pid, section in [('old', 1, 2110291), ('story', 1, 2035101), ('foreign', 2, 2110291)]:
            store.db.execute('INSERT INTO economy_runs(uuid,player_id,session_id,section_id,settled) VALUES (?,?,?, ?,1)',
                             (uid, pid, 'old-session', section))
            store.db.execute('INSERT INTO battle_entries(player_id,request_key,uuid,created_at,response) VALUES (?,?,?,?,?)',
                             (pid, uid, uid, now - 3600, b''))
        for pid, run, fid, n in [(1,'old',420501,1), (1,'old',420502,2),
                                 (1,'old',999999,100), (1,'old',420503,-1),
                                 (1,'story',420501,8), (2,'foreign',420501,9),
                                 (1,'orphan',420501,100)]:
            store.db.execute('INSERT INTO battle_element_compose VALUES (?,?,?,?)',(pid,run,fid,n))
    assert counts(cumulative_values(store, 1, now)) == {420501: 1, 420502: 2}
    assert cumulative_values(store, 1, now)['ElementExpAll'] == 90
    for _ in range(2):
        EconomyService(store)
        assert cumulative_values(store, 1, now)['ElementExpAll'] == 90
    with store.db:
        store.db.execute("INSERT INTO economy_runs(uuid,player_id,session_id,section_id) VALUES ('live-story',1,'session',2035101)")
    assert compose(e, ctx, 80).values['code'] == 13


def test_history_full_save_import_and_uuid_remapping(tmp_path):
    from tests.unit.test_save_manager import make_env, build_full_schema
    from x2server.network.dispatcher import DispatchContext
    from x2server.network.session import SessionState
    store, accounts, manager = make_env(tmp_path)
    try:
        build_full_schema(store)
        assert accounts.create('element-source', 'test-password', 100) == 'created'
        assert accounts.create('element-target', 'test-password', 101) == 'created'
        source = accounts.get_by_name('element-source')['player_id']
        target = accounts.get_by_name('element-target')['player_id']
        p = store.get(source)
        p['snapshot'].update(level=60, mobility={'power':149}, heroes=[{'id':1003,'state':2,'level':1,'star':1}])
        store.save_snapshot(source, p['snapshot'], p['revision'])
        e = EconomyService(store)
        ctx = DispatchContext('test', 'local', SessionState('test','session',player_id=source))
        first = enter(BattleService(store,e), ctx, 1)
        assert compose(e,ctx).values['code'] == 10
        archive = manager.export_save(source)
        # Both the raw ledger and the run it references must be remapped together.
        manager.import_save(target, archive)
        assert counts(cumulative_values(store,target,e.clock())) == {420501:1}
        assert cumulative_values(store,target,e.clock())['ElementExpAll'] == 30
        imported_run = store.db.execute('SELECT run_uuid FROM battle_element_compose WHERE player_id=?',(target,)).fetchone()[0]
        assert imported_run != first.values['uuid']
        assert store.db.execute('SELECT player_id FROM economy_runs WHERE uuid=?',(imported_run,)).fetchone()[0] == target
        assert cumulative_values(store,source,e.clock())['ElementExpAll'] == 30
        # Repeat import replaces progress rather than adding it again.
        manager.import_save(target, archive)
        assert cumulative_values(store,target,e.clock())['ElementExpAll'] == 30
    finally:
        manager.close()
        store.close()


def test_history_native_numlimit_excludes_current_run_and_failure_does_not_count(env):
    store, e, ctx = env
    # Formula 420502: numLimit=10, no per-operation roundLimit.
    BattleService(store, e)
    now = e.clock()
    with store.db:
        store.db.execute("INSERT INTO economy_runs(uuid,player_id,session_id,section_id,settled) VALUES ('past',1,'past',2110291,1)")
        store.db.execute("INSERT INTO battle_entries(player_id,request_key,uuid,created_at,response) VALUES (1,'past','past',?,?)",
                         (now - 3600, b''))
        store.db.execute("INSERT INTO battle_element_compose VALUES (1,'past',420502,9)")
    enter(BattleService(store,e), ctx, 1)
    assert compose(e,ctx,10,420502,2).values['code'] == 13
    assert counts(cumulative_values(store,1,now)) == {420502:9}
    # MaxComposeNum = numLimit - (all - single): the current run may only grow
    # until the weekly total reaches numLimit, so exactly one more fits.
    assert compose(e,ctx,11,420502,1).values['code'] == 10
    assert compose(e,ctx,12,420502,1).values['code'] == 13
    assert counts(cumulative_values(store,1,now)) == {420502:10}
    enter(BattleService(store,e), ctx, 13)
    assert compose(e,ctx,14,420502,1).values['code'] == 13
    assert counts(cumulative_values(store,1,now)) == {420502:10}


def test_compose_limits_reset_on_monday_but_not_midweek_16th(env):
    store,e,ctx=env
    stamp=lambda y,m,d,h=0: int(datetime(y,m,d,h,tzinfo=timezone(timedelta(hours=8))).timestamp())
    clock=[stamp(2026,12,8,12)]
    e.clock=lambda:clock[0]
    battle=BattleService(store,e)
    enter(battle,ctx,1)
    for rid in range(10,22):
        assert compose(e,ctx,rid,420562,1).values['code']==10
    assert compose(e,ctx,22,420562,1).values['code']==13
    assert counts(cumulative_values(store,1,clock[0]))=={420562:12}
    xp=cumulative_values(store,1,clock[0])['ElementExpAll']
    clock[0]=stamp(2026,12,14)
    push=e.endless.refresh_week(1)
    assert push is not None and not counts(WEEKLY.decode(push.values['Weekly']))
    assert cumulative_values(store,1,clock[0])['ElementExpAll']==xp
    assert compose(e,ctx,23,420562,1).values['code']==13
    enter(battle,ctx,24)
    assert compose(e,ctx,25,420562,2).values['code']==10
    clock[0]=stamp(2026,12,16)
    assert counts(weekly_values(store,1,clock[0]))=={420562:2}
    assert cumulative_values(store,1,clock[0])['ElementExpAll']==xp+60


def test_weekly_tally_does_not_multiply_duplicate_entries_or_count_future_rows(env):
    store,e,ctx=env
    battle=BattleService(store,e)
    entered=enter(battle,ctx,1)
    assert compose(e,ctx,10,420502,2).values['code']==10
    with store.db:
        store.db.execute('INSERT INTO battle_entries(player_id,request_key,uuid,created_at,response) VALUES (1,?,?,?,?)',
                         ('duplicate',entered.values['uuid'],e.clock(),b''))
    assert counts(cumulative_values(store,1,e.clock()))=={420502:2}
    with store.db:
        store.db.execute('UPDATE battle_entries SET created_at=? WHERE uuid=?',(e.clock()+3600,entered.values['uuid']))
    assert not counts(cumulative_values(store,1,e.clock()))
    assert cumulative_values(store,1,e.clock())['ElementExpAll']==60
