"""Bounded first-battle compatibility service; rewards/checkout remain separate.

Entry probes are free until checkout is supported. They never mutate player
level, inventory, chapter completion or mobility. Sessions are server-generated
and persisted, so retransmitting an identical request cannot mint another run.
"""
import hashlib
import logging
import secrets
import time
import uuid

from x2server.messages.battle import BATTLE_SCHEMAS, CHECKOUT, PROFILE_HERO, HERO_SKILL, HERO_ATTR, FIGHT_HERO, FIGHT_DATA, FIGHT_PROFILE
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError


class BattleService:
    # Canonical SectionTable: tutorial and the first selectable main story.
    SECTIONS = {2110001: (2010000, 2210001), 2110801: (2010100, 2210801)}

    def __init__(self, store):
        self.store = store
        with store.db:
            store.db.execute("""CREATE TABLE IF NOT EXISTS battle_entries (
                player_id INTEGER NOT NULL, request_key TEXT NOT NULL, uuid TEXT NOT NULL,
                created_at INTEGER NOT NULL, response BLOB NOT NULL,
                PRIMARY KEY(player_id, request_key))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS battle_receipts (
                uuid TEXT PRIMARY KEY, request_hash TEXT NOT NULL,
                created_at INTEGER NOT NULL, response BLOB NOT NULL)""")

    def handlers(self):
        return {"C2L_FightData": self.enter, "C2L_DelFightProfile": self.clear_profile,
                "C2L_FightDropData": self.drop_data,
                "C2L_CheckoutMainMissionSign": self.checkout,
                "C2L_FightKillInfo": self.kill_info}

    async def kill_info(self, context, packet):
        if context.session.player_id is None:
            raise ProtocolError("kill info before login")
        # Task/kill reward accounting is not implemented.
        return OutboundMessage("L2C_FightKillInfo", {"code": 13})

    async def checkout(self, context, packet):
        """Close a local free-entry probe; never grant rewards or progression.

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
        reject = OutboundMessage("L2C_CheckoutMainMission", {"result": 13})
        if (section not in self.SECTIONS or request.get("chapterId") != self.SECTIONS[section][0]
                or request.get("expertMode") or request.get("checkGm")
                or not 0 <= request.get("fightTime", 0) <= 3600):
            return reject
        row = self.store.db.execute("SELECT uuid, created_at, response FROM battle_entries WHERE player_id=? ORDER BY rowid DESC LIMIT 1",
                                    (player_id,)).fetchone()
        if not row or int(time.time()) - row["created_at"] > 3600:
            return reject
        entry = BATTLE_SCHEMAS["L2C_FightData"].decode(row["response"])
        if FIGHT_DATA.decode(entry["data"])["missionId"] != section:
            return reject
        digest = hashlib.sha256(raw).hexdigest()
        cached = self.store.db.execute("SELECT request_hash, response FROM battle_receipts WHERE uuid=?", (row["uuid"],)).fetchone()
        schema = BATTLE_SCHEMAS["L2C_CheckoutMainMission"]
        if cached:
            return OutboundMessage("L2C_CheckoutMainMission", schema.decode(cached["response"])) if cached["request_hash"] == digest else reject
        snapshot = self.store.get(player_id)["snapshot"]
        heroes = snapshot.get("heroes", [])
        values = {"result": 10, "success": request.get("success", False), "rewardData": b"",
            "roleLevel": snapshot["level"], "roleExp": snapshot.get("exp", 0), "UpLevelNum": 0,
            "heroIDList": [h["id"] for h in heroes], "heroLevel": [h["level"] for h in heroes],
            "heroExp": [h.get("exp", 0) for h in heroes], "heroUpLevelNum": [0] * len(heroes),
            "heroFavorExp": [0] * len(heroes), "heroAddFavorExp": [0] * len(heroes),
            "heroFavorLevel": [0] * len(heroes), "heroFullLevel": [False] * len(heroes),
            "favorFullLevel": [False] * len(heroes), "fightTimeLength": request.get("fightTime", 0)}
        with self.store.db:
            self.store.db.execute("INSERT INTO battle_receipts VALUES (?,?,?,?)",
                (row["uuid"], digest, int(time.time()), schema.encode(values)))
        return OutboundMessage("L2C_CheckoutMainMission", values)

    async def drop_data(self, context, packet):
        if context.session.player_id is None:
            raise ProtocolError("battle drop requested before login")
        request = BATTLE_SCHEMAS["C2L_FightDropData"].decode(packet.body)
        logging.getLogger("x2.battle").info("unsupported drop query section=%s", request.get("missionId", 0))
        # No authoritative drop ledger exists yet. Respond explicitly rather
        # than leave a request pending until the game reconnects, or invent loot.
        return OutboundMessage("L2C_FightDropData", {"result": 13})

    async def clear_profile(self, context, packet):
        if context.session.player_id is None:
            raise ProtocolError("profile requested before login")
        request = BATTLE_SCHEMAS["C2L_DelFightProfile"].decode(packet.body)
        # There is no resumable profile in this free-entry implementation.
        # Acknowledgement does not settle a fight or delete its audit record.
        logging.getLogger("x2.battle").info("clear absent battle profile section=%s", request.get("sectionID", 0))
        return OutboundMessage("L2C_DelFightProfile", {"code": 10, "sectionID": request.get("sectionID", 0)})

    async def enter(self, context, packet):
        if context.session.player_id is None:
            raise ProtocolError("battle requested before login")
        request = BATTLE_SCHEMAS["C2L_FightData"].decode(packet.body)
        section = request.get("missionId", 0)
        logging.getLogger("x2.battle").info("battle entry section=%s chapter=%s scene=%s", section,
            request.get("chapter"), request.get("sceneId"))
        reject = OutboundMessage("L2C_FightData", {"result": 13})
        if section not in self.SECTIONS or request.get("expertMode") or request.get("checkGm") or request.get("isFromProfile"):
            return reject
        chapter, scene = self.SECTIONS[section]
        if request.get("chapter", 0) != chapter or request.get("sceneId", 0) not in (0, scene):
            return reject
        player = self.store.get(context.session.player_id)
        snapshot = player["snapshot"]
        selected = [PROFILE_HERO.decode(raw) for raw in request.get("heros", [])]
        # Only the currently recovered 1-star/level-1 hero is supported.
        if len(selected) != 1 or selected[0].get("heroId") != 1003:
            return reject
        hero = next((h for h in snapshot.get("heroes", []) if h["id"] == 1003), None)
        if not hero or (hero["state"], hero["level"], hero["star"]) != (2, 1, 1):
            return reject
        key = hashlib.sha256((context.session.session_id + ':' + str(packet.header.request_id)).encode() + packet.body).hexdigest()
        cached = self.store.db.execute("SELECT response FROM battle_entries WHERE player_id=? AND request_key=?",
                                      (player["id"], key)).fetchone()
        if cached:
            return OutboundMessage("L2C_FightData", BATTLE_SCHEMAS["L2C_FightData"].decode(cached[0]))
        # Values shown by the unmodified client for this exact local hero.
        attrs = HERO_ATTR.encode({"atk": 72, "def": 44, "hp": 720, "sp": 3000})
        skills = [HERO_SKILL.encode({"id": i, "level": 1}) for i in (10030, 10031, 10032, 10033, 10035)]
        fight_hero = FIGHT_HERO.encode({**hero, "heroGodEquip": b"", "heroSkill": skills, "heroAttrCount": attrs})
        data = FIGHT_DATA.encode({"fightHeros": [fight_hero], "missionId": section, "dropData": b"", "CRIDmg": 15000})
        profile = FIGHT_PROFILE.encode({"missionId": section, "chapterId": chapter, "layer": 0,
            "sceneId": scene, "randomSeed": secrets.randbelow(2**30), "isProfileValid": False})
        values = {"result": 10, "uuid": str(uuid.uuid4()), "sign": secrets.token_bytes(32),
                  "data": data, "fightDataProfile": profile, "playerLevel": snapshot["level"]}
        with self.store.db:
            self.store.db.execute("INSERT INTO battle_entries VALUES (?,?,?,?,?)", (player["id"], key,
                values["uuid"], int(time.time()), BATTLE_SCHEMAS["L2C_FightData"].encode(values)))
        return OutboundMessage("L2C_FightData", values)
