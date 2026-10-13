import asyncio
import json
import pytest

from tests.unit.test_origin_season import env
from tests.unit.test_battle import packet
from x2server.messages.activity import ACTIVITY_SCHEMAS
from x2server.messages.economy import GOODS, TASK
from x2server.player.activity import ActivityService
from x2server.player.activity_runtime import ActivityRuntime
from x2server.player.activity_rotation import ActivityRotation
from x2server.player.mail import MailService
from x2server.player.battle import BattleService
from x2server.player.economy import UnresolvedEconomy


def ctx():
    from x2server.network.dispatcher import DispatchContext
    from x2server.network.session import SessionState
    return DispatchContext('test', 'local', SessionState('test', 'season-protocol', player_id=1))


@pytest.mark.parametrize('theme', range(7))
def test_real_season_shop_684_685_entry_independent_of_theme_live_gate_and_closed(env, theme):
    store, e, s = env
    from x2server.player.season_schedule import ANCHOR
    now = ANCHOR + 3600
    e.clock = lambda: now
    with store.db:
        store.db.execute('UPDATE season_calendar SET start_sec=? WHERE instance_id=?', (ActivityRotation.ANCHOR, s.instance))
    a = ActivityService(e)
    a.rotation.anchor = now - theme * ActivityRotation.SECONDS
    a.rotation.first_duration = ActivityRotation.SECONDS
    assert a.rotation.at().theme == a.rotation.themes[theme]
    rt = ActivityRuntime(a, MailService(store, e))
    e.activity = a
    request = packet({'activityType': 4}, 1, 'C2L_ActivityShop')
    result = asyncio.run(rt.handle(ctx(), request))
    assert result.values['code'] == 10 and result.values['activityType'] == 4
    ACTIVITY_SCHEMAS['L2C_ActivityShop'].encode(result.values)
    shops = [ACTIVITY_SCHEMAS['ActivityShopGoods'].decode(raw) for raw in result.values['goodsList']]
    assert len(shops) == 1 and shops[0]['shopId'] == 898 and len(shops[0]['goods']) == 9
    with e.transaction():
        state = s.state(1)
        state['exp'] = 80000
        s.write(1, state)
    assert len(ACTIVITY_SCHEMAS['ActivityShopGoods'].decode(asyncio.run(rt.handle(ctx(), request)).values['goodsList'][0])['goods']) == 53
    with store.db:
        store.db.execute('UPDATE season_calendar SET closed=1 WHERE instance_id=?', (s.instance,))
    assert asyncio.run(rt.handle(ctx(), request)).values == {'code': 13, 'activityType': 4}


def select(s, *ids):
    with s.e.transaction():
        state = s.state(1)
        state['selected_tasks'] = list(ids)
        s.write(1, state)


def task(s, tid):
    return next(TASK.decode(raw) for raw in s.task_values(1)['taskList'] if TASK.decode(raw)['taskId'] == tid)


def test_three_stage_task_next_task_progress_claim_and_red_dot_updates(env):
    _, e, s = env
    select(s, 6007005)  # TaskConditionLine620001: strengthen 5/10/15 times.
    s.pushes(1)
    for index, threshold in enumerate([5, 10, 15]):
        with e.transaction():
            s.event(1, f'strengthen:{index}', 12, 0, 5)
        before = task(s, 6007005)
        assert before['stage'] == index and before['taskStatus'] == 3 and before['taskProgress'] == threshold
        assert any(p.message_name == 'L2C_TaskUpdate' and p.values['type'] == 15 for p in s.pushes(1))
        result = s.claim_task_response(1, 6007005, f'claim:{index}')
        assert result['code'] == 10 and 'nextTask' in result
        after = TASK.decode(result['nextTask'])
        assert after['finishTimes'] == index + 1
        assert after['stage'] == min(index + 1, 2)
        assert after['taskStatus'] == (4 if index == 2 else 2)
        assert s.claim_task_response(1, 6007005, f'claim:{index}') == result
        assert any(p.message_name == 'L2C_TaskUpdate' for p in s.pushes(1))
        assert not s.pushes(1)
    assert s.claim_task_response(1, 6007005, 'already-claimed')['code'] == 13


def test_unrestored_tasks_not_assigned_or_left_in_old_week_state(env):
    _, _, s = env
    for week in range(30):
        assert all(s.task_available(tid) for tid in s.choose_tasks(1, week))
    select(s, 6007001, 6007008, 6007031)
    state = s.state(1)
    assert 6007008 not in state['selected_tasks'] and 6007031 in state['selected_tasks']
    assert len(state['selected_tasks']) == 3
    assert state['selected_tasks'] == s.state(1)['selected_tasks']


