from tests.activity_calendar_helpers import activity_start, next_activity_cycle
import asyncio
import json

import pytest

from tests.unit.test_economy import env
from tests.unit.test_bag_client_fixes import stock, use
from tests.unit.test_battle import packet, request
from x2server.messages.battle import BATTLE_SCHEMAS, CHECKOUT, PROFILE_HERO
from x2server.messages.core import INT_PAIR
from x2server.messages.economy import REWARD, REWARD_ITEM, TASK
from x2server.messages.element_compose import ELEMENT_COMPOSE_SCHEMAS
from x2server.player.activity import ActivityService
from x2server.player.activity_cafe import ActivityCafe
from x2server.player.activity_rotation import ActivityRotation
from x2server.player.bag_items import recover_hero_boxes
from x2server.player.battle import BattleService
from x2server.player.endless import KILLS, PROFILE_CURRENCY


@pytest.mark.parametrize('index', range(11))
def test_every_random_three_star_outcome_is_owned_and_replayed_once(env, monkeypatch, index):
    store, economy, ctx = env
    economy.clock = lambda: ActivityRotation.ANCHOR + 3600
    gift = economy.bag_catalog['gifts']['776052']
    draw = sum(gift['weights'][:index])
    monkeypatch.setattr('x2server.player.bag_items.secrets.randbelow', lambda n: draw)
    stock(store, 1203000, 1)
    reply = use(economy, ctx, 1203000)
    assert reply.values['code'] == 10
    expected = gift['items'][index][0] - 1210000
    assert any(h['id'] == expected and h['state'] == 2 for h in store.get(1)['snapshot']['heroes'])
    snapshot = store.get(1)['snapshot']
    assert use(economy, ctx, 1203000).values == reply.values
    assert store.get(1)['snapshot'] == snapshot
    assert recover_hero_boxes(economy, 1) == 0
    assert store.db.execute('SELECT quantity FROM inventory WHERE item_id=1203000').fetchone()[0] == 0


def test_locked_hero_is_unlocked_not_silently_converted(env, monkeypatch):
    store, economy, ctx = env
    p = store.get(1)
    p['snapshot']['heroes'].append({'id': 1005, 'state': 0, 'level': 1, 'star': 0})
    store.save_snapshot(1, p['snapshot'], p['revision'])
    monkeypatch.setattr('x2server.player.bag_items.secrets.randbelow', lambda n: 0)
    stock(store, 1203000, 1)
    reply = use(economy, ctx, 1203000)
    hero = next(h for h in store.get(1)['snapshot']['heroes'] if h['id'] == 1005)
    assert hero['state'] == 2
    assert not REWARD_ITEM.decode(REWARD.decode(reply.values['rewardData'])['rewardItem'][0])['transform']
    assert len([h for h in store.get(1)['snapshot']['heroes'] if h['id'] == 1005]) == 1


def test_saved_outcome_restores_missing_hero_without_reroll_or_repeat(env, monkeypatch):
    store, economy, ctx = env
    monkeypatch.setattr('x2server.player.bag_items.secrets.randbelow', lambda n: 0)
    stock(store, 1203000, 1)
    use(economy, ctx, 1203000)
    p = store.get(1)
    p['snapshot']['heroes'] = [h for h in p['snapshot']['heroes'] if h['id'] != 1005]
    store.save_snapshot(1, p['snapshot'], p['revision'])
    monkeypatch.setattr('x2server.player.bag_items.secrets.randbelow', lambda n: pytest.fail('repair must not roll'))
    assert recover_hero_boxes(economy, 1) == 1
    snapshot = store.get(1)['snapshot']
    assert recover_hero_boxes(economy, 1) == 0
    assert store.get(1)['snapshot'] == snapshot
    assert any(h['id'] == 1005 for h in snapshot['heroes'])


def test_spent_duplicate_rewards_are_not_paid_again(env, monkeypatch):
    store, economy, ctx = env
    monkeypatch.setattr('x2server.player.bag_items.secrets.randbelow', lambda n: 0)
    stock(store, 1203000, 2)
    use(economy, ctx, 1203000, count=2)
    with store.db:
        store.db.execute('UPDATE inventory SET quantity=0 WHERE item_id!=1203000')
    assert recover_hero_boxes(economy, 1) == 0
    assert all(row[0] == 0 for row in store.db.execute('SELECT quantity FROM inventory'))


