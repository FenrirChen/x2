from tests.activity_calendar_helpers import activity_start, next_activity_cycle
import asyncio
import pytest
from tests.unit.test_economy import env, rewards
from tests.unit.test_battle import packet
from x2server.messages.activity import ACTIVITY_SCHEMAS
from x2server.player.activity import ActivityService
from x2server.player.activity_runtime import ActivityRuntime
from x2server.player.activity_rotation import ActivityRotation
from x2server.player.mail import MailService
from x2server.player.economy import UnresolvedEconomy


@pytest.fixture
def runtime(env):
    store, economy, context = env
    now = [ActivityRotation.ANCHOR + 3600]
    economy.clock = lambda: now[0]
    activity = ActivityService(economy)
    runtime = ActivityRuntime(activity, MailService(store, economy, economy.clock))
    operate = runtime.operate

    def checked_operate(player, operation, request, token):
        # All gameplay tests must also exercise the actual response contract.
        # A business-only assertion missed the extra storeType in response 839.
        from x2server.messages.lobby import LOBBY_SCHEMAS
        values = operate(player, operation, request, token)
        name = 'L2C_' + operation
        schema = ACTIVITY_SCHEMAS.get(name) or LOBBY_SCHEMAS[name]
        schema.encode(values)
        return values

    runtime.operate = checked_operate
    return store, economy, context, runtime, now


def test_yuexi_frontier_updates_on_checkout_and_resets_next_period(runtime):
    _, _, _, rt, now = runtime
    now[0] = activity_start(6) + 3600
    period = rt.a.period(1)
    assert rt.records(1, period)['previousRecord'] == 0
    for sid in period.theme['section_ids']:
        rt.r.put(1, period, 'clear', sid, 1)
        result = rt.operate(1, 'QueryActivityMissionRecord', {}, 'query')
        assert result['previousRecord'] == sid
        pushed = next(m for m in rt.progress_messages(1)
                      if m.message_name == 'L2C_QueryActivityMissionRecord')
        assert pushed.values['previousRecord'] == sid
    now[0] = next_activity_cycle(now[0])
    assert rt.records(1, rt.a.period(1))['previousRecord'] == 0


@pytest.mark.parametrize('chapter_id,soul', [(2021511,1290189), (2022811,1290190),
                                           (2021023,1290191), (2022711,1290192)])
def test_yuexi_pov_soul_paid_only_after_all_successful_stages(runtime, chapter_id, soul):
    store, economy, _, rt, now = runtime
    from x2server.player.battle import BattleService
    BattleService(store, economy)
    economy.activity = rt.a
    now[0] = activity_start(6) + 3600
    chapter = next(c for c in rt.a.tables['POVChapterInfo'] if c['ChapterID'] == chapter_id)
    def finish(sid, key, success=True):
        with economy.transaction():
            store.db.execute("""INSERT INTO economy_runs
                (uuid,player_id,session_id,section_id,settled,section_type,entry_source)
                VALUES (?,1,'session',?,0,4,'MainMission')""", (key, sid))
            result, _ = economy.settle(1, key, sid, success, section_type=4)
        return rewards(result)
    for index, sid in enumerate(chapter['StageID']):
        if index == len(chapter['StageID']) - 1:
            assert soul not in finish(sid, f'fail-{sid}', False)
        result = finish(sid, f'pass-{sid}')
        assert result.get(soul, 0) == int(index == len(chapter['StageID']) - 1)
    assert soul not in finish(chapter['StageID'][-1], 'repeat')
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?', (soul,)).fetchone()[0] == 1


@pytest.mark.parametrize('theme', [3])
def test_tower_entry_queries_use_real_catalog_and_stable_passives(runtime, theme):
    _, _, context, rt, now = runtime
    now[0] = activity_start(theme) + 3600
    for op in ('QueryActivityTower', 'ActivityTowerPassive'):
        response = asyncio.run(rt.handle(context, packet({}, 990 + theme, 'C2L_' + op)))
        assert response.values['code'] == 10
        ACTIVITY_SCHEMAS['L2C_' + op].encode(response.values)
        assert not response.before_response
    infos = rt.operate(1, 'QueryActivityTower', {}, 'tower-info')['towerInfo']
    ids = [ACTIVITY_SCHEMAS['ActivityTowerInfo'].decode(raw).get('id', 0) for raw in infos]
    assert ids == [0]  # Native skips ID 0; no paid tower is unlocked for free.
    first = rt.operate(1, 'ActivityTowerPassive', {}, 'passive-a')
    assert rt.operate(1, 'ActivityTowerPassive', {}, 'passive-b') == first
    assert first['passives']


def test_retired_activity_battle_entry_and_query_are_rejected(runtime):
    from x2server.player.battle import BattleService
    from x2server.messages.battle import PROFILE_HERO
    _, e, ctx, rt, _ = runtime
    e.activity = rt.a
    battle = BattleService(rt.a.store, e)
    for sid in rt.r.catalog['closed_section_ids']:
        entry = asyncio.run(battle.enter(ctx, packet({'missionId': sid,
            'heros': [PROFILE_HERO.encode({'heroId': 1003, 'leader': 1})]})))
        assert entry.values['result'] == 13
    reply = asyncio.run(rt.handle(ctx, packet({'activityId': 72020}, 988, 'C2L_ActivityMissionData')))
    assert reply.values['code'] == 13


