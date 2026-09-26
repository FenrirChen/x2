"""887.outsideItems -> EquipmentInstanceFactory -> HeroEquip delivery.

Star comes verbatim from outsideItems.quality (client IdentifyItem result; server
never rerolls). Affix-count tiers (65/35) and ValueSec chain rolls are
REVIVAL_COMPATIBILITY / USER_DECISIONs with injectable RNG for determinism.
"""
import asyncio
import random
import sqlite3

import pytest

from tests.unit.test_battle import packet, request
from tests.unit.test_economy import env, rewards  # noqa: F401  (fixtures)
from x2server.messages.battle import CHECKOUT, DROP_DATA, FIGHT_DATA, OUTSIDE_ITEM
from x2server.messages.equipment import EQUIP_PARAM, HERO_EQUIP
from x2server.messages.economy import REWARD
from x2server.network.dispatcher import DispatchContext
from x2server.network.session import SessionState
from x2server.player.battle import BattleService
from x2server.player.economy import EconomyService
from x2server.player.equipment import EquipmentService
from x2server.player.equipment_factory import (EquipmentInstanceFactory,
                                               EquipmentValidationError)
from x2server.player.store import PlayerStore

SECTION = dict(section=2110801, chapter=2010100, scene=2210801)


def seeded_factory(seed):
    return EquipmentInstanceFactory(rng=random.Random(seed))


def equip_env(env, seed=1):
    """env fixture with the factory RNG pinned for deterministic count tiers."""
    store, economy, ctx = env
    economy.equipment_factory = seeded_factory(seed)
    EquipmentService(store, economy)  # production wiring creates the ledger table
    battle = BattleService(store, economy)
    values = request()
    values.update(missionId=SECTION["section"], chapter=SECTION["chapter"], sceneId=SECTION["scene"])
    result = asyncio.run(battle.enter(ctx, packet(values)))
    assert result.values["result"] == 10
    return store, economy, ctx, battle


def checkout_equipment(battle, ctx, outside, request_id=1):
    raw = CHECKOUT.encode({"chapterId": SECTION["chapter"], "sectionId": SECTION["section"],
        "success": True, "fightTime": 120,
        "outsideItems": [OUTSIDE_ITEM.encode(row) for row in outside]})
    return asyncio.run(battle.checkout(ctx, packet({"checkout": raw},
        name="C2L_CheckoutMainMissionSign", request_id=request_id)))


def reward_equips(raw):
    return [HERO_EQUIP.decode(e) for e in REWARD.decode(raw).get("rewardEquip", [])]


def decoded_param(wire_param):
    return EQUIP_PARAM.decode(wire_param)


def db_instances(store):
    return store.db.execute("SELECT id, type_id, level, exp, star, param, marker "
                            "FROM equipment_instances WHERE player_id=1 ORDER BY id").fetchall()


def test_star_equals_outside_quality_and_typeid_preserved(env):
    store, economy, ctx, battle = equip_env(env)
    result = checkout_equipment(battle, ctx, ({"id": 1240001, "num": 1, "quality": 5, "eNum": 0},))
    assert result.values["result"] == 10
    equips = reward_equips(result.values["rewardData"])
    assert len(equips) == 1
    assert equips[0]["star"] == 5 and equips[0]["typeId"] == 1240001  # 1240|SS|P kept
    rows = db_instances(store)
    assert len(rows) == 1 and rows[0][1] == 1240001 and rows[0][4] == 5


def test_three_star_fixed_three_affixes(env):
    store, economy, ctx, battle = equip_env(env)
    result = checkout_equipment(battle, ctx, ({"id": 1240001, "num": 1, "quality": 3, "eNum": 0},))
    param = decoded_param(reward_equips(result.values["rewardData"])[0]["param"])
    minors = [param[f"at{i}"] for i in range(2, 7) if param[f"at{i}"]]
    assert len(minors) == 3  # canonical AttribBD base row 13000000 MinorAttrNum=3


