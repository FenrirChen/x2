"""College snapshot initialization and reload without active-player DB access."""

import asyncio

from tests.unit.test_battle import packet
from x2server.messages.lobby import BUILDING_BASE_INFO, GROWTH_BASE
from x2server.player.college import CollegeStateRepository
from x2server.player.lobby import LobbyService
from x2server.player.store import PlayerStore
from x2server.player.login import LoginService
from x2server.network.dispatcher import DispatchContext
from x2server.network.session import SessionState


class FixedClock:
    def now(self):
        return 1_800_000_000


def test_growth_base_static_initial_and_persistence(tmp_path):
    path = tmp_path / "college.db"
    store = PlayerStore(path)
    store.login("college-test", 1, 0)
    repo = CollegeStateRepository(store, FixedClock())
    ctx = DispatchContext("test", "local", SessionState("test", "session", player_id=1))
    lobby = LobbyService(college=repo)
    first = asyncio.run(lobby.query(ctx, packet({}, 1, "C2L_QueryGrowthBase")))
    second = asyncio.run(lobby.query(ctx, packet({}, 2, "C2L_QueryGrowthBase")))
    assert first.values == second.values
    assert GROWTH_BASE.decode(GROWTH_BASE.encode(first.values)) == GROWTH_BASE.decode(GROWTH_BASE.encode(repo.growth_base(1)))
    assert len(first.values["buildingList"]) == 8
    assert len(first.values["civilization"]) == 7  # 728 BuildingOpen is unknown.
    assert not first.values["exploreList"] and not first.values["trainingList"]
    assert BUILDING_BASE_INFO.decode(first.values["buildingList"][0]) == {
        "buildingId": 701, "buildingLevel": 1, "buildingStar": 1}
    row = store.db.execute("SELECT created_at,updated_at FROM college_state WHERE player_id=1").fetchone()
    assert tuple(row) == (1_800_000_000, 1_800_000_000)
    state = repo.load(1)
    state["star_energy"] = 17
    repo.save(1, state)
    store.close()

    restored_store = PlayerStore(path)
    restored = CollegeStateRepository(restored_store, FixedClock())
    assert restored.growth_base(1)["starEnergy"] == 17
    assert len(restored.growth_base(1)["buildingList"]) == 8
    class Identity:
        account = "college-test"

        @staticmethod
        def validates_game_identity(player_id, token):
            return player_id == 1 and token == "test"

        @staticmethod
        def account_for_player(player_id):
            return "college-test"

    relog_context = DispatchContext("relog", "local", SessionState("relog", "session"))
    login = asyncio.run(LoginService(Identity(), restored_store, clock=FixedClock(), college=restored).login(
        relog_context, packet({"id": 1, "token": "test"}, 3, "C2L_Login")))
    query = asyncio.run(LobbyService(college=restored).query(relog_context,
        packet({}, 4, "C2L_QueryGrowthBase")))
    login_growth = GROWTH_BASE.decode(login.values["growthBase"])
    query_growth = GROWTH_BASE.decode(GROWTH_BASE.encode(query.values))
    for field in ("buildingList", "civilization"):
        assert field in login_growth
    for field in ("exploreList", "trainingList", "buildQueue",
                  "wonderQueue", "prayQueue"):
        assert field not in login_growth
    assert login_growth["buildingList"] == query_growth["buildingList"]
    assert login_growth["civilization"] == query_growth["civilization"]
    restored_store.close()