def test_missing_duplicate_ledger_destinations_are_repaired_once(env, monkeypatch):
    store, economy, ctx = env
    monkeypatch.setattr('x2server.player.bag_items.secrets.randbelow', lambda n: 0)
    stock(store, 1203000, 2)
    use(economy, ctx, 1203000, count=2)
    with store.db:
        store.db.execute('UPDATE inventory SET quantity=0 WHERE item_id!=1203000')
        store.db.execute("UPDATE economy_grants SET rewards='{}' WHERE source LIKE 'item-opt:%'")
    assert recover_hero_boxes(economy, 1) == 1
    quantities = list(store.db.execute('SELECT item_id,quantity FROM inventory ORDER BY item_id'))
    assert any(row[1] > 0 for row in quantities)
    assert recover_hero_boxes(economy, 1) == 0
    assert [tuple(r) for r in store.db.execute('SELECT item_id,quantity FROM inventory ORDER BY item_id')] == [tuple(r) for r in quantities]


def activity(economy, slot=0):
    economy.clock = lambda: activity_start(slot) + 3600
    service = ActivityService(economy)
    economy.activity = service
    return service


def test_activity_currency_identity_repair_and_repeat_cycle(env):
    store, economy, _ = env
    a = activity(economy)
    p = a.period(1)
    task = next(t for t in a.task_catalog(p, 9).values()
                if a.conditions[t['TaskConditionID']]['CompleteType']['value'] == 38)
    c = a.conditions[task['TaskConditionID']]
    item = next(r['ItemID'] for r in a.tables['Item'] if r.get('EffData') == c['CompleteValue1']
                and r['ItemType']['value'] == 16)
    with economy.transaction():
        a.obtained(1, p, {item: 7}, 'one')
        a.obtained(1, p, {item: 7}, 'one')
    assert a.rotation.get(1, p, 'tasks', task['ChallengeTaskID'])['progress'] == 7
    # Old obtained-item records were saved, but the old item ID event missed the task.
    with economy.transaction():
        a.rotation.put(1, p, 'tasks', task['ChallengeTaskID'], {'progress': 0, 'claimed': False})
    a.task_values(1, 9)
    assert a.rotation.get(1, p, 'tasks', task['ChallengeTaskID'])['progress'] == 7
    next_time = next_activity_cycle(p.start + 3600)
    economy.clock = lambda: next_time
    a.rotation.clock = economy.clock
    new = a.period(1)
    a.task_values(1, 9)
    assert a.rotation.get(1, new, 'tasks', task['ChallengeTaskID'])['progress'] == 0


def test_activity_specific_kill_high_water_marks(env):
    _, economy, _ = env
    a = activity(economy)
    p = a.period(1)
    task = next(t for t in a.task_catalog(p, 9).values()
                if a.conditions[t['TaskConditionID']]['CompleteType']['value'] == 1)
    unit = a.conditions[task['TaskConditionID']]['CompleteValue1'][0]
    with economy.transaction():
        for count in (3, 3, 1, 5):
            a.battle_kills(1, 'one', {unit: count}, p)
    assert a.rotation.get(1, p, 'tasks', task['ChallengeTaskID'])['progress'] == 5


