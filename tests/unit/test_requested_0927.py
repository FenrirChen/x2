"""The operator's selected packages and reported reward/progression failures."""

import asyncio

from tests.unit.test_battle import packet
from tests.unit.test_economy import env, rewards
from x2server.messages.economy import GIFT_PACKAGE_DATA, TREASURE_BOX
from x2server.messages.core import HERO_DATA, HERO_GOD_EQUIP, GOD_SLOT_LOCK_INFO
from x2server.player.gift_packages import GiftPackageService
from x2server.player.progression import ProgressionService, catalog


def test_all_owned_hero_skills_have_progression_rows():
    data = catalog()
    available = {row["skill_id"] for row in data["skill_progression"]}
    assert len(data["hero_unlock"]) == 39
    assert all(set(hero["initial_skills"]) <= available for hero in data["hero_unlock"])


def test_reported_hero_skill_can_upgrade(env):
    store, economy, ctx = env
    service = ProgressionService(store, economy)
    with economy.transaction():
        state = store.get(1)["snapshot"]
        state["heroes"].append({"id": 1028, "state": 2, "level": 60, "star": 3})
        economy.save_snapshot(1, state)
        economy._grant(1, "test-skill", {1202080: 5, 1237901: 100_000})
    result = asyncio.run(service.handle(ctx, packet(
        {"heroId": 1028, "skillId": 10280, "uplevel": 1}, 527, "C2L_UpHeroSkill")))
    assert result.values["code"] == 10
    hero = next(h for h in store.get(1)["snapshot"]["heroes"] if h["id"] == 1028)
    assert next(s for s in hero["skills"] if s["id"] == 10280)["level"] == 2


def test_artifact_unlock_route_covers_every_configured_hero(env):
    store, economy, ctx = env
    service = ProgressionService(store, economy)
    heroes = catalog()["hero_unlock"]
    with economy.transaction():
        state = store.get(1)["snapshot"]
        state["heroes"] = [{"id": row["hero_id"], "state": 2, "level": 60, "star": 3}
                           for row in heroes]
        economy.save_snapshot(1, state)
    for index, row in enumerate(heroes):
        result = asyncio.run(service.handle(ctx, packet({"opt": 0, "heroId": row["hero_id"]},
            600 + index, "C2L_Artifact")))
        assert result.values["code"] == 10, row["hero_id"]
    state = store.get(1)["snapshot"]
    assert all(hero["god_equip"]["id"] == row["artifact_id"] and hero["god_equip"]["star"] == 1
               for hero, row in zip(state["heroes"], heroes))


def test_six_star_godlike_answers_and_unlocks_client_skill(env):
    store, economy, ctx = env
    service = ProgressionService(store, economy)
    with economy.transaction():
        state = store.get(1)["snapshot"]
        state["heroes"].append({"id": 1028, "state": 2, "level": 60, "star": 46,
                               "god_equip": {"id": 1528, "level": 100, "star": 6}})
        economy.save_snapshot(1, state)
        economy._grant(1, "test-godlike", {1206028: 20})
    request = {"heroId": 1028}
    first = asyncio.run(service.handle(ctx, packet(request, 940, "C2L_HeroGodLike")))
    assert first.message_name == "L2C_HeroGodLike" and first.values["code"] == 10
    assert first.pushes[0].message_name == "L2C_HeroUpdate"
    hero = next(h for h in store.get(1)["snapshot"]["heroes"] if h["id"] == 1028)
    assert any(s["id"] == 10286 and s["level"] == 1 for s in hero["skills"])
    assert asyncio.run(service.handle(ctx, packet(request, 941, "C2L_HeroGodLike"))).values["code"] == 13
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1206028").fetchone()[0] == 0
    slot = {"heroID": 1028, "slotIndex": 5}
    second = asyncio.run(service.handle(ctx, packet(slot, 942, "C2L_GodSlotLock")))
    assert second.values["code"] == 10 and second.message_name == "L2C_GodSlotLock"
    wire = HERO_DATA.decode(second.pushes[0].values["heros"][-1])
    equip = HERO_GOD_EQUIP.decode(wire["godEquip"])
    assert GOD_SLOT_LOCK_INFO.decode(equip["godSlotLockInfo"][0]) == {"slot": 5, "state": 1}
    assert asyncio.run(service.handle(ctx, packet(slot, 943, "C2L_GodSlotLock"))).values["code"] == 10


def test_activity_boxes_show_status_claim_once_and_roll_over(env):
    store, economy, _ = env
    with economy.transaction():
        economy._grant(1, "test-activity", {1237910: 20})
    boxes = list(map(TREASURE_BOX.decode, economy.task_values(1, 1)["boxList"]))
    assert len(boxes) == 5 and boxes[0]["pickStatus"] == 1 and boxes[1]["pickStatus"] == 0
    first = economy.pick_treasure_box(1, {"boxId": 0, "type": 1})
    assert first.values["code"] == 10
    assert rewards(first.values["rewardData"]) == economy.gifts([760001])
    assert economy.pick_treasure_box(1, {"boxId": 0, "type": 1}).values["code"] == 13
    assert TREASURE_BOX.decode(economy.task_values(1, 1)["boxList"][0])["pickStatus"] == 2
    with economy.transaction():
        snapshot = store.get(1)["snapshot"]
        snapshot["daily_activity"] = 100
        economy.save_snapshot(1, snapshot)
    before = store.get(1)["snapshot"]["crystal"]
    last = economy.pick_treasure_box(1, {"boxId": 4, "type": 1})
    assert last.values["code"] == 10
    assert rewards(last.values["rewardData"])[1237902] == 100
    assert store.get(1)["snapshot"]["crystal"] == before + 100
    economy.clock = lambda: 2_000_000_000
    economy.ensure_periods(1)
    assert TREASURE_BOX.decode(economy.task_values(1, 1)["boxList"][0])["pickStatus"] == 0


