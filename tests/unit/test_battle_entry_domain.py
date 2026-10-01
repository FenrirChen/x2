"""Battle entry variants share run creation while preserving main progression."""
import asyncio
import json
import pytest
from pathlib import Path

from tests.unit.test_battle import packet, request
from tests.unit.test_economy import env
from tests.unit.test_economy import rewards
from x2server.messages.battle import CHECKOUT, FIGHT_DATA, FIGHT_PROFILE, PROFILE_HERO, OUTSIDE_ITEM
from x2server.messages.lobby import MISSION_PAIR, MISSION_TYPE, LOBBY_SCHEMAS
from x2server.player.battle import BattleService
from x2server.player.reward_system import SectionRewardCatalog
from x2server.player.economy import EconomyService
from x2server.player.login import LoginService
from x2server.player.store import PlayerStore
from tests.unit.test_world_boss import admit_fixture
from x2server.messages.core import BASE_INFO, PLAYER_DATA, INT_PAIR


def daily(section=2130101, chapter=2030100, scene=2230101):
    values = request()
    values.update(missionId=section, chapter=chapter, sceneId=scene)
    return values


def test_daily_dungeon_reward_profile_is_not_global():
    catalog = SectionRewardCatalog()
    gold = catalog.get(2130101)
    material = catalog.get(2130201)
    assert len(catalog.sections) == 3203
    assert gold["dungeon_ids"] == [2030100] and material["dungeon_ids"] == [2030200]
    assert gold["droop_display"] == [1237901]
    assert material["droop_display"] == [1238100]
    assert gold["drop_value_id"] == 10630101
    assert material["drop_value_id"] == 10630201
    assert gold["first_reward"] == [730001]
    assert gold["normal_reward"] == [730071]
    assert gold["sweep_reward"] == [730071, 795201]
    assert material["normal_reward"] == [730077, 722011, 722012]
    assert material["compat_policy"] is None


def test_main_entry_regression_and_run_metadata(env):
    store, economy, ctx = env
    service = BattleService(store, economy)
    result = asyncio.run(service.enter(ctx, packet(request())))
    assert result.values["result"] == 10
    assert FIGHT_DATA.decode(result.values["data"])["missionId"] == 2110801
    entry = store.db.execute("SELECT section_type,entry_source,map_id,team_json FROM battle_entries WHERE uuid=?",
                             (result.values["uuid"],)).fetchone()
    assert tuple(entry[:3]) == (0, "MainMission", 2210801)
    assert json.loads(entry[3]) == [1003]
    run = store.db.execute("SELECT section_type,entry_source FROM economy_runs WHERE uuid=?",
                           (result.values["uuid"],)).fetchone()
    assert tuple(run) == (0, "MainMission")
    assert store.get(1)["snapshot"]["mobility"]["power"] == 143


def test_successful_checkout_collects_maze_relics_once(env):
    store, economy, ctx = env
    battle = BattleService(store, economy)
    assert asyncio.run(battle.enter(ctx, packet(request()))).values["result"] == 10
    maze = [OUTSIDE_ITEM.encode({"id": item_id, "num": 1, "quality": 3, "eNum": 1})
            for item_id in (1004007, 1004024, 1004007, 1100001)]
    checkout = packet({"checkout": CHECKOUT.encode({"chapterId": 2010100,
        "sectionId": 2110801, "success": True, "fightTime": 100, "mazeItems": maze})},
        name="C2L_CheckoutMainMissionSign")
    first = asyncio.run(battle.checkout(ctx, checkout))
    assert first.values["result"] == 10
    assert [tuple(row) for row in store.db.execute("""SELECT item_id,quantity FROM inventory
        WHERE player_id=1 AND item_id IN (1004007,1004024) ORDER BY item_id""")] == [
            (1004007, 1), (1004024, 1)]
    assert asyncio.run(battle.checkout(ctx, checkout)).values == first.values
    assert store.db.execute("SELECT COUNT(*) FROM inventory WHERE player_id=1 AND item_id=1100001").fetchone()[0] == 0
    assert store.db.execute("SELECT COUNT(*) FROM inventory WHERE player_id=1 AND item_id=1004007").fetchone()[0] == 1
    player_data = PLAYER_DATA.decode(PLAYER_DATA.encode(
        LoginService.snapshot_push(store.get(1), store).values))
    relics = [INT_PAIR.decode(raw) for raw in player_data["RelicPack"]]
    assert relics == [{"Key": 0, "Value": 1004007}, {"Key": 1, "Value": 1004024}]