@pytest.mark.parametrize('slot', [0, 5])
def test_food_recipe_and_business_revenue_task_semantics(env, slot):
    _, economy, _ = env
    a = activity(economy, slot)
    p = a.period(1)
    cafe = ActivityCafe(a)
    tasks = a.task_catalog(p, 20)
    if not tasks:
        # The older food theme has no enabled NewYearFoodTask rows. Its cooking
        # still settles; do not manufacture tasks belonging to the other theme.
        food = a.rotation.of_type(27, p)
        recipe = next(r for r in cafe.recipes.values() if set(r['ItemGroup']).issubset(food['ActivityParam2']))
        state = {'queues': [{'end': 0, 'start': 0, 'recipe': recipe['RecipeID'], 'token': 'cook', 'exp': 1, 'revenue': 35}],
                 'exp': 0, 'revenue': 0, 'level': 1, 'employees': {}, 'unlocked': True}
        with economy.transaction():
            cafe.settle(1, p, food['ActivityParam1'][0], state)
        assert state['revenue'] == 35 and not state['queues']
        return
    cook = next(t for t in tasks.values() if a.conditions[t['TaskConditionID']]['CompleteType']['value'] == 99)
    sell = next(t for t in tasks.values() if a.conditions[t['TaskConditionID']]['CompleteType']['value'] == 101)
    recipe = a.conditions[cook['TaskConditionID']]['CompleteValue1'][0]
    shop = a.conditions[sell['TaskConditionID']]['CompleteValue1'][0]
    state = {'queues': [{'end': 0, 'start': 0, 'recipe': recipe, 'token': 'cook', 'exp': 123, 'revenue': 35}],
             'exp': 0, 'revenue': 0, 'level': 1, 'employees': {}, 'unlocked': True}
    with economy.transaction():
        cafe.settle(1, p, shop, state)
        cafe.settle(1, p, shop, state)
    assert a.rotation.get(1, p, a.task_namespace(cook), cook['ChallengeTaskID'])['progress'] == 1
    assert a.rotation.get(1, p, a.task_namespace(sell), sell['ChallengeTaskID'])['progress'] == 35


def test_endless_compose_counts_experience_replay_and_recovery(env):
    store, economy, ctx = env
    battle = BattleService(store, economy)
    r = request()
    r.update(missionId=2110291, chapter=2060101, sceneId=2210191)
    entered = asyncio.run(battle.enter(ctx, packet(r)))
    assert entered.values['result'] == 10
    formula = next(iter(economy.element_compose.formulas.values()))
    pkt = packet({'elementID': formula['id'], 'count': 1}, name='C2L_ElementCompose', request_id=2)
    assert asyncio.run(economy.element_compose.compose(ctx, pkt)).values['code'] == 10
    asyncio.run(economy.element_compose.compose(ctx, pkt))
    progress = dict(store.db.execute('SELECT task_id,progress FROM endless_tasks'))
    assert progress[100017] == 1 and progress[100016] == formula['exp']
    # Emulate pre-fix compose records which had not reached any task.
    with store.db:
        store.db.execute('DELETE FROM endless_tasks')
        store.db.execute('DELETE FROM endless_observations WHERE kind IN (61,65)')
    economy.endless.task_values(1, 2060101)
    assert dict(store.db.execute('SELECT task_id,progress FROM endless_tasks')) == progress
    economy.endless.task_values(1, 2060101)
    assert dict(store.db.execute('SELECT task_id,progress FROM endless_tasks')) == progress


def test_endless_survival_count_is_not_team_size(env):
    store, economy, _ = env
    with economy.transaction():
        economy.endless.completed(1, 'one', 2110291, [1003, 1004])
        economy.endless.completed(1, 'two', 2110291, [1003, 1004, 1005])
        economy.endless.completed(1, 'two', 2110291, [1003, 1004, 1005])
    progress = dict(store.db.execute('SELECT task_id,progress FROM endless_tasks'))
    assert progress[100006] == 1 and progress[100010] == 1


def test_drop_string_fields_match_native_wire():
    s = BATTLE_SCHEMAS['C2L_FightDropData']
    # Independent native tags: 20/21 UTF-8 strings, 22/23 repeated messages,
    # and two occurrences of field16. Do not round-trip our own serializer.
    raw = bytes.fromhex('a20108636865636b73756d aa01067265706f7274 '
                        'b201040807100b ba01040807100b 820100 820100')
    assert s.decode(raw)['dropDataC'] == 'checksum'
    assert s.decode(raw)['dropDataD'] == 'report'
    assert INT_PAIR.decode(s.decode(raw)['sectionlParam'][0]) == {'Key': 7, 'Value': 11}
    assert len(s.decode(raw)['antiCheat']) == 2


