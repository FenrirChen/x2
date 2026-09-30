"""Main growth on new upgrades; minor increments retain their existing behavior."""
import asyncio
import json

import pytest

from tests.unit.test_battle import packet
from tests.unit.test_economy import env  # noqa: F401
from x2server.messages.equipment import EQUIP_PARAM, HERO_EQUIP
from x2server.player.equipment import EquipmentService


def seed(store, service, star, level=0):
    base = service.main_growth[str(star)]["0"]["100"]["value_sec"][0]
    param = {"at1": 100, "av1": base, "lock1": 0,
             "at2": 102, "av2": 40, "lock2": 0,
             "at3": 104, "av3": 200, "lock3": 0}
    equip_id = store.db.execute(
        "INSERT INTO equipment_instances (player_id,type_id,star,level,param,marker) VALUES (?,?,?,?,?,?)",
        (1, 1240001, star, level, json.dumps(param), "main-growth-test")).lastrowid
    player = store.get(1)
    store.save_snapshot(1, dict(player["snapshot"], gold=10_000_000, equip_exp=10_000_000),
                        player["revision"])
    store.db.commit()
    return equip_id, param


def upgrade(service, ctx, equip_id):
    return asyncio.run(service.strengthen(ctx, packet(
        {"equipID": equip_id}, name="C2L_EquipStrengthen")))


@pytest.mark.parametrize("star", range(1, 7))
def test_each_level_grows_main_and_preserves_minor_rules(env, monkeypatch, star):
    store, economy, ctx = env
    service = EquipmentService(store, economy)
    equip_id, initial = seed(store, service, star)
    # Fix only the existing minor RNG: first eligible slot, minimum increment.
    monkeypatch.setattr("x2server.player.equipment.secrets.choice", lambda slots: slots[0])
    monkeypatch.setattr("x2server.player.equipment.secrets.randbelow", lambda upper: 0)
    bonus = service.increments[(star, 102)][0]
    for level in range(1, 16):
        response = upgrade(service, ctx, equip_id)
        assert response.values["code"] == 10
        growth = store.db.execute("SELECT growth_value FROM equipment_main_growth WHERE equip_id=?",
                                  (equip_id,)).fetchone()[0]
        assert growth in service.main_growth[str(star)]["1"]["100"]["value_sec"]
        wire = HERO_EQUIP.decode(response.before_response[0].values["equip"][0])
        param = EQUIP_PARAM.decode(wire["param"])
        assert wire["level"] == level
        assert param["av1"] == initial["av1"] + growth * level
        assert param["av2"] == initial["av2"] + bonus * (level // 3)
        assert param["av3"] == initial["av3"]
        assert (param["at1"], param["at2"], param["at3"]) == (100, 102, 104)
        assert store.db.execute("SELECT COUNT(*) FROM equipment_enhancements WHERE equip_id=?",
                                (equip_id,)).fetchone()[0] == level // 3
        # Service recreation retains the single growth roll, including across
        # the non-event levels where minors must remain exactly unchanged.
        service = EquipmentService(store, economy)
    before = store.db.execute("SELECT param FROM equipment_instances WHERE id=?", (equip_id,)).fetchone()[0]
    assert upgrade(service, ctx, equip_id).values["code"] == 13
    assert store.db.execute("SELECT param FROM equipment_instances WHERE id=?", (equip_id,)).fetchone()[0] == before


def test_existing_levels_are_not_backfilled(env):
    store, economy, ctx = env
    service = EquipmentService(store, economy)
    equip_id, initial = seed(store, service, 6, level=3)
    service = EquipmentService(store, economy)
    stored = json.loads(store.db.execute("SELECT param FROM equipment_instances WHERE id=?", (equip_id,)).fetchone()[0])
    assert stored == initial
    assert store.db.execute("SELECT COUNT(*) FROM equipment_main_growth").fetchone()[0] == 0
    response = upgrade(service, ctx, equip_id)
    assert response.values["level"] == 4
    growth = store.db.execute("SELECT growth_value FROM equipment_main_growth").fetchone()[0]
    updated = json.loads(store.db.execute("SELECT param FROM equipment_instances WHERE id=?", (equip_id,)).fetchone()[0])
    assert updated == dict(initial, av1=initial["av1"] + growth)
