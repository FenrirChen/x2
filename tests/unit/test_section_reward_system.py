"""Cross-section settlement evidence and idempotence for client outsideItems."""
import asyncio
import json

from tests.unit.test_battle import packet, request
from tests.unit.test_economy import env, rewards
from x2server.messages.battle import CHECKOUT, OUTSIDE_ITEM
from x2server.player.battle import BattleService
from x2server.player.economy import EconomyService
from x2server.player.reward_system import SectionRewardCatalog, expand_drop_roots
from x2server.player.store import PlayerStore
from x2server.network.dispatcher import DispatchContext
from x2server.network.session import SessionState


def enter(service, ctx, section=2110801, chapter=2010100, scene=2210801, request_id=1):
    values = request()
    values.update(missionId=section, chapter=chapter, sceneId=scene)
    result = asyncio.run(service.enter(ctx, packet(values, request_id)))
    assert result.values["result"] == 10
    return result.values["uuid"]


def checkout(service, ctx, section=2110801, chapter=2010100, outside=(), success=True):
    raw = CHECKOUT.encode({"chapterId": chapter, "sectionId": section,
        "success": success, "fightTime": 120,
        "outsideItems": [OUTSIDE_ITEM.encode(row) for row in outside]})
    return asyncio.run(service.checkout(ctx, packet({"checkout": raw},
        name="C2L_CheckoutMainMissionSign")))


def test_all_sections_have_profiles_and_own_compat(env):
    catalog = SectionRewardCatalog()
    assert len(catalog.sections) == 3203
    assert len({p["section_type"] for p in catalog.sections.values()}) == 24
    for section_id in (2130101, 2130102, 2130103, 2130104, 2130105):
        p = catalog.get(section_id)
        assert p["compat_policy"]["quantity"] > 0
        assert p["compat_policy"]["gift_group"] in p["sweep_reward"]
    assert catalog.get(2130101)["compat_policy"]["quantity"] == 2078
    assert catalog.get(2130102)["compat_policy"]["quantity"] == 4678
    assert catalog.get(2130201)["compat_policy"] is None
    assert catalog.get(2190001)["section_type_name"] == "E_Battlepass"


def test_nested_and_repeated_drop_groups_define_possible_items_only():
    groups = {
        1309001: {"Picks": 5, "ItemList": [1238100, 1309002]},
        1309002: {"Picks": 1, "ItemList": [1238101]},
    }
    result = expand_drop_roots([1309001], groups)
    assert result == {"direct_items": [1238100], "nested_drop_items": [1238101],
                      "contains_adc": False, "mode": "STRICT_STATIC"}
    groups[1309002]["IsADC"] = {"value": 1}
    assert expand_drop_roots([1309001], groups)["mode"] == "DYNAMIC_ALLOWED"


def test_outside_items_multiple_currency_and_replay(env):
    store, economy, ctx = env
    service = BattleService(store, economy)
    run = enter(service, ctx)
    result = checkout(service, ctx, outside=(
        {"id": 1238100, "num": 2, "quality": 2, "eNum": 0},
        {"id": 1238101, "num": 3},
        {"id": 1237901, "num": 17}))
    assert result.values["result"] == 10
    delivered = rewards(result.values["rewardData"])
    assert delivered[1238100] == 2 and delivered[1238101] == 3
    assert delivered[1237901] == 197  # Section fixed 180 + outsideItems 17
    assert store.get(1)["snapshot"]["gold"] >= 17
    before = store.get(1)
    assert checkout(service, ctx, outside=(
        {"id": 1238100, "num": 2, "quality": 2, "eNum": 0},
        {"id": 1238101, "num": 3}, {"id": 1237901, "num": 17})).values == result.values
    assert store.get(1) == before
    audit = store.db.execute("SELECT sources FROM reward_settlement_audit WHERE run_id=?", (run,)).fetchone()
    sources = json.loads(audit[0])
    assert len(sources["RUNTIME_BATTLE_DROP"]) == 3
    assert store.db.execute("SELECT COUNT(*) FROM economy_grants WHERE source=?",
                            (f"battle:{run}",)).fetchone()[0] == 1


def test_invalid_outside_and_battle_currency_do_not_settle(env):
    store, economy, ctx = env
    service = BattleService(store, economy)
    run = enter(service, ctx)
    before = store.get(1)
    for item in ({"id": 1237903, "num": 1}, {"id": 1238100, "num": 0},
                 {"id": 9999999, "num": 1}, {"id": 1238100, "num": 100001}):
        assert checkout(service, ctx, outside=(item,)).values["result"] == 13
        assert store.get(1) == before
        assert store.db.execute("SELECT settled FROM economy_runs WHERE uuid=?", (run,)).fetchone()[0] == 0


def test_runtime_equipment_is_instantiated_and_delivered(env):
    """2026-09-25: equipment outsideItems go through EquipmentInstanceFactory
    (Star=quality) instead of parking in pending_reward_instances."""
    store, economy, ctx = env
    service = BattleService(store, economy)
    run = enter(service, ctx)
    result = checkout(service, ctx, outside=({"id": 1240001, "num": 1, "quality": 4, "eNum": 5},))
    assert result.values["result"] == 10
    assert store.db.execute("SELECT COUNT(*) FROM pending_reward_instances "
        "WHERE run_id=?", (run,)).fetchone()[0] == 0
    instance = store.db.execute("SELECT type_id, star, marker FROM equipment_instances "
        "WHERE player_id=1").fetchall()
    assert len(instance) == 1 and instance[0][0] == 1240001 and instance[0][1] == 4
    assert instance[0][2].startswith(f"drop:{run}:")
    assert 1240001 not in rewards(result.values["rewardData"])  # not a stackable grant
    audit = store.db.execute("SELECT sources FROM reward_settlement_audit WHERE run_id=?", (run,)).fetchone()
    assert json.loads(audit[0])["EQUIP_INSTANCE"]