def test_yuexi_skipped_intro_claim_persists_and_cannot_pay_twice(runtime):
    store, e, ctx, rt, now = runtime
    now[0] = activity_start(6) + 3600
    request = packet({}, 975, 'C2L_ActivityDialogue')
    assert rt.operate(1, 'ActivityDialogReciveInfo', {}, 'query')['lastReciveTimeSec'] == 0
    claimed = asyncio.run(rt.handle(ctx, request))
    assert claimed.values['code'] == 10
    assert rewards(claimed.values['rewardData']) == e.gifts([776004], allow_daily_random=True)
    snapshot = store.get(1)
    assert asyncio.run(rt.handle(ctx, request)).values == claimed.values
    assert store.get(1) == snapshot
    denied = asyncio.run(rt.handle(ctx, packet({}, 976, 'C2L_ActivityDialogue')))
    assert denied.values['code'] == 10 and not denied.values.get('rewardData')
    acknowledgement = rt.a.pre_notice(1, 1, claim=True)
    assert acknowledgement['code'] == 10 and not acknowledgement.get('rewardData')
    restored = ActivityRuntime(ActivityService(e), MailService(store, e, e.clock))
    assert restored.operate(1, 'ActivityDialogReciveInfo', {}, 'relogin')['lastReciveTimeSec'] == now[0]
    now[0] += 86400
    rows = [ACTIVITY_SCHEMAS['ActivityData'].decode(r) for r in rt.a.query_activity(1)['activityData']]
    assert next(r for r in rows if r['actId'] == 70009).get('state', 0) == 0
    assert next(r for r in rows if r['actId'] == 70010)['state'] == 1
    acknowledged = asyncio.run(rt.handle(ctx, packet({}, 977, 'C2L_ActivityDialogue')))
    assert acknowledged.values['code'] == 10 and not acknowledged.values.get('rewardData')
    now[0] += 48 * 86400
    assert rt.operate(1, 'ActivityDialogReciveInfo', {}, 'next-period')['lastReciveTimeSec'] == 0


def test_yuexi_midday_review_closes_only_preview_at_beijing_midnight(runtime):
    _, _, _, rt, now = runtime
    rt.r.anchor += 23 * 3600
    now[0] = rt.r.bounds(6)[0] + 60
    period = rt.r.at()
    assert rt.a.yuexi_preview_end(period) == period.start + 3600
    now[0] = period.start + 3600
    data = [ACTIVITY_SCHEMAS['ActivityData'].decode(r) for r in rt.a.query_activity(1)['activityData']]
    assert {r['actId'] for r in data if r.get('state') == 1} == {70010, 70011}
    with pytest.raises(UnresolvedEconomy):
        rt.operate(1, 'ActivityDialogue', {}, 'closed')


def test_yuexi_generic_preview_claim_is_shared_with_plot_completion(runtime):
    _, _, _, rt, now = runtime
    now[0] = activity_start(6) + 3600
    assert rt.a.pre_notice(1, 1, claim=True)['code'] == 10
    assert rt.operate(1, 'ActivityDialogReciveInfo', {}, 'query')['lastReciveTimeSec'] == now[0]
    acknowledged = rt.operate(1, 'ActivityDialogue', {}, 'alternate-route')
    assert acknowledged['code'] == 10 and not acknowledged.get('rewardData')


def test_winter_progress_and_story_protocols_use_current_period(runtime):
    _, e, ctx, rt, now = runtime
    now[0] = activity_start(4) + 3600
    period = rt.r.at()
    response = asyncio.run(rt.handle(ctx, packet({}, 981, 'C2L_QueryShuangHanActivity')))
    assert response.values['code'] == 10
    chapters = [ACTIVITY_SCHEMAS['ActivityShuangHan'].decode(raw) for raw in response.values['activityInfo']]
    assert [c['chapterId'] for c in chapters] == [2060251, 2060261, 2060271, 2060281]
    assert all(not c['lastPassMissionId'] and not c['storyPlayState'] for c in chapters)
    denied = asyncio.run(rt.handle(ctx, packet({'chapterId': 2060261}, 982, 'C2L_PlayShuangHanPV')))
    assert denied.values['code'] == 13
    played = asyncio.run(rt.handle(ctx, packet({'chapterId': 2060251}, 983, 'C2L_PlayShuangHanPV')))
    assert ACTIVITY_SCHEMAS['ActivityShuangHan'].decode(played.values['activityInfo'])['storyPlayState']
    with e.transaction():
        for sid in rt.a.chapters[2060251]['SectionID']:
            rt.r.put(1, period, 'clear', sid, 1)
    assert rt.a.frost_values(1)['activityInfo'][0] == ACTIVITY_SCHEMAS['ActivityShuangHan'].encode(
        {'chapterId': 2060251, 'storyPlayState': True, 'lastPassMissionId': 2160259})
    assert asyncio.run(rt.handle(ctx, packet({'chapterId': 2060261}, 984, 'C2L_PlayShuangHanPV'))).values['code'] == 10
    now[0] = next_activity_cycle(now[0])
    reset = rt.a.frost_values(1)
    assert all(not ACTIVITY_SCHEMAS['ActivityShuangHan'].decode(raw)['lastPassMissionId']
               for raw in reset['activityInfo'])


