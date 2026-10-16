import asyncio
import pytest
from tests.unit.test_economy import env
from tests.unit.test_activity_runtime import runtime
from tests.unit.test_battle import packet
from tests.unit.test_restored_shops_favor import listing, buy, fund
from tests.activity_calendar_helpers import activity_start, next_activity_cycle
from x2server.player.shop import ShopService
from x2server.player.wish import WishService
from x2server.player.server_clock import ServerClock


def test_club_shelves_all_deliver_and_limits(env):
    store, e, ctx = env
    service = ShopService(store, e)
    fund(store, 1237924, 1000000)
    # Existing purchases of the old placeholder goods must not mark the new
    # cosmetic/6-star-box sold out, and the new quotas still persist normally.
    with store.db:
        for gid, period in [(1916101,'lifetime'),(1915101,service._period(2)),(1915301,service._period(2))]:
            store.db.execute('INSERT INTO shop_compat_counts VALUES (1,807,?,?,?)',(gid,period,2))
    goods = listing(service, ctx, 807)
    assert len(goods) == 29
    assert all(g['hasBuyTimes']==0 for g in goods if g['goodsId'] in (1916101,1915101))
    assert next(g for g in goods if g['goodsId']==1915301)['hasBuyTimes']==2
    for index, good in enumerate(goods):
        result = buy(service, ctx, 807, good['goodsId'], rid=8000+index)
        assert result.values['code'] == 10, good
        assert result.values['itemNum'] == good['num']
    for gid in (1916201, 1916301, 1916401, 1917801):
        assert buy(service, ctx, 807, gid, rid=9000+gid).values['code'] == 13
    # 价格与客户端 ShopGoodsGroup.ItemPrice 绑死在货位号上: 151 表价 50 ->
    # 迷你礼物盒, 154 表价 1200 -> 6★随机兽主, 否则客户端按表价准备扣费、
    # 服务端按高价校验失败回 13 而客户端静默忽略 (「兑换了但东西没发」)。
    assert next(g for g in goods if g['goodsId'] == 1915101)['itemId'] == 1203001
    assert next(g for g in goods if g['goodsId'] == 1915401)['itemId'] == 1203023
    assert next(g for g in goods if g['goodsId'] == 1916101)['canBuyTimes'] == 1
    assert buy(service, ctx, 807, 1916101, rid=9999).values['code'] == 13


def test_featured_pity_pool_isolation_and_live_legacy_import(env):
    store, e, _ = env
    wish = WishService(store, e)
    with store.db:
        store.db.execute("INSERT OR REPLACE INTO wish_pity VALUES (1,'limited',5,33,99)")
        for pool, count in [(22401,69),(22204,20),(22402,10),(22202,100)]:
            store.db.execute('INSERT INTO wish_state(player_id,pool_id,since_featured) VALUES (1,?,?)',(pool,count))
    # Simulates replacing wish tables via save import after service construction.
    assert wish.state(1,22401)[-1] == 60
    assert wish.state(1,22204)[-1] == 20
    assert wish.state(1,22402)[-1] == 10
    assert wish.state(1,22202)[-1] == 0
    assert wish.state(1,22401)[3:5] == (5,33)
    again = WishService(store,e)
    assert again.state(1,22401)[-1] == 60
    assert store.db.execute('SELECT since_featured FROM wish_state WHERE pool_id=22401').fetchone()[0] == 60
    assert again.state(1,22204)[-1] == 20


@pytest.mark.parametrize('theme',[0,5])
def test_food_boxes_use_currency_threshold_and_replay(runtime,theme):
    store, e, ctx, rt, now = runtime
    now[0] = activity_start(theme) + 3600
    period = rt.a.period(1)
    row = rt.r.of_type(29, period)
    assert row
    aid = row['ActivityID']
    currency = row['ActivityParam2'][0]
    thresholds = row['ActivityParam4']
    assert thresholds
    for index, threshold in enumerate(thresholds):
        fund(store, currency, threshold-1)
        req = {'activityId':aid,'scoreCount':threshold}
        assert asyncio.run(rt.handle(ctx,packet(req,100+index,'C2L_ReceiveFoodMissionReward'))).values['code'] == 13
        fund(store,currency,threshold)
        result = asyncio.run(rt.handle(ctx,packet(req,200+index,'C2L_ReceiveFoodMissionReward')))
        assert result.values['code'] == 10
        assert result.values['scoreCount'] == threshold
        assert result.values['receivedList'] == thresholds[:index+1]
        assert asyncio.run(rt.handle(ctx,packet(req,200+index,'C2L_ReceiveFoodMissionReward'))).values == result.values
        assert asyncio.run(rt.handle(ctx,packet(req,300+index,'C2L_ReceiveFoodMissionReward'))).values['code'] == 13
    assert asyncio.run(rt.handle(ctx,packet({'activityId':aid,'scoreCount':0},900,'C2L_ReceiveFoodMissionReward'))).values['code'] == 13
    now[0] = next_activity_cycle(now[0])
    fresh = asyncio.run(rt.handle(ctx,packet({'activityId':aid},1000,'C2L_QueryFoodMissionReward')))
    assert fresh.values['code'] == 10 and fresh.values['receivedList'] == [0]
    fund(store,currency,thresholds[0])
    assert asyncio.run(rt.handle(ctx,packet({'activityId':aid,'scoreCount':thresholds[0]},1200,'C2L_ReceiveFoodMissionReward'))).values['code'] == 10