def test_four_star_base_tier_three_affixes(env):
    # random.Random(1).random() = 0.134 < 0.65 -> base tier (REVIVAL_COMPAT 65/35)
    store, economy, ctx, battle = equip_env(env, seed=1)
    result = checkout_equipment(battle, ctx, ({"id": 1240001, "num": 1, "quality": 4, "eNum": 0},))
    param = decoded_param(reward_equips(result.values["rewardData"])[0]["param"])
    assert sum(1 for i in range(2, 7) if param[f"at{i}"]) == 3


def test_four_star_max_tier_four_affixes(env):
    # random.Random(0).random() = 0.844 >= 0.65 -> max tier
    store, economy, ctx, battle = equip_env(env, seed=0)
    result = checkout_equipment(battle, ctx, ({"id": 1240001, "num": 1, "quality": 4, "eNum": 0},))
    param = decoded_param(reward_equips(result.values["rewardData"])[0]["param"])
    assert sum(1 for i in range(2, 7) if param[f"at{i}"]) == 4


@pytest.mark.parametrize("star", (5, 6))
def test_five_and_six_star_counts_within_official_tiers(env, star):
    for seed in (0, 1):
        store, economy, ctx, battle = equip_env(env, seed=seed)
        result = checkout_equipment(battle, ctx, ({"id": 1240001, "num": 1, "quality": star, "eNum": 0},))
        param = decoded_param(reward_equips(result.values["rewardData"])[0]["param"])
        assert sum(1 for i in range(2, 7) if param[f"at{i}"]) in {4, 5}


def test_affix_values_only_from_official_valuesec(env):
    store, economy, ctx, battle = equip_env(env, seed=0)
    result = checkout_equipment(battle, ctx, ({"id": 1240001, "num": 1, "quality": 4, "eNum": 0},))
    param = decoded_param(reward_equips(result.values["rewardData"])[0]["param"])
    tables = economy.equipment_factory.data
    assert param["av1"] in tables["equib_attrib"]["4"]["0"][str(param["at1"])]["value_sec"]
    for i in range(2, 7):
        if param[f"at{i}"]:
            ladder = tables["equib_attrib"]["4"]["2"][str(param[f"at{i}"])]["value_sec"]
            assert param[f"av{i}"] in ladder


def test_main_attr_from_equibbase_pool(env):
    store, economy, ctx, battle = equip_env(env, seed=2)
    result = checkout_equipment(battle, ctx, ({"id": 1240002, "num": 1, "quality": 3, "eNum": 0},))
    param = decoded_param(reward_equips(result.values["rewardData"])[0]["param"])
    pool = economy.equipment_factory.data["equib_base"]["1240002"]["main_attr_type"]
    assert param["at1"] in pool  # part 2 has three official candidates [101,105,113]


def test_minor_types_from_pool_distinct(env):
    store, economy, ctx, battle = equip_env(env, seed=0)
    result = checkout_equipment(battle, ctx, ({"id": 1240001, "num": 1, "quality": 4, "eNum": 0},))
    param = decoded_param(reward_equips(result.values["rewardData"])[0]["param"])
    pool = set(economy.equipment_factory.data["equib_base"]["1240001"]["minor_attr_type"])
    minors = [param[f"at{i}"] for i in range(2, 7) if param[f"at{i}"]]
    assert minors and set(minors) <= pool
    assert len(minors) == len(set(minors))  # official plates never repeat types


def test_num_two_creates_two_distinct_instances(env):
    store, economy, ctx, battle = equip_env(env)
    result = checkout_equipment(battle, ctx, ({"id": 1240001, "num": 2, "quality": 4, "eNum": 0},))
    equips = reward_equips(result.values["rewardData"])
    assert len(equips) == 2
    assert len({e["id"] for e in equips}) == 2  # independent instance ids
    params = [tuple(sorted(decoded_param(e["param"]).items())) for e in equips]
    assert len(set(params)) == 2  # independently rolled params


def test_reward_equips_wire_defaults(env):
    store, economy, ctx, battle = equip_env(env)
    result = checkout_equipment(battle, ctx, ({"id": 1240001, "num": 1, "quality": 3, "eNum": 0},))
    equip = reward_equips(result.values["rewardData"])[0]
    assert (equip["level"], equip["exp"], equip["status"], equip["lockState"],
            equip["timeSec"], equip["seasonId"]) == (0, 0, 0, 0, 0, 0)