def test_every_main_section_enters_including_trial_and_missing_level_gate(env):
    store, economy, ctx = env
    battle = BattleService(store, economy)
    main_sections = sorted((row for row in battle.catalog.sections.values() if row["Type"] == 0),
                           key=lambda row: row["SectionID"])
    assert len(main_sections) == 79
    for index, row in enumerate(main_sections):
        section = row["SectionID"]
        values = request()
        values.update(missionId=section, chapter=row["ChapterID"], sceneId=row["Maps"][0])
        if row.get("AssistType", {}).get("value") == 1:
            values["heros"] = [PROFILE_HERO.encode({"heroId": row["AssistParam"][0], "leader": 1})]
        reply = asyncio.run(battle.enter(ctx, packet(values, 1000 + index)))
        assert reply.values["result"] == 10, section

    # The SectionTable's E_Trial AssistParam names a unit variant. Its hero
    # counterpart must enter even when it is absent from the player's roster.
    for index, (section, hero_id) in enumerate(((2110208, 1019), (2110409, 1016),
                                                (2110606, 1007), (2110707, 1003))):
        row = battle.catalog.sections[section]
        values = request()
        values.update(missionId=section, chapter=row["ChapterID"],
                      sceneId=row["Maps"][0],
                      heros=[PROFILE_HERO.encode({"heroId": hero_id, "leader": 1})])
        reply = asyncio.run(battle.enter(ctx, packet(values, 2000 + index)))
        assert reply.values["result"] == 10, section


def test_daily_entry_uses_static_section_and_compat_policy(env):
    store, economy, ctx = env
    service = BattleService(store, economy)
    before = store.get(1)["snapshot"]["mobility"]["power"]
    result = asyncio.run(service.enter(ctx, packet(daily())))
    assert result.values["result"] == 10
    assert FIGHT_DATA.decode(result.values["data"])["missionId"] == 2130101
    profile = FIGHT_PROFILE.decode(result.values["fightDataProfile"])
    assert (profile["chapterId"], profile["sceneId"]) == (2030100, 2230101)
    row = store.db.execute("SELECT section_type,entry_source,map_id,team_json FROM battle_entries WHERE uuid=?",
                           (result.values["uuid"],)).fetchone()
    assert tuple(row[:3]) == (3, "DailyDungeon", 2230101)
    assert json.loads(row[3]) == [1003]
    assert store.db.execute("SELECT section_type,entry_source FROM economy_runs WHERE uuid=?",
                            (result.values["uuid"],)).fetchone()[:] == (3, "DailyDungeon")
    assert store.get(1)["snapshot"]["mobility"]["power"] == before - 6
    drop = packet({"missionId": 2130101, "chapterId": 2030100}, name="C2L_FightDropData")
    assert asyncio.run(service.drop_data(ctx, drop)).values["result"] == 10
    assert asyncio.run(service.enter(ctx, packet(daily()))).values == result.values
    retry = asyncio.run(service.enter(ctx, packet(daily(), 2)))
    assert retry.values["result"] == 10
    assert retry.values["uuid"] != result.values["uuid"]
    assert store.db.execute("SELECT settled FROM economy_runs WHERE uuid=?",
                            (result.values["uuid"],)).fetchone()[0] == 1
    assert store.get(1)["snapshot"]["mobility"]["power"] == before - 6