@pytest.mark.parametrize('group', [7, 33, 13, 99])
def test_purchase_refreshes_all_activity_shop_stock_caches(runtime, group):
    from tests.unit.test_activity_exchange import open_shop
    from x2server.messages.economy import GOODS
    _, e, ctx, rt, now = runtime
    index = next(i for i, t in enumerate(rt.r.themes) if t['group'] == group)
    now[0] = activity_start(index) + 3600
    period = rt.r.at()
    shop = next(s for s in rt.exchange.shops.values() if s['group'] == group and s['stage'] == 1)
    open_shop(rt.a, e, shop, period)
    offer = shop['goods'][0]
    with e.transaction():
        e._grant(1, 'test:popup-stock', {offer['currencyItemId']: 100000})
    request = {'shopId': shop['shopId'], 'goodsId': offer['goodsId'], 'buyNum': offer['canBuyTimes']}
    response = asyncio.run(rt.exchange.handle(ctx, packet(request, 991, 'C2L_BuyGoods'),
                           'C2L_BuyGoods', request))
    assert response.values['code'] == 10
    push = next(p for p in response.pushes if p.message_name == 'L2C_ActivityShop')
    wire = ACTIVITY_SCHEMAS['L2C_ActivityShop'].decode(ACTIVITY_SCHEMAS['L2C_ActivityShop'].encode(push.values))
    shops = [ACTIVITY_SCHEMAS['ActivityShopGoods'].decode(raw) for raw in wire['goodsList']]
    row = next(GOODS.decode(raw) for s in shops for raw in s['goods'] if GOODS.decode(raw)['goodsId'] == offer['goodsId'])
    assert row['canBuyTimes'] - row['hasBuyTimes'] == 0
    rejected = asyncio.run(rt.exchange.handle(ctx, packet(request, 992, 'C2L_BuyGoods'),
                           'C2L_BuyGoods', request))
    assert rejected.values['code'] == 13


def test_cafe_staff_transport_replay_and_all_success_response_shapes(runtime):
    store, e, ctx, rt, now = runtime
    seed(rt, {1290301: 1, 1290317: 30, 1290318: 20, 1237984: 1000})
    requests = [('CafeStoreUnLock', {'storeType': 7}),
                ('CafeStorePositionSet', {'storeType': 7, 'heroId': 1003, 'position': 1}),
                *[('CafeStoreCooking', {'storeType': 7, 'recipeID': 25})] * 3]
    for seq, (op, values) in enumerate(requests, 800):
        req = packet(values, seq, 'C2L_' + op)
        response = asyncio.run(rt.handle(ctx, req))
        assert response.values['code'] == 10
        ACTIVITY_SCHEMAS['L2C_' + op].encode(response.values)
        assert asyncio.run(rt.handle(ctx, req)).values == response.values
    busy = asyncio.run(rt.handle(ctx, packet({'storeType': 7, 'heroId': 0, 'position': 1},
                                            805, 'C2L_CafeStorePositionSet')))
    assert busy.values == {'code': 13}
    now[0] += rt.cafe.recipes[25]['WaitTimes']
    for seq, op in enumerate(('CafeStoreUpdate', 'CafeStoreReceiveRevenue', 'CafeStoreLevelUp'), 806):
        response = asyncio.run(rt.handle(ctx, packet({'storeType': 7}, seq, 'C2L_' + op)))
        assert response.values['code'] == 10
        ACTIVITY_SCHEMAS['L2C_' + op].encode(response.values)
    assert rt.cafe.values(1, 7)['employeeInfo']


def test_activity_protocol_error_rolls_back_and_returns_error_not_disconnect(runtime, monkeypatch):
    store, e, ctx, rt, _ = runtime

    def incompatible(player, op, request, token):
        rt.r.put(player, rt.r.at(), 'must-rollback', 1, 1)
        return {'code': 10, 'storeType': 7}

    monkeypatch.setattr(rt, 'operate', incompatible)
    response = asyncio.run(rt.handle(ctx, packet({'storeType': 7, 'heroId': 1003, 'position': 1},
                                                999, 'C2L_CafeStorePositionSet')))
    assert response.values == {'code': 13}
    assert rt.r.get(1, rt.r.at(), 'must-rollback', 1, 0) == 0
    assert not store.db.execute('SELECT 1 FROM activity_receipts').fetchone()


@pytest.mark.parametrize('theme_index', range(7))
def test_every_activity_route_returns_encodable_response_in_every_period(runtime, theme_index):
    from x2server.messages.lobby import LOBBY_SCHEMAS
    _, _, ctx, rt, now = runtime
    now[0] = activity_start(theme_index) + 3600
    for seq, name in enumerate(rt.handlers(), 3000):
        response = asyncio.run(rt.handle(ctx, packet({}, seq, name)))
        schema = ACTIVITY_SCHEMAS.get(response.message_name) or LOBBY_SCHEMAS[response.message_name]
        schema.encode(response.values)


