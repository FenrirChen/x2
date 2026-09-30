import asyncio
from tests.unit.test_economy import env
from tests.unit.test_battle import packet
from x2server.player.favor import FavorService


def test_fetter_cost_gate_and_saved_upgrade(env):
    store, economy, ctx = env
    service = FavorService(store, economy)
    req = packet({"mainHeroId": 1003, "positionId": 1}, name="C2L_UpgradeFetters")
    assert asyncio.run(service.handle(ctx, req)).values["code"] == 13
    p = store.get(1)
    p["snapshot"]["heroes"][0]["level"] = 30
    p["snapshot"]["gold"] = 10000
    store.save_snapshot(1, p["snapshot"], p["revision"])
    assert asyncio.run(service.handle(ctx, req)).values["code"] == 10
    assert store.get(1)["snapshot"]["gold"] == 0
    assert store.get(1)["snapshot"]["heroes"][0]["favor_fetters"] == {"1": 1}
    assert asyncio.run(service.handle(ctx, req)).values["code"] == 13


def test_period_repair_preserves_claims_and_progress(env):
    store, economy, _ = env
    economy.ensure_periods(1)
    with store.db:
        store.db.execute("DELETE FROM economy_tasks WHERE player_id=1 AND task_id=630006")
        store.db.execute("UPDATE economy_tasks SET progress=1000,claimed=1 WHERE player_id=1 AND task_id=630019")
    economy.ensure_periods(1)
    economy.ensure_periods(1)
    assert store.db.execute("SELECT COUNT(*) FROM economy_tasks WHERE player_id=1 AND task_id=630006").fetchone()[0] == 1
    assert tuple(store.db.execute("SELECT progress,claimed FROM economy_tasks WHERE player_id=1 AND task_id=630019").fetchone()) == (1000, 1)
