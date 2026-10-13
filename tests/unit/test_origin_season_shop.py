import asyncio
import json
import pytest

from tests.unit.test_origin_season import env
from tests.unit.test_battle import packet
from x2server.messages.economy import GOODS
from x2server.messages.activity import ACTIVITY_SCHEMAS
from x2server.player.shop import ShopService
from x2server.player.season import SeasonService


def listing(service, ctx):
    return asyncio.run(service.handle(ctx, packet({'shopId': 898}, name='C2L_ShopGoods')))


def context():
    from x2server.network.dispatcher import DispatchContext
    from x2server.network.session import SessionState
    return DispatchContext('test', 'local', SessionState('test', 'shop', player_id=1))


def buy(service, ctx, gid, qty=1, rid=10):
    return asyncio.run(service.handle(ctx, packet({'shopId': 898, 'goodsId': gid, 'buyNum': qty}, rid, 'C2L_BuyGoods')))


def level(e, s, value):
    with e.transaction():
        state = s.state(1)
        state['exp'] = value * s.bp['LevelExp']
        s.write(1, state)


def test_origin_identity_activity_config_sections_and_ticket_all_match(env):
    _, _, s = env
    activities = [ACTIVITY_SCHEMAS['ActivityData'].decode(raw) for raw in s.activity_values()]
    assert {x['actId'] for x in activities} == {74001, 74002}
    assert all(x['activityGroup'] == 16 for x in activities)
    assert next(x for x in activities if x['actType'] == 55)['param1'] == [10000]
    assert next(x for x in activities if x['actType'] == 56)['param1'] == [898]
    assert all(74001 in r['SeasonID'] and r['ConsumeItem'] == 1202901 for r in s.configs.values())


def test_foreign_season_page_id_in_old_state_is_normalized(env):
    _, e, s = env
    with e.transaction():
        state = s.state(1)
        state.update(last_config=2092001, max_layer=3, shop_counts={'1970101': 2})
        s.write(1, state)
    normalized = s.state(1)
    assert normalized['last_config'] == 2090004
    assert normalized['shop_counts'] == {'1970101': 2}
    assert s.mission_values(1)['lastSeasonId'] in s.configs


@pytest.mark.parametrize('current,count', [(0, 9), (19, 9), (20, 20), (39, 20), (40, 31), (59, 31), (60, 42), (79, 42), (80, 53)])
def test_all_five_shop_level_gates_and_direct_buy_gates(env, current, count):
    store, e, s = env
    ctx = context()
    service = ShopService(store, e)
    level(e, s, current)
    rows = [GOODS.decode(raw) for raw in listing(service, ctx).values['goods']]
    assert len(rows) == count
    with store.db:
        store.db.execute('INSERT INTO inventory VALUES (1,1237998,10000)')
    for stage in range(1, 6):
        row = next(r for r in s.shop.goods.values() if r['stage'] == stage)
        response = buy(service, ctx, row['goodsId'], rid=20 + stage)
        assert response.values['code'] == (10 if current >= row['unlockLevel'] else 13)


def test_every_offer_exact_quantity_currency_price_stock_and_replay(env):
    store, e, s = env
    ctx = context()
    service = ShopService(store, e)
    level(e, s, 80)
    with store.db:
        store.db.execute('INSERT INTO inventory VALUES (1,1237998,1000000)')
    for index, row in enumerate(s.shop.goods.values()):
        result = buy(service, ctx, row['goodsId'], qty=row['canBuyTimes'], rid=100 + index)
        assert result.values['code'] == 10, (row, result.values)
        assert result.values['itemNum'] == row['num'] * row['canBuyTimes']
        balance = store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237998').fetchone()[0]
        assert buy(service, ctx, row['goodsId'], qty=row['canBuyTimes'], rid=100 + index).values == result.values
        assert buy(service, ctx, row['goodsId'], rid=200 + index).values['code'] == 13
        assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237998').fetchone()[0] == balance
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1206036').fetchone()[0] == 14


def test_unfunded_locked_overlimit_and_wrong_shop_do_not_mutate(env):
    store, e, s = env
    service, ctx = ShopService(store, e), context()
    before = store.get(1)
    for gid, qty in [(1970101, 1), (1970101, 11), (1971101, 1), (1970101, 0), (1970101, -1)]:
        assert buy(service, ctx, gid, qty).values['code'] == 13
    result = asyncio.run(service.handle(ctx, packet({'shopId': 801, 'goodsId': 1970101, 'buyNum': 1}, 77, 'C2L_BuyGoods')))
    assert result.values['code'] == 13
    assert store.get(1) == before
    assert not s.state(1).get('shop_counts')
    assert store.db.execute("SELECT count(*) FROM season_receipts WHERE message='L2C_BuyGoods'").fetchone()[0] == 0


def test_failed_delivery_rolls_back_debit_stock_and_receipt(env, monkeypatch):
    store, e, s = env
    service, ctx = ShopService(store, e), context()
    with store.db:
        store.db.execute('INSERT INTO inventory VALUES (1,1237998,100)')
    def fail(*args, **kwargs):
        raise RuntimeError('injected delivery failure')
    monkeypatch.setattr(e, '_grant', fail)
    with pytest.raises(RuntimeError, match='injected'):
        buy(service, ctx, 1970101)
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237998').fetchone()[0] == 100
    assert not s.state(1).get('shop_counts')
    assert store.db.execute("SELECT count(*) FROM season_receipts WHERE message='L2C_BuyGoods'").fetchone()[0] == 0


def test_quota_survives_week_and_restart_new_instance_resets(env):
    store, e, s = env
    service, ctx = ShopService(store, e), context()
    with store.db:
        store.db.execute('INSERT INTO inventory VALUES (1,1237998,10000)')
    assert buy(service, ctx, 1970101, 10).values['code'] == 10
    now = int(e.clock())
    e.clock = lambda: now + 86400 * 7
    assert buy(service, ctx, 1970101, rid=11).values['code'] == 13
    e.season = SeasonService(e, enabled=True, instance=s.instance)
    assert buy(ShopService(store, e), ctx, 1970101, rid=12).values['code'] == 13
    e.season = SeasonService(e, enabled=True, instance='origin-review-next')
    assert buy(ShopService(store, e), ctx, 1970101, rid=13).values['code'] == 10
