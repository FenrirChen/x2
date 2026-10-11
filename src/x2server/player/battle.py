"""Bounded first battle; optional confirmed fixed rewards, no invented drops."""
import hashlib
import json
import logging
import secrets
import time
import uuid
from importlib.resources import files

from x2server.messages.battle import (BATTLE_SCHEMAS, CHECKOUT, DROP_DATA, OUTSIDE_ITEM, PROFILE_HERO,
    HERO_SKILL, HERO_ATTR, HERO_ATTR_ADD, FIGHT_HERO, FIGHT_DATA, FIGHT_PROFILE, FIGHT_KILL_DATA)
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
        self.monster_levels = {int(k): v for k, v in json.loads(
            files("x2server").joinpath("data/battle_monster_levels.json").read_text(encoding="utf-8"))["levels"].items()}
        self.unit_types = {int(k): v for k, v in json.loads(
            files("x2server").joinpath("data/unit_types.json").read_text(encoding="utf-8")).items()}
        from .drop_budget import DropBudgetCompatibilityPolicy
        self.drop_budget = DropBudgetCompatibilityPolicy(
            {s["SectionID"]: s.get("DifficultyLevel", 0) for s in self.catalog.sections.values()})
        main_rows = (economy.sections.values() if economy else
                     (r for r in self.catalog.sections.values() if r["Type"] == 0))
        self.SECTIONS = {s["SectionID"]: (s["ChapterID"], s["Maps"][0])
                         for s in main_rows if s.get("Maps")}
        with store.db:
            store.db.execute("""CREATE TABLE IF NOT EXISTS battle_entries (
                player_id INTEGER NOT NULL, request_key TEXT NOT NULL, uuid TEXT NOT NULL,
                created_at INTEGER NOT NULL, response BLOB NOT NULL,
                PRIMARY KEY(player_id, request_key))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS battle_drop_budget_versions (
                uuid TEXT PRIMARY KEY, policy_version TEXT NOT NULL)""")
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
            self._add_column("battle_entries", "ai_cost", "INTEGER NOT NULL DEFAULT 0")
            if economy:
                self._add_column("economy_runs", "section_type", "INTEGER NOT NULL DEFAULT 0")
                self._add_column("economy_runs", "entry_source", "TEXT NOT NULL DEFAULT 'MainMission'")
            from .drop_report import FightDropRecorder
            self.drop_recorder = FightDropRecorder(store)

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
        return {"C2L_PrepareMainMission": self.prepare_main_mission,
                "C2L_FightData": self.enter, "C2L_DelFightProfile": self.clear_profile,
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
        except UnresolvedEconomy as exc:
            logging.getLogger("x2.battle").info(
                "sweep rejected player=%s section=%s count=%s reason=%s", player_id, section, count, exc)
            return reject
        logging.getLogger("x2.battle").info("sweep accepted player=%s section=%s count=%s", player_id, section, count)
        return OutboundMessage("L2C_SecSweep", values, pushes=self.economy.pushes(player_id))

    async def kill_info(self, context, packet):
        if context.session.player_id is None:
            raise ProtocolError("kill info before login")
        request = BATTLE_SCHEMAS["C2L_FightKillInfo"].decode(packet.body)
        section = request.get("sectionId", 0)
        row = self.store.db.execute("SELECT uuid, response, created_at FROM battle_entries WHERE player_id=? ORDER BY rowid DESC LIMIT 1",
                                    (context.session.player_id,)).fetchone()
        accepted = bool(row and int(time.time()) - row["created_at"] <= 3600
            and FIGHT_DATA.decode(BATTLE_SCHEMAS["L2C_FightData"].decode(row["response"])["data"])["missionId"] == section)
        credited = False
        if (accepted and self.economy and request.get("datas")
                and self.catalog.sections.get(section, {}).get('Type') != 5):
            receipt = self.store.db.execute("SELECT response FROM battle_receipts WHERE uuid=?", (row["uuid"],)).fetchone()
            settled = BATTLE_SCHEMAS["L2C_CheckoutMainMission"].decode(receipt[0]) if receipt else {}
            if settled.get("result") == 10 and settled.get("success"):
                by_type = {}
                total = 0
                for raw in request["datas"]:
                    report = FIGHT_KILL_DATA.decode(raw)
                    units, counts = report.get("unitId", []), report.get("num", [])
                    if len(units) != len(counts) or len(units) > 512:
                        continue
                    for unit, count in zip(units, counts):
                        if type(count) is not int or not 0 < count <= 10_000:
                            continue
                        total += count
                        kind = self.unit_types.get(unit)
                        if kind is not None:
                            by_type[kind] = by_type.get(kind, 0) + count
                if 0 < total <= 100_000:
                    with self.economy.transaction():
                        chapter = self.catalog.sections[section]["ChapterID"]
                        for raw in request["datas"]:
                            report = FIGHT_KILL_DATA.decode(raw)
                            units, counts = report.get("unitId", []), report.get("num", [])
                            if len(units) == len(counts) and len(units) <= 512:
                                for unit, count in zip(units, counts):
                                    if 0 < count <= 10_000:
                                        if self.catalog.sections[section]['Type'] == 7:
                                            self.economy.endless.observe(context.session.player_id, row['uuid'], 1, unit, count)
                                        self.economy.dp.observe(context.session.player_id, chapter,
                                            row["uuid"], "kill", unit, count, report.get("heroId", 0))
                        self.economy._event(context.session.player_id, f"kills:{row['uuid']}", 1, 0, total)
                        self.economy.dp.refresh(context.session.player_id, chapter)
                        for kind, count in by_type.items():
                            self.economy._event(context.session.player_id,
                                f"kills:{row['uuid']}:type:{kind}", 2, kind, count)
                    credited = True
        logging.getLogger("x2.battle").info("practice kill report section=%s accepted=%s digest=%s",
            section, accepted, hashlib.sha256(packet.body).hexdigest())
        return OutboundMessage("L2C_FightKillInfo", {"code": 10 if accepted else 13},
            pushes=self.economy.pushes(context.session.player_id) if credited else ())

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
        outside_decoded = [OUTSIDE_ITEM.decode(o) for o in request.get("outsideItems", [])]
        logging.getLogger("x2.battle").debug("checkout outsideItems=%s detail=%s killMonster=%s npcEvents=%s",
            len(request.get("outsideItems", [])), outside_decoded, "killMonster" in request,
            len(request.get("npcEventOnNumber", [])))
        reject = OutboundMessage("L2C_CheckoutMainMission", {"result": 13})

        def reject_with(reason):
            logging.getLogger("x2.battle").info("checkout rejected section=%s reason=%s", section, reason)
            return reject
        static = self.catalog.sections.get(section)
        section_type = static["Type"] if static else None
        if (not static or request.get("chapterId") != static["ChapterID"]
                or request.get("checkGm")
                or not 0 <= request.get("fightTime", 0) <= 3600):
            return reject_with('static/chapter/checkGm/fightTime gate')
        row = self.store.db.execute("SELECT uuid, created_at, response, ai_cost FROM battle_entries WHERE player_id=? ORDER BY rowid DESC LIMIT 1",
                                    (player_id,)).fetchone()
        if not row or int(time.time()) - row["created_at"] > 3600:
            return reject_with('no/expired battle entry')
        # Some 2.4 client paths submit fightTime=0. The entry timestamp is the
        # server-side start of this run, so use elapsed time for that case.
        fight_seconds = request.get("fightTime", 0) or max(1, min(3600, int(time.time()) - row["created_at"]))
        entry = BATTLE_SCHEMAS["L2C_FightData"].decode(row["response"])
        if FIGHT_DATA.decode(entry["data"])["missionId"] != section:
            return reject_with('entry missionId mismatch')
        if self.economy:
            run = self.store.db.execute("SELECT * FROM economy_runs WHERE uuid=?", (row["uuid"],)).fetchone()
            if not run or run["player_id"] != player_id or run["section_type"] != section_type:
                return reject_with('economy run missing/mismatched')  # Old practice entries cannot acquire rewards retroactively.
        reward_equips: tuple = ()
        digest = hashlib.sha256(packet.body if self.economy else raw).hexdigest()
        cached = self.store.db.execute("SELECT request_hash, response FROM battle_receipts WHERE uuid=?", (row["uuid"],)).fetchone()
        schema = BATTLE_SCHEMAS["L2C_CheckoutMainMission"]
        if cached:
            if cached['request_hash'] != digest:
                return reject
            before, pushes = self._checkout_star_sync(self.economy.pushes(player_id) if self.economy else ())
            return OutboundMessage("L2C_CheckoutMainMission", schema.decode(cached["response"]),
                                   before_response=before, pushes=pushes)
        snapshot = self.store.get(player_id)["snapshot"]
        heroes = snapshot.get("heroes", [])
        # The client echoes the selected hero state in checkout.  Preserve a
        # validated god-equip payload so the next Current Echoes configuration
        # can see traces carried out of the run.  Older builds omit this field.
        carried_artifacts = {}
        for raw_hero in request.get("heros", []):
            try:
                wire_hero = FIGHT_HERO.decode(raw_hero)
                god_raw = wire_hero.get("heroGodEquip", b"")
                if not god_raw:
                    continue
                god = __import__("x2server.messages.core", fromlist=["HERO_GOD_EQUIP"]).HERO_GOD_EQUIP.decode(god_raw)
                if god.get("id", 0) > 0 and wire_hero.get("id", 0) > 0:
                    carried_artifacts[int(wire_hero["id"])] = god
            except (TypeError, ValueError, KeyError):
                continue
        values = {"result": 10, "success": request.get("success", False), "rewardData": b"",
            "roleLevel": snapshot["level"], "roleExp": snapshot.get("exp", 0), "UpLevelNum": 0,
            "heroIDList": [h["id"] for h in heroes], "heroLevel": [h["level"] for h in heroes],
            "heroExp": [h.get("exp", 0) for h in heroes], "heroUpLevelNum": [0] * len(heroes),
            "heroFavorExp": [0] * len(heroes), "heroAddFavorExp": [0] * len(heroes),
            "heroFavorLevel": [0] * len(heroes), "heroFullLevel": [False] * len(heroes),
            "favorFullLevel": [False] * len(heroes), "fightTimeLength": fight_seconds}
        try:
            with self.store.db:
                if (self.economy and carried_artifacts and section_type != 5
                        and self.economy.sections.get(section, {}).get("AssistType", {}).get("value") != 1):
                    current = self.store.get(player_id)["snapshot"]
                    changed = False
                    for hero in current.get("heroes", []):
                        god = carried_artifacts.get(int(hero.get("id", 0)))
                        if not god or hero.get("state") != 2:
                            continue
                        artifact = hero.get("god_equip") or {}
                        if artifact.get("id") != god.get("id"):
                            continue
                        artifact["level"] = int(god.get("level", artifact.get("level", 0)))
                        artifact["star"] = int(god.get("star", artifact.get("star", 0)))
                        hero["god_equip"] = artifact
                        changed = True
                    if changed:
                        self.economy.save_snapshot(player_id, current)
                if self.economy:
                    if request.get('useAIPoint') and row['ai_cost'] == 0:
                        from .star_chart import consume_battle_ai
                        consume_battle_ai(self.economy, player_id, section)
                    self.store.db.execute("INSERT OR IGNORE INTO economy_checkouts VALUES (?,?,?)", (player_id, digest, row["uuid"]))
                    values["rewardData"], reward_equips = self.economy.settle(
                        player_id, row["uuid"], section, request.get("success", False), section_type,
                        request.get("outsideItems", []), request.get("mazeItems", []))
                    if section_type == 6:
                        self.economy.world_boss.finish_battle(player_id,row['uuid'],request.get('success',False),confirmed=True)
                    updated = self.store.get(player_id)["snapshot"]
                    values.update(roleExp=updated.get("exp", 0), roleLevel=updated["level"], UpLevelNum=updated["level"]-snapshot["level"])
                self.store.db.execute("INSERT INTO battle_receipts VALUES (?,?,?,?)",
                    (row["uuid"], digest, int(time.time()), schema.encode(values)))
                self.store.db.execute("INSERT INTO battle_checkout_wire VALUES (?,?,?)",
                    (row["uuid"], raw, json.dumps(self._unknown_checkout_fields(raw))))
        except UnresolvedEconomy as exc:
            logging.getLogger("x2.battle").info(
                "checkout rejected section=%s reason=settle: %s", section, exc)
            return reject
        pushes = self.economy.pushes(player_id) if self.economy else ()
        if reward_equips:
            # Official "subsequent change" channel: some client builds only apply
            # equipment ledger updates via EquipUpdate, not via 152.rewardEquip.
            pushes = (OutboundMessage("L2C_EquipUpdate",
                                      {"code": 10, "equip": reward_equips}),) + tuple(pushes)
        # StarChartModule.OnCheckOutMainMission reads StarMap during this
        # response callback. Publish it first so a chapter completion unlocks
        # its ability immediately without requiring another login.
        star_before, pushes = self._checkout_star_sync(pushes)
        return OutboundMessage("L2C_CheckoutMainMission", values, pushes=pushes,
                               before_response=star_before)

    @staticmethod
    def _checkout_star_sync(pushes):
        before, after = [], []
        for push in pushes:
            if push.message_name == 'PlayerDataProto' and 'StarMap' in push.values:
                before.append(OutboundMessage('PlayerDataProto', {'StarMap': push.values['StarMap']},
                                              data_version=push.data_version))
                after.append(OutboundMessage('PlayerDataProto',
                    {k: v for k, v in push.values.items() if k != 'StarMap'}, data_version=push.data_version))
            else:
                after.append(push)
        return tuple(before), tuple(after)

    async def drop_data(self, context, packet):
        if context.session.player_id is None:
            raise ProtocolError("battle drop requested before login")
        request = BATTLE_SCHEMAS["C2L_FightDropData"].decode(packet.body)
        section = request.get("missionId", 0)
        reject = OutboundMessage("L2C_FightDropData", {"result": 13})
        def reject_with(reason):
            logging.getLogger("x2.battle").info(
                "battle drop rejected section=%s reason=%s", section, reason)
            return reject

        static = self.catalog.sections.get(section)
        if (not static or request.get("chapterId") != static["ChapterID"]):
            return reject_with('static/chapter gate')
        row = self.store.db.execute("""SELECT e.response,e.created_at,v.policy_version
            FROM battle_entries e LEFT JOIN battle_drop_budget_versions v ON v.uuid=e.uuid
            WHERE e.player_id=? ORDER BY e.rowid DESC LIMIT 1""",
                                    (context.session.player_id,)).fetchone()
        if not row or int(time.time()) - row["created_at"] > 3600:
            return reject_with('no/expired battle entry')
        entry = BATTLE_SCHEMAS["L2C_FightData"].decode(row["response"])
        if FIGHT_DATA.decode(entry["data"])["missionId"] != section:
            return reject_with('entry missionId mismatch')
        try:
            with self.store.db:
                self.drop_recorder.record(context.session.player_id, context.session.session_id,
                    packet.header.request_id, entry["uuid"], packet.body, request,
                    {"section_id": section, "chapter_id": static["ChapterID"],
                     "scene_id": request.get("sceneId", 0), "section_type": static["Type"]})
        except Exception:
            logging.getLogger("x2.battle").exception("264 observation failed")
        boss_confirmed = False
        if self.economy:
            try:
                with self.economy.transaction():
                    if static['Type'] == 6:
                        boss_confirmed = self.economy.world_boss.confirm_battle(context.session.player_id, entry['uuid'])
                    self.economy.endless.save(context.session.player_id, entry, request)
                    self.economy.dp.report(context.session.player_id, static["ChapterID"], entry["uuid"], request)
            except Exception:
                logging.getLogger("x2.battle").exception("264 DP observation failed")
        # Official chain (ARM64 2026-09-25): FightModule.OnFightDropData(0x1447E1C)
        # checks result==10, deserializes response.data as FightDropData and feeds its
        # dropValues into the running battle as LogicX2Command.UpdateDropValue
        # (LogicBattle.OnInput 0x1448224) — that is how BattleInfo.dropValues (the
        # JudgeDropItem budget) is armed mid-battle. An empty dropValues kept every
        # client-side ItemStruct drop rejected (outsideItems stayed empty).
        # Budget VALUES are REVIVAL_COMPATIBILITY tiers
        # (docs/decisions/compatibility/equip_dropvalues_budget.md).
        # Entry wire is the immutable value cap for this run. Repeated 264,
        # restart, configuration changes and rollback must not replace it or
        # add another full allowance. The client retains its cumulative ledger.
        saved_drop = DROP_DATA.decode(FIGHT_DATA.decode(entry['data'])['dropData'])
        drop_values = saved_drop.get('dropValues', [])
        from .drop_budget import GROUP_COUNT, LEGACY_GROUP_COUNT
        if (saved_drop.get('missionId') != section
                or len(drop_values) not in (LEGACY_GROUP_COUNT, GROUP_COUNT)
                or any(value < 0 for value in drop_values)):
            return reject_with('invalid saved budget')
        tier, known = self.drop_budget.tier_for(section)
        logging.getLogger("x2.battle").info(
            "battle drop query section=%s difficulty=%s tier=%s known=%s default_group_budget=%s budget_groups=%d beastlord_budget=%s budget_version=%s",
            section, static.get("DifficultyLevel", 0), tier, known,
            drop_values[0], len(drop_values), drop_values[5],
            row['policy_version'] or 'legacy-20260926')
        return OutboundMessage("L2C_FightDropData", {"result": 10, "uuid": entry["uuid"],
            "sign": entry["sign"], "data": DROP_DATA.encode({"dropValues": drop_values,
                                                             "missionId": section})},
            before_response=self.economy.pushes(context.session.player_id) if boss_confirmed else ())

    async def clear_profile(self, context, packet):
        if context.session.player_id is None:
            raise ProtocolError("profile requested before login")
        request = BATTLE_SCHEMAS["C2L_DelFightProfile"].decode(packet.body)
        # No resumable profile; a replacement entry handles abandoned-run refunds.
        # Acknowledgement does not settle a fight or delete its audit record.
        if self.economy:
            with self.economy.transaction():
                self.store.db.execute('DELETE FROM endless_profiles WHERE player_id=? AND section_id=?', (context.session.player_id,request.get('sectionID',0)))
        logging.getLogger("x2.battle").info("clear battle profile section=%s", request.get("sectionID", 0))
        return OutboundMessage("L2C_DelFightProfile", {"code": 10, "sectionID": request.get("sectionID", 0)})

    async def prepare_main_mission(self, context, packet):
        if context.session.player_id is None:
            raise ProtocolError("mission preparation before login")
        from x2server.messages.core import C2L_PREPARE_MAIN_MISSION
        request = C2L_PREPARE_MAIN_MISSION.decode(packet.body)
        chapter, section = request.get("chapter", 0), request.get("level", 0)
        row = self.catalog.sections.get(section)
        accepted = bool(row and row["ChapterID"] == chapter and row["Type"] == 0)
        logging.getLogger("x2.tutorial").info("prepare mission player=%s chapter=%s section=%s accepted=%s",
            context.session.player_id, chapter, section, accepted)
        return OutboundMessage("L2C_PrepareMainMission", {"result": 10 if accepted else 13})

    async def enter(self, context, packet):
        if context.session.player_id is None:
            raise ProtocolError("battle requested before login")
        request = BATTLE_SCHEMAS["C2L_FightData"].decode(packet.body)
        section = request.get("missionId", 0)
        logging.getLogger("x2.battle").info(
            "battle entry section=%s chapter=%s scene=%s expert=%s gm=%s profile=%s selectedRelicList=%s",
            section, request.get("chapter"), request.get("sceneId"),
            request.get("expertMode", False), request.get("checkGm", False),
            request.get("isFromProfile", False), request.get("selectedRelicList", []))
        reject = OutboundMessage("L2C_FightData", {"result": 13})
        player = self.store.get(context.session.player_id)
        snapshot = player["snapshot"]
        selected = [PROFILE_HERO.decode(raw) for raw in request.get("heros", [])]
        if not 1 <= len(selected) <= 3 or len({h.get("heroId") for h in selected}) != len(selected):
            return reject
        if request.get('isFromProfile') and self.economy and self.catalog.sections.get(section, {}).get('Type') == 7:
            saved = self.store.db.execute('SELECT * FROM endless_profiles WHERE player_id=? AND section_id=?', (player['id'],section)).fetchone()
            if not saved or not self.economy.endless.active_run(saved['run_id'],player['id']):
                return reject
            run = self.store.db.execute('SELECT response,team_json FROM battle_entries WHERE uuid=? AND player_id=?', (saved['run_id'],player['id'])).fetchone()
            if not run or {h.get('heroId') for h in selected} != set(json.loads(run['team_json'])):
                return reject
            values = BATTLE_SCHEMAS['L2C_FightData'].decode(run['response'])
            # Restore the run's element-compose tally so the resumed battle shows
            # the same formula counts / exp the client had before the reconnect.
            values['fightDataProfile'] = self.economy.element_compose.refresh_profile(
                player['id'], saved['run_id'], saved['profile'])
            with self.store.db:
                self.store.db.execute('UPDATE battle_entries SET created_at=? WHERE uuid=?', (int(time.time()),saved['run_id']))
                self.store.db.execute('UPDATE economy_runs SET session_id=? WHERE uuid=?', (context.session.session_id,saved['run_id']))
            return OutboundMessage('L2C_FightData', values, pushes=self.economy.pushes(player['id']))
        from .progression import battle_hero_base, hero_attributes, hero_skills, catalog
        owned = {h["id"]: h for h in snapshot.get("heroes", [])}
        section_config = self.economy.sections.get(section) if self.economy else None
        trial_unit = None
        if section_config and section_config.get("AssistType", {}).get("value") == 1:
            trial_unit = next((unit for unit in section_config.get("AssistParam", []) if unit > 0), None)
        heroes = []
        for selected_hero in selected:
            hero_id = selected_hero.get("heroId")
            if trial_unit is not None:
                from .trial_units import trial_hero
                hero = trial_hero(trial_unit, hero_id)
            else:
                hero = owned.get(hero_id)
            heroes.append(hero)
        if any(not h or h["state"] != 2 or str(h.get("battle_base_id", h["id"])) not in battle_hero_base()
               or not 1 <= h["level"] <= 120 or not 1 <= h["star"] <= 46 for h in heroes):
            return reject
        key = hashlib.sha256((context.session.session_id + ':' + str(packet.header.request_id)).encode() + packet.body).hexdigest()
        cached = self.store.db.execute("SELECT response FROM battle_entries WHERE player_id=? AND request_key=?",
                                      (player["id"], key)).fetchone()
        if cached:
            logging.getLogger("x2.battle").info("battle entry replay player=%s section=%s", player["id"], section)
            return OutboundMessage("L2C_FightData", BATTLE_SCHEMAS["L2C_FightData"].decode(cached[0]),
                pushes=self.economy.pushes(player['id']) if self.economy else ())
        try:
            entry_context = self.catalog.resolve(player_id=player["id"], request=request,
                snapshot=snapshot, selected_ids=[h["id"] for h in heroes], store=self.store,
                economy=self.economy)
        except (EntryDenied, UnresolvedEconomy) as exc:
            logging.getLogger("x2.battle").info("battle entry denied section=%s reason=%s", section, exc)
            return reject
        chapter, scene = entry_context.chapter_id, entry_context.map_id
        if entry_context.section_type == 6 and self.economy:
            try:
                resumed=self.economy.world_boss.resume_battle(player['id'],section,[h['id'] for h in heroes])
            except ValueError as exc:
                logging.getLogger('x2.battle').info('Boss resume rejected player=%s reason=%s',player['id'],exc)
                return reject
            if resumed:
                return OutboundMessage('L2C_FightData',resumed,pushes=self.economy.pushes(player['id']))
        selected_relics = request.get("selectedRelicList", [])
        if selected_relics:
            from .login import relic_item_ids
            from importlib.resources import files
            # Client MiracleChooseModule also adds StarDefultRelic. These are
            # canonical built-ins, not collected bag items; never grant them.
            defaults = set(json.loads(files("x2server").joinpath(
                "data/battle_relic_defaults.json").read_text(encoding="utf-8"))["StarDefultRelic"])
            collected = set()
            if self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='inventory'").fetchone():
                collected = {r[0] for r in self.store.db.execute(
                    "SELECT item_id FROM inventory WHERE player_id=? AND quantity>0", (player["id"],))
                    if r[0] in relic_item_ids()}
            if (len(set(selected_relics)) != len(selected_relics)
                    or not set(selected_relics) <= collected | defaults):
                logging.getLogger("x2.battle").info(
                    "battle entry denied section=%s reason=invalid/unowned selectedRelicList=%s",
                    section, selected_relics)
                return reject
        fight_heroes = []
        for hero in heroes:
            from .battle_equipment import battle_equipment
            from .battle_bonuses import artifact_attributes, other_attributes
            try:
                stat_hero = {**hero, "id": hero.get("battle_base_id", hero["id"])}
                if hero.get('trial_unit'):
                    from .trial_units import equipment
                    equipped, suit_effects = equipment(hero)
                    other_bonus = {}
                else:
                    equipped, suit_effects = battle_equipment(self.store, player['id'], hero)
                    other_bonus = other_attributes(self.store, player['id'], hero)
                artifact_bonus = artifact_attributes(stat_hero)
            except (ValueError, KeyError, TypeError) as exc:
                logging.getLogger('x2.battle').warning(
                    'battle entry denied player=%s hero=%s equipment=%s', player['id'], hero['id'], exc)
                return reject
            stat_hero = {**hero, "id": hero.get("battle_base_id", hero["id"])}
            attrs = HERO_ATTR.encode(hero_attributes(stat_hero))
            skills = [HERO_SKILL.encode(s) for s in hero_skills(stat_hero)]
            hero_values = {k:v for k,v in hero.items() if k in ("id", "state", "level", "star", "exp")}
            # Raw bases are keyed by the selected hero; the client applies growth.
            base_values = battle_hero_base()[str(stat_hero["id"])]
            raw_attributes = {r["attrId"]: base_values[r["name"]]
                              for r in catalog()["battle_base_1003"]["attributes"]}
            for attr_id, value in other_bonus.items():
                raw_attributes[attr_id] = raw_attributes.get(attr_id, 0) + value
            base = [HERO_ATTR_ADD.encode({"attrId": attr_id, "attrValue": value})
                    for attr_id, value in sorted(raw_attributes.items())]
            artifact = hero.get("god_equip")
            god_equip = b""
            if artifact:
                from x2server.messages.core import HERO_GOD_EQUIP, INT_PAIR, GOD_SLOT_LOCK_INFO
                god_equip = HERO_GOD_EQUIP.encode({"id": artifact.get("id", 0),
                    "level": artifact.get("level", 0), "star": artifact.get("star", 0),
                    "godEquipAttr": artifact_bonus,
                    "jewel": [INT_PAIR.encode({"Key": int(slot), "Value": int(item)})
                              for slot, item in artifact.get("jewels", {}).items()],
                    "godSlotLockInfo": [GOD_SLOT_LOCK_INFO.encode({"slot": int(slot), "state": 1})
                                        for slot in artifact.get("god_slot_lock", [])]})
            skin = self.store.db.execute("SELECT skin_id FROM appearance_wear WHERE player_id=? AND hero_id=? AND type=1", (player["id"], hero["id"])).fetchone() if self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='appearance_wear'").fetchone() else None
            logging.getLogger("x2.battle").info(
                "battle hero player=%s section=%s hero=%s battleSkinId=%s beastlords=%s suits=%s baseStats=%s artifactAttrBytes=%s otherBonuses=%s database=%s",
                player["id"], section, hero["id"], skin[0] if skin else 0,
                len(equipped), len(suit_effects), hero_attributes(stat_hero),
                len(artifact_bonus), other_bonus, self.store.path.resolve())
            fight_heroes.append(FIGHT_HERO.encode({**hero_values, "heroGodEquip": god_equip, "battleSkinId": hero.get("trial_skin", skin[0] if skin else 0),
                "heroSkill": skills, "heroAttrCount": attrs, "attrAdd": base,
                "heroEquip": equipped, "equipSuitAttr": suit_effects}))
        # Official chain (ARM64 2026-09-25): BattleInfo.SetSceneInfo copies
        # FightData.dropData.dropValues -> BattleInfo.dropValues, which JudgeDropItem
        # consumes as the per-AddADCGroup drop value budget (equipment = group 5).
        # Secondary carrier; the primary arm/update loop is 264 C2L_FightDropData ->
        # 266 L2C_FightDropData -> UpdateDropValue (see drop_data below).
        # Values: REVIVAL_COMPATIBILITY tiers (drop_budget.py) — official per-group
        # budget values are lost with the official server data.
        drop_values = self.drop_budget.budget_for(section)
        if entry_context.section_type == 5:
            drop_values = [0] * len(drop_values)
        data = FIGHT_DATA.encode({"fightHeros": fight_heroes, "missionId": section,
                                  "expertMode": request.get("expertMode", False),
                                  "dropData": DROP_DATA.encode({"dropValues": drop_values,
                                                                "missionId": section}),
                                  "CRIDmg": 15000})
        profile = FIGHT_PROFILE.encode({"missionId": section, "chapterId": chapter, "layer": 0,
            "relicList": selected_relics,
            "expertMode": request.get("expertMode", False),
            "sceneId": scene, "randomSeed": secrets.randbelow(2**30), "isProfileValid": False})
        values = {"result": 10, "uuid": str(uuid.uuid4()), "sign": secrets.token_bytes(32),
                  "data": data, "fightDataProfile": profile, "playerLevel": snapshot["level"],
                  "monsterInitLevel": self.monster_levels.get(scene, 0)}
        if self.economy and self.catalog.sections[section].get('Type') == 6:
            boss_id = self.economy.world_boss.public_bosses(player['id'])
            values['monsterInitLevel'] = self.economy.world_boss.get_boss(boss_id)['monster_level']
        if selected_relics:
            values["selectedRelicList"] = selected_relics
        logging.getLogger("x2.battle").info(
            "battle difficulty section=%s scene=%s tier=%s expert=%s monsterInitLevel=%s",
            section, scene, self.catalog.sections[section].get("DifficultyLevel", 0),
            request.get("expertMode", False), values["monsterInitLevel"])
        try:
            with self.store.db:
                if self.economy:
                    # Replacing an unfinished run abandons it, refunding its cost.
                    for old in self.store.db.execute("SELECT uuid FROM economy_runs WHERE player_id=? AND settled=0", (player["id"],)).fetchall():
                        self.economy.refund_battle(player["id"], old[0])
                        self.store.db.execute("UPDATE economy_runs SET settled=1 WHERE uuid=?", (old[0],))
                        self.economy.world_boss.finish_battle(player['id'],old[0],False)
                    self.economy.charge_battle(player["id"], values["uuid"], section, entry_context.stamina_cost)
                    ai_cost = 0
                    if request.get('useAIPoint'):
                        from .star_chart import consume_battle_ai
                        ai_cost = consume_battle_ai(self.economy, player['id'], section)
                    if entry_context.section_type != 5:
                        self.economy._event(player["id"], f"entry:{values['uuid']}", 87, section, 1)
                    self.store.db.execute("""INSERT INTO economy_runs
                        (uuid,player_id,session_id,section_id,section_type,entry_source) VALUES (?,?,?,?,?,?)""",
                        (values["uuid"], player["id"], context.session.session_id, section,
                         entry_context.section_type, entry_context.entry_source))
                self.store.db.execute("""INSERT INTO battle_entries
                    (player_id,request_key,uuid,created_at,response,section_type,entry_source,map_id,team_json)
                    VALUES (?,?,?,?,?,?,?,?,?)""", (player["id"], key, values["uuid"], int(time.time()),
                    BATTLE_SCHEMAS["L2C_FightData"].encode(values), entry_context.section_type,
                    entry_context.entry_source, entry_context.map_id, json.dumps(entry_context.hero_ids)))
                self.store.db.execute('INSERT INTO battle_drop_budget_versions VALUES (?,?)',
                    (values['uuid'], self.drop_budget.version))
                if self.economy:
                    self.store.db.execute('UPDATE battle_entries SET ai_cost=? WHERE uuid=?',
                                          (ai_cost, values['uuid']))
                    if entry_context.section_type == 6:
                        self.economy.world_boss.bind_battle(player['id'], section,
                            entry_context.hero_ids, values['uuid'])
        except UnresolvedEconomy as exc:
            logging.getLogger("x2.battle").info(
                "checkout rejected section=%s reason=settle: %s", section, exc)
            return reject
        return OutboundMessage("L2C_FightData", values, pushes=self.economy.pushes(player["id"]) if self.economy else ())
