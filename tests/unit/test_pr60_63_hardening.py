import asyncio
from datetime import datetime, timedelta, timezone
import pytest

from tests.unit.test_economy import env, rewards
from tests.unit.test_battle import packet
from tests.unit.test_item_exchange_currency import exchange, quantity, CHIP, FRAGMENT_MONEY
from x2server.messages.core import CORE_SCHEMAS
from x2server.messages.economy import GOODS
from x2server.player.battle_shop import BattleShopService
from x2server.player.shop import ShopService


def fund(store, item, amount):
    with store.db:
        store.db.execute('INSERT INTO inventory VALUES (?,?,?) ON CONFLICT(player_id,item_id) DO UPDATE SET quantity=excluded.quantity', (1, item, amount))


def test_fragment_conversion_accepts_client_bulk_count_and_refreshes_first(env):
    store, economy, ctx = env
    fund(store, CHIP, 1000)
    pkt = exchange([(CHIP, 1000)])
    result = asyncio.run(economy.handle(ctx, pkt))
    assert result.values['code'] == 10
    assert rewards(result.values['rewardData']) == {FRAGMENT_MONEY: 5000}
    assert quantity(store, CHIP) == 0
    assert result.before_response and not result.pushes
    assert any(m.message_name == 'PlayerDataProto' for m in result.before_response)
    for m in (*result.before_response, result):
        CORE_SCHEMAS[m.message_name].encode(m.values)
    assert asyncio.run(economy.handle(ctx, pkt)).values == result.values
    assert quantity(store, FRAGMENT_MONEY) == 5000


def test_duplicate_fragment_rows_and_overflow_roll_back(env):
    store, economy, ctx = env
    fund(store, CHIP, 3)
    assert asyncio.run(economy.handle(ctx, exchange([(CHIP, 2), (CHIP, 2)]))).values['code'] == 13
    assert quantity(store, CHIP) == 3 and quantity(store, FRAGMENT_MONEY) == 0
    fund(store, FRAGMENT_MONEY, 2**31 - 2)
    assert asyncio.run(economy.handle(ctx, exchange([(CHIP, 1)], request_id=92))).values['code'] == 13
    assert quantity(store, CHIP) == 3
    assert quantity(store, FRAGMENT_MONEY) == 2**31 - 2
    assert store.db.execute('SELECT count(*) FROM item_opt_receipts').fetchone()[0] == 0


def test_fragment_batch_is_bounded_before_deductions(env):
    store, economy, ctx = env
    fund(store, CHIP, 200)
    result = asyncio.run(economy.handle(ctx, exchange([(CHIP, 1)] * 129)))
    assert result.values['code'] == 13 and quantity(store, CHIP) == 200


def test_friend_shop_midnight_reset_and_price_query_agree(env):
    store, economy, ctx = env
    local = datetime(2026, 10, 18, 23, 59, 59, tzinfo=timezone(timedelta(hours=8)))
    now = [int(local.timestamp())]
    economy.clock = lambda: now[0]
    service = ShopService(store, economy)
    fund(store, 1237917, 2000)
    listing = asyncio.run(service.handle(ctx, packet({'shopId': 802}, name='C2L_ShopGoods')))
    assert listing.values['NextRefreshTime'] == now[0] + 1
    goods = {r['goodsId']: r for r in map(GOODS.decode, listing.values['goods'])}
    query = asyncio.run(service.handle(ctx, packet({'goodsId': 1903601}, name='C2L_QueryGoodsInfo')))
    assert query.values['price'] == goods[1903601]['price'] == 708
    assert query.values['originalPrice'] == 1200
    def buy(seq):
        return asyncio.run(service.handle(ctx, packet({'shopId': 802, 'goodsId': 1903601, 'buyNum': 1}, seq, 'C2L_BuyGoods')))
    assert buy(10).values['code'] == 10
    assert buy(11).values['code'] == 13
    now[0] += 1
    assert buy(12).values['code'] == 10
    assert quantity(store, 1203002) == 2
    assert quantity(store, 1237917) == 584


@pytest.mark.parametrize('wallet', [0, -1])
def test_weekly_shop_cannot_buy_without_prisms(env, wallet):
    store, economy, ctx = env
    with store.db:
        store.db.execute("INSERT INTO economy_runs (uuid,player_id,session_id,section_id,settled) VALUES ('weekly',1,'s',2110291,0)")
    service = BattleShopService(store, economy)
    asyncio.run(service.request_shop(ctx, packet({'shopID': 400203, 'level': 8, 'sectionId': 2110291}, name='C2L_RequestInsideBattleShop')))
    result = asyncio.run(service.buy(ctx, packet({'itemID': 1103006, 'itemNum': wallet, 'sectionId': 2110291}, name='C2L_BuyInsideBattleShopItems')))
    assert result.values['result'] == 13
    assert store.db.execute('SELECT count(*) FROM battle_shop_purchases').fetchone()[0] == 0
