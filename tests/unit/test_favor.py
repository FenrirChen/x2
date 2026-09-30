"""Favor mutations use official single-value gifts and one SQLite transaction."""
import asyncio
from pathlib import Path
import pytest

from tests.unit.test_battle import packet
from tests.unit.test_economy import env
from x2server.messages.core import HERO_DATA
from x2server.messages.favor import FAVOR, FAVOR_MAP_ENTRY, HERO_ARCHIVE
from x2server.player.favor import FavorService
from x2server.player.hero import encode_hero_data
from x2server.player.login import LoginService
from x2server.player.store import PlayerStore


def test_favor_gift_archive_and_relog(env):
    store, economy, ctx = env
    service = FavorService(store, economy)
    assert HERO_DATA.decode(encode_hero_data(store.get(1)["snapshot"]["heroes"][0]))["archives"]
    assert asyncio.run(service.handle(ctx, packet({"heroID": 1003}, name="C2L_QueryHeroArchives"))).values["code"] == 10
    assert asyncio.run(service.handle(ctx, packet({"heroId": 9999}, name="C2L_QueryHeroJournal"))).values["code"] == 13
    with store.db:
        store.db.execute("INSERT INTO inventory VALUES (1,1204000,2)")
    request = {"opt": 2, "optionId": 1204000, "heroId": 1003, "num": 2}
    answer = asyncio.run(service.handle(ctx, packet(request, name="C2L_AddFavor")))
    assert answer.values["code"] == 10
    assert answer.values["newExp"] == 10
    assert answer.values["newLevel"] == 1
    assert answer.values["giftsTimes"] == 2
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1204000").fetchone()[0] == 0
    assert store.get(1)["snapshot"]["heroes"][0]["favor"] == {"level": 1, "exp": 10}
    assert store.get(1)["snapshot"]["heroes"][0]["favor_gifts"]["count"] == 2
    assert asyncio.run(service.handle(ctx, packet(request, name="C2L_AddFavor"))).values["code"] == 13
    assert asyncio.run(service.handle(ctx, packet({"heroID": 1003, "archivesID": 5100301},
        name="C2L_UnlockHeroArchives"))).values["code"] == 10
    assert 5100301 in store.get(1)["snapshot"]["heroes"][0]["favor_archives"]
    assert asyncio.run(service.handle(ctx, packet({"heroId": 1003}, name="C2L_FavorBreak"))).values["code"] == 13
    assert asyncio.run(service.handle(ctx, packet({"opt": 2, "optionId": 1204000,
        "heroId": 1004, "num": 1}, name="C2L_AddFavor"))).values["code"] == 13
    encoded = LoginService.snapshot_push(store.get(1)).values
    entry = FAVOR_MAP_ENTRY.decode(encoded["favor"][0])
    assert FAVOR.decode(entry["Value"]) == {"level": 1, "exp": 10}
    reopened = PlayerStore(Path(store.db.execute("PRAGMA database_list").fetchone()[2]))
    try:
        from x2server.player.economy import EconomyService
        service = FavorService(reopened, EconomyService(reopened))
        assert reopened.get(1)["snapshot"]["heroes"][0]["favor"]["exp"] == 10
        assert 5100301 in reopened.get(1)["snapshot"]["heroes"][0]["favor_archives"]
    finally:
        reopened.close()


def test_two_value_gift_uses_base_gain_and_consumes(env):
    store, economy, ctx = env
    service = FavorService(store, economy)
    store.db.execute("INSERT INTO inventory VALUES (1,1204003,5)")
    answer = asyncio.run(service.handle(ctx, packet({"opt": 2, "optionId": 1204003,
        "heroId": 1003, "num": 1}, name="C2L_AddFavor")))
    assert answer.values["code"] == 10
    assert answer.values["newExp"] == service.gifts[1204003]["EffData"][0]
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1204003").fetchone()[0] == 4