def test_every_supported_daily_section_enters_and_settles_in_order(env):
    store, economy, ctx = env
    service = BattleService(store, economy)
    player = store.get(1)
    snapshot = player["snapshot"]
    snapshot["mobility"]["power"] = 9999
    store.save_snapshot(1, snapshot, player["revision"])
    supported_dungeons = (2030100, 2030200, 2032000, 2032100)
    gold_by_section = dict(zip(range(2130101, 2130106),
                               (2078, 4678, 9356, 14552, 20788)))
    checked = []
    for dungeon_id in supported_dungeons:
        for section in service.catalog.daily_dungeons[dungeon_id]["SectionID"]:
            row = service.catalog.sections[section]
            entry = asyncio.run(service.enter(ctx, packet(
                daily(section, dungeon_id, row["Maps"][0]), 100 + len(checked))))
            assert entry.values["result"] == 10, section
            done = packet({"checkout": CHECKOUT.encode({"chapterId": dungeon_id,
                "sectionId": section, "success": True, "fightTime": 120})},
                name="C2L_CheckoutMainMissionSign")
            settled = asyncio.run(service.checkout(ctx, done))
            assert settled.values["result"] == 10, section
            if section in gold_by_section:
                # 2026-09-26: manual gold comes from E_ReportCurrency pouch conversion;
                # with no pouches injected, the removed MopReward compat grants nothing.
                assert 1237901 not in rewards(settled.values["rewardData"])
            checked.append(section)
    assert len(checked) == 20
    assert store.db.execute("SELECT COUNT(*) FROM economy_clears WHERE player_id=1").fetchone()[0] == 20


def test_every_catalogued_main_section_has_an_entry_response(env):
    store, economy, ctx = env
    service = BattleService(store, economy)
    player = store.get(1)
    snapshot = player["snapshot"]
    snapshot["mobility"]["power"] = 9999
    store.save_snapshot(1, snapshot, player["revision"])
    for index, section in enumerate(economy.sections):
        row = service.catalog.sections[section]
        values = request()
        values.update(missionId=section, chapter=row["ChapterID"], sceneId=row["Maps"][0])
        if row.get("AssistType", {}).get("value") == 1:
            values["heros"] = [PROFILE_HERO.encode({"heroId": row["AssistParam"][0], "leader": 1})]
        entry = asyncio.run(service.enter(ctx, packet(values, 200 + index)))
        assert entry.values["result"] == 10, section
        assert FIGHT_DATA.decode(entry.values["data"])["missionId"] == section
    assert len(economy.sections) == 78


def test_each_static_section_type_enters_and_settles_without_invented_reward(env):
    store, economy, ctx = env
    service = BattleService(store, economy)
    player = store.get(1)
    snapshot = player["snapshot"]
    snapshot["level"] = 100
    snapshot["mobility"]["power"] = 9999
    store.save_snapshot(1, snapshot, player["revision"])
    with store.db:
        # 星图空间 requires completion of chapter 2 in the native client.
        store.db.execute("INSERT OR IGNORE INTO economy_clears VALUES (1,2110106,'star-prerequisite')")
    representatives = {}
    for row in service.catalog.sections.values():
        representatives.setdefault(row["Type"], row)
    assert set(representatives) == set(range(24))
    for section_type, row in sorted(representatives.items()):
        if row.get("OpenType", {}).get("value") == 2 and row.get("OpenParam"):
            with store.db:
                store.db.execute("INSERT OR IGNORE INTO economy_clears VALUES (?,?,?)",
                                 (1, row["OpenParam"], "static-prerequisite"))
        section = row["SectionID"]
        if section_type == 6:
            admit_fixture(economy, section)
        chapter = row["ChapterID"]
        entry = asyncio.run(service.enter(ctx, packet(
            daily(section, chapter, row["Maps"][0]), 400 + section_type)))
        assert entry.values["result"] == 10, (section_type, section)
        assert FIGHT_DATA.decode(entry.values["data"])["missionId"] == section
        drop = asyncio.run(service.drop_data(ctx, packet(
            {"missionId": section, "chapterId": chapter}, name="C2L_FightDropData")))
        assert drop.values["result"] == 10, (section_type, section)
        done = packet({"checkout": CHECKOUT.encode({"chapterId": chapter, "sectionId": section,
            "success": True, "fightTime": 120})}, name="C2L_CheckoutMainMissionSign")
        settled = asyncio.run(service.checkout(ctx, done))
        assert settled.values["result"] == 10, (section_type, section)
        assert store.db.execute("SELECT settled FROM economy_runs WHERE uuid=?",
                                (entry.values["uuid"],)).fetchone()[0] == 1
        assert asyncio.run(service.checkout(ctx, done)).values == settled.values


