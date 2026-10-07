"""心愿任务 (好感日常, GameTaskType 6): 候选 / 接取 / 记账 / 领取."""
import asyncio

import pytest

from tests.unit.test_battle import packet, request
from x2server.messages.battle import BATTLE_SCHEMAS, FIGHT_DATA, FIGHT_HERO
from x2server.messages.economy import FINISH_REQUEST, FINISH_RESULT, REWARD, REWARD_ITEM, TASK
from x2server.network.dispatcher import DispatchContext
from x2server.network.session import SessionState
from x2server.player.battle import BattleService
from x2server.player.economy import EconomyService, day_index
from x2server.player.favor import FavorService
from x2server.player.store import PlayerStore

# 固定时钟: 2025-10-08 前后, 让 day_index 在用例内是常量。
DAY = 1759872000
HERO = 1003
# 带 1003 通关指定关卡 (E_CarryHeroCustomsPass=11), value2 含 2130501。
CARRY = 635030
# 给 1003 送 1204010 (E_SendDesignativeHeroGift=68), completeNum 1。
GIFT = 635036


@pytest.fixture
def wish(tmp_path):
    store = PlayerStore(tmp_path / "wish.db")
    p = store.login("lab", 1, DAY)
    store.save_snapshot(1, dict(p["snapshot"], level=60, mobility={"power": 149},
        heroes=[{"id": HERO, "state": 2, "level": 1, "star": 1}]), p["revision"])
    economy = EconomyService(store, clock=lambda: DAY)
    favor = FavorService(store, economy, clock=lambda: DAY)
    economy.attach_favor(favor)
    ctx = DispatchContext("test", "local", SessionState("test", "session", player_id=1))
    yield store, economy, favor, ctx
    store.close()


def progress(store, task_id):
    row = store.db.execute("SELECT progress,claimed FROM favor_daily_tasks "
                           "WHERE player_id=1 AND task_id=?", (task_id,)).fetchone()
    return tuple(row) if row else (0, 0)


def accept(ctx, economy, ids):
    return asyncio.run(economy.handle(
        ctx, packet({"taskIds": list(ids), "type": economy.FAVOR_DAILY_KIND},
                    name="C2L_AcceptFavorTask"))).values["code"]


def test_candidates_are_only_owned_witnessable_tasks_and_deterministic(wish):
    _, economy, _, _ = wish
    ids = economy.favor_candidates(1)
    assert len(ids) == economy.favor_task_daily_limit == 3
    for task_id in ids:
        entry = economy.favor_tasks[task_id]
        assert entry["track"] == "event" and entry["hero"] == HERO
    # 同一天同一存档重复问, 答案必须一样(否则客户端会拿到一批确认时必被拒的候选)。
    assert economy.favor_candidates(1) == ids


def test_candidate_rows_carry_the_choose_page_status(wish):
    _, economy, _, _ = wish
    page = economy.favor_task_values(1, economy.QUERY_EXTRA_GENMIND)
    assert page["code"] == 10 and page["type"] == economy.FAVOR_DAILY_KIND
    rows = [TASK.decode(r) for r in page["taskList"]]
    # 每行 taskStatus == 0 才是客户端的选择页(唯一带确认键、会发 459 的那一页)。
    assert rows and all(row["taskStatus"] == 0 for row in rows)
    assert {row["taskId"] for row in rows} == set(economy.favor_candidates(1))
    # 还没接任何任务时「我的任务」为空 -> 开始页。
    mine = economy.favor_task_values(1, 0)
    assert mine["code"] == 10 and mine["taskList"] == []


def test_accept_persists_under_the_day_key_and_replay_succeeds(wish):
    store, economy, _, ctx = wish
    ids = economy.favor_candidates(1)
    assert accept(ctx, economy, ids) == 10
    day = day_index(DAY)
    stored = {r[0] for r in store.db.execute(
        "SELECT task_id FROM favor_daily_tasks WHERE player_id=1 AND day=?", (day,))}
    assert stored == set(ids)
    # 重放的确认必须成功(idempotent), 否则客户端会弹错误。
    assert accept(ctx, economy, ids) == 10
    # 名额满了之后既不再生成候选, 也不能再接第四条。
    assert economy.favor_candidates(1) == []
    extra = next(t for t, e in economy.favor_tasks.items()
                 if e["track"] == "event" and e["hero"] == HERO and t not in ids)
    assert accept(ctx, economy, [extra]) == 13
    assert extra not in {r[0] for r in store.db.execute(
        "SELECT task_id FROM favor_daily_tasks WHERE player_id=1 AND day=?", (day,))}


def test_genmind_with_nothing_to_generate_answers_173(wish):
    _, economy, _, _ = wish
    economy.accept_favor_tasks(1, economy.favor_candidates(1))
    page = economy.favor_task_values(1, economy.QUERY_EXTRA_GENMIND)
    # 173 = E_NOT_GEN_MIND_TASK; 客户端对 type 6 走 code 10 同一条路, 落在开始页。
    assert page["code"] == 173 and page["taskList"] == []


