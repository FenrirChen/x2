"""The recovered shop must show real goods and transact atomically."""

import asyncio
from pathlib import Path

from tests.unit.test_battle import packet
from tests.unit.test_economy import env, rewards
from x2server.messages.economy import GOODS
from x2server.messages.core import BASE_INFO
from x2server.player.economy import EconomyService
from x2server.player.login import LoginService
from x2server.player.shop import ShopService
from x2server.player.store import PlayerStore


def test_recovered_shop_809_lists_and_purchases_persist(env):
    store, economy, ctx = env
    service = ShopService(store, economy)
    listing = asyncio.run(service.handle(ctx, packet({"shopId": 809}, name="C2L_ShopGoods")))
    assert listing.values["code"] == 10
    goods = [GOODS.decode(raw) for raw in listing.values["goods"]]
    assert len(goods) == 15
    assert goods[0] == {"goodsId": 1933001, "originalPrice": 1, "itemId": 1281001,
        "num": 1, "price": 1, "currencyType": 902, "canBuyTimes": 999999,
        "hasBuyTimes": 0, "goodsTag": 3, "limited": 0}
    assert goods[-1]["goodsId"] == 1933015
    assert asyncio.run(service.handle(ctx, packet({"goodsId": 1933001},
        name="C2L_QueryGoodsInfo"))).values["price"] == 1
    player = store.get(1)
    snapshot = player["snapshot"]
    snapshot["crystal"] = 10
    store.save_snapshot(1, snapshot, player["revision"])
    purchase = packet({"shopId": 809, "goodsId": 1933001, "buyNum": 2},
                      request_id=20, name="C2L_BuyGoods")
    first = asyncio.run(service.handle(ctx, purchase))
    assert first.values["code"] == 10
    assert first.values["hasBuyTimes"] == 2
    assert rewards(first.values["rewardData"]) == {1281001: 2}
    assert store.get(1)["snapshot"]["crystal"] == 8
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1281001").fetchone()[0] == 2
    assert store.db.execute("SELECT progress FROM economy_tasks WHERE player_id=1 AND task_id=630015").fetchone()[0] == 1
    replay = asyncio.run(service.handle(ctx, purchase))
    assert replay.values == first.values
    assert store.get(1)["snapshot"]["crystal"] == 8
    assert GOODS.decode(asyncio.run(service.handle(ctx, packet({"shopId": 809},
        name="C2L_ShopGoods"))).values["goods"][0])["hasBuyTimes"] == 2
    db_path = Path(store.db.execute("PRAGMA database_list").fetchone()[2])
    reopened = PlayerStore(db_path)
    try:
        reread = ShopService(reopened, EconomyService(reopened))
        assert GOODS.decode(asyncio.run(reread.handle(ctx, packet({"shopId": 809},
            name="C2L_ShopGoods"))).values["goods"][0])["hasBuyTimes"] == 2
        assert reopened.get(1)["snapshot"]["crystal"] == 8
    finally:
        reopened.close()


def test_shop_currency_balances_follow_inventory_and_purchase(env):
    store, economy, ctx = env
    service = ShopService(store, economy)
    currencies = {1237904: ("JewelChip", 4), 1237905: ("SeniorJewelChip", 5),
                  1237915: ("WishCrystal", 200), 1237917: ("FriendCoin", 17),
                  1237918: ("BossCoin", 18), 1237924: ("GuildScore", 24),
                  1237927: ("FragmentMoney", 27)}
    with store.db:
        for item_id, (_, balance) in currencies.items():
            store.db.execute("INSERT INTO inventory VALUES (?,?,?)", (1, item_id, balance))
    base = BASE_INFO.decode(LoginService.snapshot_push(store.get(1), store).values["BaseInfo"])
    assert {field: base[field] for field, _ in currencies.values()} == {
        field: balance for field, balance in currencies.values()}
    ticket_offer = next(row for row in service.compat_offers.values()
                        if row["currencyItemId"] == 1237915 and row["price"] <= 200)
    shop_id = next(shop for (shop, goods), row in service.compat_offers.items()
                   if row is ticket_offer)
    purchase = asyncio.run(service.handle(ctx, packet({"shopId": shop_id,
        "goodsId": ticket_offer["goodsId"], "buyNum": 1}, request_id=912,
        name="C2L_BuyGoods")))
    assert purchase.values["code"] == 10
    updated = next(p for p in purchase.pushes if p.message_name == "PlayerDataProto")
    assert BASE_INFO.decode(updated.values["BaseInfo"])["WishCrystal"] == 200 - ticket_offer["price"]


