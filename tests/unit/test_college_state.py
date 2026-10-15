"""College snapshot initialization and reload without active-player DB access."""

import asyncio

from tests.unit.test_battle import packet
from x2server.messages.core import MODULE_STATUS as MODULE_STATUS_PROTO
from x2server.messages.lobby import (BUILDING_BASE_INFO, GROWTH_BASE, UNLOCK_EXPLORE_RUIN, PRAY_QUEUE)
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
    assert len(first.values["civilization"]) == 8  # All wonders incl. 728 state row.
    # Absent repeated fields decode to null client-side (SilentOrbit); the
    # snapshot always carries one zero-filled idle entry per queue list.
    for field in ("exploreList", "trainingList"):
        assert len(first.values[field]) == 6 and first.values[field] != b""
    prayer_rows = [PRAY_QUEUE.decode(row) for row in first.values["prayQueue"]]
    assert {row["buildingId"] for row in prayer_rows} == set(range(721, 729))
    assert all(row["prayStatus"] == 0 for row in prayer_rows)
    assert first.values["buildQueue"] is not None and first.values["wonderQueue"] is not None
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
    for field in ("buildingList", "civilization", "exploreList", "trainingList",
                  "buildQueue", "wonderQueue", "prayQueue"):
        assert field in login_growth, field
    assert login_growth["buildingList"] == query_growth["buildingList"]
    assert login_growth["civilization"] == query_growth["civilization"]
    assert login_growth["trainingList"] == query_growth["trainingList"]
    restored_store.close()

def test_entry_queries_ruins_and_alchemy_initial_state(tmp_path):
    """623/591 close the base entry: code=10 idempotent queries of stored state."""
    path = tmp_path / "college-entry.db"
    store = PlayerStore(path)
    store.login("college-entry", 1, 0)
    repo = CollegeStateRepository(store, FixedClock())
    ctx = DispatchContext("entry", "local", SessionState("entry", "session", player_id=1))
    lobby = LobbyService(college=repo)

    first = asyncio.run(lobby.query(ctx, packet({}, 1, "C2L_UnlockExploreRuin")))
    repeat = asyncio.run(lobby.query(ctx, packet({}, 2, "C2L_UnlockExploreRuin")))
    assert first.message_name == "L2C_UnlockExploreRuin"
    assert first.values["code"] == 10
    # The official GlobalParamString.AlchemyExploreDefault unlocks the first ruin.
    assert first.values["unlockExploreRuin"] == [UNLOCK_EXPLORE_RUIN.encode(
        {'queueCount': 0, 'exp': 0, 'ruinId': 34001})]
    assert repeat.values == first.values

    # 591 moved to CollegeService; its initial state ships the six starter
    # recipes, five customers, three production slots and the six elements.
    from x2server.player.college import CollegeService
    flows = CollegeService(repo)
    alchemy = asyncio.run(flows.dispatch(ctx, packet({}, 3, "C2L_AlchemyMainData")))
    assert alchemy.message_name == "L2C_AlchemyMainData"
    assert alchemy.values["code"] == 10
    assert len(alchemy.values["recipeIdExp"]) == 6
    assert len(alchemy.values["customeres"]) == 5
    assert len(alchemy.values["productionBars"]) == 3
    assert len(alchemy.values["elements"]) == 6
    assert alchemy.values["buffType"] == 0 and alchemy.values["buffCount"] == 0
    repeat_alchemy = asyncio.run(flows.dispatch(ctx, packet({}, 4, "C2L_AlchemyMainData")))
    assert repeat_alchemy.values == alchemy.values

    # Wire round-trips keep every repeated list constructed and empty.
    from x2server.messages.college import COLLEGE_SCHEMAS
    wire = COLLEGE_SCHEMAS["L2C_AlchemyMainData"].encode(alchemy.values)
    decoded = COLLEGE_SCHEMAS["L2C_AlchemyMainData"].decode(wire)
    assert decoded["code"] == 10
    # Round-trip preserves the non-null initial alchemy lists.
    assert len(decoded["customeres"]) == 5 and len(decoded["elements"]) == 6

    # A persisted non-empty ruin list is served verbatim after relogin.
    state = repo.load(1)
    state["ruins"] = [{"ruinId": 34001, "exp": 12, "queueCount": 1}]
    repo.save(1, state)
    restored_store = PlayerStore(path)
    restored = LobbyService(college=CollegeStateRepository(restored_store, FixedClock()))
    resumed = asyncio.run(restored.query(ctx, packet({}, 5, "C2L_UnlockExploreRuin")))
    assert resumed.values["code"] == 10
    assert UNLOCK_EXPLORE_RUIN.decode(resumed.values["unlockExploreRuin"][0]) == {
        "ruinId": 34001, "exp": 12, "queueCount": 1}
    restored_store.close()


def test_login_snapshot_marks_growth_base_open(tmp_path):
    """IsCollegeEnable gates the entry on ModuleStatus.GrowthBaseStatus == 1."""
    from x2server.messages.core import PLAYER_DATA
    from x2server.player.login import LoginService
    store = PlayerStore(tmp_path / "college-status.db")
    store.login("college-status", 1, 0)
    push = LoginService.snapshot_push(store.get(1))
    data = PLAYER_DATA.decode(PLAYER_DATA.encode(push.values))
    status = MODULE_STATUS_PROTO.decode(data["ModuleStatus"])
    assert status["GrowthBaseStatus"] == 1
    store.close()


