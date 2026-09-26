import asyncio
import sqlite3

import pytest

from x2server.messages.economy import TASK, REWARD, REWARD_ITEM, FINISH_REQUEST, FINISH_RESULT
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
    assert {p.message_name for p in result.pushes} == {"L2C_ItemUpdate", "L2C_TaskUpdate", "PlayerDataProto"}
    replay = asyncio.run(economy.handle(ctx, packet({"taskId": 630019, "type": 1}, name="C2L_FinishGameTaskAsync")))
    assert FINISH_RESULT.decode(replay.values["data"])["code"] == 10
    assert store.get(1)["snapshot"]["gold"] == 800
