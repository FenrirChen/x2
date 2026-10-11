"""Event calendar and reward state must be isolated across all seven periods."""
import pytest

from tests.unit.test_economy import env, rewards
from x2server.player.activity import ActivityService
from x2server.player.activity_rotation import ActivityRotation
from x2server.player.economy import UnresolvedEconomy
from x2server.messages.activity import ACTIVITY_SCHEMAS
from x2server.messages.economy import TASK


ORDER = ['阏逢敛遗', '伪生樱之岛', '斟鄩之邑', '全景裂隙',
         '冬至万物', '珠雀绮馔', '日月盈仄']


@pytest.fixture
def activity(env):
    store, economy, ctx = env
    now = [ActivityRotation.ANCHOR]
    economy.clock = lambda: now[0]
    return store, economy, ActivityService(economy), now


def test_calendar_exact_boundaries_and_full_cycle(activity):
    _, _, service, now = activity
    rotation = service.rotation
    assert rotation.at(rotation.ANCHOR - 1) is None
    for index in range(17):
        start = rotation.ANCHOR + index * rotation.SECONDS
        period = rotation.at(start)
        assert period.index == (index // 7) * 8 + [0, 1, 2, 4, 5, 6, 7][index % 7]
        assert period.theme['title'] == ORDER[index % 7]
        assert period.start == start and period.end == start + 5 * 86400
        assert rotation.at(period.end - 1) == period
        assert rotation.at(period.end).start == period.end


def test_local_review_calendar_keeps_game_clock_and_default_anchor(activity, monkeypatch):
    store, economy, _, now = activity
    original_now = now[0]
    monkeypatch.setenv('X2_ACTIVITY_ANCHOR', str(original_now - ActivityRotation.SECONDS))
    rotation = ActivityRotation(store, economy.clock)
    period = rotation.at()
    assert period.index == 1 and period.theme['title'] == '伪生樱之岛'
    assert period.start == original_now
    assert economy.clock() == original_now
    monkeypatch.delenv('X2_ACTIVITY_ANCHOR')
    assert ActivityRotation(store, economy.clock).at().index == 0


def test_retired_sections_and_old_runs_are_closed_without_deleting_progress(activity):
    store, economy, service, now = activity
    assert all(t['group'] != 17 for t in service.rotation.themes)
    assert len(service.rotation.catalog['closed_section_ids']) == 33
    for sid in service.rotation.catalog['closed_section_ids']:
        with pytest.raises(UnresolvedEconomy, match='not open'):
            service.admission(1, sid)
        with pytest.raises(ValueError, match='closed'):
            service.rotation.bind_run(1, sid, f'closed-{sid}')
    store.db.execute('INSERT INTO activity_runs VALUES (?,?,?,?,?,0)',
                     ('retired-run', 1, 3, 2160911, now[0]))
    with pytest.raises(ValueError, match='closed'):
        service.rotation.run_period(1, 'retired-run')
    now[0] += 3 * ActivityRotation.SECONDS
    period = service.period(1)
    assert period.theme['group'] == 13 and period.index == 4
    with economy.transaction():
        service.rotation.put(1, period, 'task', 'keep-existing', {'claimed': True})
    assert ActivityService(economy).rotation.get(1, period, 'task', 'keep-existing')['claimed']


def test_period_reset_preserves_inventory_and_previous_audit(activity):
    store, economy, service, now = activity
    period = service.period(1)
    with economy.transaction():
        service.rotation.put(1, period, 'task', 123, {'claimed': True})
        economy._grant(1, 'test:keep', {1237902: 100})
    snapshot = store.get(1)
    now[0] += 35 * 86400
    second = service.period(1)
    assert second.theme['title'] == period.theme['title']
    assert service.rotation.get(1, second, 'task', 123) is None
    assert service.rotation.get(1, period, 'task', 123) == {'claimed': True}
    assert store.get(1) == snapshot
    reopened = ActivityService(economy)
    assert reopened.rotation.get(1, second, 'task', 123) is None
    assert reopened.rotation.get(1, period, 'task', 123)['claimed']


def test_all_themes_wire_has_current_dates_and_only_current_group(activity):
    _, _, service, now = activity
    for index in range(7):
        now[0] = ActivityRotation.ANCHOR + index * ActivityRotation.SECONDS
        period = service.period(1)
        rows = [ACTIVITY_SCHEMAS['ActivityData'].decode(raw)
                for raw in service.query_activity(1)['activityData']]
        assert {r['activityGroup'] for r in rows} == {period.theme['group']}
        assert all(r['startTime'] == period.start and r['endTime'] == period.end for r in rows)
        assert all(r['param1'] and r['param2'] and r['param3'] and r['param4'] for r in rows)


def test_tasks_only_active_event_deduplicate_and_reset(activity):
    store, economy, service, now = activity
    task = next(t for t in service.task_catalog(service.period(1), 9).values()
                if not t.get('LastTask'))
    tid = task['ChallengeTaskID']
    condition = service.conditions[task['TaskConditionID']]
    value = (condition.get('CompleteValue1') or [0])[0]
    value2 = (condition.get('CompleteValue2') or [0])[0]
    with economy.transaction():
        service.event(1, 'test', condition['CompleteType']['value'], value, condition['CompleteNum'], value2)
        service.event(1, 'test', condition['CompleteType']['value'], value, condition['CompleteNum'], value2)
    state = next(r for r in map(TASK.decode, service.task_values(1, 9)['taskList']) if r['taskId'] == tid)
    assert state['taskProgress'] == condition['CompleteNum'] and state['taskStatus'] == 3
    grant = service.claim_task(1, tid, 9, task['ActivityID'])
    assert grant['code'] == 10 and rewards(grant['rewardData'])
    account = store.get(1)
    assert service.claim_task(1, tid, 9, task['ActivityID'])['code'] == 13
    assert store.get(1) == account
    now[0] += 35 * 86400
    state = next(r for r in map(TASK.decode, service.task_values(1, 9)['taskList']) if r['taskId'] == tid)
    assert state['taskProgress'] == 0 and state['taskStatus'] == 2


def test_cross_boundary_fight_finishes_in_original_period(activity):
    store, economy, service, now = activity
    old = service.period(1)
    sid = old.theme['section_ids'][0]
    now[0] = old.end - 5
    with economy.transaction():
        service.admission(1, sid)
        service.rotation.bind_run(1, sid, 'run-a')
    now[0] += 10
    with pytest.raises(UnresolvedEconomy, match='not open'):
        service.admission(1, sid)
    with economy.transaction():
        service.complete(1, 'run-a', sid, True)
    assert service.rotation.get(1, old, 'clear', sid) == 1
    assert service.rotation.get(1, service.period(1), 'clear', sid) is None
    with pytest.raises(UnresolvedEconomy, match='replay'):
        with economy.transaction():
            service.complete(1, 'run-a', sid, True)


def test_pool_cost_stock_and_failed_delivery_rollback(activity, monkeypatch):
    store, economy, service, now = activity
    period = service.period(1)
    row = service.rotation.of_type(26)
    box = service.boxes[row['ActivityParam1'][0]]
    with economy.transaction():
        economy._grant(1, 'test:pool-cost', {box['CostID']: 100000})
    before = store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?', (box['CostID'],)).fetchone()[0]
    result = service.draw_pool(1, row['ActivityID'], box['BoxID'], 10, 'draw-1')
    assert result['code'] == 10
    assert sum(service.rotation.get(1, period, 'pool', box['BoxID']).values()) == 10
    balance = store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?', (box['CostID'],)).fetchone()[0]
    assert balance == before - 10 * box['CostNum']
    with pytest.raises(UnresolvedEconomy, match='duplicate'):
        service.draw_pool(1, row['ActivityID'], box['BoxID'], 10, 'draw-1')
    state = service.rotation.get(1, period, 'pool', box['BoxID'])
    def fail(*args, **kwargs):
        raise UnresolvedEconomy('delivery failed')
    monkeypatch.setattr(economy, '_grant', fail)
    with pytest.raises(UnresolvedEconomy, match='delivery failed'):
        service.draw_pool(1, row['ActivityID'], box['BoxID'], 1, 'draw-fail')
    assert service.rotation.get(1, period, 'pool', box['BoxID']) == state
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?', (box['CostID'],)).fetchone()[0] == balance
    assert not store.db.execute("SELECT 1 FROM activity_events WHERE event_key='pool-draw:draw-fail'").fetchone()


@pytest.mark.parametrize('theme_index', [0, 2, 5])
def test_pool_wire_opens_stages_in_order_and_resets_each_period(activity, theme_index):
    store, economy, service, now = activity
    now[0] += theme_index * ActivityRotation.SECONDS
    period = service.period(1)
    row = service.rotation.of_type(26)
    ids = row['ActivityParam1']

    def visible():
        return [ACTIVITY_SCHEMAS['RewardPoolInfo'].decode(raw)
                for raw in service.pool_values(1, row['ActivityID'])['rewardPoolInfos']]

    assert [info['rewardPoolId'] for info in visible()] == ids[:1]
    assert all(ACTIVITY_SCHEMAS['KeyValuePair_Int32_Int32'].decode(raw)['Value'] == 0
               for raw in visible()[0]['goodsIdCountPair'])
    before = store.get(1)
    with pytest.raises(UnresolvedEconomy, match='locked'):
        service.draw_pool(1, row['ActivityID'], ids[-1], 1, 'skip-locked')
    assert store.get(1) == before
    assert not store.db.execute("SELECT 1 FROM activity_events WHERE event_key='pool-draw:skip-locked'").fetchone()
    for index, bid in enumerate(ids[:-1]):
        box = service.boxes[bid]
        counts = dict(zip(map(str, box['UnlockGroupID']), box['UnlockGroupTimes']))
        # Missing even one required prize must keep the next stage locked.
        counts[str(box['UnlockGroupID'][-1])] -= 1
        with economy.transaction():
            service.rotation.put(1, period, 'pool', bid, counts)
        assert [info['rewardPoolId'] for info in visible()] == ids[:index + 1]
        counts[str(box['UnlockGroupID'][-1])] += 1
        with economy.transaction():
            service.rotation.put(1, period, 'pool', bid, counts)
        assert [info['rewardPoolId'] for info in visible()] == ids[:index + 2]
    reopened = ActivityService(economy)
    assert reopened.unlocked_pools(1, period, row) == ids
    now[0] += 7 * ActivityRotation.SECONDS
    assert [info['rewardPoolId'] for info in visible()] == ids[:1]


def test_pool_draw_response_unlocks_next_stage_without_reopening(activity, monkeypatch):
    _, economy, service, now = activity
    now[0] += 2 * ActivityRotation.SECONDS
    period = service.period(1)
    row = service.rotation.of_type(26)
    first, second = row['ActivityParam1'][:2]
    box = service.boxes[first]
    counts = dict(zip(map(str, box['UnlockGroupID']), box['UnlockGroupTimes']))
    target = box['UnlockGroupID'][-1]
    counts[str(target)] -= 1
    with economy.transaction():
        economy._grant(1, 'test:unlock-pool-cost', {box['CostID']: box['CostNum']})
        service.rotation.put(1, period, 'pool', first, counts)
    ticket = sum(weight for gid, weight in zip(box['GoodsGroupId'], box['GroupProbability'])
                 if gid != target and box['GoodsGroupId'].index(gid) < box['GoodsGroupId'].index(target)
                 and counts.get(str(gid), 0) < service.box_goods[gid]['BuyTimes'])
    monkeypatch.setattr('x2server.player.activity.secrets.randbelow', lambda total: ticket)
    result = service.draw_pool(1, row['ActivityID'], first, 1, 'unlock-next')
    assert [ACTIVITY_SCHEMAS['RewardPoolInfo'].decode(raw)['rewardPoolId']
            for raw in result['rewardPoolInfos']] == [first, second]
    assert service.rotation.get(1, period, 'pool', first)[str(target)] == counts[str(target)] + 1
    with economy.transaction():
        economy._grant(1, 'test:next-pool-cost', {box['CostID']: service.boxes[second]['CostNum']})
    monkeypatch.setattr('x2server.player.activity.secrets.randbelow', lambda total: 0)
    assert service.draw_pool(1, row['ActivityID'], second, 1, 'draw-next')['code'] == 10


def test_pool_cannot_skip_locked_ancestors(activity):
    _, economy, service, now = activity
    now[0] += 2 * ActivityRotation.SECONDS
    period = service.period(1)
    row = service.rotation.of_type(26)
    predecessor = service.boxes[row['ActivityParam1'][-2]]
    with economy.transaction():
        service.rotation.put(1, period, 'pool', predecessor['BoxID'],
                             dict(zip(map(str, predecessor['UnlockGroupID']),
                                      predecessor['UnlockGroupTimes'])))
    assert service.unlocked_pools(1, period, row) == row['ActivityParam1'][:1]
    with pytest.raises(UnresolvedEconomy, match='locked'):
        service.draw_pool(1, row['ActivityID'], row['ActivityParam1'][-1], 1, 'skip-ancestors')


def test_preview_claim_once_and_again_next_cycle(activity):
    store, economy, service, now = activity
    first = service.pre_notice(1, 3, claim=True)
    assert first['code'] == 10 and rewards(first['rewardData'])
    assert service.pre_notice(1, 3)['lastPreNoticSec'] == now[0]
    with pytest.raises(UnresolvedEconomy, match='already'):
        service.pre_notice(1, 3, claim=True)
    now[0] += 35 * 86400
    assert service.pre_notice(1, 3)['lastPreNoticSec'] == 0
    assert service.pre_notice(1, 3, claim=True)['code'] == 10