def test_exact_selected_gift_packages_and_one_time_claim(env):
    store, economy, ctx = env
    service = GiftPackageService(store, economy)
    listing = [GIFT_PACKAGE_DATA.decode(x) for x in service.listing(1)]
    assert [x["id"] for x in listing] == [2700000, 2700001, 2700002, 2700018, 2700092]
    assert 2700050 not in service.packages
    assert asyncio.run(service.recharge(ctx, packet({"rechargeID": 22024},
        916, "C2L_RechargeGoodsInfo"))).values["code"] == 13
    free = asyncio.run(service.buy(ctx, packet({"giftPackageID": 2700018, "num": 1},
        911, "C2L_BuyGiftPackage")))
    assert free.values["code"] == 10
    assert [GIFT_PACKAGE_DATA.decode(x)["id"] for x in service.listing(1)] == [
        2700000, 2700001, 2700002, 2700019, 2700092]
    assert asyncio.run(service.buy(ctx, packet({"giftPackageID": 2700018, "num": 1},
        912, "C2L_BuyGiftPackage"))).values["code"] == 13
    with economy.transaction():
        economy._grant(1, "test-crystal", {1237902: 100})
    before = store.get(1)["snapshot"]["crystal"]
    paid = asyncio.run(service.buy(ctx, packet({"giftPackageID": 2700002, "num": 1},
        913, "C2L_BuyGiftPackage")))
    assert paid.values["code"] == 10
    assert store.get(1)["snapshot"]["crystal"] == before - 60
    assert [GIFT_PACKAGE_DATA.decode(x)["id"] for x in service.listing(1)] == [
        2700000, 2700001, 2700003, 2700019, 2700092]
    assert asyncio.run(service.buy(ctx, packet({"giftPackageID": 2700004, "num": 1},
        915, "C2L_BuyGiftPackage"))).values["code"] == 13  # level 10 must be bought first
    assert asyncio.run(service.buy(ctx, packet({"giftPackageID": 2700033, "num": 1},
        914, "C2L_BuyGiftPackage"))).values["code"] == 13  # level 80 gate
    with economy.transaction():
        for package_id in [*range(2700003, 2700018), *range(2700019, 2700034)]:
            store.db.execute("INSERT INTO gift_package_claims VALUES (?,?,?,?)",
                (1, package_id, "once", 1))
    assert [GIFT_PACKAGE_DATA.decode(x)["id"] for x in service.listing(1)] == [2700000, 2700001, 2700092]


def test_appearance_coupon_package_can_be_bought_repeatedly(env):
    store, economy, ctx = env
    service = GiftPackageService(store, economy)
    with economy.transaction():
        economy._grant(1, "test-appearance-package-funds", {1237902: 300})
    initial_crystal = store.get(1)["snapshot"]["crystal"]
    initial_coupon = (store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237923")
                      .fetchone() or (0,))[0]
    for request_id in (1101, 1102, 1103):
        result = asyncio.run(service.buy(ctx, packet({"giftPackageID": 2700092, "num": 1},
            request_id, "C2L_BuyGiftPackage")))
        assert result.values["code"] == 10
        listed = next(GIFT_PACKAGE_DATA.decode(raw) for raw in service.listing(1)
                      if GIFT_PACKAGE_DATA.decode(raw)["id"] == 2700092)
        assert listed["state"] == 0 and listed["PurchaseTime"] == 0
    assert store.get(1)["snapshot"]["crystal"] == initial_crystal - 297
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237923").fetchone()[0] == initial_coupon + 90
    retry = asyncio.run(service.buy(ctx, packet({"giftPackageID": 2700092, "num": 1},
        1103, "C2L_BuyGiftPackage")))
    assert retry.values["code"] == 10
    assert store.get(1)["snapshot"]["crystal"] == initial_crystal - 297


def test_monthcard_reports_active_status_and_daily_allowance(env):
    store, economy, ctx = env
    now = [1_790_501_200]
    economy.clock = lambda: now[0]
    service = GiftPackageService(store, economy)
    first = asyncio.run(service.recharge(ctx, packet({"rechargeID": 22099},
        950, "C2L_RechargeGoodsInfo")))
    assert first.values["code"] == 13  # Avoid unavailable client payment SDK.
    assert any(push.message_name == "L2C_BuyGiftPackage" and push.values["code"] == 10
               for push in first.pushes)
    card = next(GIFT_PACKAGE_DATA.decode(x) for x in service.listing(1)
                if GIFT_PACKAGE_DATA.decode(x)["id"] == 2700001)
    assert card["state"] == 1 and card["leftTime"] == 30 and card["PurchaseTime"] == 1
    initial = store.get(1)["snapshot"]["crystal"]
    assert initial >= 180  # 80 initial crystal plus today's 100.
    assert not service.settle_daily(1)
    now[0] += 86400
    refreshed = asyncio.run(service.query(ctx, packet({"playerID": 1},
        951, "C2L_QueryGiftPackage")))
    assert refreshed.values["code"] == 10 and refreshed.pushes
    assert store.get(1)["snapshot"]["crystal"] == initial + 100
    assert next(GIFT_PACKAGE_DATA.decode(x) for x in service.listing(1)
                if GIFT_PACKAGE_DATA.decode(x)["id"] == 2700001)["leftTime"] == 29
    now[0] += 30 * 86400
    assert not service.settle_daily(1)
