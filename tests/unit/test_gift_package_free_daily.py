"""The shop's free daily pack (2700000, "第 7 次领纯晶石"): one claim a day."""

import asyncio

from tests.unit.test_battle import packet
from tests.unit.test_economy import env, rewards
from x2server.messages.economy import GIFT_PACKAGE_DATA
from x2server.player.gift_packages import GiftPackageService

FREE_DAILY_ID = 2700000
CYCLE = 7
FINAL_ITEM = 1237925  # Param2 gift 781005: 纯晶石


def cell(service, player_id=1):
    return next(GIFT_PACKAGE_DATA.decode(raw) for raw in service.listing(player_id)
                if GIFT_PACKAGE_DATA.decode(raw)["id"] == FREE_DAILY_ID)


def test_free_daily_pack_advances_every_day_and_pays_the_seventh(env):
    store, economy, ctx = env
    today = [1_790_501_200]
    economy.clock = lambda: today[0]
    service = GiftPackageService(store, economy)
    request_ids = iter(range(1200, 1400))

    def buy():
        return asyncio.run(service.buy(ctx, packet({"giftPackageID": FREE_DAILY_ID, "num": 1},
                                                    next(request_ids), "C2L_BuyGiftPackage")))

    assert (cell(service)["state"], cell(service)["PurchaseTime"]) == (0, 0)
    for day in range(1, CYCLE + 1):
        claim = buy()
        assert claim.values["code"] == 10, day
        items = rewards(claim.values["rewardData"])
        assert items, day
        # The client renders "领取进度：PurchaseTime % Param1[0] / Param1[0]" (Param1=[7]),
        # so the n-th day has to report n. Comparing the running total against the table's
        # Times=1 used to freeze the cell at 1/7 and reject every later claim.
        assert cell(service)["PurchaseTime"] == day
        assert cell(service)["state"] == 1
        if day == CYCLE:
            assert items == {FINAL_ITEM: 1}
        else:
            assert FINAL_ITEM not in items
        assert buy().values["code"] == 13  # a second claim on the same local day
        assert cell(service)["PurchaseTime"] == day
        today[0] += 86400
        assert (cell(service)["state"], cell(service)["PurchaseTime"]) == (0, day)


def test_free_daily_pack_repeats_its_cycle_after_seven_claims(env):
    store, economy, ctx = env
    today = [1_790_501_200]
    economy.clock = lambda: today[0]
    service = GiftPackageService(store, economy)
    request_ids = iter(range(1400, 1500))

    for day in range(1, 2 * CYCLE + 1):
        claim = asyncio.run(service.buy(ctx, packet({"giftPackageID": FREE_DAILY_ID, "num": 1},
            next(request_ids), "C2L_BuyGiftPackage")))
        assert claim.values["code"] == 10, day
        items = rewards(claim.values["rewardData"])
        # The pack never runs out: the everyday gift every day, the final one every CYCLE-th.
        assert (items == {FINAL_ITEM: 1}) == (day % CYCLE == 0), day
        assert cell(service)["PurchaseTime"] == day
        today[0] += 86400
    assert cell(service)["state"] == 0
