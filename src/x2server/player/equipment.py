"""Persisted test equipment instances sent through the existing EquipAll protocol."""
import json
import logging
import random
import secrets
from pathlib import Path

from x2server.messages.equipment import EQUIP_PARAM, HERO_EQUIP, EQUIPMENT_SCHEMAS
from x2server.player.equipment_factory import (
    load_equipment_tables, roll_value_sec, ensure_equipment_instances)
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY
from .economy import UnresolvedEconomy


class EquipmentService:
    def __init__(self, store, economy=None):
        self.store = store
        self.economy = economy
        # Canonical part/suit map: every EquibBase row (all part-level 1240xxx),
        # not just the seeded test presets.
        tables = load_equipment_tables()
        self.parts = {int(type_id): row["part"]
                      for type_id, row in tables["equib_base"].items()}
        self.main_growth = tables["equib_attrib"]
        increments = Path(__file__).resolve().parents[3] / "analysis/progression/equipment_strengthen_catalog.json"
        self.increments = {(r["quality"], r["attribute"]): r["value_range"]
                           for r in json.loads(increments.read_text(encoding="utf-8"))["rows"]}
        progression = Path(__file__).resolve().parents[3] / "analysis/progression/equipment_progression.json"
        self.exp_costs = {r["level"]: r for r in json.loads(progression.read_text(encoding="utf-8"))["level_rows"]}
        self.reclaim_stages = {r["Stage"]: r for r in json.loads(progression.read_text(encoding="utf-8"))["stage_rows"]}
        with store.db:
            # One canonical DDL for the 兽主 ledger, shared with the drop
            # materializer - see equipment_factory.ensure_equipment_instances.
            ensure_equipment_instances(store.db)
            store.db.execute("""CREATE TABLE IF NOT EXISTS equipment_enhancements (
                player_id INTEGER NOT NULL, equip_id INTEGER NOT NULL,
                level INTEGER NOT NULL, attribute_slot INTEGER NOT NULL, bonus INTEGER NOT NULL,
                PRIMARY KEY(player_id,equip_id,level))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS equipment_main_growth (
                equip_id INTEGER PRIMARY KEY, player_id INTEGER NOT NULL,
                star INTEGER NOT NULL, main_type INTEGER NOT NULL,
                growth_value INTEGER NOT NULL)""")

    def values(self, player_id):
        instances = []
        snapshot = self.store.get(player_id)["snapshot"]
        worn = {e["equip_id"] for hero in snapshot.get("heroes", []) for e in hero.get("equips", [])}
        for row in self.store.db.execute("SELECT id,type_id,level,exp,star,param,locked FROM equipment_instances "
                                         "WHERE player_id=? ORDER BY id", (player_id,)):
            instances.append(HERO_EQUIP.encode({"id": row[0], "typeId": row[1],
                "level": row[2], "exp": row[3], "star": row[4], "status": int(row[0] in worn),
                "param": EQUIP_PARAM.encode(json.loads(row[5])), "lockState": row[6],
                "timeSec": 0, "seasonId": 0}))
        return {"equip": instances}

    async def query_all(self, context, packet):
        if context.session.player_id is None:
            raise ProtocolError("equipment query before login")
        return OutboundMessage("L2C_EquipAll", self.values(context.session.player_id))

    async def lock(self, context, packet):
        """Toggle 兽主锁定 (C2L_LockEquip 883 -> L2C_LockEquip 884).

        The client's request carries only ``equipID``, so the state is toggled rather
        than set, and the updated HeroEquip is echoed back: the client's handler
        (BagModule.OnReceiveLockedEquipMsg) refreshes the bag entry from this one
        message and sends no follow-up query.
        """
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("equipment lock before login")
        equip_id = EQUIPMENT_SCHEMAS["C2L_LockEquip"].decode(packet.body).get("equipID")
        if not equip_id:
            return OutboundMessage("L2C_LockEquip", {"code": 13})
        transaction = self.economy.transaction() if self.economy is not None else self.store.db
        with transaction:
            row = self.store.db.execute(
                "SELECT locked FROM equipment_instances WHERE player_id=? AND id=?",
                (player_id, equip_id)).fetchone()
            if row is None:
                return OutboundMessage("L2C_LockEquip", {"code": 13})
            self.store.db.execute("UPDATE equipment_instances SET locked=? WHERE player_id=? AND id=?",
                                  (0 if row[0] else 1, player_id, equip_id))
        changed = next(e for e in self.values(player_id)["equip"]
                       if HERO_EQUIP.decode(e)["id"] == equip_id)
        return OutboundMessage("L2C_LockEquip", {"code": 10, "heroEquip": changed})

    def handlers(self):
        return {"C2L_EquipAll": self.query_all,
                "C2L_DoEquip": self.handle, "C2L_DoUnEquip": self.handle,
                "C2L_EquipStrengthen": self.strengthen,
                "C2L_EquipReclaim": self.reclaim,
                "C2L_LockEquip": self.lock}

    def reclaim_rewards(self, rows):
        """Mirror the client's BagDecomposePage currency preview calculation."""
        rewards = {}
        for row in rows:
            level, star = row["level"], row["star"]
            stage, exp_row = self.reclaim_stages[star], self.exp_costs[level]
            equip_exp = stage["Exp"] + (exp_row["cumulative_exp"] * stage["ExpBonus"]
                * (1000 - exp_row["loss_exp"])) // 1_000_000
            rewards[1237906] = rewards.get(1237906, 0) + equip_exp
            gold = exp_row["cumulative_gold"] * stage["GoldBonus"] // 1000
            if gold:
                rewards[1237901] = rewards.get(1237901, 0) + gold
            chip = stage.get("EquibSeniorChip", [])
            if len(chip) >= 2 and chip[0] >= 1000:
                rewards[1237920] = rewards.get(1237920, 0) + chip[1]
        return rewards

    async def reclaim(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("equipment reclaim before login")
        request = EQUIPMENT_SCHEMAS["C2L_EquipReclaim"].decode(packet.body)
        ids = request.get("equipID", [])
        reject = OutboundMessage("L2C_EquipReclaim", {"code": 13})
        if not ids or len(ids) > 200 or len(ids) != len(set(ids)) or self.economy is None:
            return reject
        snapshot = self.store.get(player_id)["snapshot"]
        worn = {e["equip_id"] for hero in snapshot.get("heroes", []) for e in hero.get("equips", [])}
        if any(equip_id in worn for equip_id in ids):
            return reject
        try:
            with self.economy.transaction():
                placeholders = ",".join("?" for _ in ids)
                rows = self.store.db.execute(
                    f"SELECT id,level,star,locked FROM equipment_instances WHERE player_id=? AND id IN ({placeholders})",
                    (player_id, *ids)).fetchall()
                if len(rows) != len(ids) or any(row["star"] not in self.reclaim_stages
                                              or row["level"] not in self.exp_costs for row in rows):
                    return reject
                # 已锁定的兽主不可分解: the client's lock button exists exactly to stop a
                # piece being consumed by accident, so the server refuses it too.
                if any(row["locked"] for row in rows):
                    return reject
                rewards = self.reclaim_rewards(rows)
                self.store.db.execute(f"DELETE FROM equipment_enhancements WHERE player_id=? AND equip_id IN ({placeholders})",
                                      (player_id, *ids))
                self.store.db.execute(f"DELETE FROM equipment_instances WHERE player_id=? AND id IN ({placeholders})",
                                      (player_id, *ids))
                rewards = self.economy._grant(player_id, "equip_reclaim:" + ",".join(map(str, sorted(ids))), rewards)
                self.store.db.execute(f"DELETE FROM equipment_main_growth WHERE player_id=? AND equip_id IN ({placeholders})",
                                      (player_id, *ids))
        except UnresolvedEconomy:
            return reject
        removed = OutboundMessage("L2C_EquipRemove", {"ids": ids})
        return OutboundMessage("L2C_EquipReclaim", {"code": 10,
            "rewardData": self.economy.reward_bytes(rewards)},
            before_response=(removed,), pushes=self.economy.pushes(player_id))

    async def strengthen(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("equipment strengthen before login")
        req = EQUIPMENT_SCHEMAS["C2L_EquipStrengthen"].decode(packet.body)
        equip_id = req.get("equipID")
        result = {"code": 13, "equipID": equip_id or 0}
        if not equip_id or self.economy is None:
            return OutboundMessage("L2C_EquipStrengthen", result)
        with self.economy.transaction():
            row = self.store.db.execute("SELECT level,star,param FROM equipment_instances WHERE player_id=? AND id=?",
                                        (player_id, equip_id)).fetchone()
            if row is None or row[0] not in self.exp_costs:
                return OutboundMessage("L2C_EquipStrengthen", result)
            cost = self.exp_costs[row[0]]
            if not cost.get("next_level"):
                return OutboundMessage("L2C_EquipStrengthen", result)
            snapshot = self.store.get(player_id)["snapshot"]
            if snapshot.get("equip_exp", 0) < cost["exp_required"] or snapshot.get("gold", 0) < cost["gold_cost"]:
                return OutboundMessage("L2C_EquipStrengthen", result)
            next_level = cost["next_level"]
            param = json.loads(row[2])
            main_type = param.get("at1", 0)
            growth_ladder = self.main_growth.get(str(row[1]), {}).get("1", {}).get(str(main_type))
            if growth_ladder is None:
                return OutboundMessage("L2C_EquipStrengthen", result)
            if next_level % 3 == 0:
                candidates = [slot for slot in range(2, 7) if param.get(f"at{slot}") and
                              (row[1], param[f"at{slot}"]) in self.increments]
                if not candidates:
                    return OutboundMessage("L2C_EquipStrengthen", result)
                slot = secrets.choice(candidates)
                limits = self.increments[(row[1], param[f"at{slot}"])]
                bonus = secrets.randbelow(limits[-1] - limits[0] + 1) + limits[0]
                param[f"av{slot}"] += bonus
                self.store.db.execute("INSERT INTO equipment_enhancements VALUES (?,?,?,?,?)",
                                      (player_id, equip_id, next_level, slot, bonus))
            saved_growth = self.store.db.execute(
                "SELECT growth_value FROM equipment_main_growth WHERE equip_id=? AND player_id=? AND star=? AND main_type=?",
                (equip_id, player_id, row[1], main_type)).fetchone()
            if saved_growth is None:
                # src1 is the official per-level main growth ladder. Select its
                # tier once using the existing Revival sequential-chain rule;
                # server-side official tier selection is not recoverable.
                growth = roll_value_sec(growth_ladder["value_sec"], growth_ladder["chance_sec"],
                                        random.SystemRandom())
                self.store.db.execute("INSERT OR REPLACE INTO equipment_main_growth VALUES (?,?,?,?,?)",
                                      (equip_id, player_id, row[1], main_type, growth))
            else:
                growth = saved_growth[0]
            # Only this new level grows Av1. Historical missing growth is not
            # backfilled; all existing minor values and events are preserved.
            param["av1"] += growth
            snapshot["equip_exp"] -= cost["exp_required"]
            snapshot["gold"] -= cost["gold_cost"]
            self.store.db.execute("UPDATE equipment_instances SET level=?,param=? WHERE player_id=? AND id=?",
                                  (next_level, json.dumps(param, sort_keys=True), player_id, equip_id))
            self.economy.save_snapshot(player_id, snapshot)
            self.economy._event(player_id, f"equip-strengthen:{equip_id}:{next_level}", 12, 0, 1)
            result.update(code=10, level=next_level)
        from .login import LoginService
        changed = next(e for e in self.values(player_id)["equip"] if HERO_EQUIP.decode(e)["id"] == equip_id)
        # The client refreshes its open strengthen window as soon as it handles
        # L2C_EquipStrengthen, so its bag entry must already contain the new level.
        before = (OutboundMessage("L2C_EquipUpdate", {"code": 10, "equip": [changed]}),
                  LoginService.snapshot_push(self.store.get(player_id), self.store))
        return OutboundMessage("L2C_EquipStrengthen", result, before_response=before)

    async def handle(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("equipment operation before login")
        name = CORE_MESSAGE_REGISTRY.name_for(packet.message_id)
        req = EQUIPMENT_SCHEMAS[name].decode(packet.body)
        response = name.replace("C2L_", "L2C_", 1)
        values = {"code": 13, **{k: v for k, v in req.items() if k in ("equipID", "heroID", "posIdx")}}
        # USER_DECISION: unload clears both normal and season slots, including
        # the season-page request (2). Season acquisition/equipping is not yet
        # implemented; do not interpret a season equip as a normal equip.
        allowed = (1,) if name == "C2L_DoEquip" else (1, 2)
        if req.get("optType") not in allowed:
            return OutboundMessage(response, values)
        player = self.store.get(player_id)
        snapshot = player["snapshot"]
        hero = next((h for h in snapshot.get("heroes", []) if h["id"] == req.get("heroID") and h["state"] == 2), None)
        if hero is None:
            return OutboundMessage(response, values)
        if name == "C2L_DoEquip":
            row = self.store.db.execute("SELECT type_id FROM equipment_instances WHERE player_id=? AND id=?",
                                        (player_id, req.get("equipID"))).fetchone()
            part = self.parts.get(row[0]) - 1 if row and row[0] in self.parts else None
            if part is None:
                return OutboundMessage(response, values)
            for other in snapshot["heroes"]:
                other["equips"] = [e for e in other.get("equips", []) if e["equip_id"] != req["equipID"]]
            hero["equips"] = [e for e in hero.get("equips", []) if e["position"] != part]
            hero["equips"].append({"position": part, "equip_id": req["equipID"]})
        else:
            slot = req.get("posIdx")
            # BagModule.UnloadAllEquip sends -1; 0..5 address one slot.
            if type(slot) is not int or not -1 <= slot < 6:
                return OutboundMessage(response, values)
            changed = False
            for field in ("equips", "season_equips"):
                previous = hero.get(field, [])
                remaining = [] if slot == -1 else [e for e in previous if e["position"] != slot]
                if len(remaining) != len(previous):
                    hero[field] = remaining
                    changed = True
            if not changed and slot != -1:
                return OutboundMessage(response, values)
        if name == "C2L_DoEquip" or changed:
            self.store.save_snapshot(player_id, snapshot, player["revision"])
        logging.getLogger("x2.equipment").info(
            "equipment operation=%s player=%s hero=%s posIdx=%s optType=%s code=10",
            name, player_id, req.get("heroID"), req.get("posIdx"), req.get("optType"))
        if name == "C2L_DoEquip" and self.economy is not None:
            # 穿戴装备 (E_EquipEquip). Keyed by the equip id, so wearing the same
            # piece a second time cannot pay the condition twice; 卸下 never
            # counts, the client's own condition is about equipping.
            self.economy.record_event(player_id, f"equip:{req['equipID']}",
                                      self.economy.TASK_EVENT_EQUIP_EQUIP, 0, 1)
        from .hero import encode_hero_data
        values["code"] = 10
        pushes = (OutboundMessage("L2C_HeroUpdate", {"code": 10,
                     "heros": [encode_hero_data(h) for h in snapshot["heroes"]]}),
                  OutboundMessage("L2C_EquipUpdate", {"code": 10,
                     "equip": self.values(player_id)["equip"]}))
        # The success callback immediately reads hero wearing state.
        return OutboundMessage(response, values, before_response=pushes)
