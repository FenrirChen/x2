import asyncio
from tests.unit.test_economy import env
from tests.unit.test_battle import packet
from x2server.messages.battle import BATTLE_SCHEMAS, DROP_REPORT_ITEM, DROP_REPORT_NPC, DROP_DATA
from x2server.player.battle import BattleService
from x2server.messages.economy import REWARD, REWARD_ITEM


def test_catalog_and_all_50_boxes_deliver_current_factory(env):
    store, economy, _ = env
    assert len(economy.dp.chapters) == 12
    assert sum(len(c["tasks"]) for c in economy.dp.chapters.values()) == 260
    boxes = {int(k): v for k, v in economy.dp.boxes.items() if v.get("supported")}
    assert len(boxes) == 50
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


def test_per_run_prism_counts_gained_not_balance(env):
    """650110 (E_GetMoneyPer, 4500 棱镜) counts prism *gained* during the run, the
    same figure the client's CheckGetMoney reads. Spending prism in the in-stage
    shop lowers currentNum, so reading only the balance left the objective
    incomplete after a run the client showed as done."""
    store, economy, _ = env
    from x2server.messages.economy import TASK
    from x2server.player.endless import PROFILE_CURRENCY
    with economy.transaction():
        economy.dp.report(1, 2010100, "run-prism", {"currency": [
            PROFILE_CURRENCY.encode({"pickupNum": 4500, "currentNum": 3500, "consumeNum": 1000, "typeId": 903})]})
    progress = dict(store.db.execute(
        "SELECT task_id,progress FROM chapter_objectives WHERE player_id=1 AND chapter_id=2010100"))
    assert progress[650110] == 4500
    assert economy.chapter_dp(1, 2010100) == 2
    task = next(t for t in map(TASK.decode, economy.dp.task_list(1, 2010100)) if t['taskId'] == 650110)
    assert (task['taskProgress'], task['taskStatus']) == (4500, 3)


def test_per_run_prism_counts_buff_granted_prism(env):
    """特大彩蛋 (item 1004932, action 41008) tops the in-stage prism up directly.
    That grant lands in currentNum but is not necessarily a pickup, so 3500
    ground pickups + a 1000 grant minus 1000 spent must still clear the 4500
    objective in one run."""
    store, economy, _ = env
    from x2server.player.endless import PROFILE_CURRENCY
    with economy.transaction():
        economy.dp.report(1, 2010100, "run-buff", {"currency": [
            PROFILE_CURRENCY.encode({"pickupNum": 3500, "currentNum": 3500, "consumeNum": 1000, "typeId": 903})]})
    progress = dict(store.db.execute(
        "SELECT task_id,progress FROM chapter_objectives WHERE player_id=1 AND chapter_id=2010100"))
    assert progress[650110] == 4500
    assert economy.chapter_dp(1, 2010100) == 2


def test_claim_atomic_and_duplicate_does_not_pay(env):
    store, economy, _ = env
    with economy.transaction():
        for task in economy.dp.chapters["2010200"]["tasks"]:
            store.db.execute("INSERT INTO chapter_objectives VALUES (1,2010200,?,?)", (task["taskId"], task["completeNums"][-1]))
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


def test_dp_box_instances_and_client_fragment_reward(env):
    store, economy, _ = env
    for chapter in (2010200, 2010900):
        with store.db:
            for task in economy.dp.chapters[str(chapter)]["tasks"]:
                store.db.execute("INSERT INTO chapter_objectives VALUES (?,?,?,?)", (1, chapter, task["taskId"], task["completeNums"][-1]))
    equips = economy.pick_chapter_dp_box(1, {"type": 7, "param": 2010200, "boxId": 1})
    assert equips.values["code"] == 10
    assert len(next(p for p in equips.pushes if p.message_name == "L2C_EquipUpdate").values["equip"]) == 6
    assert any(p.message_name == "L2C_TreasureBoxUpdate" for p in equips.pushes)
    hero = economy.pick_chapter_dp_box(1, {"type": 7, "param": 2010900, "boxId": 0})
    assert hero.values["code"] == 10
    assert not any(p.message_name == "L2C_HeroUpdate" for p in hero.pushes)
    assert not any(h["id"] == 1013 and h.get("state") == 2 for h in store.get(1)["snapshot"]["heroes"])
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1201013").fetchone()[0] == 10
    rewards = {r['itemId']: r['itemNum'] for r in map(REWARD_ITEM.decode, REWARD.decode(hero.values['rewardData'])['rewardItem'])}
    assert rewards == {1201013: 10, 1251090: 10, 1237901: 20000}


