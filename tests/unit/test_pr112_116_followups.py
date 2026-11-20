"""Cross-boundary quotas and real pool/cafe delivery after PR112-116."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from tests.activity_calendar_helpers import activity_start
from tests.unit.test_activity_runtime import runtime, seed
from tests.unit.test_economy import env
from tests.unit.test_battle import packet
from tests.unit.test_restored_shops_favor import buy, fund, listing
from x2server.messages.economy import REWARD
from x2server.messages.equipment import HERO_EQUIP
from x2server.player.activity_cafe import ActivityCafe
from x2server.player.shop import ShopService


def held(store, item):
    row = store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?', (item,)).fetchone()
    return row[0] if row else 0


def prepare_pool(rt, now):
    now[0] = activity_start(5) + 3600
    row = rt.r.of_type(26)
    period = rt.r.at()
    with rt.e.transaction():
        for bid in row['ActivityParam1'][:-1]:
            box = rt.a.boxes[bid]
            rt.r.put(1, period, 'pool', bid,
                     {str(gid): n for gid, n in zip(box['UnlockGroupID'], box['UnlockGroupTimes'])})
    assert 904 in rt.a.unlocked_pools(1, period, row)
    box = rt.a.boxes[904]
    seed(rt, {box['CostID']: box['CostNum'] * 100})
    return row, box


def test_all_eighteen_pool_receipts_deliver_stars_parts_and_replay(runtime):
    store, e, ctx, rt, now = runtime
    row, box = prepare_pool(rt, now)
    receipts = [g for g in box['GoodsGroupId'] if rt.a.box_goods[g]['ItemID'] in e.receipt_stars]
    assert len(receipts) == 18
    for index, gid in enumerate(receipts):
        good = rt.a.box_goods[gid]
        item = good['ItemID']
        # Force an actual shelf outcome while retaining its original receipt and Gift.
        box.update(GoodsGroupId=[gid], GroupProbability=[1])
        p = packet({'activityId': row['ActivityID'], 'rewardPoolId': 904, 'drawCount': 1},
                   3000 + index, 'C2L_ActivityRewardPoolDraw')
        before = held(store, box['CostID'])
        result = asyncio.run(rt.handle(ctx, p))
        assert result.values['code'] == 10
        reward = REWARD.decode(result.values['rewardData'])
        equips = [HERO_EQUIP.decode(raw) for raw in reward.get('rewardEquip', [])]
        assert len(equips) == good['ItemNum']
        assert {q['star'] for q in equips} == {e.receipt_stars[item]}
        parts = {part for group in e.auto_used_items[item] for part, _ in e.gift_contents[str(group)]['items']}
        assert {q['typeId'] for q in equips} <= parts
        assert held(store, item) == 0
        assert held(store, box['CostID']) == before - box['CostNum']
        pushes = [m for m in result.before_response if m.message_name == 'L2C_EquipUpdate']
        assert len(pushes) == 1 and pushes[0].values['equip'] == reward['rewardEquip']
        count = store.db.execute('SELECT COUNT(*) FROM equipment_instances WHERE player_id=1').fetchone()[0]
        assert asyncio.run(rt.handle(ctx, p)).values == result.values
        assert store.db.execute('SELECT COUNT(*) FROM equipment_instances WHERE player_id=1').fetchone()[0] == count
        assert held(store, box['CostID']) == before - box['CostNum']


def test_pool_equipment_failure_rolls_back_cost_stock_receipt_and_instances(runtime, monkeypatch):
    store, e, ctx, rt, now = runtime
    row, box = prepare_pool(rt, now)
    gid = next(g for g in box['GoodsGroupId'] if rt.a.box_goods[g]['ItemID'] == 1243181)
    box.update(GoodsGroupId=[gid], GroupProbability=[1])
    before = held(store, box['CostID'])
    original = e.materialize_equipment
    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise ValueError('forced instance delivery failure')
    monkeypatch.setattr(e, 'materialize_equipment', fail)
    p = packet({'activityId': row['ActivityID'], 'rewardPoolId': 904, 'drawCount': 1},
               3100, 'C2L_ActivityRewardPoolDraw')
    assert asyncio.run(rt.handle(ctx, p)).values['code'] == 13
    assert held(store, box['CostID']) == before
    if store.db.execute("SELECT 1 FROM sqlite_master WHERE name='equipment_instances'").fetchone():
        assert not store.db.execute('SELECT 1 FROM equipment_instances').fetchone()
    assert rt.r.get(1, rt.r.at(), 'pool', 904, {}) == {}
    monkeypatch.setattr(e, 'materialize_equipment', original)
    assert asyncio.run(rt.handle(ctx, p)).values['code'] == 10


def test_historical_pool_receipts_are_repaired_once(env):
    store, e, _ = env
    receipts = {item: 2 for item in e.receipt_stars if 1241000 < item < 1244000}
    assert len(receipts) == 18
    with store.db:
        store.db.executemany('INSERT INTO inventory VALUES (1,?,?)', receipts.items())
    e.login_event(1)
    assert all(held(store, item) == 0 for item in receipts)
    assert dict(store.db.execute('SELECT star,COUNT(*) FROM equipment_instances GROUP BY star')) == {4:12, 5:12, 6:12}
    e.login_event(1)
    assert store.db.execute('SELECT COUNT(*) FROM equipment_instances').fetchone()[0] == 36


@pytest.mark.parametrize('kind', [3, 4, 5])
def test_legacy_staff_bonuses_affect_actual_cooking_queue(runtime, kind):
    _, e, ctx, rt, now = runtime
    now[0] = activity_start(5) + 3600
    buff = next(r for r in rt.cafe.buffs if r['EffectType']['value'] == kind and r['EffectParam2'][0] in (1,2,3))
    shop = buff['EffectParam2'][0]
    period, food, state = rt.cafe.context(1, shop)
    state.update(unlocked=True, employees={'1':1003, str(buff['EffectParam1']):buff['UnitID']})
    with e.transaction():
        rt.cafe.save(1, period, shop, state)
    recipe = next(r for r in rt.cafe.recipes.values() if set(r['ItemGroup']).issubset(food['ActivityParam2']))
    seed(rt, {recipe['UnlockItem']:1, **dict(zip(recipe['ItemGroup'], recipe['ItemNum']))})
    assert rt.cafe.buff(shop, state, kind) == buff['EffectParam4']
    response = asyncio.run(rt.handle(ctx, packet({'storeType':shop, 'recipeID':recipe['RecipeID']},
                                               3200, 'C2L_CafeStoreCooking')))
    assert response.values['code'] == 10
    q = rt.cafe.context(1, shop)[2]['queues'][0]
    config = rt.cafe.levels[shop,1]
    assert q['end']-q['start'] == max(1, recipe['WaitTimes'] * max(100,1000-rt.cafe.buff(shop,state,5))//1000)
    assert q['revenue'] == recipe['SellPrice']*(1000+config.get('CafeSellAdd',0)+rt.cafe.buff(shop,state,3))//1000
    assert q['exp'] == recipe['CafeExp']*(1000+rt.cafe.buff(shop,state,4))//1000
    now[0] = q['end']
    settled = rt.cafe.values(1, shop)
    assert settled['exp'] == q['exp'] and settled['revenue'] == q['revenue']


def test_future_active_cafe_rows_do_not_double_legacy_buffs(runtime):
    _, _, _, rt, _ = runtime
    row = next(r for r in rt.cafe.buffs if r['ID'] == 1001)
    # A future exporter restores the row under its original old-client ID.
    active = dict(row, ID=1, EffectParam4=125)
    rt.a.tables['NewYearCafeBuff'].append(active)
    restored = ActivityCafe(rt.a)
    state = {'employees':{str(row['EffectParam1']):row['UnitID']}}
    assert restored.buff(row['EffectParam2'][0], state, row['EffectType']['value']) == 125


@pytest.mark.parametrize('shop,gid,currency,cap', [(806,1915001,1237905,1), (805,1906402,1237915,5), (802,1903404,1237917,1)])
def test_new_quotas_reset_exactly_at_beijing_boundary_and_retry_is_not_new_purchase(env, shop, gid, currency, cap):
    store, e, ctx = env
    now = [int(datetime(2026,11,30,23,59,59,tzinfo=timezone(timedelta(hours=8))).timestamp())]
    e.clock = lambda: now[0]
    service = ShopService(store,e)
    fund(store,currency,100000)
    if shop == 806:
        assert service._next_refresh(shop) == now[0] + 1
    first = buy(service,ctx,shop,gid,quantity=cap,rid=3300)
    assert first.values['code'] == 10
    balance = held(store,currency)
    assert buy(service,ctx,shop,gid,rid=3301).values['code'] == 13
    now[0] += 1
    restarted = ShopService(store,e)
    assert next(g for g in listing(restarted,ctx,shop) if g['goodsId']==gid)['hasBuyTimes'] == 0
    assert buy(restarted,ctx,shop,gid,quantity=cap,rid=3300).values == first.values
    assert held(store,currency) == balance
    assert buy(restarted,ctx,shop,gid,quantity=cap,rid=3302).values['code'] == 10