def test_unresolved_shop_goods_and_invalid_purchase_never_charge(env):
    store, economy, ctx = env
    service = ShopService(store, economy)
    before = store.get(1)
    for name, values in (("C2L_ShopGoods", {"shopId": 804}),
                         ("C2L_RefreshShop", {"shopId": 809}),
                         ("C2L_BuyGoods", {"shopId": 809, "goodsId": 1933001, "buyNum": 1}),
                         ("C2L_BuyGoods", {"shopId": 809, "goodsId": 1900101, "buyNum": 1}),
                         ("C2L_BuyGoods", {"shopId": 809, "goodsId": 1933001, "buyNum": -1})):
        assert asyncio.run(service.handle(ctx, packet(values, name=name))).values["code"] == 13
    assert store.get(1) == before
    assert store.db.execute("SELECT COUNT(*) FROM shop_receipts").fetchone()[0] == 0


def test_compat_shop_query_limit_payment_receipt_and_relog(env):
    store, economy, ctx = env
    service = ShopService(store, economy)
    listing = asyncio.run(service.handle(ctx, packet({"shopId": 801}, name="C2L_ShopGoods")))
    assert listing.values["code"] == 10
    goods = [GOODS.decode(raw) for raw in listing.values["goods"]]
    limited = next(row for row in goods if row["goodsId"] == 1900101)
    assert limited["canBuyTimes"] == 1 and limited["limited"] == 3
    assert all(row["goodsId"] != 1900313 for row in goods)  # unsupported reward destination
    assert asyncio.run(service.handle(ctx, packet({"goodsId": 1900101},
        name="C2L_QueryGoodsInfo"))).values["shopId"] == 801
    request = packet({"shopId": 801, "goodsId": 1900101, "buyNum": 1},
                     request_id=77, name="C2L_BuyGoods")
    p = store.get(1)
    store.save_snapshot(1, dict(p["snapshot"], crystal=30000), p["revision"])
    # Crystals cannot pay for a gold-priced offer.
    assert asyncio.run(service.handle(ctx, request)).values["code"] == 13
    p = store.get(1)
    store.save_snapshot(1, dict(p["snapshot"], gold=30000), p["revision"])
    first = asyncio.run(service.handle(ctx, request))
    assert first.values["code"] == 10
    assert first.values["hasBuyTimes"] == 1
    assert rewards(first.values["rewardData"]) == {1201003: 3}
    assert store.get(1)["snapshot"]["gold"] == 7500
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1201003").fetchone()[0] == 3
    assert asyncio.run(service.handle(ctx, request)).values == first.values
    assert asyncio.run(service.handle(ctx, packet({"shopId": 801, "goodsId": 1900101,
        "buyNum": 1}, request_id=78, name="C2L_BuyGoods"))).values["code"] == 13
    db_path = Path(store.db.execute("PRAGMA database_list").fetchone()[2])
    reopened = PlayerStore(db_path)
    try:
        reread = ShopService(reopened, EconomyService(reopened))
        assert reread._compat_count(1, 801, reread.compat_offers[(801, 1900101)]) == 1
        assert reopened.get(1)["snapshot"]["gold"] == 7500
    finally:
        reopened.close()


def test_shop_entrance_optional_queries_answer_without_mutation(env):
    store, economy, ctx = env
    service = ShopService(store, economy)
    before = store.get(1)
    for name, values in (("C2L_QueryReCommendShop", {}), ("C2L_PaymentStore", {}),
                         ("C2L_RechargeInfo", {"extra": 1})):
        response = asyncio.run(service.handle(ctx, packet(values, name=name)))
        assert response.message_name == name.replace("C2L_", "L2C_", 1)
        assert response.values == {"code": 10}
    assert store.get(1) == before
