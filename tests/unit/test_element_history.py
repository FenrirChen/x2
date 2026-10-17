import asyncio
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


def enter(battle, ctx, rid, resume=False):
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
    assert weekly['ElementExpAll'] == 90 and counts(weekly) == {420501: 1, 420502: 2}
    assert not e.endless.active_run(second.values['uuid'], 1)
    assert compose(e, ctx, 14).values['code'] == 13
    rebuilt = EconomyService(store, clock=e.clock)
    login = LoginService.snapshot_push(store.get(1), store, now=now[0])
    assert WEEKLY.decode(login.values['Weekly'])['ElementExpAll'] == 90
    third = enter(BattleService(store, rebuilt), ctx, 15)
    weekly = WEEKLY.decode(third.before_response[0].values['Weekly'])
    assert counts(weekly) == {420501: 1, 420502: 2}
    assert weekly['ElementExpAll'] == 90
    assert compose(rebuilt, ctx, 16, 420502, 1).values['code'] == 10
    assert cumulative_values(store, 1)['ElementExpAll'] == 120


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
    assert cumulative_values(store, 1)['ElementExpAll'] == 30
    assert compose(e, ctx, 13).values['code'] == 10
    assert cumulative_values(store, 1)['ElementExpAll'] == 60


def test_history_legacy_rows_invalid_data_other_players_and_non_element_runs(env):
    store, e, ctx = env
    with store.db:
        for uid, pid, section in [('old', 1, 2110291), ('story', 1, 2035101), ('foreign', 2, 2110291)]:
            store.db.execute('INSERT INTO economy_runs(uuid,player_id,session_id,section_id,settled) VALUES (?,?,?, ?,1)',
                             (uid, pid, 'old-session', section))
        for pid, run, fid, n in [(1,'old',420501,1), (1,'old',420502,2),
                                 (1,'old',999999,100), (1,'old',420503,-1),
                                 (1,'story',420501,8), (2,'foreign',420501,9),
                                 (1,'orphan',420501,100)]:
            store.db.execute('INSERT INTO battle_element_compose VALUES (?,?,?,?)',(pid,run,fid,n))
    assert counts(cumulative_values(store, 1)) == {420501: 1, 420502: 2}
    assert cumulative_values(store, 1)['ElementExpAll'] == 90
    for _ in range(2):
        EconomyService(store)
        assert cumulative_values(store, 1)['ElementExpAll'] == 90
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
        assert counts(cumulative_values(store,target)) == {420501:1}
        assert cumulative_values(store,target)['ElementExpAll'] == 30
        imported_run = store.db.execute('SELECT run_uuid FROM battle_element_compose WHERE player_id=?',(target,)).fetchone()[0]
        assert imported_run != first.values['uuid']
        assert store.db.execute('SELECT player_id FROM economy_runs WHERE uuid=?',(imported_run,)).fetchone()[0] == target
        assert cumulative_values(store,source)['ElementExpAll'] == 30
        # Repeat import replaces progress rather than adding it again.
        manager.import_save(target, archive)
        assert cumulative_values(store,target)['ElementExpAll'] == 30
    finally:
        manager.close()
        store.close()


def test_history_native_numlimit_excludes_current_run_and_failure_does_not_count(env):
    store, e, ctx = env
    # Formula 420502: numLimit=10, no per-operation roundLimit.
    with store.db:
        store.db.execute("INSERT INTO economy_runs(uuid,player_id,session_id,section_id,settled) VALUES ('past',1,'past',2110291,1)")
        store.db.execute("INSERT INTO battle_element_compose VALUES (1,'past',420502,9)")
    enter(BattleService(store,e), ctx, 1)
    assert compose(e,ctx,10,420502,2).values['code'] == 13
    assert counts(cumulative_values(store,1)) == {420502:9}
    assert compose(e,ctx,11,420502,1).values['code'] == 10
    # Current-run singleComposeTime is subtracted by the native selector.
    assert compose(e,ctx,12,420502,1).values['code'] == 10
    assert counts(cumulative_values(store,1)) == {420502:11}
    enter(BattleService(store,e), ctx, 13)
    assert compose(e,ctx,14,420502,1).values['code'] == 13
    assert counts(cumulative_values(store,1)) == {420502:11}
