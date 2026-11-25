from datetime import datetime, timedelta, timezone

from tests.unit.test_economy import env
from tests.unit.test_restored_shops_favor import listing, buy, fund
from x2server.player.shop import ShopService

TZ = timezone(timedelta(hours=8))


def test_daily_tracks_delivery_limits_replay_and_midnight(env):
    store, economy, ctx = env
    now = [int(datetime(2026, 10, 18, 23, 59, tzinfo=TZ).timestamp())]
    economy.clock = lambda: now[0]
    service = ShopService(store, economy)
    fund(store, 1237927, 100000)
    goods = listing(service, ctx, 810)
    track_slots = {1918101, 1918301, 1918401, 1918501}
    tracks = [g for g in goods if g['goodsId'] in track_slots]
    research = [g for g in goods if g['goodsId'] not in track_slots and g['itemId'] != 1206000]
    assert len(goods) == 12 and len(tracks) == 4 and len(research) == 7
    assert len({g['itemId'] for g in tracks}) == 4
    assert all(g['itemId'] in service.divine_track_pool for g in tracks)
    assert all(g['price'] == 270 and g['num'] == 1 and g['limited'] == 3 for g in tracks)
    assert all(g['canBuyTimes'] == 10 for g in tracks)
    assert {g['goodsId']: g['itemId'] for g in research} == {
        1918701: 1202086, 1918801: 1202087, 1918901: 1202088, 1919001: 1202089,
        1919101: 1237807, 1919201: 1237808, 1918402: 1237809,
    }
    assert all(g['num'] == 1 and g['limited'] == 3 for g in research)
    assert next(g for g in goods if g['itemId'] == 1206000)['canBuyTimes'] == 2
    assert listing(ShopService(store, economy), ctx, 810) == goods
    assert service._next_refresh(810) == now[0] + 60
    for i, good in enumerate(goods):
        limit = good['canBuyTimes']
        result = buy(service, ctx, 810, good['goodsId'], limit, rid=1000+i)
        assert result.values['code'] == 10
        assert result.values['itemId'] == good['itemId']
        assert result.values['itemNum'] == limit
        assert buy(service, ctx, 810, good['goodsId'], limit, rid=1000+i).values == result.values
        before = store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237927').fetchone()[0]
        assert buy(service, ctx, 810, good['goodsId'], rid=2000+i).values['code'] == 13
        assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237927').fetchone()[0] == before
        assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?', (good['itemId'],)).fetchone()[0] == limit
    assert all(g['hasBuyTimes'] == g['canBuyTimes'] for g in listing(service, ctx, 810))
    now[0] += 60
    refreshed = listing(service, ctx, 810)
    assert all(g['hasBuyTimes'] == 0 for g in refreshed)
    assert [g['itemId'] for g in refreshed] != [g['itemId'] for g in goods]
    assert buy(service, ctx, 810, 1918201, 2, rid=3000).values['code'] == 10


def test_ticket_shop_research_items_listed_and_delivered(env):
    store, economy, ctx = env
    service = ShopService(store, economy)
    fund(store, 1237915, 10000)
    expected = {1905107: 1206000, 1906403: 1237807, 1906404: 1237808, 1906405: 1237809,
                1906406: 1202086, 1906407: 1202087, 1906408: 1202088, 1906409: 1202089}
    goods = {g['goodsId']: g for g in listing(service, ctx, 805)}
    for goods_id, item_id in expected.items():
        assert goods[goods_id]['itemId'] == item_id
        assert goods[goods_id]['price'] == (200 if goods_id == 1905107 else 8)
        result = buy(service, ctx, 805, goods_id, rid=6000 + goods_id % 1000)
        assert result.values['code'] == 10 and result.values['itemId'] == item_id
        assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?',
                                (item_id,)).fetchone()[0] == 1


def test_ticket_rounds_reset_monday(env):
    store, economy, ctx = env
    now = [int(datetime(2026, 10, 18, 23, 59, tzinfo=TZ).timestamp())]
    economy.clock = lambda: now[0]
    service = ShopService(store, economy)
    fund(store, 1237915, 1000)
    for i in range(5):
        assert buy(service, ctx, 805, 1905301+i, rid=4000+i).values['code'] == 10
    assert next(g for g in listing(service, ctx, 805) if g['goodsId'] == 1905305)['hasBuyTimes'] == 1
    now[0] += 60
    rounds = [g for g in listing(service, ctx, 805) if 1905301 <= g['goodsId'] <= 1905305]
    assert len(rounds) == 1 and rounds[0]['goodsId'] == 1905301 and rounds[0]['hasBuyTimes'] == 0
    assert buy(service, ctx, 805, 1905301, rid=5000).values['code'] == 10
