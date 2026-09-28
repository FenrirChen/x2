"""The recovered onboarding messages use isolated account/player storage."""
import asyncio

from x2server.messages.core import BASE_INFO, INT_PAIR
from x2server.messages.battle import PROFILE_HERO, FIGHT_DATA
from x2server.network.dispatcher import DispatchContext
from x2server.network.session import SessionState
from x2server.player.appearance import AppearanceService
from x2server.player.economy import EconomyService
from x2server.player.login import LoginService
from x2server.player.new_player import new_player_snapshot
from x2server.player.tutorial import TutorialService
from x2server.player.battle import BattleService
from tests.integration.test_local_registration import AccountFlow
from tests.unit.test_battle import packet
from tools.repair_early_tutorial_account import repair


def test_fresh_guide_name_and_relog(tmp_path):
    flow = AccountFlow(tmp_path)
    assert flow.register("fresh", "pw") == {"success": True}
    _, identity = flow.game_session("fresh", "pw")
    player_id = identity["playerID"]
    economy = EconomyService(flow.store)
    appearance = AppearanceService(flow.store, economy)
    guide = TutorialService(flow.store)
    login = LoginService(flow.identity, flow.store, economy=economy)
    context = DispatchContext("test", "local", SessionState("test", "session", player_id=player_id))

    first = asyncio.run(login.login(context, packet({"id": player_id,
        "token": identity["token"]}, name="C2L_Login")))
    assert first.values["isCreateRole"] is True
    assert flow.store.get(player_id)["snapshot"]["nickname"] == ""
    assert [h["id"] for h in flow.store.get(player_id)["snapshot"]["heroes"]] == [1003]
    before = BASE_INFO.decode(login.snapshot_push(flow.store.get(player_id)).values["BaseInfo"])
    assert before["NickName"] == ""

    prepare = asyncio.run(BattleService(flow.store, economy).prepare_main_mission(context,
        packet({"chapter": 2010000, "level": 2110001}, name="C2L_PrepareMainMission")))
    assert prepare.values["result"] == 10
    entry = asyncio.run(BattleService(flow.store, economy).enter(context, packet({
        "missionId": 2110001, "chapter": 2010000, "sceneId": 2210001,
        "heros": [PROFILE_HERO.encode({"heroId": 1003, "leader": 1})]},
        name="C2L_FightData")))
    assert entry.values["result"] == 10
    assert FIGHT_DATA.decode(entry.values["data"])["missionId"] == 2110001
    step = packet({"stepId": 21011, "stepState": 2}, name="C2L_GuideStep")
    assert asyncio.run(guide.guide_step(context, step)).values["code"] == 10
    assert asyncio.run(guide.guide_step(context, step)).values["code"] == 10
    group = packet({"opt": 3, "values": [1, 2]}, name="C2L_Account")
    assert asyncio.run(appearance.handle(context, group)).values["result"] == 10
    name = packet({"opt": 7, "strvals": ["测试玩家"]}, name="C2L_Account")
    for _ in range(2):
        assert asyncio.run(appearance.handle(context, name)).values["result"] == 10
    for invalid in ("", " ", "a" * 17, "bad\nname"):
        request = packet({"opt": 7, "strvals": [invalid]}, name="C2L_Account")
        assert asyncio.run(appearance.handle(context, request)).values["result"] == 13
    assert asyncio.run(appearance.handle(context,
        packet({"opt": 7, "strvals": ["different"]}, name="C2L_Account"))).values["result"] == 13

    saved = flow.store.get(player_id)
    assert saved["snapshot"]["guide_steps"] == {"21011": 2}
    assert saved["snapshot"]["guide_groups"] == {"1": 2}
    assert saved["snapshot"]["nickname"] == "测试玩家"
    flow.accounts.close()
    flow.store.close()
    restored = AccountFlow(tmp_path)
    _, again = restored.game_session("fresh", "pw")
    assert again["playerID"] == player_id
    second = asyncio.run(LoginService(restored.identity, restored.store).login(
        DispatchContext("relog", "local", SessionState("relog")),
        packet({"id": player_id, "token": again["token"]}, name="C2L_Login")))
    assert second.values["isCreateRole"] is False
    snapshot = restored.store.get(player_id)["snapshot"]
    assert snapshot["nickname"] == "测试玩家"
    base = BASE_INFO.decode(LoginService.snapshot_push(restored.store.get(player_id)).values["BaseInfo"])
    assert base["NickName"] == "测试玩家"
    assert [INT_PAIR.decode(raw) for raw in base["QuestIDs"]] == [{"Key": 1, "Value": 2}]


def test_skip_is_explicit_and_fresh_default(monkeypatch):
    monkeypatch.delenv("X2_SKIP_TUTORIAL", raising=False)
    fresh = new_player_snapshot()
    assert fresh["tutorial_mode"] == "tutorial" and fresh["nickname"] == ""
    monkeypatch.setenv("X2_SKIP_TUTORIAL", "true")
    skipped = new_player_snapshot()
    assert skipped["tutorial_mode"] == "skip" and skipped["nickname"] == "Revival"
    assert skipped["heroes"] == []


def test_early_registration_repair_is_targeted_and_preview_only(tmp_path):
    flow = AccountFlow(tmp_path)
    flow.register("legacyfresh", "pw")
    flow.register("other", "pw")
    player = flow.store.get(1)
    old = dict(player["snapshot"], nickname="Revival", heroes=[], show=0)
    old.pop("bootstrap_version")
    old.pop("tutorial_mode")
    flow.store.save_snapshot(1, old, player["revision"])
    economy = EconomyService(flow.store)
    context = DispatchContext("repair", "local", SessionState("repair", "session", player_id=1))
    fight_request = packet({"missionId": 2110001, "chapter": 2010000,
        "sceneId": 2210001, "heros": [PROFILE_HERO.encode({"heroId": 1003, "leader": 1})]},
        name="C2L_FightData")
    assert asyncio.run(BattleService(flow.store, economy).enter(context, fight_request)).values["result"] == 13
    database = tmp_path / "player.db"
    before = flow.store.get(1)
    other = flow.store.get(2)
    assert repair(database, 1, "legacyfresh") == "eligible: dry run, no database changes"
    assert flow.store.get(1) == before
    assert repair(database, 1, "legacyfresh", apply=True) == "applied"
    assert flow.store.get(1)["snapshot"]["nickname"] == ""
    assert asyncio.run(BattleService(flow.store, economy).enter(context, fight_request)).values["result"] == 10
    assert flow.store.get(2) == other