def test_preferred_gift_doubles_favor_and_opens_archive(env):
    store, economy, ctx = env
    service = FavorService(store, economy)
    favorite = 1204009
    assert favorite in service.favorites[1003]
    base = service.gifts[favorite]["EffData"][0]
    count = (210 + base * 2 - 1) // (base * 2)
    store.db.execute("INSERT INTO inventory VALUES (?,?,?)", (1, favorite, count))
    result = asyncio.run(service.handle(ctx, packet({"opt": 2, "optionId": favorite,
        "heroId": 1003, "num": count}, name="C2L_AddFavor")))
    assert result.values["code"] == 10
    assert result.values["newExp"] == base * 2 * count
    assert result.values["newLevel"] >= 2
    hero_push = next(push for push in result.pushes if push.message_name == "L2C_HeroUpdate")
    archives = [HERO_ARCHIVE.decode(raw) for raw in HERO_DATA.decode(hero_push.values["heros"][0])["archives"]]
    assert next(row for row in archives if row["fileId"] == 5100303)["status"] == 2
    query = asyncio.run(service.handle(ctx, packet({"heroID": 1003}, name="C2L_QueryHeroArchives")))
    assert query.values["needRefresh"] is True
    assert query.pushes[0].message_name == "L2C_HeroUpdate"


def test_favor_break_charges_material_before_lifting_level_cap(env):
    store, economy, ctx = env
    service = FavorService(store, economy)
    player = store.get(1)
    snapshot = player["snapshot"]
    snapshot["heroes"][0]["favor"] = {"level": 4, "exp": 840}
    store.save_snapshot(1, snapshot, player["revision"])
    request = packet({"heroId": 1003}, name="C2L_FavorBreak")
    assert asyncio.run(service.handle(ctx, request)).values["code"] == 13
    assert store.get(1)["snapshot"]["heroes"][0]["favor"]["level"] == 4
    store.db.execute("INSERT INTO inventory VALUES (1,1283001,20)")
    result = asyncio.run(service.handle(ctx, request))
    assert result.values["code"] == 10
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1283001").fetchone()[0] == 0
    assert store.get(1)["snapshot"]["heroes"][0]["favor"]["level"] == 5
    assert asyncio.run(service.handle(ctx, request)).values["code"] == 13


def test_gift_charge_rolls_back_when_state_write_fails(env, monkeypatch):
    store, economy, ctx = env
    service = FavorService(store, economy)
    with store.db:
        store.db.execute("INSERT INTO inventory VALUES (1,1204000,2)")
    def fail(*args):
        raise RuntimeError("state write failed")
    monkeypatch.setattr(economy, "save_snapshot", fail)
    with pytest.raises(RuntimeError):
        asyncio.run(service.handle(ctx, packet({"opt": 2, "optionId": 1204000,
            "heroId": 1003, "num": 1}, name="C2L_AddFavor")))
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1204000").fetchone()[0] == 2
    assert "favor" not in store.get(1)["snapshot"]["heroes"][0]


def test_tap_interaction_completes_daily_interactive_task(env):
    """The daily tap sends opt=1, heroId=0, optionId=InteractiveID (46001 -> 1003)."""
    store, economy, ctx = env
    service = FavorService(store, economy)
    from x2server.messages.economy import TASK
    answer = asyncio.run(service.handle(ctx, packet(
        {"opt": 1, "optionId": 46001, "heroId": 0, "num": 0}, name="C2L_AddFavor")))
    assert answer.values["code"] == 10
    assert answer.values["heroId"] == 1003
    assert store.db.execute("SELECT count FROM favor_touch_log WHERE player_id=1 AND hero_id=1003"
                            ).fetchone()[0] == 1
    task_row = next(TASK.decode(raw) for raw in economy.task_values(1, 1)["taskList"]
                    if TASK.decode(raw)["taskId"] == 630010)
    assert task_row["taskProgress"] == 1 and task_row["taskStatus"] == 3
    # An interaction id whose god is not owned falls back to the showcase hero.
    fallback = asyncio.run(service.handle(ctx, packet(
        {"opt": 1, "optionId": 48707, "heroId": 0, "num": 0}, name="C2L_AddFavor")))
    assert fallback.values["code"] == 10 and fallback.values["heroId"] == 1003
    # Three taps per day: the fourth is rejected and never advances the task.
    assert asyncio.run(service.handle(ctx, packet(
        {"opt": 1, "optionId": 46001, "heroId": 0, "num": 0}, name="C2L_AddFavor"))).values["code"] == 10
    capped = asyncio.run(service.handle(ctx, packet(
        {"opt": 1, "optionId": 46001, "heroId": 0, "num": 0}, name="C2L_AddFavor")))
    assert capped.values["code"] == 13
    task_row = next(TASK.decode(raw) for raw in economy.task_values(1, 1)["taskList"]
                    if TASK.decode(raw)["taskId"] == 630010)
    assert task_row["taskProgress"] == 1  # capped tap must not over-count
