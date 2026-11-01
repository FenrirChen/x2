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
    # until the half-month total reaches numLimit, so exactly one more fits.
    assert compose(e,ctx,11,420502,1).values['code'] == 10
    assert compose(e,ctx,12,420502,1).values['code'] == 13
    assert counts(cumulative_values(store,1,now)) == {420502:10}
    enter(BattleService(store,e), ctx, 13)
    assert compose(e,ctx,14,420502,1).values['code'] == 13
    assert counts(cumulative_values(store,1,now)) == {420502:10}


def test_half_month_numlimit_survives_weekly_refresh_and_resets_on_the_16th(env):
    """配方「可合成次数」按半月: 周刷新不清, 跨 16 日才清.

    周期取证: client AnswerConfig 281048 (Question 2810482
    「【乌洛波罗斯】的光能奖励，会按下哪个周期重置？」, AnswerName
    [2810483 周, 2810484 15日, 2810485 月], RightAnswer=1 -> 「15 日」).
    周刷新只重置 WeeklyDungeon.EndlessWeekVowLimit 的周光, 见 endless.ensure_week.
    """
    store, e, ctx = env
    clock = [int(datetime(2026, 12, 8, 12, tzinfo=timezone(timedelta(hours=8))).timestamp())]
    e.clock = lambda: clock[0]
    BattleService(store, e)
    with store.db:
        store.db.execute("INSERT INTO economy_runs(uuid,player_id,session_id,section_id,settled) VALUES ('last-half',1,'past',2110291,1)")
        store.db.execute("INSERT INTO battle_entries(player_id,request_key,uuid,created_at,response) VALUES (1,'last-half','last-half',?,?)",
                         (clock[0] - 10 * 86400, b''))
        store.db.execute("INSERT INTO battle_element_compose VALUES (1,'last-half',420562,12)")
    # 420562: numLimit=12, no per-operation roundLimit.
    assert not counts(cumulative_values(store, 1, clock[0]))
    first = enter(BattleService(store, e), ctx, 1)
    with store.db:
        # 入场时间按测试时钟打点: 生产里 battle_entries.created_at 用的就是同一个墙钟。
        store.db.execute('UPDATE battle_entries SET created_at=? WHERE uuid=?', (clock[0], first.values['uuid']))
    for rid in range(10, 22):
        assert compose(e, ctx, rid, 420562, 1).values['code'] == 10
    assert compose(e, ctx, 22, 420562, 1).values['code'] == 13
    assert counts(cumulative_values(store, 1, clock[0])) == {420562: 12}
    experience = cumulative_values(store, 1, clock[0])['ElementExpAll']
    # Weekly Monday refresh (12-14) clears 周光 only; the settled run's 12 composes
    # still count because they were made inside the same half-month.
    clock[0] += 7 * 86400
    push = e.endless.refresh_week(1)
    assert push is not None and WEEKLY.decode(push.values['Weekly'])['EndlessWeekVowOfStone'] == 0
    assert counts(cumulative_values(store, 1, clock[0])) == {420562: 12}
    # The Weekly wire the client receives keeps that tally after the weekly push.
    assert counts(weekly_values(store, 1, clock[0])) == {420562: 12}
    # Crossing the 16th starts a new half-month: the compose tally resets, the
    # lifetime element experience does not.
    clock[0] += 24 * 3600
    assert not counts(cumulative_values(store, 1, clock[0]))
    assert cumulative_values(store, 1, clock[0])['ElementExpAll'] == experience
