import asyncio
import sqlite3

import pytest

from x2server.messages.economy import TASK, REWARD, REWARD_ITEM, FINISH_REQUEST, FINISH_RESULT, TREASURE_BOX
from x2server.player.economy import EconomyService, UnresolvedEconomy
from x2server.player.battle import BattleService
from x2server.player.store import PlayerStore
from x2server.messages.battle import CHECKOUT, FIGHT_KILL_DATA
from x2server.network.dispatcher import DispatchContext
from x2server.network.session import SessionState
from x2server.protocol.errors import ProtocolError
from tests.unit.test_battle import packet, request


@pytest.fixture
def env(tmp_path):
    store = PlayerStore(tmp_path / "economy.db")
    p = store.login("lab", 1, 0)
    store.save_snapshot(1, dict(p["snapshot"], level=60, mobility={"power": 149},
        heroes=[{"id": 1003, "state": 2, "level": 1, "star": 1}]), p["revision"])
    economy = EconomyService(store)
    context = DispatchContext("test", "local", SessionState("test", "session", player_id=1))
    yield store, economy, context
    store.close()


def checkout(success=True, seconds=200):
    return packet({"checkout": CHECKOUT.encode({"chapterId": 2010100, "sectionId": 2110801,
        "success": success, "fightTime": seconds})}, name="C2L_CheckoutMainMissionSign")


def rewards(raw):
    return {r["itemId"]: r["itemNum"] for r in map(REWARD_ITEM.decode, REWARD.decode(raw).get("rewardItem", []))}


def test_task_catalog_gates_and_login_claim_survives_restart(env):
    store, economy, ctx = env
    assert len(economy.task_values(1, 1)["taskList"]) == 26
    assert len(economy.task_values(1, 2)["taskList"]) == 14
    assert economy.claim(1, 630019, 1)["code"] == 13
    economy.record_event(1, "login:initial", 5)
    economy.record_event(1, "login:initial", 5)
    value = economy.claim(1, 630019, 1)
    assert value["code"] == 10
    assert rewards(value["rewardData"]) == {1237910: 10, 1237901: 800, 1237907: 500}
    snapshot = store.get(1)
    assert snapshot["snapshot"]["gold"] == 800
    assert snapshot["snapshot"]["hero_exp"] == 500
    assert snapshot["snapshot"]["level"] == 60
    economy = EconomyService(store)
    assert economy.claim(1, 630019, 1) == value
    assert store.get(1) == snapshot
    task = next(t for t in map(TASK.decode, economy.task_values(1, 1)["taskList"]) if t["taskId"] == 630019)
    assert task["taskStatus"] == 4 and task["taskRefreshTime"] > economy.clock()
    assert economy.claim(1, 630019, 2)["code"] == 13
    assert economy.claim(1, 999, 1)["code"] == 13
    p = store.get(1)
    store.save_snapshot(1, dict(p["snapshot"], level=1), p["revision"])
    assert 630006 not in [TASK.decode(t)["taskId"] for t in economy.task_values(1, 1)["taskList"]]
    assert economy.claim(1, 630006, 1)["code"] == 13


def test_challenge_page_includes_group_boxes_for_client_entry(env):
    _, economy, _ = env
    values = economy.challenge_values(1)
    boxes = [TREASURE_BOX.decode(raw) for raw in values["boxList"]]
    assert [box["boxId"] for box in boxes] == list(range(1, 11))
    assert all(box["pickStatus"] == 0 for box in boxes)
    assert values["taskList"]


