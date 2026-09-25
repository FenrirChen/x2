"""Bounded first battle; optional confirmed fixed rewards, no invented drops."""
import hashlib
import json
import logging
import secrets
import time
import uuid

from x2server.messages.battle import BATTLE_SCHEMAS, CHECKOUT, DROP_DATA, PROFILE_HERO, HERO_SKILL, HERO_ATTR, HERO_ATTR_ADD, FIGHT_HERO, FIGHT_DATA, FIGHT_PROFILE
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.protobuf import decode_varint, _skip_unknown
from .economy import UnresolvedEconomy
from .battle_entry import BattleEntryCatalog, EntryDenied


class BattleService:
    def __init__(self, store, economy=None):
        self.store = store
        self.economy = economy
        self.catalog = BattleEntryCatalog()
        main_rows = (economy.sections.values() if economy else
                     (r for r in self.catalog.sections.values() if r["Type"] == 0))
        self.SECTIONS = {s["SectionID"]: (s["ChapterID"], s["Maps"][0])
                         for s in main_rows if s.get("Maps")}
        with store.db:
            store.db.execute("""CREATE TABLE IF NOT EXISTS battle_entries (
                player_id INTEGER NOT NULL, request_key TEXT NOT NULL, uuid TEXT NOT NULL,
                created_at INTEGER NOT NULL, response BLOB NOT NULL,
                PRIMARY KEY(player_id, request_key))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS battle_receipts (
                uuid TEXT PRIMARY KEY, request_hash TEXT NOT NULL,
                created_at INTEGER NOT NULL, response BLOB NOT NULL)""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS battle_checkout_wire (
                uuid TEXT PRIMARY KEY, checkout BLOB NOT NULL,
                unknown_field_numbers TEXT NOT NULL)""")
            # Repeatable additive migration; legacy runs remain MainMission.
            self._add_column("battle_entries", "section_type", "INTEGER NOT NULL DEFAULT 0")
            self._add_column("battle_entries", "entry_source", "TEXT NOT NULL DEFAULT 'MainMission'")
            self._add_column("battle_entries", "map_id", "INTEGER NOT NULL DEFAULT 0")
            self._add_column("battle_entries", "team_json", "TEXT NOT NULL DEFAULT '[]'")
            if economy:
                self._add_column("economy_runs", "section_type", "INTEGER NOT NULL DEFAULT 0")
                self._add_column("economy_runs", "entry_source", "TEXT NOT NULL DEFAULT 'MainMission'")

    def _add_column(self, table, name, declaration):
        if name not in {r[1] for r in self.store.db.execute(f"PRAGMA table_info({table})")}:
            self.store.db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")

    @staticmethod
    def _unknown_checkout_fields(raw):
        known = {field.number for field in CHECKOUT.fields}
        view = memoryview(raw)
        offset = 0
        unknown = []
        while offset < len(view):
            tag, offset = decode_varint(view, offset)
            number, wire_type = tag >> 3, tag & 7
            if number not in known:
                unknown.append(number)
            offset = _skip_unknown(wire_type, view, offset)
        return sorted(set(unknown))

    def handlers(self):
        return {"C2L_FightData": self.enter, "C2L_DelFightProfile": self.clear_profile,
                "C2L_FightDropData": self.drop_data,
                "C2L_SecSweep": self.sweep,
                "C2L_CheckoutMainMissionSign": self.checkout,
                "C2L_FightKillInfo": self.kill_info}

    async def sweep(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("sweep before login")
        request = BATTLE_SCHEMAS["C2L_SecSweep"].decode(packet.body)
        section, count = request.get("sectionId", 0), request.get("sweepCount", 0)
        reject = OutboundMessage("L2C_SecSweep", {"code": 13, "sectionId": section, "sweepCount": count})
        if not self.economy:
            return reject
        key = hashlib.sha256((str(player_id) + ":" + context.session.session_id + ":" +
            str(packet.header.request_id)).encode() + packet.body).hexdigest()
        schema = BATTLE_SCHEMAS["L2C_SecSweep"]
        cached = self.store.db.execute("SELECT response FROM sweep_receipts WHERE request_key=? AND player_id=?",
                                       (key, player_id)).fetchone()
        if cached:
            return OutboundMessage("L2C_SecSweep", schema.decode(cached[0]),
                                   pushes=self.economy.pushes(player_id))
        try:
            with self.store.db:
                reward_data = self.economy.settle_sweep(player_id, section, count, key)
                values = {"code": 10, "sectionId": section, "sweepCount": count,
                          "rewardData": reward_data}
                self.store.db.execute("INSERT INTO sweep_receipts VALUES (?,?,?,?)",
                    (key, player_id, section, schema.encode(values)))
        except UnresolvedEconomy:
            return reject
        return OutboundMessage("L2C_SecSweep", values, pushes=self.economy.pushes(player_id))

    async def kill_info(self, context, packet):
        if context.session.player_id is None:
            raise ProtocolError("kill info before login")
        request = BATTLE_SCHEMAS["C2L_FightKillInfo"].decode(packet.body)
        section = request.get("sectionId", 0)
        row = self.store.db.execute("SELECT response, created_at FROM battle_entries WHERE player_id=? ORDER BY rowid DESC LIMIT 1",
                                    (context.session.player_id,)).fetchone()
        accepted = bool(row and int(time.time()) - row["created_at"] <= 3600
            and FIGHT_DATA.decode(BATTLE_SCHEMAS["L2C_FightData"].decode(row["response"])["data"])["missionId"] == section)
        # Receipt of practice telemetry only; no tasks or rewards are updated.
        logging.getLogger("x2.battle").info("practice kill report section=%s accepted=%s digest=%s",
            section, accepted, hashlib.sha256(packet.body).hexdigest())
        return OutboundMessage("L2C_FightKillInfo", {"code": 10 if accepted else 13})

    async def checkout(self, context, packet):
        """Close a bounded run; economy and receipt commit atomically when enabled.

        This is a single-account compatibility receipt, not replay verification.
        The latest bounded entry is the only candidate and expires in one hour.
        An identical retry returns the stored result; a conflicting one is denied.
        """
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("checkout before login")
        envelope = BATTLE_SCHEMAS["C2L_CheckoutMainMissionSign"].decode(packet.body)
        raw = envelope.get("checkout", b"")
        request = CHECKOUT.decode(raw)
        section = request.get("sectionId", 0)
        logging.getLogger("x2.battle").info("practice checkout section=%s success=%s", section, request.get("success", False))
        logging.getLogger("x2.battle").info("checkout outsideItems=%s killMonster=%s npcEvents=%s",
            len(request.get("outsideItems", [])), "killMonster" in request,
            len(request.get("npcEventOnNumber", [])))
        reject = OutboundMessage("L2C_CheckoutMainMission", {"result": 13})
        static = self.catalog.sections.get(section)
        section_type = static["Type"] if static else None
        if (not static or request.get("chapterId") != static["ChapterID"]
                or request.get("checkGm")
                or not 0 <= request.get("fightTime", 0) <= 3600):
            return reject
        row = self.store.db.execute("SELECT uuid, created_at, response FROM battle_entries WHERE player_id=? ORDER BY rowid DESC LIMIT 1",
                                    (player_id,)).fetchone()
        if not row or int(time.time()) - row["created_at"] > 3600:
            return reject
        entry = BATTLE_SCHEMAS["L2C_FightData"].decode(row["response"])
        if FIGHT_DATA.decode(entry["data"])["missionId"] != section:
            return reject
        if self.economy:
            run = self.store.db.execute("SELECT * FROM economy_runs WHERE uuid=?", (row["uuid"],)).fetchone()
            if not run or run["player_id"] != player_id or run["section_type"] != section_type:
                return reject  # Old practice entries cannot acquire rewards retroactively.
        digest = hashlib.sha256(packet.body if self.economy else raw).hexdigest()
        cached = self.store.db.execute("SELECT request_hash, response FROM battle_receipts WHERE uuid=?", (row["uuid"],)).fetchone()
        schema = BATTLE_SCHEMAS["L2C_CheckoutMainMission"]
        if cached:
            return OutboundMessage("L2C_CheckoutMainMission", schema.decode(cached["response"]),
                pushes=self.economy.pushes(player_id) if self.economy else ()) if cached["request_hash"] == digest else reject
        snapshot = self.store.get(player_id)["snapshot"]
        heroes = snapshot.get("heroes", [])
        values = {"result": 10, "success": request.get("success", False), "rewardData": b"",
            "roleLevel": snapshot["level"], "roleExp": snapshot.get("exp", 0), "UpLevelNum": 0,
            "heroIDList": [h["id"] for h in heroes], "heroLevel": [h["level"] for h in heroes],
            "heroExp": [h.get("exp", 0) for h in heroes], "heroUpLevelNum": [0] * len(heroes),
            "heroFavorExp": [0] * len(heroes), "heroAddFavorExp": [0] * len(heroes),
            "heroFavorLevel": [0] * len(heroes), "heroFullLevel": [False] * len(heroes),
            "favorFullLevel": [False] * len(heroes), "fightTimeLength": request.get("fightTime", 0)}
        try:
            with self.store.db:
                if self.economy:
                    self.store.db.execute("INSERT OR IGNORE INTO economy_checkouts VALUES (?,?,?)", (player_id, digest, row["uuid"]))
                    values["rewardData"] = self.economy.settle(
                        player_id, row["uuid"], section, request.get("success", False), section_type,
                        request.get("outsideItems", []))
                    updated = self.store.get(player_id)["snapshot"]
                    values.update(roleExp=updated.get("exp", 0), roleLevel=updated["level"], UpLevelNum=updated["level"]-snapshot["level"])
                self.store.db.execute("INSERT INTO battle_receipts VALUES (?,?,?,?)",
                    (row["uuid"], digest, int(time.time()), schema.encode(values)))
                self.store.db.execute("INSERT INTO battle_checkout_wire VALUES (?,?,?)",
                    (row["uuid"], raw, json.dumps(self._unknown_checkout_fields(raw))))
        except UnresolvedEconomy:
            return reject
        return OutboundMessage("L2C_CheckoutMainMission", values,
            pushes=self.economy.pushes(player_id) if self.economy else ())

    async def drop_data(self, context, packet):
        if context.session.player_id is None:
            raise ProtocolError("battle drop requested before login")
        request = BATTLE_SCHEMAS["C2L_FightDropData"].decode(packet.body)
        section = request.get("missionId", 0)
        reject = OutboundMessage("L2C_FightDropData", {"result": 13})
        static = self.catalog.sections.get(section)
        if (not static or request.get("chapterId") != static["ChapterID"]):
            return reject
        row = self.store.db.execute("SELECT response, created_at FROM battle_entries WHERE player_id=? ORDER BY rowid DESC LIMIT 1",
                                    (context.session.player_id,)).fetchone()
        if not row or int(time.time()) - row["created_at"] > 3600:
            return reject
        entry = BATTLE_SCHEMAS["L2C_FightData"].decode(row["response"])
        if FIGHT_DATA.decode(entry["data"])["missionId"] != section:
            return reject
        # Explicit local practice rule: no server drops. The receiver constructs
        # its list before decoding, so an empty repeated field remains valid.
        logging.getLogger("x2.battle").info("practice empty drop query section=%s", section)
        return OutboundMessage("L2C_FightDropData", {"result": 10, "uuid": entry["uuid"],
            "sign": entry["sign"], "data": DROP_DATA.encode({"missionId": section})})

    async def clear_profile(self, context, packet):
        if context.session.player_id is None:
            raise ProtocolError("profile requested before login")
        request = BATTLE_SCHEMAS["C2L_DelFightProfile"].decode(packet.body)
        # No resumable profile; a replacement entry handles abandoned-run refunds.
        # Acknowledgement does not settle a fight or delete its audit record.
        logging.getLogger("x2.battle").info("clear absent battle profile section=%s", request.get("sectionID", 0))
        return OutboundMessage("L2C_DelFightProfile", {"code": 10, "sectionID": request.get("sectionID", 0)})

    async def enter(self, context, packet):
        if context.session.player_id is None:
            raise ProtocolError("battle requested before login")
        request = BATTLE_SCHEMAS["C2L_FightData"].decode(packet.body)
        section = request.get("missionId", 0)
        logging.getLogger("x2.battle").info(
            "battle entry section=%s chapter=%s scene=%s expert=%s gm=%s profile=%s",
            section, request.get("chapter"), request.get("sceneId"),
            request.get("expertMode", False), request.get("checkGm", False),
            request.get("isFromProfile", False))
        reject = OutboundMessage("L2C_FightData", {"result": 13})
        player = self.store.get(context.session.player_id)
        snapshot = player["snapshot"]
        selected = [PROFILE_HERO.decode(raw) for raw in request.get("heros", [])]
        if not 1 <= len(selected) <= 3 or len({h.get("heroId") for h in selected}) != len(selected):
            return reject
        from .progression import battle_hero_base, hero_attributes, hero_skills, catalog
        owned = {h["id"]: h for h in snapshot.get("heroes", [])}
        heroes = [owned.get(h.get("heroId")) for h in selected]
        if any(not h or h["state"] != 2 or str(h["id"]) not in battle_hero_base()
               or not 1 <= h["level"] <= 120 or not 1 <= h["star"] <= 46 for h in heroes):
            return reject
        try:
            entry_context = self.catalog.resolve(player_id=player["id"], request=request,
                snapshot=snapshot, selected_ids=[h["id"] for h in heroes], store=self.store,
                economy=self.economy)
        except (EntryDenied, UnresolvedEconomy) as exc:
            logging.getLogger("x2.battle").info("battle entry denied section=%s reason=%s", section, exc)
            return reject
        chapter, scene = entry_context.chapter_id, entry_context.map_id
        key = hashlib.sha256((context.session.session_id + ':' + str(packet.header.request_id)).encode() + packet.body).hexdigest()
        cached = self.store.db.execute("SELECT response FROM battle_entries WHERE player_id=? AND request_key=?",
                                      (player["id"], key)).fetchone()
        if cached:
            return OutboundMessage("L2C_FightData", BATTLE_SCHEMAS["L2C_FightData"].decode(cached[0]))
        fight_heroes = []
        for hero in heroes:
            attrs = HERO_ATTR.encode(hero_attributes(hero))
            skills = [HERO_SKILL.encode(s) for s in hero_skills(hero)]
            hero_values = {k:v for k,v in hero.items() if k in ("id", "state", "level", "star", "exp")}
            # Raw bases are keyed by the selected hero; the client applies growth.
            base_values = battle_hero_base()[str(hero["id"])]
            base = [HERO_ATTR_ADD.encode({"attrId":r["attrId"], "attrValue":base_values[r["name"]]})
                for r in catalog()["battle_base_1003"]["attributes"]]
            fight_heroes.append(FIGHT_HERO.encode({**hero_values, "heroGodEquip": b"",
                "heroSkill": skills, "heroAttrCount": attrs, "attrAdd": base}))
        data = FIGHT_DATA.encode({"fightHeros": fight_heroes, "missionId": section,
                                  "dropData": b"", "CRIDmg": 15000})
        profile = FIGHT_PROFILE.encode({"missionId": section, "chapterId": chapter, "layer": 0,
            "sceneId": scene, "randomSeed": secrets.randbelow(2**30), "isProfileValid": False})
        values = {"result": 10, "uuid": str(uuid.uuid4()), "sign": secrets.token_bytes(32),
                  "data": data, "fightDataProfile": profile, "playerLevel": snapshot["level"]}
        try:
            with self.store.db:
                if self.economy:
                    # Replacing an unfinished run abandons it, refunding its cost.
                    for old in self.store.db.execute("SELECT uuid FROM economy_runs WHERE player_id=? AND settled=0", (player["id"],)).fetchall():
                        self.economy.refund_battle(player["id"], old[0])
                        self.store.db.execute("UPDATE economy_runs SET settled=1 WHERE uuid=?", (old[0],))
                    self.economy.charge_battle(player["id"], values["uuid"], section, entry_context.stamina_cost)
                    self.store.db.execute("""INSERT INTO economy_runs
                        (uuid,player_id,session_id,section_id,section_type,entry_source) VALUES (?,?,?,?,?,?)""",
                        (values["uuid"], player["id"], context.session.session_id, section,
                         entry_context.section_type, entry_context.entry_source))
                self.store.db.execute("""INSERT INTO battle_entries
                    (player_id,request_key,uuid,created_at,response,section_type,entry_source,map_id,team_json)
                    VALUES (?,?,?,?,?,?,?,?,?)""", (player["id"], key, values["uuid"], int(time.time()),
                    BATTLE_SCHEMAS["L2C_FightData"].encode(values), entry_context.section_type,
                    entry_context.entry_source, entry_context.map_id, json.dumps(entry_context.hero_ids)))
        except UnresolvedEconomy:
            return reject
        return OutboundMessage("L2C_FightData", values, pushes=self.economy.pushes(player["id"]) if self.economy else ())
