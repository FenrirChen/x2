from argparse import Namespace
import asyncio
import sqlite3

from tools.dev.seed_test_inventory import seed
from x2server.messages.equipment import EQUIP_PARAM, HERO_EQUIP
from x2server.messages.core import HERO_DATA, INT_PAIR
from x2server.network.dispatcher import DispatchContext
from x2server.network.session import SessionState
from tests.unit.test_battle import packet
from x2server.player.economy import EconomyService
from x2server.player.equipment import EquipmentService
from x2server.player.store import PlayerStore


def test_seed_backs_up_preserves_progress_and_is_idempotent(tmp_path):
    path = tmp_path / "active" / "player.sqlite3"
    store = PlayerStore(path)
    player = store.login("lab", 1, 0)
    original = {**player["snapshot"], "level": 60, "main_section": 2110803,
                "heroes": [{"id": 1003, "state": 2, "level": 2, "star": 2}]}
    store.save_snapshot(1, original, player["revision"])
    EconomyService(store)
    store.close()
    args = Namespace(database=path, player="lab", preset="progression", mode="ensure",
        dry_run=False, currency_amount=10_000_000, radiance_amount=100_000,
        hero_exp_amount=10_000_000, equipment_exp_amount=10_000_000,
        material_amount=999, fragment_amount=999)
    seed(args)
    backups = list((tmp_path / "backups").glob("*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as old:
        assert old.execute("SELECT COUNT(*) FROM inventory").fetchone()[0] == 0
    store = PlayerStore(path)
    state = store.get(1)["snapshot"]
    assert (state["level"], state["main_section"], state["heroes"]) == (60, 2110803, original["heroes"])
    assert (state["gold"], state["crystal"], state["hero_exp"]) == (10_000_000, 100_000, 10_000_000)
    assert state["equip_exp"] == 10_000_000
    economy = EconomyService(store)
    equipment = EquipmentService(store, economy)
    encoded = equipment.values(1)["equip"]
    assert len(encoded) == 42
    first = HERO_EQUIP.decode(encoded[0])
    assert (first["typeId"], first["level"], first["exp"], first["star"]) == (1240001, 0, 0, 6)
    assert EQUIP_PARAM.decode(first["param"])["at1"] == 100
    revision = store.get(1)["revision"]
    store.close()
    seed(args)
    assert len(list((tmp_path / "backups").glob("*.sqlite3"))) == 1
    store = PlayerStore(path)
    assert store.get(1)["revision"] == revision
    economy = EconomyService(store)
    equipment = EquipmentService(store, economy)
    ctx = DispatchContext("test", "local", SessionState("test", "session", player_id=1))
    equipped = asyncio.run(equipment.handle(ctx, packet({"equipID": first["id"], "heroID": 1003, "optType": 1}, 4, "C2L_DoEquip")))
    assert equipped.values["code"] == 10
    hero_wire = HERO_DATA.decode(equipped.pushes[0].values["heros"][0])
    assert INT_PAIR.decode(hero_wire["equips"][0]) == {"Key": 0, "Value": first["id"]}
    assert HERO_EQUIP.decode(equipment.values(1)["equip"][0])["status"] == 1
    strengthened = asyncio.run(equipment.strengthen(ctx, packet({"equipID": first["id"]}, 5, "C2L_EquipStrengthen")))
    assert strengthened.values == {"code": 10, "equipID": first["id"], "level": 1}
    assert store.get(1)["snapshot"]["equip_exp"] == 10_000_000 - 30
    for expected_level in (2, 3):
        strengthened = asyncio.run(equipment.strengthen(ctx, packet({"equipID": first["id"]}, 5 + expected_level, "C2L_EquipStrengthen")))
        assert strengthened.values["level"] == expected_level
    assert store.get(1)["snapshot"]["equip_exp"] == 10_000_000 - 150
    assert strengthened.before_response[0].message_name == "L2C_EquipUpdate"
    upgraded = HERO_EQUIP.decode(strengthened.before_response[0].values["equip"][0])
    assert upgraded["level"] == 3
    assert EQUIP_PARAM.decode(upgraded["param"]) != EQUIP_PARAM.decode(first["param"])
    assert store.db.execute("SELECT COUNT(*) FROM equipment_enhancements").fetchone()[0] == 1
    fourth = asyncio.run(equipment.strengthen(ctx, packet({"equipID": first["id"]}, 9, "C2L_EquipStrengthen")))
    assert fourth.values["level"] == 4
    assert len(EquipmentService(store).values(1)["equip"]) == 42
    store.close()