@pytest.mark.parametrize('theme_index', range(7))
def test_all_theme_login_scene_parameters_and_real_shop_requests(runtime, theme_index):
    _, _, ctx, rt, now = runtime
    from x2server.protocol.registry import CORE_MESSAGE_REGISTRY
    assert CORE_MESSAGE_REGISTRY.name_for(1038) == 'C2L_SceneGlobalParam'
    now[0] = activity_start(theme_index) + 3600
    response = asyncio.run(rt.handle(ctx, packet({}, 6100, 'C2L_SceneGlobalParam')))
    assert response.message_name == 'L2C_SceneGlobalParam' and response.values['code'] == 10
    rows = [ACTIVITY_SCHEMAS['SceneSectionParam'].decode(wire)
            for wire in response.values['sceneSectionParam']]
    counts = {pair['Key']: pair['Value'] for row in rows for pair in
              map(ACTIVITY_SCHEMAS['KeyValuePair_Int32_Int32'].decode, row['sectionParam'])}
    period = rt.r.at()
    assert all(counts[sid] == 0 for sid in period.theme['section_ids'])
    if period.theme['section_ids']:
        sid = period.theme['section_ids'][0]
        with rt.e.transaction():
            rt.r.put(1, period, 'clear', sid, 4)
        updated = asyncio.run(rt.handle(ctx, packet({}, 6101, 'C2L_SceneGlobalParam')))
        rows = [ACTIVITY_SCHEMAS['SceneSectionParam'].decode(w) for w in updated.values['sceneSectionParam']]
        assert any(pair['Key'] == sid and pair['Value'] == 4 for row in rows for pair in
                   map(ACTIVITY_SCHEMAS['KeyValuePair_Int32_Int32'].decode, row['sectionParam']))
    family = 2 if period.theme['group'] == 7 else 1 if period.theme['group'] == 99 else 3
    shop = asyncio.run(rt.handle(ctx, packet({'activityType': family}, 6102, 'C2L_ActivityShop')))
    has_shop = any(s['group'] == period.theme['group'] for s in rt.exchange.shops.values())
    assert shop.values['code'] == (10 if has_shop else 13)
    for wire in shop.values.get('goodsList', []):
        listing = ACTIVITY_SCHEMAS['ActivityShopGoods'].decode(wire)
        assert listing['shopId'] in rt.exchange.shops and listing['goods']


def seed(rt, items, key='seed'):
    with rt.e.transaction():
        period = rt.a.period(1)
        rt.e._grant(1, key, items)
        rt.a.obtained(1, period, items, key)


def test_cafe_paid_cooking_sale_level_staff_restart(runtime):
    store, e, ctx, rt, now = runtime
    seed(rt, {1290301: 1, 1290317: 30, 1290318: 20, 1237984: 1000})
    with e.transaction():
        assert len(rt.operate(1, 'CafeStoreInfo', {}, 'i')['storeInfo']) == 3
        rt.operate(1, 'CafeStoreUnLock', {'storeType': 7}, 'u')
        rt.operate(1, 'CafeStorePositionSet', {'storeType': 7, 'heroId': 1003, 'position': 1}, 's')
        rt.operate(1, 'CafeStoreCooking', {'storeType': 7, 'recipeID': 25}, 'c')
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1290317').fetchone()[0] == 27
    now[0] += 10000
    with e.transaction():
        result = rt.operate(1, 'CafeStoreReceiveRevenue', {'storeType': 7}, 'r')
    assert rewards(result['rewardData'])[1237984] > 0
    with pytest.raises(UnresolvedEconomy), e.transaction():
        rt.operate(1, 'CafeStoreReceiveRevenue', {'storeType': 7}, 'r2')
    reopened = ActivityRuntime(ActivityService(e), rt.mail)
    assert reopened.cafe.values(1, 7)['exp'] > 0


@pytest.mark.parametrize('theme_index', [0, 5])
def test_all_cafe_recipes_exact_ingredients_in_every_store(runtime, theme_index):
    store, e, ctx, rt, now = runtime
    base_time = activity_start(theme_index) + 3600
    now[0] = base_time
    food = rt.r.of_type(27, rt.r.at())
    recipes = [r for r in rt.cafe.recipes.values()
               if set(r['ItemGroup']).issubset(food['ActivityParam2'])]
    assert len(recipes) == (11 if theme_index == 0 else 13)
    seed(rt, {r['UnlockItem']: 1 for r in recipes})
    for store_type in food['ActivityParam1']:
        with e.transaction():
            rt.operate(1, 'CafeStoreUnLock', {'storeType': store_type}, f'unlock-{store_type}')
            rt.operate(1, 'CafeStorePositionSet', {'storeType': store_type,
                'heroId': 1003, 'position': 1}, f'staff-{store_type}')
        for recipe in recipes:
            now[0] = base_time
            with e.transaction():
                for item, count in zip(recipe['ItemGroup'], recipe['ItemNum'], strict=True):
                    store.db.execute('''INSERT INTO inventory VALUES (?,?,?)
                        ON CONFLICT(player_id,item_id) DO UPDATE SET quantity=excluded.quantity''',
                        (1, item, count))
            request = packet({'storeType': store_type, 'recipeID': recipe['RecipeID']},
                             2000 + store_type * 100 + recipe['RecipeID'], 'C2L_CafeStoreCooking')
            response = asyncio.run(rt.handle(ctx, request))
            assert response.values['code'] == 10, (store_type, recipe['RecipeID'])
            queue = ACTIVITY_SCHEMAS['CafeStoreQueue'].decode(response.values['queue'])
            assert queue['recipeId'] == recipe['RecipeID']
            assert all(store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?',
                       (i,)).fetchone()[0] == 0 for i in recipe['ItemGroup'])
            assert asyncio.run(rt.handle(ctx, request)).values == response.values
            assert len(rt.cafe.values(1, store_type)['cafeStoreQueueInfo']) == 1
            now[0] += recipe['WaitTimes'] + 1
            with e.transaction():
                sold = rt.operate(1, 'CafeStoreReceiveRevenue', {'storeType': store_type},
                                  f'sale-{store_type}-{recipe["RecipeID"]}')
            assert rewards(sold['rewardData'])[1237984] == recipe['SellPrice']
            assert rt.cafe.values(1, store_type)['cafeStoreQueueInfo'] == []


