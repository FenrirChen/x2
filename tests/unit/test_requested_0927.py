"""The operator's selected packages and reported reward/progression failures."""

import asyncio

from tests.unit.test_battle import packet
from tests.unit.test_economy import env, rewards
from x2server.messages.economy import GIFT_PACKAGE_DATA, TREASURE_BOX
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
    economy.clock = lambda: 2_000_000_000
    economy.ensure_periods(1)
    assert TREASURE_BOX.decode(economy.task_values(1, 1)["boxList"][0])["pickStatus"] == 0


def test_exact_selected_gift_packages_and_one_time_claim(env):
    store, economy, ctx = env
    service = GiftPackageService(store, economy)
    listing = [GIFT_PACKAGE_DATA.decode(x) for x in service.listing(1)]
    assert [x["id"] for x in listing] == list(range(2700000, 2700034))
    free = asyncio.run(service.buy(ctx, packet({"giftPackageID": 2700018, "num": 1},
        911, "C2L_BuyGiftPackage")))
    assert free.values["code"] == 10
    assert asyncio.run(service.buy(ctx, packet({"giftPackageID": 2700018, "num": 1},
        912, "C2L_BuyGiftPackage"))).values["code"] == 13
    with economy.transaction():
        economy._grant(1, "test-crystal", {1237902: 100})
    before = store.get(1)["snapshot"]["crystal"]
    paid = asyncio.run(service.buy(ctx, packet({"giftPackageID": 2700002, "num": 1},
        913, "C2L_BuyGiftPackage")))
    assert paid.values["code"] == 10
    assert store.get(1)["snapshot"]["crystal"] == before - 60
    assert asyncio.run(service.buy(ctx, packet({"giftPackageID": 2700033, "num": 1},
        914, "C2L_BuyGiftPackage"))).values["code"] == 13  # level 80 gate
