import asyncio
from tests.unit.test_economy import env
from tests.unit.test_battle import packet
from x2server.messages.battle import BATTLE_SCHEMAS, DROP_REPORT_ITEM, DROP_REPORT_NPC, DROP_DATA
from x2server.player.battle import BattleService
from x2server.messages.economy import REWARD, REWARD_ITEM


def test_catalog_and_all_45_boxes_deliver_current_factory(env):
    store, economy, _ = env
    assert len(economy.dp.chapters) == 12
    assert sum(len(c["tasks"]) for c in economy.dp.chapters.values()) == 260
    boxes = {int(k): v for k, v in economy.dp.boxes.items() if v.get("supported")}
    assert len(boxes) == 45
    with economy.transaction():
        for index, (item, box) in enumerate(boxes.items()):
            raw = economy.dp.grant_box(1, box["chapterId"], index, item)
            reward = REWARD.decode(raw)
            assert {r["itemId"]: r["itemNum"] for r in map(REWARD_ITEM.decode, reward["rewardItem"])} == {r["itemId"]: r["num"] for r in box["contents"]}
            assert len(reward.get("rewardEquip", [])) == (6 if box.get("equib") else 0)


def test_dp_cumulative_reports_and_restart(env):
    store, economy, _ = env
    task = next(t for t in economy.dp.chapters["2010100"]["tasks"] if t.get("completeType") == "E_KillMonster")
    with economy.transaction():
        for amount in (150, 50, 150, 200):
            economy.dp.observe(1, 2010100, "run1", "kill", task["completeValue1"], amount, 1003)
    assert economy.chapter_dp(1, 2010100) == task["dp"]
    assert store.db.execute("SELECT amount FROM chapter_signals WHERE source='run1'").fetchone()[0] == 200
    from x2server.player.economy import EconomyService
    assert EconomyService(store).chapter_dp(1, 2010100) == task["dp"]


def test_claim_atomic_and_duplicate_does_not_pay(env):
    store, economy, _ = env
    with economy.transaction():
        for task in economy.dp.chapters["2010200"]["tasks"]:
            store.db.execute("INSERT INTO chapter_objectives VALUES (1,2010200,?,?)", (task["taskId"], task.get("completeNum", 1)))
    request = {"type": 7, "param": 2010200, "boxId": 0}
    assert economy.pick_chapter_dp_box(1, request).values["code"] == 10
    before = store.get(1)
    assert economy.pick_chapter_dp_box(1, request).values["code"] == 13
    assert store.get(1) == before


def test_old_floor_archived_not_added(env):
    store, economy, _ = env
    with store.db:
        store.db.execute("INSERT INTO chapter_dp_floors VALUES (1,2010200,10,'operator skip')")
        store.db.execute("INSERT INTO task_boxes VALUES (1,7,2010200,0)")
    assert economy.chapter_dp(1, 2010200) == 0
    assert '2010200' in store.db.execute("SELECT legacy_floors FROM chapter_dp_migrations").fetchone()[0]
    assert economy.pick_chapter_dp_box(1, {"type": 7, "param": 2010200, "boxId": 0}).values["code"] == 13


def test_dp_box_instances_and_hero_update_pushes(env):
    store, economy, _ = env
    for chapter in (2010200, 2010900):
        with store.db:
            for task in economy.dp.chapters[str(chapter)]["tasks"]:
                store.db.execute("INSERT INTO chapter_objectives VALUES (?,?,?,?)", (1, chapter, task["taskId"], task.get("completeNum", 1)))
    equips = economy.pick_chapter_dp_box(1, {"type": 7, "param": 2010200, "boxId": 1})
    assert equips.values["code"] == 10
    assert len(next(p for p in equips.pushes if p.message_name == "L2C_EquipUpdate").values["equip"]) == 6
    assert any(p.message_name == "L2C_TreasureBoxUpdate" for p in equips.pushes)
    hero = economy.pick_chapter_dp_box(1, {"type": 7, "param": 2010900, "boxId": 0})
    assert hero.values["code"] == 10
    assert any(p.message_name == "L2C_HeroUpdate" for p in hero.pushes)
    assert sum(h["id"] == 1013 for h in store.get(1)["snapshot"]["heroes"]) == 1
    from x2server.player.progression import catalog
    prototype = next(h for h in catalog()["hero_unlock"] if h["hero_id"] == 1013)
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?", (prototype["fragment_item_id"],)).fetchone()[0] == 9 * prototype["fragment_count"]