def test_cafe_incomplete_ingredients_roll_back_entire_order(runtime):
    store, e, _, rt, _ = runtime
    seed(rt, {1290301: 1, 1290317: 3, 1290318: 1})
    with e.transaction():
        rt.operate(1, 'CafeStoreUnLock', {'storeType': 7}, 'unlock')
        rt.operate(1, 'CafeStorePositionSet', {'storeType': 7, 'heroId': 1003, 'position': 1}, 'chef')
    with pytest.raises(UnresolvedEconomy), e.transaction():
        rt.operate(1, 'CafeStoreCooking', {'storeType': 7, 'recipeID': 25}, 'insufficient')
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1290317').fetchone()[0] == 3
    assert rt.cafe.values(1, 7)['cafeStoreQueueInfo'] == []


def test_cafe_empty_queue_staff_busy_capacity_sale_and_level_loop(runtime):
    store, e, ctx, rt, now = runtime
    seed(rt, {1290301: 1, 1290317: 30, 1290318: 20, 1237984: 1000})
    with e.transaction():
        rt.operate(1, 'CafeStoreUnLock', {'storeType': 7}, 'unlock')
        idle = rt.cafe.values(1, 7)
        assert idle['cafeStoreQueueInfo'] == []
        wire = ACTIVITY_SCHEMAS['CafeStoreInfo'].decode(ACTIVITY_SCHEMAS['CafeStoreInfo'].encode(idle))
        assert 'cafeStoreQueueInfo' not in wire  # Native patch initializes an empty list.
        with pytest.raises(UnresolvedEconomy):
            rt.operate(1, 'CafeStoreCooking', {'storeType': 7, 'recipeID': 25}, 'no-chef')
        rt.operate(1, 'CafeStorePositionSet', {'storeType': 7, 'heroId': 1003, 'position': 1}, 'staff')
        for i in range(3):
            rt.operate(1, 'CafeStoreCooking', {'storeType': 7, 'recipeID': 25}, f'cook-{i}')
        assert len(rt.cafe.values(1, 7)['cafeStoreQueueInfo']) == 3
    balance = dict(store.db.execute('SELECT item_id,quantity FROM inventory WHERE player_id=1'))
    for op, request in [('CafeStoreCooking', {'storeType': 7, 'recipeID': 25}),
                        ('CafeStorePositionSet', {'storeType': 7, 'heroId': 0, 'position': 1})]:
        with pytest.raises(UnresolvedEconomy), e.transaction():
            rt.operate(1, op, request, 'blocked-' + op)
    assert dict(store.db.execute('SELECT item_id,quantity FROM inventory WHERE player_id=1')) == balance
    now[0] += rt.cafe.recipes[25]['WaitTimes']
    with e.transaction():
        updated = rt.operate(1, 'CafeStoreUpdate', {'storeType': 7}, 'complete')
        values = ACTIVITY_SCHEMAS['CafeStoreInfo'].decode(updated['storeInfo'])
        assert values.get('cafeStoreQueueInfo', []) == []
        assert values['revenue'] == 3 * rt.cafe.recipes[25]['SellPrice']
        revenue = rt.operate(1, 'CafeStoreReceiveRevenue', {'storeType': 7}, 'sale')
        assert rewards(revenue['rewardData'])[1237984] == values['revenue']
        upgraded = rt.operate(1, 'CafeStoreLevelUp', {'storeType': 7}, 'level')
        assert upgraded['level'] == 2
        assert upgraded['exp'] == 3 * rt.cafe.recipes[25]['CafeExp'] - 200
        rt.operate(1, 'CafeStorePositionSet', {'storeType': 7, 'heroId': 0, 'position': 1}, 'remove')
        rt.operate(1, 'CafeStorePositionSet', {'storeType': 7, 'heroId': 1003, 'position': 1}, 'replace')
        cooking = rt.operate(1, 'CafeStoreCooking', {'storeType': 7, 'recipeID': 25}, 'again')
        queue = ACTIVITY_SCHEMAS['CafeStoreQueue'].decode(cooking['queue'])
        assert queue['preRevenue'] == rt.cafe.recipes[25]['SellPrice'] * 1050 // 1000


def test_cafe_retained_recipe_unlocks_next_occurrence(runtime):
    _, e, _, rt, now = runtime
    seed(rt, {1290301: 1, 1290317: 10, 1290318: 10})
    now[0] = next_activity_cycle(now[0])
    with e.transaction():
        assert rt.r.get(1, rt.r.at(), 'obtained-item', 1290301, 0) == 0
        rt.operate(1, 'CafeStoreUnLock', {'storeType': 7}, 'next-unlock')
        rt.operate(1, 'CafeStorePositionSet', {'storeType': 7, 'heroId': 1003, 'position': 1}, 'next-staff')
        assert rt.operate(1, 'CafeStoreCooking', {'storeType': 7, 'recipeID': 25}, 'next-cook')['code'] == 10


