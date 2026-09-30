import asyncio

import pytest

from x2server.messages.battle import BATTLE_SCHEMAS, CHECKOUT, DROP_DATA, PROFILE_HERO, FIGHT_DATA, FIGHT_PROFILE, FIGHT_HERO, HERO_ATTR
from x2server.network.dispatcher import DispatchContext
from x2server.network.session import SessionState
from x2server.player.battle import BattleService
from x2server.player.store import PlayerStore
from x2server.protocol.codec import ProtocolCodec
from x2server.protocol.errors import ProtocolError
from x2server.protocol.headers import RequestHeader


def packet(values, request_id=1, name="C2L_FightData"):
    codec = ProtocolCodec()
    return codec.decode(codec.encode(name, values, RequestHeader(request_id=request_id)), RequestHeader).packet


def request(**changes):
    return dict(missionId=2110801, chapter=2010100, sceneId=2210801,
                heros=[PROFILE_HERO.encode({"heroId": 1003, "leader": 1})], **changes)


def test_moon_phase_entries_preserve_selected_scene_and_expert_mode(tmp_path):
    store = PlayerStore(tmp_path / "moon-phases.db")
    player = store.login("moon-phases", 1, 0)
    store.save_snapshot(1, dict(player["snapshot"], level=60,
        heroes=[{"id": 1003, "state": 2, "level": 1, "star": 1}]), player["revision"])
    context = DispatchContext("test", "local", SessionState("test", "moon-phases", player_id=1))
    service = BattleService(store)
    levels = (15, 23, 31, 40, 53, 64, 78, 89, 103, 290)
    for difficulty, (section, level) in enumerate(zip(range(2110851, 2110861), levels), start=1):
        static = service.catalog.sections[section]
        assert static["DifficultyLevel"] == difficulty
        values = request(expertMode=True)
        values.update(missionId=section, chapter=static["ChapterID"], sceneId=static["Maps"][0])
        result = asyncio.run(service.enter(context, packet(values, difficulty)))
        assert result.values["result"] == 10
        wire = BATTLE_SCHEMAS["L2C_FightData"].encode(result.values)
        assert BATTLE_SCHEMAS["L2C_FightData"].decode(wire)["monsterInitLevel"] == level
        fight = FIGHT_DATA.decode(result.values["data"])
        profile = FIGHT_PROFILE.decode(result.values["fightDataProfile"])
        assert fight["missionId"] == profile["missionId"] == section
        assert profile["sceneId"] == static["Maps"][0]
        assert fight["expertMode"] is True and profile["expertMode"] is True
        assert asyncio.run(service.enter(context, packet(values, difficulty))).values == result.values
    # Switching back to a normal story entry must also reach the client.
    result = asyncio.run(service.enter(context, packet(request(expertMode=False), 11)))
    assert result.values["result"] == 10
    assert FIGHT_DATA.decode(result.values["data"])["expertMode"] is False
    assert FIGHT_PROFILE.decode(result.values["fightDataProfile"])["expertMode"] is False
    assert result.values["monsterInitLevel"] == 2
    store.close()