def test_client_stages_alternative_ids_and_relog(env):
    from x2server.messages.economy import TASK
    from x2server.player.economy import EconomyService
    store, economy, _ = env
    chapter = 2010100
    assert economy.chapter_dp_capacity(chapter) == 100
    # Client 650101: any of 3031/3622/3628; 150/250/500 earn +1/+1/+2.
    with store.db:
        economy.dp.observe(1, chapter, 'a', 'kill', 3031, 100)
        economy.dp.observe(1, chapter, 'b', 'kill', 3622, 50)
    assert economy.chapter_dp(1, chapter) == 1
    task = next(t for t in map(TASK.decode, economy.dp.task_list(1, chapter)) if t['taskId'] == 650101)
    assert (task['stage'], task['taskProgress'], task['taskStatus']) == (1, 150, 2)
    with store.db:
        economy.dp.observe(1, chapter, 'b', 'kill', 3622, 150)
        economy.dp.observe(1, chapter, 'b', 'kill', 3622, 50)
    assert EconomyService(store).chapter_dp(1, chapter) == 2
    with store.db:
        economy.dp.observe(1, chapter, 'b', 'kill', 3622, 400)
    assert economy.chapter_dp(1, chapter) == 4
    task = next(t for t in map(TASK.decode, economy.dp.task_list(1, chapter)) if t['taskId'] == 650101)
    assert (task['stage'], task['taskProgress'], task['taskStatus']) == (2, 500, 3)


def test_exact_star_tasks_and_all_equipment_parts(env):
    store, economy, _ = env
    chapter = 2010200
    with store.db:
        economy.dp.equipment(1, chapter, 'a', [{'star': 6, 'item_id': 1240016}] * 5)
    economy.chapter_dp(1, chapter)
    # 650223 requires exactly five stars; 650224 accepts four/five/six.
    progress = dict(store.db.execute('SELECT task_id,progress FROM chapter_objectives WHERE player_id=1 AND chapter_id=?', (chapter,)))
    assert progress[650223] == 0 and progress[650224] == 2
    with store.db:
        economy.dp.equipment(1, chapter, 'b', [{'star': 5, 'item_id': 1240015}] * 5)
    economy.chapter_dp(1, chapter)
    progress = dict(store.db.execute('SELECT task_id,progress FROM chapter_objectives WHERE player_id=1 AND chapter_id=?', (chapter,)))
    assert progress[650223] == 2 and progress[650222] == 10


def test_hundred_point_box_is_reachable_without_percent_conversion(env):
    store, economy, _ = env
    chapter = 2010200
    with store.db:
        for task in economy.dp.chapters[str(chapter)]['tasks']:
            store.db.execute('INSERT INTO chapter_objectives VALUES (?,?,?,?)', (1, chapter, task['taskId'], task['completeNums'][-1]))
    assert economy.chapter_dp(1, chapter) == 100
    request = {'type': 7, 'param': chapter, 'boxId': 4}
    assert economy.pick_chapter_dp_box(1, request).values['code'] == 10
    assert economy.pick_chapter_dp_box(1, request).values['code'] == 13


def test_client_prologue_has_zero_marker_and_no_reward_box(env):
    _, economy, _ = env
    assert economy.chapter_dp_catalog['2010000']['dpThresholds'] == [0]
    assert economy.chapter_dp_boxes(1, 2010000) == []
    assert economy.pick_chapter_dp_box(1, {'type': 7, 'param': 2010000, 'boxId': 0}).values['code'] == 13