@pytest.mark.parametrize('theme_index', range(7))
def test_activity_currency_snapshot_balances_follow_inventory(runtime, theme_index):
    from x2server.messages.core import BASE_INFO
    from x2server.player.login import LoginService, SHOP_CURRENCY_FIELDS
    store, e, ctx, rt, now = runtime
    now[0] = activity_start(theme_index) + 3600
    items = {i: 7 + n for n, i in enumerate(SHOP_CURRENCY_FIELDS) if i >= 1237976}
    seed(rt, items)
    base = BASE_INFO.decode(LoginService.snapshot_push(store.get(1), store, now[0]).values['BaseInfo'])
    expected = {}
    for item, amount in items.items():
        field = SHOP_CURRENCY_FIELDS[item]
        expected[field] = expected.get(field, 0) + amount
    assert all(base[field] == amount for field, amount in expected.items())
    with e.transaction():
        rt.a.spend(1, rt.r.at(), 1237984, 2, 'consume')
    base = BASE_INFO.decode(LoginService.snapshot_push(store.get(1), store, now[0]).values['BaseInfo'])
    assert base['NewYearCoin'] == expected['NewYearCoin'] - 2


def test_lantern_answer_boxes_paper_replay_and_rollback(runtime):
    store, e, ctx, rt, now = runtime
    seed(rt, {1290333: 20})
    for i in range(3):
        with e.transaction():
            q = rt.operate(1, 'LanternShowQuestion', {'activityId': 72046}, f'q{i}')
            pending = rt.operate(1, 'LanternShowQuestion', {'activityId': 72046}, f'qp{i}')
            assert pending == q
            row = next(r for r in rt.a.tables['AnswerConfig'] if r['QaID'] == q['questionId'])
            answer = rt.operate(1, 'LanternShowAnswerQuestion', {'activityId': 72046,
                'questionId': q['questionId'], 'answerIndex': row['RightAnswer'] - 1}, f'a{i}')
            assert answer['right']
        with pytest.raises(UnresolvedEconomy), e.transaction():
            rt.operate(1, 'LanternShowAnswerQuestion', {'activityId': 72046,
                'questionId': q['questionId'], 'answerIndex': row['RightAnswer'] - 1}, f'ax{i}')
    with e.transaction():
        result = rt.operate(1, 'LanternShowRecBox', {'activityId': 72046, 'boxIndex': 0}, 'b')
        assert result['receivedBoxs'] == [0]
        paper = rt.operate(1, 'LanternShowPaper', {'activityId': 72047}, 'p')
        assert ACTIVITY_SCHEMAS['AccountBuffData'].decode(paper['buffData'])['buffId'] in rt.buff_rows
    with pytest.raises(UnresolvedEconomy), e.transaction():
        rt.operate(1, 'LanternShowRecBox', {'activityId': 72046, 'boxIndex': 0}, 'b2')


def test_pool_transaction_receipts_and_invalid_offer_no_charge(runtime):
    store, e, ctx, rt, now = runtime
    box = rt.a.boxes[923]
    seed(rt, {box['CostID']: box['CostNum'] * 5})
    p = packet({'activityId': 72042, 'rewardPoolId': 923, 'drawCount': 1}, name='C2L_ActivityRewardPoolDraw')
    response = asyncio.run(rt.handle(ctx, p))
    assert response.values['code'] == 10
    balance = store.get(1)
    assert asyncio.run(rt.handle(ctx, p)).values == response.values
    assert store.get(1) == balance
    with pytest.raises(UnresolvedEconomy), e.transaction():
        rt.operate(1, 'ActivityRewardPoolDraw', {'activityId': 72042, 'rewardPoolId': 927, 'drawCount': 1}, 'locked')
    assert store.get(1) == balance


def test_extra_daily_cap_period_binding_and_ordinary_stage_isolation(runtime):
    store, e, ctx, rt, now = runtime
    with e.transaction():
        assert rt.extra_rewards(1, 'ordinary', 2110801, {1237901: 100}) == {}
        for i in range(6):
            rt.r.bind_run(1, 2161121, f'x{i}')
            result = rt.extra_rewards(1, f'x{i}', 2161121, {})
            if i < 3:
                assert result[1203021] == 1
            else:
                assert 1203021 not in result
            if i < 5:
                assert result[1290333] == 1
            else:
                assert 1290333 not in result
    now[0] += 86400
    with e.transaction():
        rt.r.bind_run(1, 2161121, 'next-day')
        assert rt.extra_rewards(1, 'next-day', 2161121, {})[1290333] == 1


def test_daily_mail_idempotent_reset_and_active_catalog(runtime):
    store, e, ctx, rt, now = runtime
    rt.deliver_daily_mail(1)
    rt.deliver_daily_mail(1)
    assert store.db.execute('SELECT count(*) FROM player_mail').fetchone()[0] == 2
    rows = rt.a.query_activity(1)['activityData']
    assert all(ACTIVITY_SCHEMAS['ActivityData'].decode(r)['activityGroup'] == 37 for r in rows)
    now[0] += 86400
    rt.deliver_daily_mail(1)
    assert store.db.execute('SELECT count(*) FROM player_mail').fetchone()[0] == 4


