import asyncio
import pytest
from tests.unit.test_economy import env
from tests.unit.test_activity_runtime import runtime
from tests.unit.test_battle import packet
from tests.activity_calendar_helpers import activity_start, next_activity_cycle
from x2server.messages.activity import ACTIVITY_SCHEMAS as S
from x2server.player.economy import UnresolvedEconomy


def quantity(store, item):
    row = store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?', (item,)).fetchone()
    return row[0] if row else 0


def send(rt, ctx, op, values=None, seq=1):
    return asyncio.run(rt.handle(ctx, packet(values or {}, seq, name='C2L_' + op)))


def setup(runtime):
    store, e, ctx, rt, now = runtime
    now[0] = activity_start(1) + 3600
    e.activity = rt.a
    return store, e, ctx, rt, now


def test_all_four_buildings_unlock_upgrade_live_query_and_replay(runtime):
    store, e, ctx, rt, now = setup(runtime)
    query = send(rt, ctx, 'ActivityBuilding')
    assert [S['ActivityBuilding'].decode(r) for r in query.values['buildings']] == [{'id': i, 'lv': 0} for i in range(1, 5)]
    with e.transaction():
        e._grant(1, 'test:building-materials', {1290232: 100, 1290233: 100})
    spent = {1290232: 0, 1290233: 0}
    for bid in range(1, 5):
        for lv in range(1, 5):
            row = rt.buildings.rows[(bid, lv)]
            result = send(rt, ctx, 'ActivityBuildingUpgrade', {'id': bid}, bid * 10 + lv)
            assert result.values == {'code': 10, 'id': bid, 'lv': lv}
            assert {'L2C_ItemUpdate', 'L2C_ExtraDropData'} <= {p.message_name for p in result.before_response}
            assert send(rt, ctx, 'ActivityBuildingUpgrade', {'id': bid}, bid * 10 + lv).values == result.values
            spent[row['UnlockItem']] += row['LevelUpNum']
        assert send(rt, ctx, 'ActivityBuildingUpgrade', {'id': bid}, bid * 10 + 5).values['code'] == 13
    assert all(quantity(store, item) == 100 - amount for item, amount in spent.items())
    fresh = send(rt, ctx, 'ActivityBuilding')  # Same query request ID still reads live state.
    assert all(S['ActivityBuilding'].decode(r)['lv'] == 4 for r in fresh.values['buildings'])
    assert len(rt.buildings.effects(1, rt.r.at())) == 16
    now[0] = next_activity_cycle(now[0])
    assert not rt.buildings.effects(1, rt.r.at())
    assert all(S['ActivityBuilding'].decode(r)['lv'] == 0 for r in send(rt, ctx, 'ActivityBuilding').values['buildings'])


def test_building_insufficient_exact_material_and_wrong_theme(runtime):
    store, e, ctx, rt, now = setup(runtime)
    assert send(rt, ctx, 'ActivityBuildingUpgrade', {'id': 1}).values['code'] == 13
    with e.transaction():
        e._grant(1, 'test:exact-building-cost', {1290233: 2})
    assert send(rt, ctx, 'ActivityBuildingUpgrade', {'id': 1}, 2).values['lv'] == 1
    assert quantity(store, 1290233) == 0
    assert send(rt, ctx, 'ActivityBuildingUpgrade', {'id': 999}, 3).values['code'] == 13
    now[0] = activity_start(2) + 3600
    assert send(rt, ctx, 'ActivityBuildingUpgrade', {'id': 1}, 4).values['code'] == 13
    assert send(rt, ctx, 'ActivityBuilding', seq=5).values['code'] == 13


def test_building_effects_snapshot_daily_caps_and_rollback(runtime, monkeypatch):
    store, e, ctx, rt, now = setup(runtime)
    with e.transaction():
        e._grant(1, 'test:materials', {1290233: 50})
    period = rt.r.at()
    with e.transaction():
        rt.r.bind_run(1, 2161031, 'before-building')
        rt.prepare_buffs(1, 2161031, 'before-building', 6)
    for lv in range(1, 5):
        assert send(rt, ctx, 'ActivityBuildingUpgrade', {'id': 1}, lv).values['lv'] == lv
    with e.transaction():
        assert rt.extra_rewards(1, 'before-building', 2161031, {1237901: 100}) == {}
    monkeypatch.setattr('x2server.player.economy.secrets.randbelow', lambda total: 0)
    expected = {}
    for gid in (776617, 776626, 776618):
        for item, num in e.gifts([gid], allow_daily_random=True).items():
            expected[item] = expected.get(item, 0) + num
    expected[1237901] = expected.get(1237901, 0) + 100
    for number in range(6):
        key = 'active-building-' + str(number)
        with e.transaction():
            rt.r.bind_run(1, 2161031, key)
            rt.prepare_buffs(1, 2161031, key, 6)
            assert rt.extra_rewards(1, key, 2161031, {1237901: 100}) == (expected if number < 5 else {})
    now[0] += 86400
    with e.transaction():
        rt.r.bind_run(1, 2161031, 'new-day')
        rt.prepare_buffs(1, 2161031, 'new-day', 6)
    with pytest.raises(RuntimeError):
        with e.transaction():
            assert rt.extra_rewards(1, 'new-day', 2161031, {1237901: 100}) == expected
            raise RuntimeError('rollback')
    with e.transaction():
        assert rt.extra_rewards(1, 'new-day', 2161031, {1237901: 100}) == expected


