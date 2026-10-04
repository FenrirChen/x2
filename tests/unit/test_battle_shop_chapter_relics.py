"""The in-battle shop must offer each stage's own relics, per player and per run.

Tester report 2026-10-04: 黑暗金字塔 (chapter 2010500) never showed its own relics,
notably 1004635 溜了溜了溜了. The offer used to be seeded with shop+floor only, so
every player saw the same six items forever, and the 圣遗物 slots were a lottery
against the whole id block. These cases pin both halves of the fix: the per-run seed
and the chapter-relic narrowing.
"""
import asyncio

from tests.unit.test_battle import packet
from tests.unit.test_economy import env
from x2server.player.battle_shop import BattleShopService

SHOP, FLOOR, SECTION = 400201, 4, 2110401  # dark pyramid, a section of chapter 2010500


def test_stock_rolls_per_player_and_run(env):
    store, economy, _ = env
    service = BattleShopService(store, economy)
    first = service.stock(SHOP, FLOOR, "1:run-a")
    assert first is not None
    assert service.stock(SHOP, FLOOR, "1:run-a") == first       # stable inside a run
    assert service.stock(SHOP, FLOOR, "1:run-b") != first        # a new run re-rolls
    assert service.stock(SHOP, FLOOR, "2:run-a") != first        # another player differs


def test_relic_slots_prefer_the_chapters_own_relics(env):
    store, economy, _ = env
    service = BattleShopService(store, economy)
    recommended = service.relic_chapters[2010500]
    big_slot = {1004601, 1004631, 1004634, 1004635, 1004639, 1004640, 1004641}
    seen = set()
    for run in range(200):
        offers = service.stock(SHOP, FLOOR, f"1:{run}", 2010500)
        assert offers is not None
        # offers[3] = relic_mid_plus: disjoint from this chapter -> full pool kept.
        assert offers[3]["itemId"] not in recommended
        assert offers[4]["itemId"] in big_slot
        assert offers[5]["itemId"] in recommended
        seen.add(offers[4]["itemId"])
    assert 1004635 in seen  # 溜了溜了溜了 is now reachable


def test_chapter_for_section_resolves_the_dark_pyramid(env):
    store, economy, _ = env
    service = BattleShopService(store, economy)
    assert service.chapter_for_section(SECTION) == 2010500
    assert service.chapter_for_section(999999) == 0
    assert BattleShopService(store).chapter_for_section(SECTION) == 0  # no economy -> no bias


def test_request_shop_persists_run_and_answers_chapter_relics(env):
    store, economy, ctx = env
    with store.db:
        store.db.execute("INSERT INTO economy_runs VALUES ('run-dark', 1, 's', ?, 0)", (SECTION,))
    service = BattleShopService(store, economy)
    answer = asyncio.run(service.request_shop(ctx, packet(
        {"shopID": SHOP, "level": FLOOR, "sectionId": SECTION},
        name="C2L_RequestInsideBattleShop")))
    assert answer.values["result"] == 10
    row = store.db.execute(
        "SELECT run_id FROM battle_shop_visits WHERE player_id=1 AND shop_id=? AND level=?",
        (SHOP, FLOOR)).fetchone()
    assert row["run_id"] == "run-dark"
    assert answer.values["shopItems"]
    # A buy of an offered relic must still resolve against the same run's stock.
    item = next(o for o in service.stock(SHOP, FLOOR, "1:run-dark", 2010500)
                if o["itemId"] in service.relic_chapters[2010500])
    bought = asyncio.run(service.buy(ctx, packet(
        {"itemID": item["itemId"], "itemNum": 999999, "sectionId": SECTION},
        name="C2L_BuyInsideBattleShopItems")))
    assert bought.values["result"] == 10