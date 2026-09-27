"""Favor mutations use official single-value gifts and one SQLite transaction."""
import asyncio
from pathlib import Path
import pytest

from tests.unit.test_battle import packet
from tests.unit.test_economy import env
from x2server.messages.core import HERO_DATA
from x2server.messages.favor import FAVOR, FAVOR_MAP_ENTRY
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
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1204000").fetchone()[0] == 0
    assert store.get(1)["snapshot"]["heroes"][0]["favor"] == {"level": 1, "exp": 10}
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


def test_uncertain_gift_gain_never_consumes(env):
    store, economy, ctx = env
    service = FavorService(store, economy)
    store.db.execute("INSERT INTO inventory VALUES (1,1204003,5)")
    answer = asyncio.run(service.handle(ctx, packet({"opt": 2, "optionId": 1204003,
        "heroId": 1003, "num": 1}, name="C2L_AddFavor")))
    assert answer.values["code"] == 13
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1204003").fetchone()[0] == 5
    assert "favor" not in store.get(1)["snapshot"]["heroes"][0]


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
