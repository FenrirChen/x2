from tests.activity_calendar_helpers import activity_start, next_activity_cycle
"""All supplied exchange rows must deliver, charge and cap atomically."""
import pytest
import asyncio
import json
from importlib.resources import files

from tests.unit.test_economy import env, rewards
from tests.unit.test_activity_rotation import activity
from x2server.player.activity_exchange import ActivityExchange
from x2server.player.activity_rotation import ActivityRotation
from x2server.player.appearance import AppearanceService
from x2server.player.economy import UnresolvedEconomy
from x2server.network.dispatcher import DispatchContext
from x2server.network.session import SessionState
from x2server.messages.activity import ACTIVITY_SCHEMAS
from x2server.messages.economy import ECONOMY_SCHEMAS
from tests.unit.test_battle import packet


def open_shop(service, economy, shop, period):
    rule = shop['unlock']
    with economy.transaction():
        if rule['kind'] == 'period_item':
            service.obtained(1, period, {i: 1 for i in rule['items']}, f'test:unlock:{shop["shopId"]}')
        elif rule['kind'] == 'item_count':
            economy._grant(1, f'test:souls:{shop["shopId"]}',
                           {i: 1 for i in rule['items'][:rule['count']]})
        elif rule['kind'] == 'memory_count':
            service.obtained(1, period, {1290100 + i: 1 for i in range(1, rule['count'] + 1)}, f'test:unlock:{shop["shopId"]}')
        elif rule['kind'] == 'chapter_pass':
            for sid in service.chapters[rule['chapter']]['SectionID']:
                service.rotation.put(1, period, 'clear', sid, 1)


def test_yuexi_client_shop_rows_match_purchase_unlock_rules(activity):
    _, _, service, _ = activity
    exchange = ActivityExchange(service)
    import json
    from pathlib import Path
    catalog = json.loads((Path(__file__).resolve().parents[2] /
        'src/x2server/data/activity_rotation_catalog.json').read_text(encoding='utf-8'))
    rows = {r['ShopID']: r for r in catalog['tables']['ShopConfig']}
    for shop_id, count in zip(range(887, 891), (0, 1, 2, 4)):
        assert rows[shop_id]['ShopParam1'] == 70011
        assert rows[shop_id]['ShopParam2'] == [count]
        assert rows[shop_id]['ShopIcon']
        assert exchange.shops[shop_id]['unlock'] == {'kind': 'item_count', 'items': list(range(1290189, 1290193)), 'count': count}


@pytest.mark.parametrize('group', [7, 33, 13, 99])
def test_all_stages_visible_before_unlock_but_purchase_gates_remain(activity, group):
    _, economy, service, now = activity
    exchange = ActivityExchange(service)
    index = next(i for i, theme in enumerate(service.rotation.themes) if theme['group'] == group)
    now[0] = activity_start(index)
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
    now[0] = activity_start(index)
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
    now[0] = activity_start(index)
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
    now[0] = next_activity_cycle(now[0])
    assert all(exchange.count(1, service.period(1), g['goodsId']) == 0 for g in shop['goods'])


