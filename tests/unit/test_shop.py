"""The recovered shop must show real goods and transact atomically."""

import asyncio
from pathlib import Path

from tests.unit.test_battle import packet
from tests.unit.test_economy import env, rewards
from x2server.messages.economy import GOODS
from x2server.player.economy import EconomyService
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


def test_unresolved_shop_goods_and_invalid_purchase_never_charge(env):
    store, economy, ctx = env
    service = ShopService(store, economy)
    before = store.get(1)
    for name, values in (("C2L_ShopGoods", {"shopId": 801}),
                         ("C2L_RefreshShop", {"shopId": 809}),
                         ("C2L_BuyGoods", {"shopId": 809, "goodsId": 1933001, "buyNum": 1}),
                         ("C2L_BuyGoods", {"shopId": 809, "goodsId": 1900101, "buyNum": 1}),
                         ("C2L_BuyGoods", {"shopId": 809, "goodsId": 1933001, "buyNum": -1})):
        assert asyncio.run(service.handle(ctx, packet(values, name=name))).values["code"] == 13
    assert store.get(1) == before
    assert store.db.execute("SELECT COUNT(*) FROM shop_receipts").fetchone()[0] == 0


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