def test_all_extracted_sections_resolve_with_satisfied_static_prerequisites(env):
    store, economy, _ = env
    service = BattleService(store, economy)
    player = store.get(1)
    snapshot = player["snapshot"]
    snapshot["level"] = 100
    snapshot['star_chart'] = {'skills': {'391001': 3}}
    store.db.execute("INSERT OR IGNORE INTO economy_clears VALUES (1,2110106,'star-prerequisite')")
    for row in service.catalog.sections.values():
        if row.get("OpenType", {}).get("value") == 2 and row.get("OpenParam"):
            store.db.execute("INSERT OR IGNORE INTO economy_clears VALUES (?,?,?)",
                             (1, row["OpenParam"], "static-prerequisite"))
    for dungeon in service.catalog.daily_dungeons.values():
        for section in dungeon["SectionID"]:
            store.db.execute("INSERT OR IGNORE INTO economy_clears VALUES (?,?,?)",
                             (1, section, "daily-prerequisite"))
    for section, row in service.catalog.sections.items():
        if row["Type"] == 6 and admit_fixture(economy, section) is None:
            from x2server.player.battle_entry import EntryDenied
            with pytest.raises(EntryDenied):
                service.catalog.resolve(player_id=1, request={"missionId":section,
                    "chapter":row["ChapterID"],"sceneId":row["Maps"][0]},
                    snapshot=snapshot,selected_ids=[1003],store=store,economy=economy)
            continue  # Unreleased Boss stages have no WorldBossInfo entry.
        for expert_mode in (False, True):
            resolved = service.catalog.resolve(player_id=1, request={"missionId": section,
                "chapter": row["ChapterID"], "sceneId": row["Maps"][0],
                "expertMode": expert_mode}, snapshot=snapshot,
                selected_ids=[1003], store=store, economy=economy)
            assert (resolved.section_id, resolved.section_type, resolved.map_id) == (
                section, row["Type"], row["Maps"][0])
    assert len(service.catalog.sections) == 3203


def test_challenge_settlement_uses_only_static_gift_items_and_records_unpayable(env):
    store, economy, ctx = env
    service = BattleService(store, economy)
    row = service.catalog.sections[2110251]
    before = store.get(1)["snapshot"]
    entry = asyncio.run(service.enter(ctx, packet(
        daily(2110251, row["ChapterID"], row["Maps"][0]), 799)))
    assert entry.values["result"] == 10
    assert store.get(1)["snapshot"]["mobility"]["power"] == before["mobility"]["power"] - 30
    done = packet({"checkout": CHECKOUT.encode({"chapterId": row["ChapterID"],
        "sectionId": 2110251, "success": True, "fightTime": 120})},
        name="C2L_CheckoutMainMissionSign")
    result = asyncio.run(service.checkout(ctx, done))
    assert result.values["result"] == 10
    assert rewards(result.values["rewardData"]) == {
        1237901: 900, 1237902: 30, 1237907: 300, 1237908: 30, 1237914: 1}
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237914").fetchone()[0] == 1
    assert asyncio.run(service.checkout(ctx, done)).values == result.values
    challenge_progress = [MISSION_TYPE.decode(raw) for raw in economy.mission_values(1)["OtherChapter"]]
    assert challenge_progress[0]["type"] == 2
    assert MISSION_PAIR.decode(challenge_progress[0]["missionData"][0]) == {
        "Key": row["ChapterID"], "Value": 2110251}


