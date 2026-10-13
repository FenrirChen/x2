from tests.activity_calendar_helpers import activity_start, next_activity_cycle
"""Exercise bag operations against activity progress and balances, not UI mocks."""
from collections import Counter

import pytest

from tests.unit.test_economy import env
from tests.unit.test_bag_client_fixes import stock, use
from x2server.messages.economy import REWARD, REWARD_ITEM
from x2server.player.activity import ActivityService
from x2server.player.activity_rotation import ActivityRotation


def setup_activity(economy, slot):
    now = [activity_start(slot) + 3600]
    economy.clock = lambda: now[0]
    activity = ActivityService(economy)
    economy.activity = activity
    return activity, now


def test_ancient_box_currency_reaches_task_and_stat_once_then_resets_next_cycle(env, monkeypatch):
    store, economy, ctx = env
    a, now = setup_activity(economy, 2)
    period = a.period(1)
    task = next(t for t in a.task_catalog(period, 9).values()
                if a.conditions[t['TaskConditionID']]['CompleteType']['value'] == 38
                and a.conditions[t['TaskConditionID']]['CompleteValue1'] == [981])
    tid = task['ChallengeTaskID']
    a.task_values(1, 9)  # Complete historical repair before this fresh box use.
    gift = economy.bag_catalog['gifts']['776439']
    index = gift['items'].index([1237981, 50])
    monkeypatch.setattr('x2server.player.bag_items.secrets.randbelow', lambda n: sum(gift['weights'][:index]))
    stock(store, 1203027, 2)
    reply = use(economy, ctx, 1203027, count=2)
    assert reply.values['code'] == 10
    assert store.db.execute('SELECT quantity FROM inventory WHERE item_id=1237981').fetchone()[0] == 100
    assert a.rotation.get(1, period, 'tasks', tid)['progress'] == 100
    assert a.rotation.get(1, period, 'obtained-item', 1237981) == 100
    use(economy, ctx, 1203027, count=2)
    assert a.rotation.get(1, period, 'tasks', tid)['progress'] == 100
    assert a.rotation.get(1, period, 'obtained-item', 1237981) == 100
    now[0] = next_activity_cycle(now[0])
    new = a.period(1)
    a.task_values(1, 9)
    assert a.rotation.get(1, new, 'tasks', tid)['progress'] == 0
    stock(store, 1203027, 1)
    assert use(economy, ctx, 1203027, request=21).values['code'] == 10
    assert a.rotation.get(1, new, 'tasks', tid)['progress'] == 50


def test_wrong_activity_currency_does_not_complete_current_theme_task(env, monkeypatch):
    store, economy, ctx = env
    a, _ = setup_activity(economy, 0)
    p = a.period(1)
    task = next(t for t in a.task_catalog(p, 9).values()
                if a.conditions[t['TaskConditionID']]['CompleteType']['value'] == 38)
    a.task_values(1, 9)
    gift = economy.bag_catalog['gifts']['776051']
    index = gift['items'].index([1237989, 50])
    monkeypatch.setattr('x2server.player.bag_items.secrets.randbelow', lambda n: sum(gift['weights'][:index]))
    stock(store, 1203010, 1)
    assert use(economy, ctx, 1203010).values['code'] == 10
    assert a.rotation.get(1, p, 'tasks', task['ChallengeTaskID'])['progress'] == 0


def test_red_packet_power_reward_keeps_pending_regen_and_can_exceed_cap(env, monkeypatch):
    store, economy, ctx = env
    _, now = setup_activity(economy, 0)
    cap = economy.power_caps[60]
    p = store.get(1)
    p['snapshot']['mobility'] = {'power': cap - 20, 'recover_anchor': now[0] - 20 * economy.POWER_RECOVER_SECONDS}
    store.save_snapshot(1, p['snapshot'], p['revision'])
    gift = economy.bag_catalog['gifts']['776193']
    index = gift['items'].index([1237900, 88])
    monkeypatch.setattr('x2server.player.bag_items.secrets.randbelow', lambda n: sum(gift['weights'][:index]))
    stock(store, 1203021, 1)
    reply = use(economy, ctx, 1203021)
    assert reply.values['code'] == 10
    assert store.get(1)['snapshot']['mobility']['power'] == cap + 88
    assert use(economy, ctx, 1203021).values == reply.values
    assert store.get(1)['snapshot']['mobility']['power'] == cap + 88


