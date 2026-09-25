import asyncio

import pytest

from x2server.messages.battle import CHECKOUT, DROP_DATA, PROFILE_HERO, FIGHT_DATA, FIGHT_HERO, HERO_ATTR
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
    assert DROP_DATA.decode(drops.values["data"]) == {"missionId": 2110801}
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
