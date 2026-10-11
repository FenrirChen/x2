"""All supplied exchange rows must deliver, charge and cap atomically."""
import pytest
import asyncio

from tests.unit.test_economy import env, rewards
from tests.unit.test_activity_rotation import activity
from x2server.player.activity_exchange import ActivityExchange
from x2server.player.activity_rotation import ActivityRotation
from x2server.player.economy import UnresolvedEconomy
from x2server.messages.activity import ACTIVITY_SCHEMAS
from x2server.messages.economy import ECONOMY_SCHEMAS
from tests.unit.test_battle import packet


def open_shop(service, economy, shop, period):
    rule = shop['unlock']
    with economy.transaction():
        if rule['kind'] == 'period_item':
            service.obtained(1, period, {i: 1 for i in rule['items']}, f'test:unlock:{shop["shopId"]}')
        elif rule['kind'] == 'memory_count':
            service.obtained(1, period, {1290100 + i: 1 for i in range(1, rule['count'] + 1)}, f'test:unlock:{shop["shopId"]}')
        elif rule['kind'] == 'chapter_pass':
            for sid in service.chapters[rule['chapter']]['SectionID']:
                service.rotation.put(1, period, 'clear', sid, 1)


@pytest.mark.parametrize('group', [7, 33, 13, 99])
def test_all_stages_visible_before_unlock_but_purchase_gates_remain(activity, group):
    _, economy, service, now = activity
    exchange = ActivityExchange(service)
    index = next(i for i, theme in enumerate(service.rotation.themes) if theme['group'] == group)
    now[0] = ActivityRotation.ANCHOR + index * ActivityRotation.SECONDS
    period = service.period(1)
    family = 2 if group == 7 else 1 if group == 99 else 3
    result = exchange.activity_listing(1, family)
    ACTIVITY_SCHEMAS['L2C_ActivityShop'].encode(result)
    stages = sorted((s for s in exchange.shops.values() if s['group'] == group), key=lambda s: s['stage'])
    rows = [ACTIVITY_SCHEMAS['ActivityShopGoods'].decode(wire) for wire in result['goodsList']]
    assert [row['shopId'] for row in rows] == [s['shopId'] for s in stages]
    assert all(row['goods'] for row in rows)
    for shop in stages:
        if not exchange.unlocked(1, period, shop):
            with pytest.raises(UnresolvedEconomy, match='locked'):
                exchange.listing(1, shop['shopId'])
            offer = shop['goods'][0]
            with pytest.raises(UnresolvedEconomy, match='locked'):
                exchange.buy(1, shop['shopId'], offer['goodsId'], 1, f'locked:{shop["shopId"]}')
        open_shop(service, economy, shop, period)
        assert exchange.listing(1, shop['shopId'])['code'] == 10


@pytest.mark.parametrize('shop_id', [860, 861, 862, 871, 872, 873, 874, 876, 877, 878, 879, 887, 888, 889, 890])
def test_purchase_details_use_exact_wire_contract(activity, shop_id):
    _, economy, service, now = activity
    exchange = ActivityExchange(service)
    shop = exchange.shops[shop_id]
    index = next(i for i, theme in enumerate(service.rotation.themes) if theme['group'] == shop['group'])
    now[0] = ActivityRotation.ANCHOR + index * ActivityRotation.SECONDS
    period = service.period(1)
    open_shop(service, economy, shop, period)
    from x2server.network.dispatcher import DispatchContext
    from x2server.network.session import SessionState
    ctx = DispatchContext('shop-test', 'local', SessionState('shop-test', 'session', player_id=1))
    for offer in shop['goods']:
        request = {'goodsId': offer['goodsId']}
        result = asyncio.run(exchange.handle(ctx, packet(request, name='C2L_QueryGoodsInfo'),
                                             'C2L_QueryGoodsInfo', request))
        values = ECONOMY_SCHEMAS[result.message_name].decode(ECONOMY_SCHEMAS[result.message_name].encode(result.values))
        assert values['code'] == 10 and values['goodsId'] == offer['goodsId']
        assert values['shopId'] == shop_id and values['itemNum'] == offer['num']
        assert values['price'] == offer['price'] and values['currencyType'] == offer['currencyType']