def test_gold_dungeon_pouches_convert_and_no_mopreward_compat(env):
    """2026-09-26: E_ReportCurrency pouches convert to account gold at settle;
    the old manual-play MopReward compat (2078/14552...) is removed."""
    store, economy, ctx = env
    service = BattleService(store, economy)
    enter(service, ctx, 2130101, 2030100, 2230101)
    result = checkout(service, ctx, 2130101, 2030100, outside=(
        {"id": 1101076, "num": 100, "quality": 1, "eNum": 0},
        {"id": 1101077, "num": 30, "quality": 1, "eNum": 0},
        {"id": 1101078, "num": 13, "quality": 1, "eNum": 0},
        {"id": 1101079, "num": 8, "quality": 1, "eNum": 0},
        {"id": 1101080, "num": 2, "quality": 1, "eNum": 0}))
    assert result.values["result"] == 10
    delivered = rewards(result.values["rewardData"])
    # 100x28 + 30x84 + 13x252 + 8x336 + 2x560 — proxies merged into one gold grant
    assert delivered[1237901] == 12404
    for proxy in (1101076, 1101077, 1101078, 1101079, 1101080):
        assert proxy not in delivered  # faceless proxies never reach rewardItem
    assert store.get(1)["snapshot"]["gold"] == 12404
    assert store.db.execute("SELECT COUNT(*) FROM inventory WHERE item_id=1101076").fetchone()[0] == 0


def test_non_gold_daily_does_not_receive_preview_item(env):
    store, economy, ctx = env
    service = BattleService(store, economy)
    enter(service, ctx, 2130201, 2030200, 2230201)
    result = checkout(service, ctx, 2130201, 2030200)
    assert rewards(result.values["rewardData"])[1238100] == 8


def test_sweep_uses_mop_only_and_replay_is_idempotent(env):
    store, economy, ctx = env
    service = BattleService(store, economy)
    enter(service, ctx, 2130101, 2030100, 2230101)
    checkout(service, ctx, 2130101, 2030100)
    before_power = store.get(1)["snapshot"]["mobility"]["power"]
    req = packet({"sectionId": 2130101, "sweepCount": 2}, 912, "C2L_SecSweep")
    result = asyncio.run(service.sweep(ctx, req))
    assert result.values["code"] == 10
    assert rewards(result.values["rewardData"])[1237901] == 4156
    assert store.get(1)["snapshot"]["mobility"]["power"] == before_power - 12
    before = store.get(1)
    assert asyncio.run(service.sweep(ctx, req)).values == result.values
    assert store.get(1) == before


def test_failed_battle_does_not_grant_or_consume_outside(env):
    store, economy, ctx = env
    service = BattleService(store, economy)
    enter(service, ctx)
    before = store.get(1)["snapshot"]["gold"]
    assert checkout(service, ctx, outside=({"id": 1237901, "num": 5},), success=False).values["result"] == 13
    result = checkout(service, ctx, success=False)
    assert result.values["result"] == 10
    assert store.get(1)["snapshot"]["gold"] == before


def test_runtime_delivery_and_pending_instance_survive_relogin(tmp_path):
    path = tmp_path / "reward.db"
    store = PlayerStore(path)
    player = store.login("lab", 1, 0)
    store.save_snapshot(1, dict(player["snapshot"], level=60, mobility={"power": 149},
        heroes=[{"id": 1003, "state": 2, "level": 1, "star": 1}]), player["revision"])
    economy = EconomyService(store)
    context = DispatchContext("test", "local", SessionState("test", "session", player_id=1))
    service = BattleService(store, economy)
    run = enter(service, context)
    result = checkout(service, context, outside=(
        {"id": 1238100, "num": 2}, {"id": 1240001, "num": 1, "quality": 4, "eNum": 5}))
    assert result.values["result"] == 10
    store.close()
    store = PlayerStore(path)
    economy = EconomyService(store)
    service = BattleService(store, economy)
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1238100").fetchone()[0] == 2
    # 1240001 is a real HeroEquip instance now (Star=quality), surviving relogin
    instance = store.db.execute("SELECT type_id, star, level, param FROM equipment_instances "
                                "WHERE player_id=1").fetchall()
    assert len(instance) == 1 and instance[0][0] == 1240001 and instance[0][1] == 4 and instance[0][2] == 0
    assert store.db.execute("SELECT COUNT(*) FROM pending_reward_instances WHERE run_id=?",
                            (run,)).fetchone()[0] == 0
    replay = checkout(service, context, outside=(
        {"id": 1238100, "num": 2}, {"id": 1240001, "num": 1, "quality": 4, "eNum": 5}))
    assert rewards(replay.values["rewardData"])[1238100] == 2
    assert store.db.execute("SELECT COUNT(*) FROM equipment_instances WHERE player_id=1").fetchone()[0] == 1
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1238100").fetchone()[0] == 2
    store.close()