def test_nested_box_is_preserved_in_bag_and_can_be_opened_separately(env, monkeypatch):
    store, economy, ctx = env
    setup_activity(economy, 6)
    monkeypatch.setattr('x2server.player.bag_items.secrets.randbelow', lambda n: 0)
    stock(store, 1203010, 1)
    reply = use(economy, ctx, 1203010)
    rewards = [REWARD_ITEM.decode(r) for r in REWARD.decode(reply.values['rewardData'])['rewardItem']]
    assert [(r['itemId'], r['itemNum']) for r in rewards] == [(1203001, 1)]
    assert store.db.execute('SELECT quantity FROM inventory WHERE item_id=1203001').fetchone()[0] == 1
    inner = use(economy, ctx, 1203001, request=21)
    assert inner.values['code'] == 10
    assert store.db.execute('SELECT quantity FROM inventory WHERE item_id=1203001').fetchone()[0] == 0
    assert REWARD.decode(inner.values['rewardData'])['rewardItem']


def test_failed_candidate_rolls_back_box_rewards_and_activity_progress(env, monkeypatch):
    store, economy, ctx = env
    a, _ = setup_activity(economy, 6)
    p = a.period(1)
    stock(store, 1203010, 1)
    before = store.get(1)['snapshot']
    # Reject an unresolved late destination after a valid early currency result.
    unsupported = next(i for i, r in economy.items.items()
                       if r.get('ItemType', {}).get('value') not in economy.STACKABLE_REWARD_TYPES | {10,11,15,16,20}
                       and i != 1260015)
    monkeypatch.setattr('x2server.player.bag_items.resolve_bag_gifts',
                        lambda *args: Counter({1237989: 50, unsupported: 1}))
    reply = use(economy, ctx, 1203010)
    assert reply.values['code'] == 13
    assert store.get(1)['snapshot'] == before
    assert store.db.execute('SELECT quantity FROM inventory WHERE item_id=1203010').fetchone()[0] == 1
    assert not store.db.execute('SELECT 1 FROM inventory WHERE item_id=1237989').fetchone()
    assert not store.db.execute('SELECT 1 FROM item_opt_receipts').fetchone()
    assert a.rotation.get(1, p, 'obtained-item', 1237989, 0) == 0


def test_old_successful_box_currency_is_credited_only_to_its_original_period(env, monkeypatch):
    store, economy, ctx = env
    a, now = setup_activity(economy, 2)
    p = a.period(1)
    task = next(t for t in a.task_catalog(p, 9).values()
                if a.conditions[t['TaskConditionID']]['CompleteType']['value'] == 38)
    gift = economy.bag_catalog['gifts']['776439']
    index = gift['items'].index([1237981, 50])
    monkeypatch.setattr('x2server.player.bag_items.secrets.randbelow', lambda n: sum(gift['weights'][:index]))
    stock(store, 1203027, 1)
    # Simulate the old server's missing notification, keeping genuine receipt
    # and balance grant as the only evidence for the repair.
    del economy.activity
    assert use(economy, ctx, 1203027).values['code'] == 10
    economy.activity = a
    with store.db:
        store.db.execute('UPDATE economy_grants SET created_at=?', (now[0],))
    balance = store.db.execute('SELECT quantity FROM inventory WHERE item_id=1237981').fetchone()[0]
    for _ in range(2):
        a.task_values(1,9)
    assert a.rotation.get(1, p, 'tasks', task['ChallengeTaskID'])['progress'] == 50
    assert a.rotation.get(1, p, 'obtained-item', 1237981) == 50
    assert store.db.execute('SELECT quantity FROM inventory WHERE item_id=1237981').fetchone()[0] == balance
    now[0] = next_activity_cycle(now[0])
    new = a.period(1)
    a.task_values(1,9)
    assert a.rotation.get(1, new, 'tasks', task['ChallengeTaskID'])['progress'] == 0
