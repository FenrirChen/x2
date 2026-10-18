"""元素之章 (weekly 2060101/2060201) portal shops must sell the stage's own goods.

Tester report 2026-10-18: the shops next to the portal on floors 8 and 17 showed the
generic consumables and relics instead. The client opens 400203 (four slots) and
400202 (six slots) out of its own table/NpcEvent 60010/60011, and player recordings
show 元素晶体·水/火/地/风 at 100 棱镜 each - in stacks of 2 or 6 with the whole stack
at 8折/8.5折 - plus the 加棱镜 圣遗物 1004030/1004631/1004932. These cases pin the
per-shop slot sets, the stack a variant carries, that a bought stack costs its stack
price, and that the generic shops are untouched.
"""
import asyncio

from tests.unit.test_battle import packet
from tests.unit.test_economy import env
from x2server.player.battle_shop import BattleShopService

CRYSTALS = (1103006, 1103007, 1103008, 1103009)  # 元素晶体·水/火/地/风
PRISM_RELICS = (1004030, 1004631, 1004932)        # 彩蛋/大彩蛋/特大彩蛋, 棱镜+200/+500/+1000
PRISM = 903                                       # table/CurrencyType TpyeId 903
UNIT_PRICE = 100                                   # 棱镜 per crystal in the recordings
WEEKLY_SECTION = 2110291                          # 元素之章：白夜


def test_four_slot_weekly_shop_sells_one_stack_per_crystal(env):
    store, economy, _ = env
    service = BattleShopService(store, economy)
    offers = service.stock(400203, 8, '1:run')
    assert [r['itemId'] for r in offers] == list(CRYSTALS)
    assert [r['groupId'] for r in offers] == [30213, 30214, 30215, 30216]
    for offer in offers:
        assert offer['moneyType'] == PRISM
        assert offer['star'] == 1
        assert offer['num'] in (2, 6)
        # 100 棱镜 each and the whole stack paid at discount%: x2 -> 200, x6 at 8折
        # -> 480, x6 at 8.5折 -> 510 - the same pairs the recordings show.
        assert offer['price'] == UNIT_PRICE * offer['num'] * offer['discount'] // 100


def test_six_slot_weekly_shop_adds_the_prism_relics(env):
    store, economy, _ = env
    service = BattleShopService(store, economy)
    offers = service.stock(400202, 17, '1:run')
    assert [r['groupId'] for r in offers] == [30207, 30208, 30209, 30210, 30211, 30212]
    assert [r['itemId'] for r in offers[:4]] == list(CRYSTALS)
    assert offers[4]['itemId'] in PRISM_RELICS
    assert offers[5]['itemId'] in PRISM_RELICS
    assert offers[4]['num'] == 1 and offers[5]['num'] == 1


def test_weekly_shop_stock_is_stable_inside_a_run(env):
    store, economy, _ = env
    service = BattleShopService(store, economy)
    four = service.stock(400203, 8, '1:run')
    assert service.stock(400203, 8, '1:run') == four   # re-opening the same battle
    assert service.stock(400203, 8, '1:other') is not None  # another run still answers


def test_generic_shops_keep_one_piece_and_no_discount(env):
    store, economy, _ = env
    service = BattleShopService(store, economy)
    for shop_id, level in ((400101, 3), (400201, 4), (400802, 15)):
        offers = service.stock(shop_id, level, '1:run')
        assert offers is not None
        assert all(o['num'] == 1 and o['discount'] == 100 for o in offers)
        assert all(o['itemId'] not in CRYSTALS for o in offers)


def test_weekly_buy_charges_the_rolled_stack_price(env):
    store, economy, ctx = env
    with store.db:
        store.db.execute("INSERT INTO economy_runs (uuid,player_id,session_id,section_id,settled)"
                         " VALUES ('weekly',1,'s',?,0)", (WEEKLY_SECTION,))
    service = BattleShopService(store, economy)
    asyncio.run(service.request_shop(ctx, packet(
        {'shopID': 400203, 'level': 8, 'sectionId': WEEKLY_SECTION},
        name='C2L_RequestInsideBattleShop')))
    offer = service.stock(400203, 8, '1:weekly')[0]
    # The client sends its own 棱镜 counter as itemNum; a stack is affordable at its
    # stack price and short by one prism below it.
    bought = asyncio.run(service.buy(ctx, packet(
        {'itemID': offer['itemId'], 'itemNum': offer['price'], 'sectionId': WEEKLY_SECTION},
        name='C2L_BuyInsideBattleShopItems')))
    assert bought.values['result'] == 10
    assert bought.values['itemNum'] == offer['num']
    assert bought.values['itemPrice'] == offer['price']
    short = asyncio.run(service.buy(ctx, packet(
        {'itemID': offer['itemId'], 'itemNum': offer['price'] - 1, 'sectionId': WEEKLY_SECTION},
        name='C2L_BuyInsideBattleShopItems')))
    assert short.values['result'] == 13
