"""Full appearance listing and populated White Night Planet entry data."""

import asyncio

from tests.unit.test_battle import packet
from tests.unit.test_economy import env
from x2server.messages.appearance import COMMERCIAL_GOODS
from x2server.messages.lobby import BUILDING_BASE_INFO, GROWTH_BASE, growth_base_values
from x2server.player.appearance import AppearanceService
from x2server.player.appearance_shop import AppearanceShopService
from x2server.player.lobby import LobbyService


def test_all_appearance_goods_are_listed_and_purchasable(env):
    store, economy, ctx = env
    appearance = AppearanceService(store, economy)
    service = AppearanceShopService(store, economy, appearance)
    listing = [COMMERCIAL_GOODS.decode(x) for x in service.listing(1)]
    assert len(listing) == 27
    assert len({x["itemId"] for x in listing}) == 27
    assert 1223003 not in {x["itemId"] for x in listing}
    assert all(x["rechargeID"] == 0 and x["price"] > 0 for x in listing)
    assert [(x["currencyType"], x["price"]) for x in listing
            if x["goodsId"] in (1980004, 1980005)] == [(902, 980), (902, 980)]
    with economy.transaction():
        economy._grant(1, "test-appearance-currency", {1237902: 1500, 1237923: 500})
    first = asyncio.run(service.buy(ctx, packet({"goodsId": 1980001, "shopType": 1,
        "currencyType": 902}, 1200, "C2L_BuyCommercialGoods")))
    assert first.values["code"] == 10
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1221103").fetchone()[0] == 1
    assert asyncio.run(service.buy(ctx, packet({"goodsId": 1980001, "shopType": 1,
        "currencyType": 902}, 1201, "C2L_BuyCommercialGoods"))).values["code"] == 13
    second = asyncio.run(service.buy(ctx, packet({"goodsId": 1980010, "shopType": 1,
        "currencyType": 923}, 1202, "C2L_BuyCommercialGoods")))
    assert second.values["code"] == 10
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237923").fetchone()[0] == 80
    assert asyncio.run(service.buy(ctx, packet({"goodsId": 1980011, "shopType": 1,
        "currencyType": 923}, 1203, "C2L_BuyCommercialGoods"))).values["code"] == 13


def test_white_night_planet_has_buildings_and_query_reply(env):
    _, _, ctx = env
    data = GROWTH_BASE.decode(GROWTH_BASE.encode(growth_base_values()))
    assert len(data["buildingList"]) == 8
    assert len(data["civilization"]) == 7
    assert BUILDING_BASE_INFO.decode(data["buildingList"][0]) == {
        "buildingId": 701, "buildingLevel": 1, "buildingStar": 1}
    lobby = LobbyService()
    query = asyncio.run(lobby.query(ctx, packet({}, 1210, "C2L_QueryGrowthBase")))
    assert query.message_name == "L2C_QueryGrowthBase" and len(query.values["buildingList"]) == 8
    ruin = asyncio.run(lobby.query(ctx, packet({}, 1211, "C2L_UnlockExploreRuin")))
    assert ruin.message_name == "L2C_UnlockExploreRuin" and ruin.values["code"] == 13
