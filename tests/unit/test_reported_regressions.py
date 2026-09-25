import asyncio
from datetime import datetime

from tests.unit.test_battle import packet
from tests.unit.test_economy import env
from x2server.messages.battle import FIGHT_DATA, FIGHT_HERO, PROFILE_HERO
from x2server.messages.core import HERO_DATA, HERO_GOD_EQUIP, INT_PAIR
from x2server.messages.wish import CARD_POOL
from x2server.player.battle import BattleService
from x2server.player.economy import EconomyService
from x2server.player.hero import encode_hero_data
from x2server.player.progression import ProgressionService
from x2server.player.server_clock import BEIJING, ServerClock
from x2server.player.wish import WishService


def stamp(hour):
    return int(datetime(2026, 9, 24, hour, tzinfo=BEIJING).timestamp())


def test_jewel_pity_shared_and_display_advances(env, monkeypatch):
    store, economy, context = env
    player = store.get(1)
    store.save_snapshot(1, dict(player["snapshot"], crystal=1000), player["revision"])
    wish = WishService(store, economy, clock=ServerClock(lambda: WishService.ANCHOR + 1))
    monkeypatch.setattr(wish, "_pick", lambda pool, group="common":
                        {"item_id": 1250011, "quantity": 1})
    first = wish.groups["jewel"][0]
    second = wish.groups["jewel"][1]
    result = asyncio.run(wish.draw(context, packet({"drawnId": first, "drawType": 0},
                                                   name="C2L_LuckDraw")))
    assert result.values["code"] == 10
    assert result.values["securityNum"] == 1
    assert wish.state(1, second)[4] == 1
    assert wish.state(1, wish.groups["up"][0])[4] == 0
    cards = [CARD_POOL.decode(raw) for raw in wish.values(1)["cardPoolList"]]
    assert {card["poolId"]: card["securityNum"] for card in cards}[second] == 1


def test_artifact_jewel_uses_exact_socket_and_returns_replaced_item(env):
    store, economy, context = env
    service = ProgressionService(store, economy)
    snapshot = store.get(1)["snapshot"]
    snapshot["heroes"][0]["god_equip"] = {"id": 1503, "level": 0, "star": 1}
    economy.save_snapshot(1, snapshot)
    store.db.execute("INSERT INTO inventory VALUES (1,1250011,1)")
    store.db.execute("INSERT INTO inventory VALUES (1,1250021,1)")
    def beset(jewel, hole, request_id):
        return asyncio.run(service.handle(context, packet(
            {"opt": 2, "heroId": 1003, "jewelId": jewel, "holeId": hole},
            request_id=request_id, name="C2L_Artifact")))
    assert beset(1250011, 5, 101).values["code"] == 10
    assert beset(1250021, 6, 102).values["code"] == 10
    hero = store.get(1)["snapshot"]["heroes"][0]
    wire = HERO_GOD_EQUIP.decode(HERO_DATA.decode(encode_hero_data(hero))["godEquip"])
    assert [INT_PAIR.decode(raw) for raw in wire["jewel"]] == [
        {"Key": 5, "Value": 1250011}, {"Key": 6, "Value": 1250021}]
    assert beset(1250021, 5, 103).values["code"] == 13
    assert beset(0, 5, 104).values["code"] == 10
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1250011").fetchone()[0] == 1
    assert store.get(1)["snapshot"]["heroes"][0]["god_equip"]["jewels"] == {"6": 1250021}


def test_owned_multicharacter_team_enters_battle(env):
    store, economy, context = env
    snapshot = store.get(1)["snapshot"]
    snapshot["heroes"].append({"id": 1004, "state": 2, "level": 1, "star": 3})
    economy.save_snapshot(1, snapshot)
    service = BattleService(store, economy)
    section = 2110801
    result = asyncio.run(service.enter(context, packet({
        "missionId": section, "chapter": economy.sections[section]["ChapterID"],
        "sceneId": economy.sections[section]["Maps"][0],
        "heros": [PROFILE_HERO.encode({"heroId": i, "leader": int(i == 1003)})
                  for i in (1003, 1004)]}, name="C2L_FightData")))
    assert result.values["result"] == 10
    assert [FIGHT_HERO.decode(raw)["id"] for raw in FIGHT_DATA.decode(result.values["data"])["fightHeros"]] == [1003, 1004]


def test_timed_online_tasks_complete_only_in_their_beijing_windows(env):
    store, _, _ = env
    now = [stamp(11)]
    economy = EconomyService(store, clock=lambda: now[0])
    assert economy.task_values(1, 1)["code"] == 10
    assert dict(store.db.execute("SELECT task_id,progress FROM economy_tasks WHERE task_id IN (630021,630022)")) == {630021: 0, 630022: 0}
    now[0] = stamp(12)
    economy.task_values(1, 1)
    assert dict(store.db.execute("SELECT task_id,progress FROM economy_tasks WHERE task_id IN (630021,630022)")) == {630021: 1, 630022: 0}
    now[0] = stamp(18)
    economy.task_values(1, 1)
    assert dict(store.db.execute("SELECT task_id,progress FROM economy_tasks WHERE task_id IN (630021,630022)")) == {630021: 1, 630022: 1}
    before = store.get(1)["snapshot"]["mobility"]["power"]
    assert economy.claim(1, 630021, 1)["code"] == 10
    assert economy.claim(1, 630022, 1)["code"] == 10
    assert economy.claim(1, 630021, 1)["code"] == 10
    assert store.get(1)["snapshot"]["mobility"]["power"] > before