def test_real_challenge_expert_flag_enters_drop_and_settles(env):
    store, economy, ctx = env
    service = BattleService(store, economy)
    row = service.catalog.sections[2110851]
    values = daily(2110851, row["ChapterID"], row["Maps"][0])
    values["expertMode"] = True
    entry = asyncio.run(service.enter(ctx, packet(values, 809)))
    assert entry.values["result"] == 10
    drop = asyncio.run(service.drop_data(ctx, packet({"missionId": 2110851,
        "chapterId": row["ChapterID"], "expertMode": True}, name="C2L_FightDropData")))
    assert drop.values["result"] == 10
    done = packet({"checkout": CHECKOUT.encode({"chapterId": row["ChapterID"],
        "sectionId": 2110851, "success": True, "expertMode": True,
        "fightTime": 120})}, name="C2L_CheckoutMainMissionSign")
    result = asyncio.run(service.checkout(ctx, done))
    assert result.values["result"] == 10
    assert store.db.execute("SELECT settled FROM economy_runs WHERE uuid=?",
                            (entry.values["uuid"],)).fetchone()[0] == 1


def test_daily_first_clear_rewards_delivery_unlock_and_idempotency(env):
    store, economy, ctx = env
    service = BattleService(store, economy)
    entry = asyncio.run(service.enter(ctx, packet(daily())))
    before = store.get(1)["snapshot"]
    values = {"chapterId": 2030100, "sectionId": 2130101, "success": True, "fightTime": 120}
    done = packet({"checkout": CHECKOUT.encode(values)}, name="C2L_CheckoutMainMissionSign")
    result = asyncio.run(service.checkout(ctx, done))
    assert result.values["result"] == 10
    assert rewards(result.values["rewardData"]) == {1237902: 30, 1237908: 6, 1237907: 60}
    assert asyncio.run(service.checkout(ctx, done)).values == result.values
    assert store.db.execute("SELECT settled FROM economy_runs WHERE uuid=?",
                            (entry.values["uuid"],)).fetchone()[0] == 1
    state = store.get(1)["snapshot"]
    assert state["crystal"] == before["crystal"] + 30
    assert state["hero_exp"] == before.get("hero_exp", 0) + 60
    assert store.db.execute("SELECT COUNT(*) FROM economy_clears WHERE section_id=2130101").fetchone()[0] == 1
    assert store.db.execute("SELECT COUNT(*) FROM pending_rewards WHERE source=?",
                            (f"battle:{entry.values['uuid']}",)).fetchone()[0] == 0
    mission = service.economy.mission_values(1)
    assert mission["mainMission"] == []
    chapter = MISSION_TYPE.decode(mission["OtherChapter"][0])
    assert chapter["type"] == 3
    assert MISSION_PAIR.decode(chapter["missionData"][0]) == {"Key": 2030100, "Value": 2130101}
    encoded = LOBBY_SCHEMAS["L2C_QueryMission"].encode(mission)
    assert LOBBY_SCHEMAS["L2C_QueryMission"].decode(encoded)["OtherChapter"] == mission["OtherChapter"]
    queried = asyncio.run(economy.handle(ctx, packet({}, name="C2L_QueryMission")))
    assert queried.values == mission
    assert asyncio.run(service.enter(ctx, packet(daily(2130102, 2030100, 2230102), 2))).values["result"] == 10
    conflict = packet({"checkout": CHECKOUT.encode(dict(values, success=False))},
                      name="C2L_CheckoutMainMissionSign")
    assert asyncio.run(service.checkout(ctx, conflict)).values == {"result": 13}


def test_daily_repeat_clear_excludes_first_reward(env):
    store, economy, ctx = env
    service = BattleService(store, economy)
    first = asyncio.run(service.enter(ctx, packet(daily(), 1)))
    done = packet({"checkout": CHECKOUT.encode({"chapterId": 2030100, "sectionId": 2130101,
        "success": True, "fightTime": 120})}, name="C2L_CheckoutMainMissionSign")
    assert rewards(asyncio.run(service.checkout(ctx, done)).values["rewardData"])[1237902] == 30
    before = store.get(1)["snapshot"]
    second = asyncio.run(service.enter(ctx, packet(daily(), 2)))
    assert second.values["uuid"] != first.values["uuid"]
    result = asyncio.run(service.checkout(ctx, done))
    assert rewards(result.values["rewardData"]) == {1237908: 6, 1237907: 60}
    assert asyncio.run(service.checkout(ctx, done)).values == result.values
    assert store.get(1)["snapshot"]["crystal"] == before["crystal"]
    assert store.db.execute("SELECT COUNT(*) FROM economy_clears WHERE section_id=2130101").fetchone()[0] == 1