@pytest.mark.parametrize('shop_id', [860, 861, 862, 871, 872, 873, 874, 876, 877, 878, 879, 887, 888, 889, 890])
def test_every_supplied_offer_delivers_and_period_stock_resets(activity, shop_id):
    store, economy, service, now = activity
    exchange = ActivityExchange(service)
    shop = exchange.shops[shop_id]
    index = next(i for i, t in enumerate(service.rotation.themes) if t['group'] == shop['group'])
    now[0] = ActivityRotation.ANCHOR + index * ActivityRotation.SECONDS
    period = service.period(1)
    open_shop(service, economy, shop, period)
    assert exchange.listing(1, shop_id)['code'] == 10
    currency = shop['goods'][0]['currencyItemId']
    with economy.transaction():
        economy._grant(1, 'test:currency', {currency: 10000000})
    for offer in shop['goods']:
        gid, item = offer['goodsId'], offer['itemId']
        before = store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?', (currency,)).fetchone()[0]
        result = exchange.buy(1, shop_id, gid, 1, f'test:{gid}')
        assert result['code'] == 10
        assert rewards(result['rewardData']) == {item: offer['num']}
        assert exchange.count(1, period, gid) == 1
        assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?', (currency,)).fetchone()[0] == before - offer['price']
        assert exchange.buy(1, shop_id, gid, 1, f'test:{gid}') == result
        assert exchange.count(1, period, gid) == 1
        with pytest.raises(UnresolvedEconomy, match='stock exhausted'):
            exchange.buy(1, shop_id, gid, offer['canBuyTimes'], f'over:{gid}')
    now[0] += 35 * 86400
    assert all(exchange.count(1, service.period(1), g['goodsId']) == 0 for g in shop['goods'])


def test_sakura_derived_stages_match_osiris_amount_and_stock(activity):
    _, _, service, _ = activity
    exchange = ActivityExchange(service)
    for stage in range(2, 5):
        sakura = exchange.shops[870 + stage]['goods']
        osiris = exchange.shops[875 + stage]['goods']
        assert len(sakura) == len(osiris)
        for actual, reference in zip(sakura, osiris):
            assert actual['num'] == reference['num']
            assert actual['canBuyTimes'] == reference['canBuyTimes']
            assert actual['price'] == max(1, reference['price'] * 5 // 9)
            assert actual['itemId'] == (1251170 if reference['itemId'] == 1251140 else reference['itemId'])


def test_insufficient_currency_and_failure_leave_no_purchase(activity, monkeypatch):
    store, economy, service, now = activity
    exchange = ActivityExchange(service)
    now[0] = ActivityRotation.ANCHOR + ActivityRotation.SECONDS
    offer = exchange.shops[871]['goods'][0]
    period = service.period(1)
    gid = offer['goodsId']
    with pytest.raises(UnresolvedEconomy, match='not enough'):
        exchange.buy(1, 871, gid, 1, 'no-money')
    assert exchange.count(1, period, gid) == 0
    with economy.transaction():
        economy._grant(1, 'test:currency', {1237978: 1000})
    def fail(*args, **kwargs):
        raise UnresolvedEconomy('test delivery failure')
    monkeypatch.setattr(economy, '_grant', fail)
    with pytest.raises(UnresolvedEconomy, match='delivery failure'):
        exchange.buy(1, 871, gid, 1, 'fail')
    assert exchange.count(1, period, gid) == 0
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237978').fetchone()[0] == 1000
    assert not store.db.execute("SELECT 1 FROM activity_receipts WHERE request_key='fail'").fetchone()


def test_locked_wrong_theme_and_mismatched_goods_rejected(activity):
    _, economy, service, now = activity
    exchange = ActivityExchange(service)
    now[0] = ActivityRotation.ANCHOR + ActivityRotation.SECONDS
    with pytest.raises(UnresolvedEconomy, match='locked'):
        exchange.listing(1, 872)
    with pytest.raises(UnresolvedEconomy, match='closed'):
        exchange.listing(1, 860)
    offer = exchange.shops[871]['goods'][0]
    with pytest.raises(UnresolvedEconomy, match='mismatched'):
        exchange.buy(1, 872, offer['goodsId'], 1, 'wrong-shop')


def test_winter_fallback_cost_and_moon_typo_use_unit_price(activity):
    _, _, service, _ = activity
    exchange = ActivityExchange(service)
    for sid in (860, 861, 862):
        row = exchange.shops[sid]['goods'][-1]
        assert (row['itemId'], row['num'], row['price'], row['currencyItemId']) == (1237901, 1000, 10, 1237985)
    mini = next(g for g in exchange.shops[890]['goods'] if g['itemId'] == 1203001)
    assert mini['price'] == 60 and mini['canBuyTimes'] == 10
    refresh = next(g for g in exchange.shops[862]['goods'] if g['itemId'] == 1202085)
    assert refresh['price'] == 50