def test_accepted_task_owns_the_task_page_status(wish):
    _, economy, _, _ = wish
    economy.accept_favor_tasks(1, [CARRY, GIFT])
    rows = {TASK.decode(r)["taskId"]: TASK.decode(r)
            for r in economy.favor_task_values(1, 0)["taskList"]}
    assert set(rows) == {CARRY, GIFT}
    # 刚接、进度 0 -> 2 START(进行中), 不是候选页的 0。
    assert rows[CARRY]["taskStatus"] == 2


def test_carry_hero_clear_and_gift_credit_only_accepted_rows(wish):
    store, economy, _, _ = wish
    assert economy.accept_favor_tasks(1, [CARRY, GIFT]) == 10
    with economy.transaction():
        # 带 1003 通关 2130501: 命中 CARRY。
        economy.credit_favor_task(1, "clear:run", economy.TASK_EVENT_CARRY_HERO_CUSTOMS_PASS,
                                  HERO, 2130501)
        # 带着 1003 打了别的关卡: 不命中(关卡是 value2 那一维)。
        economy.credit_favor_task(1, "clear:other", economy.TASK_EVENT_CARRY_HERO_CUSTOMS_PASS,
                                  HERO, 2110801)
        # 送 1204010: 命中 GIFT(completeNum 3, 送 1 个只走到 1)。
        economy.credit_favor_task(1, "gift:1", economy.TASK_EVENT_SEND_DESIGNATIVE_HERO_GIFT,
                                  HERO, 1204010, 1)
    assert progress(store, CARRY) == (1, 0)
    assert progress(store, GIFT) == (1, 0)
    # 同一 token 重放不再加: 记账靠 economy_events 里的 token 去重。
    with economy.transaction():
        economy.credit_favor_task(1, "gift:1", economy.TASK_EVENT_SEND_DESIGNATIVE_HERO_GIFT,
                                  HERO, 1204010, 1)
    assert progress(store, GIFT) == (1, 0)


def test_claimed_task_pays_gift_items_favor_exp_and_repaints(wish):
    store, economy, _, ctx = wish
    assert economy.accept_favor_tasks(1, [CARRY]) == 10
    with economy.transaction():
        economy.credit_favor_task(1, "clear:run", economy.TASK_EVENT_CARRY_HERO_CUSTOMS_PASS,
                                  HERO, 2130501)
    before = store.get(1)["snapshot"]["heroes"][0].get("favor", {"level": 1, "exp": 0})
    out = asyncio.run(economy.handle(ctx, packet(
        {"data": [FINISH_REQUEST.encode({"taskId": CARRY, "type": 6})]},
        name="C2L_FinishGameTask")))
    result = FINISH_RESULT.decode(out.values["data"][0])
    assert result["code"] == 10 and result["taskId"] == CARRY
    # 道具那半: 任务自己的 Gift 组。
    items = REWARD.decode(result["rewardData"]).get("rewardItem", [])
    assert {r["itemId"] for r in map(REWARD_ITEM.decode, items)}
    assert store.db.execute("SELECT claimed FROM favor_daily_tasks WHERE player_id=1 AND task_id=?",
                            (CARRY,)).fetchone()[0] == 1
    # 好感那半: FavorService.grant_favor 把 FavorabilityGift 加到这位神格身上。
    assert store.get(1)["snapshot"]["heroes"][0]["favor"] != before
    pushed = {p.message_name for p in out.pushes}
    assert "L2C_FavorChangeInfo" in pushed  # 角色页进度条
    assert "L2C_GameTask" in pushed         # 心愿任务列表本身重画
    # 再领一次只能失败, 不能二次发奖。
    again = asyncio.run(economy.handle(ctx, packet(
        {"data": [FINISH_REQUEST.encode({"taskId": CARRY, "type": 6})]},
        name="C2L_FinishGameTask")))
    assert FINISH_RESULT.decode(again.values["data"][0])["code"] == 13


def test_gift_path_credits_the_send_designative_hero_gift_task(wish):
    store, economy, _, ctx = wish
    assert economy.accept_favor_tasks(1, [GIFT]) == 10
    with store.db:
        store.db.execute("INSERT OR REPLACE INTO inventory VALUES (1,1204010,1)")
    favor = FavorService(store, economy, clock=lambda: DAY)
    economy.attach_favor(favor)
    asyncio.run(favor.handle(ctx, packet({"opt": 2, "optionId": 1204010, "heroId": HERO, "num": 1},
                                        name="C2L_AddFavor")))
    assert progress(store, GIFT) == (1, 0)


def test_battle_entry_keeps_the_team_settle_reads(wish):
    """settle 读的是存下来的 L2C_FightData.fightHeros, 这里钉住那份数据真的在。"""
    store, economy, _, ctx = wish
    battle = BattleService(store, economy)
    asyncio.run(battle.enter(ctx, packet(request())))
    row = store.db.execute(
        "SELECT response FROM battle_entries ORDER BY rowid DESC LIMIT 1").fetchone()
    fight = FIGHT_DATA.decode(BATTLE_SCHEMAS["L2C_FightData"].decode(row[0])["data"])
    carried = [FIGHT_HERO.decode(raw)["id"] for raw in fight.get("fightHeros", ())]
    assert HERO in carried