def test_second_daily_dungeon_has_own_resource_and_fixed_gold(env):
    store, economy, ctx = env
    service = BattleService(store, economy)
    before = store.get(1)["snapshot"]["gold"]
    entry = asyncio.run(service.enter(ctx, packet(daily(2130201, 2030200, 2230201))))
    assert entry.values["result"] == 10
    done = packet({"checkout": CHECKOUT.encode({"chapterId": 2030200, "sectionId": 2130201,
        "success": True, "fightTime": 120})}, name="C2L_CheckoutMainMissionSign")
    result = asyncio.run(service.checkout(ctx, done))
    assert result.values["result"] == 10
    assert rewards(result.values["rewardData"])[1237901] == 360
    assert rewards(result.values["rewardData"])[1238100] == 8  # official Gift; no preview ×1
    assert rewards(result.values["rewardData"]).get(1238101, 0) in (0, 1)
    assert store.get(1)["snapshot"]["gold"] == before + 360
    push = next(p for p in result.pushes if p.message_name == "PlayerDataProto")
    assert BASE_INFO.decode(push.values["BaseInfo"])["Gold"] == before + 360
    assert BASE_INFO.decode(LoginService.snapshot_push(store.get(1)).values["BaseInfo"])["Gold"] == before + 360
    assert asyncio.run(service.checkout(ctx, done)).values == result.values
    assert store.db.execute("SELECT rewards FROM economy_grants WHERE source=?",
        (f"battle:{entry.values['uuid']}",)).fetchone() is not None
    db_path = store.db.execute("PRAGMA database_list").fetchone()[2]
    reopened = PlayerStore(Path(db_path))
    try:
        assert BASE_INFO.decode(LoginService.snapshot_push(reopened.get(1)).values["BaseInfo"])["Gold"] == before + 360
    finally:
        reopened.close()


def test_daily_failed_run_refunds_static_stamina_once(env):
    store, economy, ctx = env
    service = BattleService(store, economy)
    asyncio.run(service.enter(ctx, packet(daily())))
    assert store.get(1)["snapshot"]["mobility"]["power"] == 143
    done = packet({"checkout": CHECKOUT.encode({"chapterId": 2030100, "sectionId": 2130101,
        "success": False, "fightTime": 120})}, name="C2L_CheckoutMainMissionSign")
    assert asyncio.run(service.checkout(ctx, done)).values["result"] == 10
    assert asyncio.run(service.checkout(ctx, done)).values["result"] == 10
    assert store.get(1)["snapshot"]["mobility"]["power"] == 149


def test_unknown_challenge_locked_daily_invalid_team_and_missing_map(env):
    store, economy, ctx = env
    service = BattleService(store, economy)
    unknown = daily(section=9999999)
    assert asyncio.run(service.enter(ctx, packet(unknown))).values == {"result": 13}
    challenge = next(r for r in service.catalog.sections.values() if r["Type"] == 2 and r.get("Maps"))
    challenge_request = daily(section=challenge["SectionID"], chapter=challenge["ChapterID"], scene=challenge["Maps"][0])
    assert asyncio.run(service.enter(ctx, packet(challenge_request))).values["result"] == 10
    locked = daily(section=2130501, chapter=2030500, scene=2230501)
    assert asyncio.run(service.enter(ctx, packet(locked))).values == {"result": 13}
    second_before_first = daily(section=2130102, chapter=2030100, scene=2230102)
    assert asyncio.run(service.enter(ctx, packet(second_before_first))).values == {"result": 13}
    unresolved_multiple_drop_choices = daily(section=2133101, chapter=2033100, scene=2233101)
    # Unresolved reward content must not block a structurally valid entry.
    with store.db:
        store.db.execute("INSERT OR IGNORE INTO economy_clears VALUES (?,?,?)",
                         (1, service.catalog.sections[2133101]["OpenParam"], "prerequisite"))
    assert asyncio.run(service.enter(ctx, packet(unresolved_multiple_drop_choices, 2))).values["result"] == 10
    no_hero = daily()
    no_hero["heros"] = [PROFILE_HERO.encode({"heroId": 9999})]
    assert asyncio.run(service.enter(ctx, packet(no_hero))).values == {"result": 13}
    bad_scene = daily(scene=1)
    assert asyncio.run(service.enter(ctx, packet(bad_scene))).values == {"result": 13}
    no_map = dict(service.catalog.sections[2130101], Maps=[])
    service.catalog.sections[2130101] = no_map
    assert asyncio.run(service.enter(ctx, packet(daily()))).values == {"result": 13}
    assert store.db.execute("SELECT COUNT(*) FROM battle_entries").fetchone()[0] == 2