def test_login_activity_queries_encode_all_responses_and_extra_drop_860(runtime):
    from x2server.messages.core import CORE_SCHEMAS
    from x2server.protocol.registry import CORE_MESSAGE_REGISTRY
    _, _, ctx, rt, _ = runtime
    assert CORE_MESSAGE_REGISTRY.name_for(860) == 'C2L_ExtraDropData'
    requests = [('ActivityPassRecord', {}), ('ExtraDropData', {}),
                ('QueryActivityMissionRecord', {}), ('CafeStoreInfo', {}),
                ('ActivityMissionData', {'activityId': 72041}),
                ('ActivityRewardPoolInfo', {'activityId': 72042}),
                ('LanternShowQueryData', {'activityId': 72046})]
    for seq, (name, values) in enumerate(requests, 800):
        result = asyncio.run(rt.handle(ctx, packet(values, seq, 'C2L_' + name)))
        assert result.values.get('code', 10) == (13 if name == 'QueryActivityMissionRecord' else 10)
        assert not result.before_response and not result.pushes
        for message in (*result.before_response, result, *result.pushes):
            CORE_SCHEMAS[message.message_name].encode(message.values)
    denied = asyncio.run(rt.handle(ctx, packet({'activityId': 1, 'questionId': 1, 'answerIndex': 0}, 900,
        'C2L_LanternShowAnswerQuestion')))
    assert denied.values['code'] == 13
    CORE_SCHEMAS[denied.message_name].encode(denied.values)


def test_godsoon_empty_state_has_no_fake_buff_and_queries_do_not_reload_player(runtime):
    from x2server.messages.core import CORE_SCHEMAS
    _, _, ctx, rt, _ = runtime
    for seq, operation in enumerate(('AccountBuffData', 'AccountBuffAutoStop'), 910):
        response = asyncio.run(rt.handle(ctx, packet({}, seq, 'C2L_' + operation)))
        wire = CORE_SCHEMAS[response.message_name].decode(CORE_SCHEMAS[response.message_name].encode(response.values))
        assert wire.get('buffData', []) == []
        assert not response.before_response


def test_activity_initialization_uses_wire_activity_id_and_one_based_branch(runtime):
    _, e, ctx, rt, _ = runtime
    e.activity = rt.a
    initial = rt.a.mission_values(1, 72041)
    assert initial['branch'] == 1
    selected = asyncio.run(rt.handle(ctx, packet({'activityId': 72041, 'branch': 1},
        920, 'C2L_ActivityMissionSelBranch')))
    assert selected.values['code'] == 10
    assert not selected.before_response
    rejected = asyncio.run(rt.handle(ctx, packet({'activityId': 72041, 'branch': 0},
        921, 'C2L_ActivityMissionSelBranch')))
    assert rejected.values['code'] == 13
    result = asyncio.run(e.handle(ctx, packet({'type': 9, 'extraType': 72041},
        922, 'C2L_GameTask')))
    assert result.values['activityId'] == 72041
    assert result.values == rt.a.task_values(1, 9, 72041)


def test_first_theme_all_sections_enter_settle_replay_with_real_rewards(runtime):
    from x2server.player.battle import BattleService
    from x2server.messages.battle import CHECKOUT, PROFILE_HERO
    store, e, ctx, rt, now = runtime
    e.activity = rt.a
    battle = BattleService(store, e)
    p = store.get(1)
    store.save_snapshot(1, {**p['snapshot'], 'mobility': {'power': 10000}}, p['revision'])
    obtained = {}
    for idx, sid in enumerate(rt.r.at().theme['section_ids']):
        row = battle.catalog.sections[sid]
        hero = (next(h for h in row['AssistParam'] if h > 0)
                if row.get('AssistType', {}).get('value') == 1 else 1003)
        entry = asyncio.run(battle.enter(ctx, packet({'missionId': sid, 'chapter': row['ChapterID'],
            'sceneId': row['Maps'][0], 'heros': [PROFILE_HERO.encode({'heroId': hero, 'leader': 1})]}, 100 + idx)))
        assert entry.values['result'] == 10, (sid, entry.values)
        checkout = packet({'checkout': CHECKOUT.encode({'chapterId': row['ChapterID'],
            'sectionId': sid, 'success': True, 'fightTime': 200})}, 200 + idx, name='C2L_CheckoutMainMissionSign')
        result = asyncio.run(battle.checkout(ctx, checkout))
        assert result.values['result'] == 10, (sid, result.values)
        assert rt.r.get(1, rt.r.at(), 'clear', sid) == 1
        assert asyncio.run(battle.checkout(ctx, checkout)).values == result.values
        assert rt.r.get(1, rt.r.at(), 'clear', sid) == 1
        for item, num in rewards(result.values['rewardData']).items():
            obtained[item] = obtained.get(item, 0) + num
    assert obtained[1290301] > 0  # First story unlocks the food business.
    assert obtained[1290333] == 5  # Shared daily extra-drop cap.
    assert all(rt.r.get(1, rt.r.at(), 'obtained-item', item) == count for item, count in obtained.items())
    assert not store.db.execute('SELECT 1 FROM battle_unresolved_rewards WHERE reward_group>0').fetchone()