def test_empty_committed_hero_box_refunded_once_but_unproved_receipt_is_not(env):
    store, economy, _ = env
    schema = __import__('x2server.messages.economy', fromlist=['ECONOMY_SCHEMAS']).ECONOMY_SCHEMAS['L2C_ItemOpt']
    receipt = schema.encode({'code': 10, 'itemId': 1203000, 'opt': 0, 'rewardData': b''})
    with economy.transaction():
        economy._grant(1, 'item-opt:proof', {})
        store.db.execute('INSERT INTO item_opt_receipts VALUES (?,1,?)', ('proof', receipt))
        store.db.execute('INSERT INTO item_opt_receipts VALUES (?,1,?)', ('unproved', receipt))
    assert recover_hero_boxes(economy, 1) == 1
    assert store.db.execute('SELECT quantity FROM inventory WHERE item_id=1203000').fetchone()[0] == 1
    assert recover_hero_boxes(economy, 1) == 0
    assert store.db.execute('SELECT quantity FROM inventory WHERE item_id=1203000').fetchone()[0] == 1


@pytest.mark.parametrize('alive,success', [(2, True), (3, True), (3, False)])
def test_endless_full_wire_task_chain_and_historical_survival_repair(env, alive, success):
    store, economy, ctx = env
    economy.clock = lambda: ActivityRotation.ANCHOR + 3600
    p = store.get(1)
    p['snapshot']['heroes'].extend([{'id': i, 'state': 2, 'level': 1, 'star': 1} for i in [1004,1005]])
    store.save_snapshot(1, p['snapshot'], p['revision'])
    battle = BattleService(store, economy)
    r = request()
    r.update(missionId=2110291, chapter=2060101, sceneId=2210191,
             heros=[PROFILE_HERO.encode({'heroId': i, 'leader': int(i==1003), 'state': 0}) for i in [1003,1004,1005]])
    entered = asyncio.run(battle.enter(ctx, packet(r)))
    assert entered.values['result'] == 10
    drop = packet({'missionId': 2110291, 'chapterId': 2060101, 'sceneId': 2210191,
        'currency': [PROFILE_CURRENCY.encode({'typeId': 913, 'pickupNum': 0, 'currentNum': 50, 'consumeNum': 10})],
        'killMonster': KILLS.encode({'killDetail': [INT_PAIR.encode({'Key': 3023, 'Value': 20})]}),
        'dropDataC': 'checksum', 'dropDataD': 'data'}, name='C2L_FightDropData', request_id=2)
    assert asyncio.run(battle.drop_data(ctx, drop)).values['result'] == 10
    raw = CHECKOUT.encode({'sectionId': 2110291, 'chapterId': 2060101, 'success': success,
        'heros': [PROFILE_HERO.encode({'heroId': i, 'state': int(n >= alive)}) for n,i in enumerate([1003,1004,1005])],
        'killMonster': KILLS.encode({'killDetail': [INT_PAIR.encode({'Key': 3023, 'Value': 25})]})})
    checkout = packet({'checkout': raw}, name='C2L_CheckoutMainMissionSign', request_id=3)
    reply = asyncio.run(battle.checkout(ctx, checkout))
    assert reply.values['result'] == 10
    assert asyncio.run(battle.checkout(ctx, checkout)).values == reply.values
    progress = dict(store.db.execute('SELECT task_id,progress FROM endless_tasks'))
    light_awarded=sum(item['itemNum'] for item in map(REWARD_ITEM.decode,
        REWARD.decode(reply.values.get('rewardData',b'')).get('rewardItem',[])) if item['itemId']==1237913)
    assert progress[100001] == 25 and progress[100018] == max(60,light_awarded)
    assert bool(progress.get(100006)) == success
    assert bool(progress.get(100010)) == (success and alive == 3)
    with store.db:
        store.db.execute('DELETE FROM endless_observations WHERE kind=63')
        store.db.execute('DELETE FROM endless_tasks WHERE task_id BETWEEN 100005 AND 100013')
    economy.endless.task_values(1,2060101)
    repaired = dict(store.db.execute('SELECT task_id,progress FROM endless_tasks'))
    assert bool(repaired.get(100006)) == success
    assert bool(repaired.get(100010)) == (success and alive == 3)