def test_legacy_schema_migrates_and_daily_metadata_survives_reload(tmp_path):
    path = tmp_path / "legacy.db"
    store = PlayerStore(path)
    player = store.login("lab", 1, 0)
    store.save_snapshot(1, dict(player["snapshot"], level=60, mobility={"power": 149},
        heroes=[{"id": 1003, "state": 2, "level": 1, "star": 1}]), player["revision"])
    with store.db:
        store.db.execute("""CREATE TABLE battle_entries (player_id INTEGER NOT NULL,
            request_key TEXT NOT NULL, uuid TEXT NOT NULL, created_at INTEGER NOT NULL,
            response BLOB NOT NULL, PRIMARY KEY(player_id,request_key))""")
        store.db.execute("INSERT INTO battle_entries VALUES (1,'legacy','old',0,X'')")
    economy = EconomyService(store)
    service = BattleService(store, economy)
    from x2server.network.dispatcher import DispatchContext
    from x2server.network.session import SessionState
    ctx = DispatchContext("test", "local", SessionState("test", "session", player_id=1))
    result = asyncio.run(service.enter(ctx, packet(daily())))
    assert result.values["result"] == 10
    store.close()
    store = PlayerStore(path)
    economy = EconomyService(store)
    service = BattleService(store, economy)  # migration repeated safely
    old = store.db.execute("SELECT section_type,entry_source FROM battle_entries WHERE uuid='old'").fetchone()
    current = store.db.execute("SELECT section_type,entry_source,map_id FROM battle_entries WHERE uuid=?",
                               (result.values["uuid"],)).fetchone()
    assert tuple(old) == (0, "MainMission")
    assert tuple(current) == (3, "DailyDungeon", 2230101)
    assert asyncio.run(service.enter(ctx, packet(daily()))).values == result.values
    store.close()


def test_daily_clear_and_next_entry_survive_relogin(tmp_path):
    path = tmp_path / "daily.db"
    store = PlayerStore(path)
    player = store.login("lab", 1, 0)
    store.save_snapshot(1, dict(player["snapshot"], level=60, mobility={"power": 149},
        heroes=[{"id": 1003, "state": 2, "level": 1, "star": 1}]), player["revision"])
    economy = EconomyService(store)
    service = BattleService(store, economy)
    from x2server.network.dispatcher import DispatchContext
    from x2server.network.session import SessionState
    ctx = DispatchContext("test", "local", SessionState("test", "session", player_id=1))
    asyncio.run(service.enter(ctx, packet(daily())))
    done = packet({"checkout": CHECKOUT.encode({"chapterId": 2030100, "sectionId": 2130101,
        "success": True, "fightTime": 120})}, name="C2L_CheckoutMainMissionSign")
    assert asyncio.run(service.checkout(ctx, done)).values["result"] == 10
    store.close()
    store = PlayerStore(path)
    store.login("lab", 1, 1)
    economy = EconomyService(store)
    service = BattleService(store, economy)
    chapter = MISSION_TYPE.decode(economy.mission_values(1)["OtherChapter"][0])
    assert MISSION_PAIR.decode(chapter["missionData"][0]) == {"Key": 2030100, "Value": 2130101}
    next_entry = asyncio.run(service.enter(ctx, packet(daily(2130102, 2030100, 2230102), 2)))
    assert next_entry.values["result"] == 10
    assert FIGHT_PROFILE.decode(next_entry.values["fightDataProfile"])["sceneId"] == 2230102
    store.close()