def test_college_flow_chain_answers(tmp_path):
    """Full network chain: queries answer real state, mutations answer E_ERROR_OPT."""
    from x2server.messages.college import COLLEGE_SCHEMAS
    from x2server.player.college import CollegeService
    path = tmp_path / "college-chain.db"
    store = PlayerStore(path)
    store.login("college-chain", 1, 0)
    repo = CollegeStateRepository(store, FixedClock())
    ctx = DispatchContext("chain", "local", SessionState("chain", "session", player_id=1))
    flows = CollegeService(repo)

    slot = asyncio.run(flows.dispatch(ctx, packet({"posIndex": 2}, 1, "C2L_SingleCustomerInfo")))
    assert slot.values["code"] == 10 and slot.values["posIndex"] == 2
    assert slot.values["transactionNum"] == 1
    customer = slot.values["customere"]
    decoded = next(s for n, s in COLLEGE_SCHEMAS.items()
                   if n == "CustomerInfo") if False else None
    from x2server.messages.lobby import CUSTOMER_INFO
    info = CUSTOMER_INFO.decode(customer)
    assert info["questId"] >= 35303 and info["type"] == 2  # AlchemyType.TRANSACTION
    assert len(info["itemId"]) == 1 and info["adviseItemId"] > 0
    # Independent native-wire assertions: CustomerInfo.Serialize 0x38f05a8
    # uses fields 3=type, 4=advisor, 5=param, 6=result, 7=quantity.
    from x2server.protocol.protobuf import decode_varint
    def native_customer(wire):
        fields, offset = {}, 0
        while offset < len(wire):
            tag, offset = decode_varint(wire, offset)
            assert tag & 7 == 0
            value, offset = decode_varint(wire, offset)
            fields.setdefault(tag >> 3, []).append(value)
        return fields
    native = native_customer(customer)
    assert native[3] == [2] and native[7] == [1]
    assert native[4] == [info['adviseItemId']]
    main = asyncio.run(flows.dispatch(ctx, packet({}, 20, 'C2L_AlchemyMainData')))
    assert all(native_customer(raw)[3] == [2] and native_customer(raw)[7] == [1]
               for raw in main.values['customeres'])
    # Deterministic per (player, slot): repeat and relogin answer identically.
    again = asyncio.run(flows.dispatch(ctx, packet({"posIndex": 2}, 2, "C2L_SingleCustomerInfo")))
    assert again.values["customere"] == customer
    other_slot = asyncio.run(flows.dispatch(ctx, packet({"posIndex": 1}, 3, "C2L_SingleCustomerInfo")))
    assert CUSTOMER_INFO.decode(other_slot.values["customere"])["questId"] != info["questId"]

    first_recharge = asyncio.run(flows.dispatch(ctx, packet({}, 4, "C2L_QueryFirstReCharge")))
    assert first_recharge.values == {"code": 10, "state": 0}
    accumulate = asyncio.run(flows.dispatch(ctx, packet({}, 5, "C2L_QueryAccumulateReCharge")))
    assert accumulate.values["code"] == 10 and accumulate.values["totalMoney"] == 0
    assist = asyncio.run(flows.dispatch(ctx, packet({"type": 1}, 6, "C2L_HelpPowerSpeedValid")))
    assert assist.values == {"code": 13, "type": 1}  # no active construction
    help_speed = asyncio.run(flows.dispatch(ctx, packet({"helpPower": 0}, 7, "C2L_HelpPowerSpeed")))
    assert help_speed.values["code"] == 10 and help_speed.values["helpPowerSpeedParam"] == []

    # Mutations refuse with E_ERROR_OPT so the client bubbles instead of hanging.
    upgrade = asyncio.run(flows.dispatch(ctx, packet({"buildingId": 701, "type": 1}, 8,
                                                    "C2L_BuildingUpgrade")))
    assert upgrade.values["code"] == 13
    train = asyncio.run(flows.dispatch(ctx, packet({"trainId": 0, "heroId": 1003}, 9,
                                                   "C2L_StartTrain")))
    assert train.values["code"] == 13
    store.close()


def test_exchange_power_fetches_stored_causality(tmp_path):
    """238/249: 从启明之塔取出已存储因果, 每点消耗 5 星能, 体力加回 (允许超上限)。"""
    from x2server.player.college import CollegeService, CollegeStateRepository
    from x2server.player.economy import EconomyService

    store = PlayerStore(tmp_path / "college-power.db")
    p = store.login("college-power", 1, 0)
    now = 1_800_000_000
    store.save_snapshot(1, dict(p["snapshot"], level=60,
        mobility={"power": 149, "recover_anchor": now}), p["revision"])
    repo = CollegeStateRepository(store, FixedClock())
    economy = EconomyService(store, clock=lambda: now)
    economy.college = repo
    state = repo.load(1)
    state["extra_power"] = 3 * 1000  # 3 因果 (单位毫因果)
    state["star_energy"] = 40
    repo.save(1, state)
    ctx = DispatchContext("power", "local", SessionState("power", "session", player_id=1))
    flows = CollegeService(repo, economy=economy)

    reply = asyncio.run(flows.dispatch(ctx, packet({"power": 3}, 1, "C2L_ExchangePower")))
    assert reply.message_name == "L2C_ExchangePower"
    assert reply.values == {"code": 10, "power": 3, "extraPower": 0}
    assert repo.load(1)["extra_power"] == 0
    assert repo.load(1)["star_energy"] == 40 - 3 * 5
    # 取回的体力可以超过上限, 原样保留。
    assert store.get(1)["snapshot"]["mobility"]["power"] == 152

    # 塔里已无因果 → COLLEGE_NO_ITEM (22), 不改存档。
    empty = asyncio.run(flows.dispatch(ctx, packet({"power": 1}, 2, "C2L_ExchangePower")))
    assert empty.values["code"] == 22
    assert repo.load(1)["star_energy"] == 25
    store.close()
