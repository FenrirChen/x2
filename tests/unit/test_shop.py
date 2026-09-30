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


def test_shop_currency_balances_follow_inventory(env):
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
    assert all(shop_id == 801 for shop_id, _ in service.compat_offers)


def test_unresolved_shop_goods_and_invalid_purchase_never_charge(env):
    store, economy, ctx = env
    service = ShopService(store, economy)
    before = store.get(1)
    for name, values in (("C2L_RefreshShop", {"shopId": 809}),
                         ("C2L_BuyGoods", {"shopId": 809, "goodsId": 1933001, "buyNum": 1}),
                         ("C2L_BuyGoods", {"shopId": 809, "goodsId": 1900101, "buyNum": 1}),
                         ("C2L_BuyGoods", {"shopId": 809, "goodsId": 1933001, "buyNum": -1})):
        assert asyncio.run(service.handle(ctx, packet(values, name=name))).values["code"] == 13
    assert store.get(1) == before
    assert store.db.execute("SELECT COUNT(*) FROM shop_receipts").fetchone()[0] == 0


def test_random_shop_daily_shard_matches_purchase_and_replay(env):
    store, economy, ctx = env
    from datetime import datetime, timezone
    economy.clock = lambda: datetime(2026, 9, 30, 12, tzinfo=timezone.utc).timestamp()
    service = ShopService(store, economy)
    listing = asyncio.run(service.handle(ctx, packet({"shopId": 801}, name="C2L_ShopGoods")))
    goods = {row["goodsId"]: row for row in map(GOODS.decode, listing.values["goods"])}
    assert listing.values["code"] == 10 and len(goods) == 16
    assert all(row["canBuyTimes"] == 1 and row["limited"] == 3 for row in goods.values())
    assert 1286001 not in {row["itemId"] for row in goods.values()}
    selected = goods[1900101]["itemId"]
    assert selected in service.compat_offers[(801, 1900101)]["poolItems"]
    assert asyncio.run(service.handle(ctx, packet({"shopId": 801},
        name="C2L_RefreshShop"))).values["code"] == 13  # refresh requires crystals
    assert asyncio.run(service.handle(ctx, packet({"goodsId": 1900101},
        name="C2L_QueryGoodsInfo"))).values["code"] == 10
    request = packet({"shopId": 801, "goodsId": 1900101, "buyNum": 1},
                     request_id=77, name="C2L_BuyGoods")
    p = store.get(1)
    store.save_snapshot(1, dict(p["snapshot"], gold=100000), p["revision"])
    first = asyncio.run(service.handle(ctx, request))
    assert first.values["code"] == 10 and first.values["itemId"] == selected
    assert rewards(first.values["rewardData"]) == {selected: 3}
    assert store.get(1)["snapshot"]["gold"] == 77500
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?",
                            (selected,)).fetchone()[0] == 3
    assert asyncio.run(service.handle(ctx, request)).values == first.values
    assert store.get(1)["snapshot"]["gold"] == 77500
    assert asyncio.run(service.handle(ctx, packet({"shopId": 801, "goodsId": 1900101,
        "buyNum": 1}, request_id=78, name="C2L_BuyGoods"))).values["code"] == 13
    assert GOODS.decode(asyncio.run(service.handle(ctx, packet({"shopId": 801},
        name="C2L_ShopGoods"))).values["goods"][0])["hasBuyTimes"] == 1
    economy.clock = lambda: datetime(2026, 10, 1, 12, tzinfo=timezone.utc).timestamp()
    assert GOODS.decode(asyncio.run(service.handle(ctx, packet({"shopId": 801},
        name="C2L_ShopGoods"))).values["goods"][0])["hasBuyTimes"] == 0


def test_random_shop_unlimited_history_becomes_today_purchase(env):
    store, economy, ctx = env
    from datetime import datetime, timezone
    economy.clock = lambda: datetime(2026, 9, 30, 12, tzinfo=timezone.utc).timestamp()
    ShopService(store, economy)
    with store.db:
        store.db.execute("INSERT INTO shop_compat_counts VALUES (1,801,1900301,'lifetime',2)")
    service = ShopService(store, economy)
    assert store.db.execute("""SELECT quantity FROM shop_compat_counts
        WHERE player_id=1 AND shop_id=801 AND goods_id=1900301
        AND period='day:2026-09-30'""").fetchone()[0] == 2
    assert store.db.execute("""SELECT COUNT(*) FROM shop_compat_counts
        WHERE shop_id=801 AND period='lifetime'""").fetchone()[0] == 0
    info = asyncio.run(service.handle(ctx, packet({"goodsId": 1900301}, name="C2L_QueryGoodsInfo")))
    assert (info.values["canBuyTimes"], info.values["hasBuyTimes"]) == (1, 1)
    assert asyncio.run(service.handle(ctx, packet({"shopId": 801, "goodsId": 1900301,
        "buyNum": 1}, request_id=79, name="C2L_BuyGoods"))).values["code"] == 13
    economy.clock = lambda: datetime(2026, 10, 1, 12, tzinfo=timezone.utc).timestamp()
    info = asyncio.run(service.handle(ctx, packet({"goodsId": 1900301}, name="C2L_QueryGoodsInfo")))
    assert (info.values["canBuyTimes"], info.values["hasBuyTimes"]) == (1, 0)


def test_other_compat_shops_remain_retired(env):
    store, economy, ctx = env
    service = ShopService(store, economy)
    listing = asyncio.run(service.handle(ctx, packet({"shopId": 802}, name="C2L_ShopGoods")))
    assert listing.values["code"] == 10 and listing.values["goods"] == []
    assert asyncio.run(service.handle(ctx, packet({"goodsId": 1903101},
        name="C2L_QueryGoodsInfo"))).values["code"] == 13


def test_shop_entrance_optional_queries_answer_without_mutation(env):
    store, economy, ctx = env
    service = ShopService(store, economy)
    before = store.get(1)
    for name, values in (("C2L_QueryReCommendShop", {}), ("C2L_PaymentStore", {}),
                         ("C2L_RechargeInfo", {"extra": 1})):
        response = asyncio.run(service.handle(ctx, packet(values, name=name)))
        assert response.message_name == name.replace("C2L_", "L2C_", 1)
        assert response.values["code"] == 10
        if name == "C2L_QueryReCommendShop":
            assert response.values["recommendTag"]
        else:
            assert response.values == {"code": 10}
    assert store.get(1) == before
