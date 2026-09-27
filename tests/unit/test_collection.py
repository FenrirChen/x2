"""Official collection conditions, rewards, and durable claims."""
import asyncio
from pathlib import Path

from tests.unit.test_battle import packet
from tests.unit.test_economy import env, rewards
from x2server.player.collection import CollectionService
from x2server.player.economy import EconomyService
from x2server.player.store import PlayerStore


def test_collection_claim_requires_every_owned_hero_and_persists(env):
    store, economy, ctx = env
    service = CollectionService(store, economy)
    query = lambda: asyncio.run(service.query(ctx, packet({}, name="C2L_QueryCollectionAward")))
    claim = lambda: asyncio.run(service.claim(ctx, packet({"collectionAwardID": 133101},
        name="C2L_GetCollectionAward")))
    assert query().values == {"awardID": []}
    assert claim().values["code"] == 13
    p = store.get(1)
    heroes = p["snapshot"]["heroes"] + [
        {"id": id_, "state": state, "level": 1, "star": 1}
        for id_, state in ((1010, 2), (1015, 2), (1021, 1))]
    store.save_snapshot(1, dict(p["snapshot"], heroes=heroes), p["revision"])
    assert claim().values["code"] == 13
    p = store.get(1)
    p["snapshot"]["heroes"][-1]["state"] = 2
    store.save_snapshot(1, p["snapshot"], p["revision"])
    first = claim()
    assert first.values["code"] == 10
    assert first.values["awardID"] == [133101]
    assert rewards(first.values["rewardData"]) == economy.gifts([785011])
    assert query().values == {"awardID": [133101]}
    assert claim().values["code"] == 13
    assert store.db.execute("SELECT COUNT(*) FROM economy_grants WHERE player_id=1 AND source='collection:133101'").fetchone()[0] == 1
    reopened = PlayerStore(Path(store.db.execute("PRAGMA database_list").fetchone()[2]))
    try:
        service = CollectionService(reopened, EconomyService(reopened))
        assert service.claimed(1) == [133101]
    finally:
        reopened.close()