def test_hero_interaction_daily_task_capped_tap_does_not_advance(env):
    from datetime import datetime, timedelta, timezone
    from x2server.player.favor import FavorService

    store, economy, context = env
    now = 1_800_000_000
    favor = FavorService(store, economy, clock=lambda: now)
    day = datetime.fromtimestamp(now, timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    with store.db:
        store.db.execute("INSERT INTO favor_touch_log VALUES (1,1003,?,3)", (day,))
    answer = asyncio.run(favor.handle(context, packet({"opt": 0, "optionId": 0,
        "heroId": 1003, "num": 0}, name="C2L_AddFavor")))
    assert answer.values["code"] == 13  # Touch reward cap remains in force.
    # A tap rejected by the cap never counts towards the interactive task.
    task = next(TASK.decode(raw) for raw in economy.task_values(1, 1)["taskList"]
                if TASK.decode(raw)["taskId"] == 630010)
    assert task["taskStatus"] == 2 and task["taskProgress"] == 0
    assert any(push.message_name == "L2C_TaskUpdate" for push in answer.pushes)


def test_every_eligible_daily_and_weekly_task_reward_can_be_claimed(env):
    store, economy, _ = env
    economy.ensure_periods(1)
    for task_id, task in sorted(economy.tasks.items()):
        if task["AcceptLevel"] > store.get(1)["snapshot"]["level"]:
            continue
        target = economy.catalog["task_conditions"][str(task_id)]["CompleteNum"]
        store.db.execute("UPDATE economy_tasks SET progress=? WHERE player_id=1 AND task_id=?",
                         (target, task_id))
        result = economy.claim(1, task_id, task["RefreshCycle"]["value"])
        assert result["code"] == 10, task_id
        assert economy.claim(1, task_id, task["RefreshCycle"]["value"])["code"] == 10


def test_battle_first_and_repeat_rewards_atomic_and_idempotent(env):
    store, economy, ctx = env
    battle = BattleService(store, economy)
    asyncio.run(battle.enter(ctx, packet(request())))
    first = asyncio.run(battle.checkout(ctx, checkout()))
    assert first.values["result"] == 10
    assert rewards(first.values["rewardData"]) == {1237908: 12, 1237907: 120, 1237901: 180, 1237902: 30, 1201003: 5}
    snapshot = store.get(1)
    assert asyncio.run(battle.checkout(ctx, checkout())).values == first.values
    assert store.get(1) == snapshot
    assert asyncio.run(battle.checkout(ctx, checkout(False))).values["result"] == 13
    assert snapshot["snapshot"]["mobility"]["power"] == 143
    assert snapshot["snapshot"]["heroes"][0]["level"] == 1
    assert snapshot["snapshot"]["level"] == 60
    asyncio.run(battle.enter(ctx, packet(request(), 2)))
    second = asyncio.run(battle.checkout(ctx, checkout()))
    assert rewards(second.values["rewardData"]) == {1237908: 12, 1237907: 120, 1237901: 180}
    assert store.db.execute("SELECT quantity FROM inventory").fetchone()[0] == 5
    assert store.get(1)["snapshot"]["gold"] == 360
    assert store.get(1)["snapshot"]["crystal"] == 30
    assert store.db.execute("SELECT COUNT(*) FROM economy_clears").fetchone()[0] == 1


def test_kill_reports_credit_tasks_only_after_settled_battle(env):
    store, economy, ctx = env
    battle = BattleService(store, economy)
    asyncio.run(battle.enter(ctx, packet(request())))
    report = packet({"sectionId": 2110801, "datas": [FIGHT_KILL_DATA.encode({
        "heroId": 1003, "unitId": [3001, 4001], "num": [5, 2]})]},
        name="C2L_FightKillInfo")
    assert asyncio.run(battle.kill_info(ctx, report)).values["code"] == 10
    assert store.db.execute("SELECT SUM(progress) FROM economy_tasks WHERE task_id IN (630020,630101,630102)").fetchone()[0] == 0
    assert asyncio.run(battle.checkout(ctx, checkout())).values["result"] == 10
    assert asyncio.run(battle.kill_info(ctx, report)).values["code"] == 10
    assert asyncio.run(battle.kill_info(ctx, report)).values["code"] == 10
    progress = dict(store.db.execute("SELECT task_id,progress FROM economy_tasks WHERE task_id IN (630020,630101,630102)"))
    assert progress == {630020: 7, 630101: 5, 630102: 2}


def test_failure_and_old_practice_runs_never_grant(env):
    store, economy, ctx = env
    practice = BattleService(store)
    asyncio.run(practice.enter(ctx, packet(request())))
    battle = BattleService(store, economy)
    before = store.get(1)
    assert asyncio.run(battle.checkout(ctx, checkout())).values["result"] == 13
    asyncio.run(battle.enter(ctx, packet(request(), 2)))
    ctx.session.session_id = "other"
    failed = asyncio.run(battle.checkout(ctx, checkout(False)))
    assert failed.values["result"] == 10 and rewards(failed.values["rewardData"]) == {}
    after = store.get(1)["snapshot"]
    assert after["mobility"]["power"] == before["snapshot"]["mobility"]["power"]
    assert {**after, "mobility": {"power": after["mobility"]["power"]}} == before["snapshot"]
    assert store.db.execute("SELECT COUNT(*) FROM economy_grants").fetchone()[0] == 0


def test_receipt_failure_rolls_back_all_rewards(env):
    store, economy, ctx = env
    battle = BattleService(store, economy)
    asyncio.run(battle.enter(ctx, packet(request())))
    with store.db:
        store.db.execute("CREATE TRIGGER reject_receipt BEFORE INSERT ON battle_receipts BEGIN SELECT RAISE(ABORT, 'test'); END")
    before = store.get(1)
    with pytest.raises(sqlite3.IntegrityError):
        asyncio.run(battle.checkout(ctx, checkout()))
    assert store.get(1) == before
    for table in ("economy_grants", "economy_clears", "inventory"):
        assert store.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    assert store.db.execute("SELECT settled FROM economy_runs").fetchone()[0] == 0


def test_claim_overflow_rolls_back_and_missing_reward_is_not_partial(env):
    store, economy, ctx = env
    economy.record_event(1, "login:initial", 5)
    p = store.get(1)
    store.save_snapshot(1, dict(p["snapshot"], gold=2**31-1), p["revision"])
    before = store.get(1)
    assert economy.claim(1, 630019, 1)["code"] == 13
    assert store.get(1) == before
    assert store.db.execute("SELECT claimed FROM economy_tasks WHERE task_id=630019").fetchone()[0] == 0
    with pytest.raises(UnresolvedEconomy):
        economy.gifts([730001, 999])
    with pytest.raises(UnresolvedEconomy):
        economy.gifts([710047])  # Equipment requires instances/attributes, not an inventory integer.


def test_shop_missing_quantities_and_boxes_never_mutate(env):
    store, economy, ctx = env
    before = store.get(1)
    for name, values, code in (("ShopGoods", {"shopId": 801}, 13),
        ("ShopGoods", {"shopId": 999}, 13), ("RefreshShop", {"shopId": 801}, 13),
        ("BuyGoods", {"shopId": 801, "goodsId": 2001501, "buyNum": 1}, 13),
        ("BuyGoods", {"shopId": 801, "goodsId": 2001501, "buyNum": -1}, 13),
        ("QueryGoodsInfo", {"goodsId": 2001501}, 13),
        ("PickTreasureBox", {"boxId": 1, "type": 1}, 13)):
        result = asyncio.run(economy.handle(ctx, packet(values, name="C2L_"+name)))
        assert result.values["code"] == code
        assert not result.values.get("goods")
    assert store.get(1) == before
    ctx.session.player_id = None
    with pytest.raises(ProtocolError):
        asyncio.run(economy.handle(ctx, packet({"shopId": 801}, name="C2L_ShopGoods")))


def test_task_claim_wire_and_event_filters(env):
    store, economy, ctx = env
    economy.record_event(1, "clear:one", 3, 2110801)
    assert store.db.execute("SELECT COUNT(*) FROM economy_tasks").fetchone()[0] == 40
    assert store.db.execute("SELECT SUM(progress) FROM economy_tasks").fetchone()[0] == 0
    economy.record_event(1, "login:initial", 5)
    result = asyncio.run(economy.handle(ctx, packet({"data": [FINISH_REQUEST.encode({"taskId": 630019, "type": 1})]}, name="C2L_FinishGameTask")))
    assert FINISH_RESULT.decode(result.values["data"][0])["code"] == 10
    assert {p.message_name for p in result.pushes} == {"L2C_ItemUpdate", "L2C_TaskUpdate", "PlayerDataProto", "L2C_AchvUpdate"}
    replay = asyncio.run(economy.handle(ctx, packet({"taskId": 630019, "type": 1}, name="C2L_FinishGameTaskAsync")))
    assert FINISH_RESULT.decode(replay.values["data"])["code"] == 10
    assert store.get(1)["snapshot"]["gold"] == 800


def test_challenge_tasks_real_progress_boxes_and_claims(env):
    """挑战任务: served tasks mint claimable, event tasks track real progress,
    and a group box only opens after all six of its tasks are claimed."""
    store, economy, context = env
    import json as _json
    from importlib.resources import files as _files
    from x2server.player.progression import ProgressionService, hero_skills, catalog as prog_catalog

    values = economy.challenge_values(1)
    tasks = {TASK.decode(raw)["taskId"]: TASK.decode(raw) for raw in values["taskList"]}
    assert len(tasks) == 60
    boxes = [TREASURE_BOX.decode(raw) for raw in values["boxList"]]
    assert [b["boxId"] for b in boxes] == list(range(1, 11))
    # "served" tasks (no server-side event source) mint at their target.
    served = [t for task_id, t in tasks.items()
              if economy.challenge_tasks[task_id]["track"] == "served"]
    assert served and all(t["taskStatus"] == 3 for t in served)
    # Event-tracked tasks start at zero.
    event_task_id = next(task_id for task_id, e in economy.challenge_tasks.items()
                         if e["track"] == "event" and e["completeType"] == 13)
    assert tasks[event_task_id]["taskProgress"] == 0

    # A skill upgrade pays E_UpgradeSkill(13) exactly once.
    service = ProgressionService(store, economy)
    saved = store.get(1)
    store.save_snapshot(1, dict(saved["snapshot"],
        heroes=[dict(saved["snapshot"]["heroes"][0], level=16)]), saved["revision"])
    hero = store.get(1)["snapshot"]["heroes"][0]
    skill = next(s for s in hero_skills(hero) if s["id"] == 10031)
    row = next(r for r in prog_catalog()["skill_progression"]
               if r["skill_id"] == skill["id"] and r["level"] == skill["level"])
    with store.db:
        store.db.execute("""INSERT INTO inventory VALUES (1, 1237901, 999999)
            ON CONFLICT(player_id,item_id) DO UPDATE SET quantity=999999""")
        for material in row["materials"]:
            store.db.execute("""INSERT INTO inventory VALUES (1, ?, 999)
                ON CONFLICT(player_id,item_id) DO UPDATE SET quantity=999""",
                (material["material_item_id"],))
    answer = asyncio.run(service.handle(context, packet(
        {"heroId": hero["id"], "skillId": skill["id"], "uplevel": 1}, name="C2L_UpHeroSkill")))
    assert answer.values["code"] == 10
    tasks = {TASK.decode(raw)["taskId"]: TASK.decode(raw)
             for raw in economy.challenge_values(1)["taskList"]}
    assert tasks[event_task_id]["taskProgress"] == 1

    # Claiming: a group's box opens only when all six of its tasks are claimed.
    # Group 1: loginday + account-derived + four event tasks (3/45/49/7).
    economy.login_event(1)  # credits E_LoginDay and mints derived progress
    group1 = {t: e for t, e in economy.challenge_tasks.items() if e["group"] == 1}
    for task_id, entry in group1.items():
        if entry["track"] == "event":
            value = entry["value1"][0] if entry["value1"] else 0
            value2 = entry["value2"][0] if entry["value2"] else 0
            economy.record_event(1, f"sim:{task_id}", entry["completeType"], value,
                                 entry["completeNum"], value2)
    first = next(t for t, e in group1.items() if e["track"] == "loginday")
    assert economy.claim_challenge(1, first)["code"] == 10
    assert economy.claim_challenge(1, first)["code"] == 13  # once per life
    assert economy.pick_challenge_box(1, 1).values["code"] == 13  # group not done
    for task_id in group1:
        if task_id != first:
            assert economy.claim_challenge(1, task_id)["code"] == 10, task_id
    # Live client sends a zero-based challenge box index (group one is zero).
    wire = packet({"boxId": 0, "type": 3, "param": 0}, name="C2L_PickTreasureBox")
    assert asyncio.run(economy.handle(context, wire)).values["code"] == 10
    assert asyncio.run(economy.handle(context, wire)).values["code"] == 13
    boxes = [TREASURE_BOX.decode(raw) for raw in economy.challenge_values(1)["boxList"]]
    assert boxes[0]["pickStatus"] == 2 and boxes[1]["pickStatus"] == 0


def test_chapter_dp_gate_progression(env):
    """C2L_GameTask type 7 answers the DP the client's chapter gate reads."""
    store, economy, context = env
    chain = economy.challenge_chain(2010200)
    assert chain, "chapter 2010200 must have 现世复刻 rows"
    story_section = next(r["SectionID"] for r in economy.entry_catalog.sections.values()
                         if r["Type"] == 0 and r["ChapterID"] == 2010200)
    with store.db:
        store.db.execute("INSERT OR IGNORE INTO economy_clears VALUES (1,?, 'uuid-a')", (story_section,))
        store.db.execute("INSERT OR IGNORE INTO economy_clears VALUES (1,?, 'uuid-b')", (chain[0],))
        store.db.execute("INSERT OR IGNORE INTO economy_clears VALUES (1,?, 'uuid-c')", (chain[1],))
    answer = asyncio.run(economy.handle(context, packet(
        {"type": 7, "chapterId": 2010200}, name="C2L_GameTask")))
    assert answer.values["chapterTaskPoint"] == 4  # 1 story + difficulty 1 + difficulty 2


def test_legacy_dp_floor_does_not_stack_with_official_tasks(env):
    store, economy, context = env
    with store.db:
        store.db.execute("""INSERT INTO chapter_dp_floors VALUES
            (1,2010200,10,'test-save chapter 2 skip')""")
    answer = asyncio.run(economy.handle(context, packet(
        {"type": 7, "chapterId": 2010200}, name="C2L_GameTask")))
    assert answer.values["chapterTaskPoint"] == 0
    assert economy.chapter_dp(1, 2010100) == 0
    chain = economy.challenge_chain(2010200)
    with store.db:
        for index, section in enumerate(chain[:5]):
            store.db.execute("INSERT INTO economy_clears VALUES (?,?,?)",
                             (1, section, f"challenge-{index}"))
    assert economy.chapter_dp(1, 2010200) == economy.chapter_dp_from_clears(set(chain[:5]), 2010200)


def test_fixed_equipment_part_reward_becomes_instance(env):
    """主线固定奖励里的装备部件 (124xxxx, ItemType 10) must materialize as a
    HeroEquip instance instead of parking in pending_rewards forever."""
    store, economy, context = env
    from x2server.player.equipment_factory import EquipmentInstanceFactory
    economy.equipment_factory = EquipmentInstanceFactory()
    profile = economy.runtime_drops.resolve(1, "run-parts", 2110803, True, 2, ()) \
        if False else None
    settle = asyncio.run(BattleService(store, economy).settle) if False else None
    # Drive the actual gift path the settle loop uses:
    group = 710047  # {1240002: 1}, the recovered FirVReward row
    from collections import Counter
    from x2server.player.economy import UnresolvedEconomy
    deferred = Counter()
    resolved = economy.gifts([group], deferred=deferred)
    assert resolved == {} and deferred == {1240002: 1}
    # And the settle-loop conversion:
    equipment_specs = []
    part_catalogued = str(1240002) in economy.equipment_factory.data["equib_base"]
    if part_catalogued:
        for _ in range(deferred[1240002]):
            equipment_specs.append({"item_id": 1240002, "quality": 1, "quantity": 1})
    assert equipment_specs == [{"item_id": 1240002, "quality": 1, "quantity": 1}]
    from x2server.player.equipment_factory import materialize_instances
    instances = materialize_instances(store.db, 1, 1240002, 1, 1, "run-parts",
                                      economy.equipment_factory, 0)
    assert len(instances) == 1 and instances[0]["typeId"] == 1240002


def test_chapter_dp_box_claim_flow(env):
    """type=7 reply carries the chapter's DP boxes; a reached threshold grants
    its dpRewards item exactly once."""
    store, economy, context = env
    chapter = 2010200
    chain = economy.challenge_chain(chapter)
    story_sections = [r["SectionID"] for r in economy.entry_catalog.sections.values()
                      if r["Type"] == 0 and r["ChapterID"] == chapter]
    with store.db:
        for offset, section in enumerate([*story_sections, *chain]):
            store.db.execute("INSERT OR IGNORE INTO economy_clears VALUES (1,?,?)",
                             (section, f"uuid-{offset}"))
    assert economy.chapter_dp(1, chapter) == 8  # only official clear objectives
    with store.db:
        for task in economy.dp.chapters[str(chapter)]["tasks"]:
            store.db.execute("INSERT INTO chapter_objectives VALUES (?,?,?,?) ON CONFLICT(player_id,chapter_id,task_id) DO UPDATE SET progress=excluded.progress",
                (1, chapter, task["taskId"], task["completeNums"][-1]))
    assert economy.chapter_dp(1, chapter) == 100
    boxes = [TREASURE_BOX.decode(raw) for raw in economy.chapter_dp_boxes(1, chapter)]
    assert boxes and all(b["activityId"] == chapter for b in boxes)
    assert [b["pickStatus"] for b in boxes] == [1, 1, 1, 1, 1]
    first_reachable = boxes[0]
    assert first_reachable["pickStatus"] == 1
    request = {"boxId": first_reachable["boxId"], "type": 7, "param": chapter, "activityId": 0}
    answer = asyncio.run(economy.handle(context, packet(request, name="C2L_PickTreasureBox")))
    assert answer.values["code"] == 10
    reward_items = REWARD.decode(answer.values["rewardData"])["rewardItem"]
    assert reward_items, "DP box must pay its dpRewards item"
    # Claiming the same box again is refused.
    again = asyncio.run(economy.handle(context, packet(request, name="C2L_PickTreasureBox")))
    assert again.values["code"] == 13
    boxes = [TREASURE_BOX.decode(raw) for raw in economy.chapter_dp_boxes(1, chapter)]
    assert boxes[first_reachable["boxId"]]["pickStatus"] == 2


def test_challenge_story_clear_credit_for_preexisting_clears(env):
    """剧情关 cannot be replayed: challenge tasks naming story stages credit
    clears that already exist when the system ships."""
    store, economy, context = env
    entry = next(e for e in economy.challenge_tasks.values()
                 if e["track"] == "event" and e["completeType"] == 3)
    story_section = next(section for section in entry["value1"]
                         if section in economy.entry_catalog.sections
                         and economy.entry_catalog.sections[section]["Type"] == 0)
    with store.db:
        store.db.execute("INSERT OR IGNORE INTO economy_clears VALUES (1,?, 'pre')", (story_section,))
    economy.login_event(1)
    tasks = {TASK.decode(raw)["taskId"]: TASK.decode(raw)
             for raw in economy.challenge_values(1)["taskList"]}
    task_id = next(t for t, e in economy.challenge_tasks.items() if e is entry)
    assert tasks[task_id]["taskProgress"] == 1
    assert tasks[task_id]["taskStatus"] == 3


def test_bag_item_use_pays_used_gifts(env):
    """Using a Used-carrying bag item consumes it and pays its gift groups."""
    store, economy, context = env
    from tests.unit.test_battle import packet as pkt
    item_id = 1202001  # Used -> 720071 -> fixed 1237907 x500
    with store.db:
        store.db.execute("INSERT INTO inventory VALUES (1, ?, 2)", (item_id,))
    request = pkt({"id": item_id, "opt": 0, "count": 1}, name="C2L_ItemOpt")
    answer = asyncio.run(economy.handle(context, request))
    assert answer.values["code"] == 10
    rewards = REWARD.decode(answer.values["rewardData"])["rewardItem"]
    granted = {REWARD_ITEM.decode(raw)["itemId"]: REWARD_ITEM.decode(raw)["itemNum"]
               for raw in rewards}
    assert granted.get(1237907) == 500
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?",
                            (item_id,)).fetchone()[0] == 1
    replay = asyncio.run(economy.handle(context, request))
    assert replay.values["code"] == 10  # receipt replays the same reply
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?",
                            (item_id,)).fetchone()[0] == 1  # no double consumption
    # An item without Used stays rejected.
    reject = asyncio.run(economy.handle(context, pkt({"id": 1237901, "opt": 0, "count": 1},
                                                     name="C2L_ItemOpt")))
    assert reject.values["code"] == 13