def test_entry_replay_persistence_and_no_economy_changes(tmp_path):
    path = tmp_path / "player.db"
    store = PlayerStore(path)
    player = store.login("lab", 1, 0)
    store.save_snapshot(1, dict(player["snapshot"], level=60, mobility={"power": 149},
                               heroes=[{"id": 1003, "state": 2, "level": 1, "star": 1}]), player["revision"])
    before = store.get(1)
    context = DispatchContext("test", "local", SessionState("test", "session", player_id=1))
    service = BattleService(store)
    first = asyncio.run(service.enter(context, packet(request())))
    assert first.values["result"] == 10
    data = FIGHT_DATA.decode(first.values["data"])
    assert data["missionId"] == 2110801
    hero = FIGHT_HERO.decode(data["fightHeros"][0])
    assert hero["id"] == 1003 and hero["heroGodEquip"] == b""
    assert HERO_ATTR.decode(hero["heroAttrCount"])["hp"] == 720
    store.close()


    store = PlayerStore(path)
    service = BattleService(store)
    assert asyncio.run(service.enter(context, packet(request()))).values == first.values
    assert store.db.execute("SELECT COUNT(*) FROM battle_entries").fetchone()[0] == 1
    drop_packet = packet({"missionId": 2110801, "chapterId": 2010100}, name="C2L_FightDropData")
    drops = asyncio.run(service.drop_data(context, drop_packet))
    assert drops.values["result"] == 10
    drop_data = DROP_DATA.decode(drops.values["data"])
    assert drop_data["missionId"] == 2110801
    assert len(drop_data["dropValues"]) == 27  # REVIVAL_COMPAT tier budget
    assert all(v == 3000 for v in drop_data["dropValues"])  # no DifficultyLevel -> MID
    assert asyncio.run(service.drop_data(context, drop_packet)).values == drops.values
    kill = packet({"sectionId": 2110801}, name="C2L_FightKillInfo")
    assert asyncio.run(service.kill_info(context, kill)).values == {"code": 10}
    invalid_kill = packet({"sectionId": 999}, name="C2L_FightKillInfo")
    assert asyncio.run(service.kill_info(context, invalid_kill)).values == {"code": 13}
    for key, value in (("missionId", 999), ("sceneId", 2210001), ("chapter", 2010000),
                       ("checkGm", True), ("isFromProfile", True),
                       ("heros", []), ("heros", [PROFILE_HERO.encode({"heroId": 1004})])):
        invalid = request()
        invalid[key] = value
        assert asyncio.run(service.enter(context, packet(invalid, 2))).values == {"result": 13}
    result = asyncio.run(service.clear_profile(context, packet({"sectionID": 2110801}, name="C2L_DelFightProfile")))
    assert result.values == {"code": 10, "sectionID": 2110801}
    assert store.get(1) == before
    assert store.db.execute("SELECT COUNT(*) FROM battle_entries").fetchone()[0] == 1
    checkout_values = {"chapterId": 2010100, "sectionId": 2110801, "success": True, "fightTime": 300}
    checkout_packet = packet({"checkout": CHECKOUT.encode(checkout_values)}, name="C2L_CheckoutMainMissionSign")
    settled = asyncio.run(service.checkout(context, checkout_packet))
    assert settled.values["success"] is True and settled.values["rewardData"] == b""
    assert settled.values["roleLevel"] == 60
    assert asyncio.run(service.checkout(context, checkout_packet)).values == settled.values
    conflict = packet({"checkout": CHECKOUT.encode(dict(checkout_values, success=False))}, name="C2L_CheckoutMainMissionSign")
    assert asyncio.run(service.checkout(context, conflict)).values == {"result": 13}
    assert store.db.execute("SELECT COUNT(*) FROM battle_receipts").fetchone()[0] == 1
    assert store.get(1) == before
    context.session.player_id = None
    with pytest.raises(ProtocolError):
        asyncio.run(service.enter(context, packet(request())))
    store.close()


def test_zero_client_fight_time_uses_server_elapsed(tmp_path, monkeypatch):
    import x2server.player.battle as battle_module
    current = [1000]
    monkeypatch.setattr(battle_module.time, "time", lambda: current[0])
    store = PlayerStore(tmp_path / "elapsed.db")
    player = store.login("elapsed", 1, 0)
    store.save_snapshot(1, dict(player["snapshot"], level=60,
        heroes=[{"id": 1003, "state": 2, "level": 1, "star": 1}]), player["revision"])
    context = DispatchContext("test", "local", SessionState("test", "elapsed", player_id=1))
    battle = BattleService(store)
    assert asyncio.run(battle.enter(context, packet(request()))).values["result"] == 10
    current[0] = 1093
    checkout = packet({"checkout": CHECKOUT.encode({"chapterId": 2010100,
        "sectionId": 2110801, "success": True, "fightTime": 0})},
        name="C2L_CheckoutMainMissionSign")
    result = asyncio.run(battle.checkout(context, checkout))
    assert result.values["result"] == 10
    assert result.values["fightTimeLength"] == 93
    store.close()