@pytest.mark.parametrize('theme_index', range(7))
def test_all_activity_sections_enter_and_settle_in_their_period(runtime, theme_index):
    from x2server.player.battle import BattleService
    from x2server.messages.battle import CHECKOUT, PROFILE_HERO, FIGHT_PROFILE
    store, e, ctx, rt, now = runtime
    now[0] = activity_start(theme_index) + 3600
    e.activity = rt.a
    battle = BattleService(store, e)
    state = store.get(1)
    store.save_snapshot(1, {**state['snapshot'], 'mobility': {'power': 100000}}, state['revision'])
    period = rt.r.at()
    pending = set(period.theme['section_ids'])
    count = 0
    while pending:
        progressed = False
        for sid in sorted(pending):
            row = battle.catalog.sections[sid]
            predecessor = row.get('OpenParam') if row.get('OpenType', {}).get('value') == 2 else 0
            if predecessor in pending:
                continue
            hero = (next(h for h in row['AssistParam'] if h > 0)
                    if row.get('AssistType', {}).get('value') == 1 else 1003)
            entry = asyncio.run(battle.enter(ctx, packet({'missionId': sid, 'chapter': row['ChapterID'],
                'sceneId': row['Maps'][0], 'heros': [PROFILE_HERO.encode({'heroId': hero, 'leader': 1})]}, 10000 + count)))
            assert entry.values['result'] == 10, (period.theme['title'], sid, entry.values)
            assert FIGHT_PROFILE.decode(entry.values['fightDataProfile'])['sceneId'] == row['Maps'][0]
            checkout = packet({'checkout': CHECKOUT.encode({'chapterId': row['ChapterID'],
                'sectionId': sid, 'success': True, 'fightTime': 200})}, 20000 + count, name='C2L_CheckoutMainMissionSign')
            result = asyncio.run(battle.checkout(ctx, checkout))
            assert result.values['result'] == 10, (period.theme['title'], sid, result.values)
            updates = {p.message_name: p for p in result.before_response}
            assert ('L2C_QueryActivityMissionRecord' in updates) == (period.theme['group'] == 99)
            assert 'L2C_SceneGlobalParam' in updates
            assert 'L2C_ActivityPassRecord' in updates
            pairs = [ACTIVITY_SCHEMAS['KeyValuePair_Int32_Int32'].decode(raw)
                     for raw in updates['L2C_ActivityPassRecord'].values['missionPassCount']]
            assert next(p['Value'] for p in pairs if p['Key'] == sid) == 1
            if period.theme['group'] == 7:
                assert 'L2C_QueryShuangHanActivity' in updates
            for push in result.before_response:
                if push.message_name in ACTIVITY_SCHEMAS:
                    ACTIVITY_SCHEMAS[push.message_name].encode(push.values)
            assert rt.r.get(1, period, 'clear', sid) == 1
            assert asyncio.run(battle.checkout(ctx, checkout)).values == result.values
            assert rt.r.get(1, period, 'clear', sid) == 1
            pending.remove(sid)
            count += 1
            progressed = True
        assert progressed, (period.theme['title'], sorted(pending))


@pytest.mark.parametrize('theme_index,section', [(0, 2161190), (5, 2160400)])
@pytest.mark.parametrize('wire_hero', [1303, 1003])
def test_nian_feast_trial_entry_checkout_and_replay(runtime, theme_index, section, wire_hero):
    from x2server.player.battle import BattleService
    from x2server.messages.battle import CHECKOUT, PROFILE_HERO, FIGHT_DATA, FIGHT_HERO, BATTLE_SCHEMAS
    store, economy, context, rt, now = runtime
    now[0] = activity_start(theme_index) + 3600
    economy.activity = rt.a
    battle = BattleService(store, economy)
    player = store.get(1)
    store.save_snapshot(1, {**player['snapshot'], 'heroes': []}, player['revision'])
    before = store.get(1)['snapshot']
    row = battle.catalog.sections[section]
    values = {'missionId': section, 'chapter': row['ChapterID'], 'sceneId': row['Maps'][0],
              'heros': [PROFILE_HERO.encode({'heroId': wire_hero, 'leader': 1})]}
    request = packet(values, 501)
    entry = asyncio.run(battle.enter(context, request))
    assert entry.values['result'] == 10
    fight = FIGHT_DATA.decode(entry.values['data'])
    hero = FIGHT_HERO.decode(fight['fightHeros'][0])
    assert (hero['id'], hero['level'], hero['star']) == (1303, 50, 15)
    assert hero['battleSkinId'] == 1220301
    replay = asyncio.run(battle.enter(context, request))
    assert BATTLE_SCHEMAS['L2C_FightData'].encode(replay.values) == BATTLE_SCHEMAS['L2C_FightData'].encode(entry.values)
    assert store.get(1)['snapshot']['heroes'] == before['heroes']
    for seq, invalid in enumerate((
            {**values, 'sceneId': row['Maps'][0] + 1},
            {**values, 'chapter': row['ChapterID'] + 1},
            {**values, 'heros': [PROFILE_HERO.encode({'heroId': 1004, 'leader': 1})]},
            {**values, 'heros': [PROFILE_HERO.encode({'heroId': hid, 'leader': 1})
                                 for hid in (1003, 1303)]}), 510):
        assert asyncio.run(battle.enter(context, packet(invalid, seq))).values['result'] == 13
    checkout = packet({'checkout': CHECKOUT.encode({'chapterId': row['ChapterID'],
        'sectionId': section, 'success': True, 'fightTime': 200})}, 502, 'C2L_CheckoutMainMissionSign')
    result = asyncio.run(battle.checkout(context, checkout))
    assert result.values['result'] == 10
    replay = asyncio.run(battle.checkout(context, checkout))
    assert BATTLE_SCHEMAS['L2C_CheckoutMainMission'].encode(replay.values) == BATTLE_SCHEMAS['L2C_CheckoutMainMission'].encode(result.values)
    assert rt.r.get(1, rt.r.at(), 'clear', section) == 1
    assert store.get(1)['snapshot']['heroes'] == []
    now[0] = rt.r.at().end
    assert asyncio.run(battle.enter(context, packet(values, 503))).values['result'] == 13