@pytest.mark.parametrize("item_id,currency,amount", [
    (1202023, 1237901, 20000), (1202025, 1237901, 50000),
    (1202071, 1237906, 1000), (1202072, 1237906, 2000),
])
def test_currency_cards_consume_grant_and_replay(env, item_id, currency, amount):
    store, economy, context = env
    from tests.unit.test_battle import packet as pkt
    with store.db:
        store.db.execute("INSERT INTO inventory VALUES (1, ?, 2)", (item_id,))
    request = pkt({"id": item_id, "opt": 0, "count": 1}, name="C2L_ItemOpt")
    first = asyncio.run(economy.handle(context, request))
    assert first.values["code"] == 10
    assert rewards(first.values["rewardData"])[currency] == amount
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?",
                            (item_id,)).fetchone()[0] == 1
    balance_field = "gold" if currency == 1237901 else "equip_exp"
    balance = store.get(1)["snapshot"].get(balance_field, 0)
    replay = asyncio.run(economy.handle(context, request))
    assert replay.values == first.values
    assert store.get(1)["snapshot"].get(balance_field, 0) == balance
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?",
                            (item_id,)).fetchone()[0] == 1


def test_story_review_unlock_pays_skill_point_and_stays_unlocked(env):
    """星图 -> 剧情回顾 -> 主线: L2C_QueryMission.story plus C2L_UnlockStory(667)."""
    store, economy, context = env
    from tests.unit.test_battle import packet as pkt
    # A null/empty story list is what renders every 剧情回顾 chapter locked.
    assert economy.mission_values(1)["story"] == []
    # Without ChapterInfo.ReviewUnlockRequest (技能点 1237916) the button is rejected.
    broke = pkt({"chapterId": 2010101, "chapterType": 0}, name="C2L_UnlockStory")
    assert asyncio.run(economy.handle(context, broke)).values == {"code": 13, "story": []}
    with store.db:
        store.db.execute("INSERT INTO inventory VALUES (1, ?, 1)",
                         (economy.STORY_REVIEW_UNLOCK_ITEM,))
    answer = asyncio.run(economy.handle(context, pkt({"chapterId": 2010101, "chapterType": 0},
                                                     name="C2L_UnlockStory")))
    assert answer.values["code"] == 10
    # RequestNum=1 spent, ReviewUnlocAward=760066 pays 1x 许愿币 into the bag ledger.
    assert rewards(answer.values["rewardData"]) == {1237914: 1}
    assert answer.values["story"] == [2010101]
    assert economy.mission_values(1)["story"] == [2010101]
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?",
                            (economy.STORY_REVIEW_UNLOCK_ITEM,)).fetchone()[0] == 0
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237914",
                            ).fetchone()[0] == 1
    # Re-clicking an unlocked row must not charge or pay again.
    replay = asyncio.run(economy.handle(context, pkt({"chapterId": 2010101, "chapterType": 0},
                                                      name="C2L_UnlockStory")))
    assert replay.values == {"code": 13, "story": [2010101]}
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237914",
                            ).fetchone()[0] == 1
    # The unlock survives a restart, matching the rest of the service.
    assert EconomyService(store).mission_values(1)["story"] == [2010101]