def test_display_family_1245_never_becomes_instance(env):
    store, economy, ctx, battle = equip_env(env)
    run = store.db.execute("SELECT uuid FROM economy_runs ORDER BY rowid DESC LIMIT 1").fetchone()[0]
    result = checkout_equipment(battle, ctx, ({"id": 1245001, "num": 1, "quality": 6, "eNum": 0},))
    assert result.values["result"] == 10
    assert reward_equips(result.values["rewardData"]) == []
    assert store.db.execute("SELECT COUNT(*) FROM equipment_instances").fetchone()[0] == 0
    pending = store.db.execute("SELECT item_id, quantity, quality FROM pending_reward_instances "
                               "WHERE run_id=?", (run,)).fetchall()
    assert [tuple(row) for row in pending] == [(1245001, 1, 6)]  # parked as unresolved, not instantiated


def test_illegal_star_rejects_checkout(env):
    store, economy, ctx, battle = equip_env(env)
    before = db_instances(store)
    result = checkout_equipment(battle, ctx, ({"id": 1240001, "num": 1, "quality": 9, "eNum": 0},))
    assert result.values["result"] == 13
    assert db_instances(store) == before


def test_persistence_and_relog_555(tmp_path):
    path = tmp_path / "p.db"
    store = PlayerStore(path)
    player = store.login("lab", 1, 0)
    store.save_snapshot(1, dict(player["snapshot"], level=60, mobility={"power": 149},
        heroes=[{"id": 1003, "state": 2, "level": 1, "star": 1}]), player["revision"])
    economy = EconomyService(store)
    economy.equipment_factory = seeded_factory(0)
    ctx = DispatchContext("t", "local", SessionState("t", "s", player_id=1))
    battle = BattleService(store, economy)
    values = request()
    values.update(missionId=SECTION["section"], chapter=SECTION["chapter"], sceneId=SECTION["scene"])
    asyncio.run(battle.enter(ctx, packet(values)))
    checkout_equipment(battle, ctx, ({"id": 1240001, "num": 1, "quality": 6, "eNum": 0},))
    store.close()

    store = PlayerStore(path)  # relog: fresh connection over the same DB
    equipment = EquipmentService(store)
    equips = [HERO_EQUIP.decode(e) for e in equipment.values(1)["equip"]]
    dropped = [e for e in equips if e["typeId"] == 1240001]
    assert len(dropped) == 1
    assert dropped[0]["star"] == 6 and dropped[0]["level"] == 0
    param = EQUIP_PARAM.decode(dropped[0]["param"])
    assert sum(1 for i in range(2, 7) if param[f"at{i}"]) in (4, 5)
    store.close()


def test_duplicate_checkout_reuses_receipt_without_reroll(env):
    store, economy, ctx, battle = equip_env(env, seed=0)
    first = checkout_equipment(battle, ctx, ({"id": 1240001, "num": 1, "quality": 4, "eNum": 0},))
    rows = db_instances(store)
    replay = checkout_equipment(battle, ctx, ({"id": 1240001, "num": 1, "quality": 4, "eNum": 0},),
                                request_id=2)
    assert replay.values == first.values  # cached receipt -> identical rewardEquip ids/params
    assert db_instances(store) == rows    # no second generation


def test_failed_battle_never_delivers_equipment(env):
    store, economy, ctx, battle = equip_env(env)
    practice = BattleService(store)  # practice entry: no economy run
    values = request()
    values.update(missionId=SECTION["section"], chapter=SECTION["chapter"], sceneId=SECTION["scene"])
    asyncio.run(practice.enter(ctx, packet(values, 2)))
    result = checkout_equipment(battle, ctx, ({"id": 1240001, "num": 1, "quality": 4, "eNum": 0},))
    assert result.values["result"] == 13
    assert db_instances(store) == []