def test_sakura_resource_pickups_deliver_and_fund_building_upgrades(runtime):
    from tests.unit.test_economy import rewards
    from x2server.messages.battle import CHECKOUT, PROFILE_HERO, OUTSIDE_ITEM
    from x2server.player.battle import BattleService
    store, e, ctx, rt, now = setup(runtime)
    battle = BattleService(store, e)
    for bid in range(1, 5):
        sid = 2161020 + bid
        row = battle.catalog.sections[sid]
        clues = rt.buildings.rows[(bid, 1)]['BuildingClue']
        pickups = {item: 1 for item in clues}
        pickups.update({1290232: 3, 1290233: 3, 1104008: 1})
        entry = asyncio.run(battle.enter(ctx, packet({'missionId': sid, 'chapter': row['ChapterID'],
            'sceneId': row['Maps'][0], 'heros': [PROFILE_HERO.encode({'heroId': 1003, 'leader': 1})]}, 100 + bid)))
        assert entry.values['result'] == 10
        result = asyncio.run(battle.checkout(ctx, packet({'checkout': CHECKOUT.encode({
            'chapterId': row['ChapterID'], 'sectionId': sid, 'success': True, 'fightTime': 200,
            'outsideItems': [OUTSIDE_ITEM.encode({'id': item, 'num': num}) for item, num in pickups.items()]})},
            200 + bid, name='C2L_CheckoutMainMissionSign')))
        assert result.values['result'] == 10
        actual = rewards(result.values['rewardData'])
        assert all(actual.get(item) == num for item, num in pickups.items())
        assert 'L2C_ExtraDropData' in {p.message_name for p in result.before_response}
        assert all(quantity(store, clue) == 1 for clue in clues)
        assert send(rt, ctx, 'ActivityBuildingUpgrade', {'id': bid}, 300 + bid).values['lv'] == 1
    assert not store.db.execute('SELECT 1 FROM pending_rewards WHERE item_id BETWEEN 1104001 AND 1104036').fetchone()
    assert all(rt.exchange.unlocked(1, rt.r.at(), rt.exchange.shops[sid]) for sid in (871, 872, 873, 874))


def test_building_bonus_is_delivered_once_with_checkout_and_refresh(runtime, monkeypatch):
    from tests.unit.test_economy import rewards
    from x2server.messages.battle import CHECKOUT, PROFILE_HERO, OUTSIDE_ITEM
    from x2server.player.battle import BattleService
    store, e, ctx, rt, now = setup(runtime)
    with e.transaction():
        e._grant(1, 'test:building-stone', {1290233: 5})
    for lv in (1, 2):
        assert send(rt, ctx, 'ActivityBuildingUpgrade', {'id': 1}, lv).values['lv'] == lv
    monkeypatch.setattr('x2server.player.economy.secrets.randbelow', lambda total: 0)
    battle = BattleService(store, e)
    row = battle.catalog.sections[2161031]
    entry = asyncio.run(battle.enter(ctx, packet({'missionId': row['SectionID'], 'chapter': row['ChapterID'],
        'sceneId': row['Maps'][0], 'heros': [PROFILE_HERO.encode({'heroId': 1003, 'leader': 1})]}, 101)))
    assert entry.values['result'] == 10
    checkout = packet({'checkout': CHECKOUT.encode({'chapterId': row['ChapterID'],
        'sectionId': row['SectionID'], 'success': True, 'fightTime': 200,
        'outsideItems': [OUTSIDE_ITEM.encode({'id': 1237901, 'num': 100})]})},
        102, name='C2L_CheckoutMainMissionSign')
    result = asyncio.run(battle.checkout(ctx, checkout))
    assert result.values['result'] == 10
    assert rewards(result.values['rewardData'])[1237901] >= 5200  # base100 + 100%100 + rare5000
    update = next(p for p in result.before_response if p.message_name == 'L2C_ExtraDropData')
    counters = {d['Key']: d['Value'] for d in map(S['KeyValuePair_Int32_Int32'].decode, update.values['data'])}
    assert counters[1000011] == counters[1000012] == 1
    before = store.get(1)['snapshot']['gold']
    assert asyncio.run(battle.checkout(ctx, checkout)).values == result.values
    assert store.get(1)['snapshot']['gold'] == before
    assert not store.db.execute("SELECT 1 FROM activity_state WHERE namespace='run-buildings'" ).fetchone()


def test_online_rotation_and_query_refresh_building_cache(runtime, monkeypatch):
    store, e, ctx, rt, now = setup(runtime)
    with e.transaction():
        e._grant(1, 'test:online-materials', {1290233: 2})
    assert send(rt, ctx, 'ActivityBuildingUpgrade', {'id': 1}).values['lv'] == 1
    response = send(rt, ctx, 'QueryActivity', seq=99)
    assert {p.message_name for p in response.pushes} == {'L2C_ActivityBuilding', 'L2C_ExtraDropData'}
    seen = []
    class Server:
        def authenticated_player_ids(self):
            return [1]
        async def push_to_player(self, player, message):
            seen.append(message)
    calls = [0]
    async def advance(_seconds):
        calls[0] += 1
        if calls[0] == 1:
            now[0] = next_activity_cycle(now[0])
        else:
            raise RuntimeError('stop watcher')
    monkeypatch.setattr('x2server.player.activity_runtime.asyncio.sleep', advance)
    with pytest.raises(RuntimeError, match='stop watcher'):
        asyncio.run(rt.watch(Server()))
    buildings = [m for m in seen if m.message_name == 'L2C_ActivityBuilding']
    assert len(buildings) == 2
    assert S['ActivityBuilding'].decode(buildings[0].values['buildings'][0])['lv'] == 1
    assert all(S['ActivityBuilding'].decode(r)['lv'] == 0 for r in buildings[1].values['buildings'])