def test_sakura_derived_stages_match_osiris_amount_and_stock(activity):
    _, _, service, _ = activity
    exchange = ActivityExchange(service)
    raw = json.loads(files('x2server').joinpath('data/activity_exchange_catalog.json').read_text(encoding='utf8'))
    original = {g['goodsId']: g['price'] for shop in raw['shops'] for g in shop['goods']}
    for stage in range(2, 5):
        sakura = exchange.shops[870 + stage]['goods']
        osiris = exchange.shops[875 + stage]['goods']
        assert len(sakura) == len(osiris)
        for actual, reference in zip(sakura, osiris):
            assert actual['num'] == reference['num']
            assert actual['canBuyTimes'] == reference['canBuyTimes']
            # Derivation uses original prices, before either shop is discounted.
            assert actual['price'] == max(1, original[reference['goodsId']] * 5 // 9) // 2
            assert actual['itemId'] == (1251170 if reference['itemId'] == 1251140 else reference['itemId'])


def test_insufficient_currency_and_failure_leave_no_purchase(activity, monkeypatch):
    store, economy, service, now = activity
    exchange = ActivityExchange(service)
    now[0] = activity_start(1)
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
    now[0] = next_activity_cycle(activity_start(1))
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
        assert (row['itemId'], row['num'], row['price'], row['currencyItemId']) == (1237901, 1000, 5, 1237985)
    mini = next(g for g in exchange.shops[890]['goods'] if g['itemId'] == 1203001)
    assert mini['price'] == 30 and mini['canBuyTimes'] == 10
    refresh = next(g for g in exchange.shops[862]['goods'] if g['itemId'] == 1202085)
    assert refresh['price'] == 25


def test_current_sakura_shops_unlock_once_and_later_periods_stay_gated(activity):
    store,e,a,now=activity
    now[0]=a.rotation.FIRST_END
    period=a.period(1)
    assert period.index==1_000_001
    a.query_activity(1)
    x=ActivityExchange(a)
    assert all(x.unlocked(1,period,s) for s in x.shops.values() if s['group']==33)
    clues=(1104011,1104021,1104031)
    def held():
        return [store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?',(i,)).fetchone()[0] for i in clues]
    assert held()==[1,1,1]
    a.query_activity(1)
    assert held()==[1,1,1]
    now[0]=next_activity_cycle(now[0])
    later=a.period(1)
    assert later.theme['group']==33
    assert not a.shop_unlock_override(later)
    assert not x.unlocked(1,later,x.shops[872])


def test_all_activity_prices_halved_once_with_floor(activity):
    _, _, service, _ = activity
    original = json.loads(files('x2server').joinpath('data/activity_exchange_catalog.json').read_text(encoding='utf8'))
    raw = {g['goodsId']: g for shop in original['shops'] for g in shop['goods']}
    for exchange in (ActivityExchange(service), ActivityExchange(service)):
        for gid, (_, offer) in exchange.goods.items():
            assert offer['price'] == raw[gid]['price'] // 2
            assert offer['num'] == raw[gid]['num']
            assert offer['canBuyTimes'] == raw[gid]['canBuyTimes']
    assert any(g['price'] % 2 for g in raw.values())
    for box in service.tables['ActivityBox']:
        assert service.boxes[box['BoxID']]['CostNum'] == box['CostNum'] // 2


def test_yuexi_soul_gates_count_owned_kinds_not_copies_or_fragments(activity):
    store, economy, service, now = activity
    now[0] = activity_start(6)
    exchange = ActivityExchange(service)
    period = service.period(1)
    def gates():
        return [exchange.unlocked(1, service.period(1), exchange.shops[sid]) for sid in range(887,891)]
    assert gates() == [True, False, False, False]
    with economy.transaction():
        economy._grant(1, 'test:all-old-fragments', {i:1 for i in range(1290101,1290125)})
        for i in range(1290101,1290125):
            service.rotation.put(1, period, 'obtained-item', i, 1)
    assert gates() == [True, False, False, False]
    for index, item in enumerate(range(1290189,1290193)):
        with economy.transaction():
            economy._grant(1, f'test:soul:{item}', {item:3})
        assert gates() == [[True,True,False,False],[True,True,True,False],
                           [True,True,True,False],[True,True,True,True]][index]
    now[0] = next_activity_cycle(now[0])
    assert gates() == [True, True, True, True]  # Inventory survives rotations.


def test_yuexi_complete_pov_chapters_unlock_successive_shop_stages(activity):
    _, economy, service, now = activity
    now[0] = activity_start(6)
    exchange = ActivityExchange(service)
    chapters = {c['ChapterID']: c for c in service.tables['POVChapterInfo']}
    for index, cid in enumerate((2021511,2022811,2021023,2022711)):
        chapter = chapters[cid]
        for stage, sid in enumerate(chapter['StageID']):
            with economy.transaction():
                granted = service.pov_chapter_rewards(1, sid)
                economy._grant(1, f'test:pov:{sid}', granted)
            assert bool(granted) == (stage == len(chapter['StageID'])-1)
        period = service.period(1)
        gates = [exchange.unlocked(1, period, exchange.shops[sid]) for sid in range(887,891)]
        assert gates == [[True,True,False,False],[True,True,True,False],
                         [True,True,True,False],[True,True,True,True]][index]
        with economy.transaction():
            assert service.pov_chapter_rewards(1, chapter['StageID'][-1]) == {}


def test_skin_good_delivers_and_pushes_hero_appearance(activity):
    """买下皮肤类货品后必须回 L2C_HeroSkinAll / L2C_HeroSkinUpdate。

    客户端的外观页只按这两条推送重读某神格的已拥有形象, 只回 L2C_BuyGoods 时货
    已经进了背包, 但外观页会一直显示「未获得」 (同 appearance_shop 售出后的推送)。
    """
    store, economy, service, now = activity
    snapshot = store.get(1)['snapshot']
    snapshot['heroes'].append({'id': 1010, 'state': 2, 'level': 1, 'star': 1})
    store.save_snapshot(1, snapshot, store.get(1)['revision'])
    exchange = ActivityExchange(service, AppearanceService(store, economy))
    index = next(i for i, theme in enumerate(service.rotation.themes) if theme['group'] == 99)
    now[0] = activity_start(index) + 3600
    period = service.period(1)
    shop = exchange.shops[889]
    open_shop(service, economy, shop, period)
    offer = next(g for g in shop['goods'] if g['itemId'] == 1221003)
    with economy.transaction():
        economy._grant(1, 'test:skin-push', {offer['currencyItemId']: 100000})
    request = {'shopId': 889, 'goodsId': offer['goodsId'], 'buyNum': 1}
    ctx = DispatchContext('test', 'local', SessionState('test', 'skin-push', player_id=1))
    response = asyncio.run(exchange.handle(ctx, packet(request, 993, 'C2L_BuyGoods'),
                           'C2L_BuyGoods', request))
    assert response.values['code'] == 10
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1221003').fetchone()[0] == 1
    pushed = [p.message_name for p in response.pushes]
    assert 'L2C_HeroSkinAll' in pushed and 'L2C_HeroSkinUpdate' in pushed