def test_receipt_failure_rolls_back_instances(env):
    store, economy, ctx, battle = equip_env(env)
    with store.db:
        store.db.execute("CREATE TRIGGER reject_receipt BEFORE INSERT ON battle_receipts "
                         "BEGIN SELECT RAISE(ABORT, 'test'); END")
    with pytest.raises(sqlite3.IntegrityError):
        checkout_equipment(battle, ctx, ({"id": 1240001, "num": 1, "quality": 4, "eNum": 0},))
    assert db_instances(store) == []  # no half state: receipt failed -> instances rolled back
    with store.db:
        store.db.execute("DROP TRIGGER reject_receipt")


def test_factory_rejects_non_part_level_ids():
    factory = seeded_factory(0)
    with pytest.raises(EquipmentValidationError):
        factory.validate(1245001, 4, 1)  # display family
    with pytest.raises(EquipmentValidationError):
        factory.validate(9999999, 4, 1)  # unknown
    with pytest.raises(EquipmentValidationError):
        factory.validate(1240001, 7, 1)  # star out of range
    with pytest.raises(EquipmentValidationError):
        factory.validate(1240001, 4, 0)  # illegal quantity


def test_stackable_regression_with_mixed_checkout(env):
    store, economy, ctx, battle = equip_env(env)
    result = checkout_equipment(battle, ctx, (
        {"id": 1240001, "num": 1, "quality": 4, "eNum": 0},
        {"id": 1237901, "num": 17, "quality": 0, "eNum": 0}))
    assert result.values["result"] == 10
    delivered = rewards(result.values["rewardData"])
    assert delivered[1237901] >= 17  # stackable grant unaffected by equipment delivery
    assert len(reward_equips(result.values["rewardData"])) == 1


def test_dropped_instance_enters_strengthen_chain(env):
    store, economy, ctx, battle = equip_env(env)
    result = checkout_equipment(battle, ctx, ({"id": 1240001, "num": 1, "quality": 4, "eNum": 0},))
    equip = reward_equips(result.values["rewardData"])[0]
    snapshot = store.get(1)
    store.save_snapshot(1, dict(snapshot["snapshot"], equip_exp=500, gold=5000), snapshot["revision"])
    equipment_service = EquipmentService(store, economy)
    response = asyncio.run(equipment_service.strengthen(
        ctx, packet({"equipID": equip["id"]}, name="C2L_EquipStrengthen")))
    assert response.values["code"] == 10 and response.values["level"] == 1


def test_battle_entry_carries_dropvalues_budget(env):
    """SetSceneInfo copies FightData.dropData.dropValues into the JudgeDropItem
    budget; an absent dropData silently kills every client-side ItemStruct drop."""
    store, economy, ctx, battle = equip_env(env)
    values = request()
    values.update(missionId=SECTION["section"], chapter=SECTION["chapter"], sceneId=SECTION["scene"])
    entered = asyncio.run(battle.enter(ctx, packet(values)))
    data = FIGHT_DATA.decode(entered.values["data"])
    drop_data = DROP_DATA.decode(data["dropData"])
    assert len(drop_data["dropValues"]) == 27
    # 2110801 has no official DifficultyLevel -> default MID tier (REVIVAL_COMPAT)
    assert all(v == 3000 for v in drop_data["dropValues"])
    assert drop_data["missionId"] == SECTION["section"]


def test_dropped_instance_can_be_equipped(env):
    store, economy, ctx, battle = equip_env(env)
    result = checkout_equipment(battle, ctx, ({"id": 1240001, "num": 1, "quality": 4, "eNum": 0},))
    equip = reward_equips(result.values["rewardData"])[0]
    equipment_service = EquipmentService(store, economy)
    response = asyncio.run(equipment_service.handle(
        ctx, packet({"equipID": equip["id"], "heroID": 1003, "optType": 1}, name="C2L_DoEquip")))
    assert response.values["code"] == 10  # part 1 -> position 0 via canonical EquibBase
    hero = next(h for h in store.get(1)["snapshot"]["heroes"] if h["id"] == 1003)
    assert {"position": 0, "equip_id": equip["id"]} in hero["equips"]
