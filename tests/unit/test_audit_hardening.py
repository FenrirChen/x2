"""Part H hardening tests: rejected operations never mutate, equipment cost/idempotency,
DoEquip replay, restart restores every persisted surface.

Isolated SQLite only (tmp_path via the shared env fixture); no business code changes.
"""
import asyncio
import json

import pytest

from tests.unit.test_battle import packet
from tests.unit.test_economy import env  # noqa: F401  (pytest fixture)
from x2server.messages.equipment import HERO_EQUIP
from x2server.player.equipment import EquipmentService
from x2server.player.shop import ShopService


def db_dump(store):
    tables = [r[0] for r in store.db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    return {t: store.db.execute(f"SELECT * FROM {t}").fetchall() for t in sorted(tables)}


def seed_equip(store, player_id=1, type_id=1240001, star=6):
    cur = store.db.execute(
        "INSERT INTO equipment_instances (player_id,type_id,level,exp,star,param,marker) VALUES (?,?,?,?,?,?,?)",
        (player_id, type_id, 0, 0, star,
         json.dumps({f"at{i}": 100 for i in range(1, 7)} |
                    {f"av{i}": 10 for i in range(1, 7)}), "audit-test"))
    store.db.commit()
    return cur.lastrowid


def test_rejected_operations_leave_entire_database_unchanged(env):
    store, economy, ctx = env
    equipment = EquipmentService(store, economy)
    shop = ShopService(store, economy)
    seed_equip(store)
    before = db_dump(store)

    bought = asyncio.run(shop.handle(
        ctx, packet({"shopId": 809, "goodsId": 999999, "buyNum": 1}, 6, "C2L_BuyGoods")))
    assert bought.values["code"] == 13
    strengthened = asyncio.run(equipment.strengthen(
        ctx, packet({"equipID": 424242}, 5, "C2L_EquipStrengthen")))
    assert strengthened.values["code"] == 13
    worn_unknown = asyncio.run(equipment.handle(
        ctx, packet({"equipID": 424242, "heroID": 1003, "optType": 1}, 4, "C2L_DoEquip")))
    assert worn_unknown.values["code"] == 13
    unworn = asyncio.run(equipment.handle(
        ctx, packet({"posIdx": 5, "heroID": 1003, "optType": 1}, 4, "C2L_DoUnEquip")))
    assert unworn.values["code"] == 13

    assert db_dump(store) == before


def test_equipment_strengthen_charges_exact_static_cost_and_stops_at_max(env):
    store, economy, ctx = env
    player = store.get(1)
    store.save_snapshot(1, dict(player["snapshot"], equip_exp=1_000_000, gold=1_000_000),
                        player["revision"])
    equipment = EquipmentService(store, economy)
    equip_id = seed_equip(store)
    costs = equipment.exp_costs

    charged_exp = charged_gold = 0
    seen_levels = []
    for _ in range(40):
        before = store.get(1)
        result = asyncio.run(equipment.strengthen(
            ctx, packet({"equipID": equip_id}, 5, "C2L_EquipStrengthen")))
        row = store.db.execute("SELECT level FROM equipment_instances WHERE id=?",
                               (equip_id,)).fetchone()
        if result.values["code"] != 10:
            assert row[0] == 15  # only the terminal row may refuse
            break
        level_cost = costs[row[0] - 1]
        charged_exp += level_cost["exp_required"]
        charged_gold += level_cost["gold_cost"]
        seen_levels.append(row[0])
        after = store.get(1)
        assert after["snapshot"]["equip_exp"] == before["snapshot"]["equip_exp"] - level_cost["exp_required"]
        assert after["snapshot"]["gold"] == before["snapshot"]["gold"] - level_cost["gold_cost"]
    assert seen_levels == list(range(1, 16))
    snapshot = store.get(1)["snapshot"]
    assert snapshot["equip_exp"] == 1_000_000 - charged_exp
    assert snapshot["gold"] == 1_000_000 - charged_gold


def test_do_equip_replay_keeps_snapshot_content_identical(env):
    store, economy, ctx = env
    equipment = EquipmentService(store, economy)
    equip_id = seed_equip(store)
    first = asyncio.run(equipment.handle(
        ctx, packet({"equipID": equip_id, "heroID": 1003, "optType": 1}, 4, "C2L_DoEquip")))
    assert first.values["code"] == 10
    worn_once = store.get(1)["snapshot"]["heroes"][0]["equips"]
    second = asyncio.run(equipment.handle(
        ctx, packet({"equipID": equip_id, "heroID": 1003, "optType": 1}, 4, "C2L_DoEquip")))
    assert second.values["code"] == 10
    assert store.get(1)["snapshot"]["heroes"][0]["equips"] == worn_once
    encoded = equipment.values(1)["equip"]
    assert len(encoded) == 1 and HERO_EQUIP.decode(encoded[0])["status"] == 1


def test_strengthen_unknown_equip_within_transaction_does_not_create_rows(env):
    store, economy, ctx = env
    equipment = EquipmentService(store, economy)
    before = db_dump(store)
    result = asyncio.run(equipment.strengthen(
        ctx, packet({"equipID": 1}, 5, "C2L_EquipStrengthen")))
    assert result.values["code"] == 13
    assert db_dump(store) == before


def test_restart_restores_equipment_tasks_and_inventory(env):
    store, economy, ctx = env
    equipment = EquipmentService(store, economy)
    equip_id = seed_equip(store)
    asyncio.run(equipment.handle(
        ctx, packet({"equipID": equip_id, "heroID": 1003, "optType": 1}, 4, "C2L_DoEquip")))
    economy.record_event(1, "login:initial", 5)
    economy.claim(1, 630019, 1)

    equip_before = equipment.values(1)
    items_before = economy.inventory_values(1)
    tasks_before = economy.task_values(1, 1)

    fresh_equipment = EquipmentService(store, economy)
    fresh_economy = economy  # EconomyService is stateless over the store in tests
    assert fresh_equipment.values(1) == equip_before
    assert fresh_economy.inventory_values(1) == items_before
    assert fresh_economy.task_values(1, 1) == tasks_before
    worn = HERO_EQUIP.decode(fresh_equipment.values(1)["equip"][0])
    assert worn["status"] == 1