def test_manual_refresh_cannot_reintroduce_unavailable_or_refresh_claimed_tasks(env):
    _, e, s = env
    select(s, 6007009, 6007032)
    for index in range(20):
        tid = s.state(1)['selected_tasks'][index % 2]
        with e.transaction():
            result = s.operate(1, 'RefreshBattleTask', {'taskId': tid}, f'refresh:{index}')
        assert s.task_available(result['taskId'])
    with e.transaction():
        state = s.state(1)
        tid = state['selected_tasks'][0]
        state['task_claimed'].append(tid)
        s.write(1, state)
    with pytest.raises(UnresolvedEconomy), e.transaction():
        s.operate(1, 'RefreshBattleTask', {'taskId': tid}, 'refresh-claimed')


def test_all_assigned_counter_families_can_complete_and_claim(env):
    _, e, s = env
    for tid in sorted(s.tasks):
        if not s.task_available(tid):
            continue
        select(s, tid)
        with e.transaction():
            state = s.state(1)
            condition, maximum, _, _ = s.task_condition(tid, state)
            kind = condition['CompleteType']['value']
            if kind not in (36, 37):
                value = next((v for v in condition.get('CompleteValue1', []) if v not in (0, -1)), 0)
                value2 = next((v for v in condition.get('CompleteValue2', []) if v not in (0, -1)), 0)
                s.event(1, f'family:{tid}', kind, value, maximum, value2)
            else:
                relics = [i for i, r in e.items.items() if r.get('ItemType', {}).get('value') == 4][:maximum]
                for run in range(maximum):
                    s.loot(1, f'loot:{tid}:{run}', [{'id': run, 'star': 4}] * maximum, relics)
        assert task(s, tid)['taskStatus'] == 3, tid
        assert s.claim_task_response(1, tid, f'claim-family:{tid}')['code'] == 10


def test_normal_battle_kill_deltas_prism_spending_and_training_exclusion(env):
    store, e, s = env
    BattleService(store, e)
    select(s, 6007018, 6007032, 6007036)  # normal monsters, specified boss, per-run spending.
    with e.transaction():
        store.db.execute("INSERT INTO economy_runs(uuid,player_id,session_id,section_id,settled,section_type) VALUES ('run',1,'session',2110801,1,0)")
        monster = next(i for i, typ in s.unit_types.items() if typ == 2)
        s.kills(1, 'run', {monster: 10, 8101: 2}, confirmed=True)
        s.kills(1, 'run', {monster: 10, 8101: 2}, confirmed=True)
        s.kills(1, 'run', {monster: 12, 8101: 3}, confirmed=True)
        e._event(1, 'kills:run:type:2', 2, 2, 12)  # aggregate late report must not count a second time.
        s.battle_spend(1, 'run', 'pay1', 903, 400)
        s.battle_spend(1, 'run', 'pay1', 903, 400)
        s.battle_spend(1, 'run', 'pay2', 903, 200)
    assert task(s, 6007018)['taskProgress'] == 12
    assert task(s, 6007032)['taskProgress'] == 3
    assert task(s, 6007036)['taskProgress'] == 600 and task(s, 6007036)['taskStatus'] == 3
    with e.transaction():
        store.db.execute("INSERT INTO economy_runs(uuid,player_id,session_id,section_id,settled,section_type) VALUES ('training',1,'session',2110801,1,5)")
        s.kills(1, 'training', {monster: 100}, confirmed=True)
        s.battle_spend(1, 'training', 'training-pay', 903, 1000)
        s.kills(1, 'run', {monster: 1000})  # No successful receipt, so not trusted.
    assert task(s, 6007018)['taskProgress'] == 12


def test_real_gift_packet_counts_and_rejected_gift_does_not(env):
    from x2server.player.favor import FavorService
    store, e, s = env
    select(s, 6007012)
    favor = FavorService(store, e)
    with store.db:
        store.db.execute('INSERT INTO inventory VALUES (1,1204000,5)')
    request = packet({'opt': 2, 'optionId': 1204000, 'heroId': 1003, 'num': 5}, 99, 'C2L_AddFavor')
    assert asyncio.run(favor.handle(ctx(), request)).values['code'] == 10
    assert task(s, 6007012)['taskProgress'] == 5 and task(s, 6007012)['taskStatus'] == 3
    assert asyncio.run(favor.handle(ctx(), request)).values['code'] == 13
    assert task(s, 6007012)['taskProgress'] == 5


def test_weekly_changed_task_ids_replaces_client_list(env):
    _, _, s = env
    select(s, 6007001)
    s.pushes(1)
    select(s, 6007002)
    message = next(m for m in s.pushes(1) if m.message_name == 'L2C_GameTask')
    assert message.values['type'] == 15
    assert [TASK.decode(raw)['taskId'] for raw in message.values['taskList']] == [6007002]
