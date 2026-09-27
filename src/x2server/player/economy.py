"""Confirmed rewards and tasks with the user-defined Revival calendar."""
from collections import Counter
from contextlib import contextmanager
from importlib.resources import files
import json
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone

from x2server.messages.economy import ECONOMY_SCHEMAS, ITEM, REWARD, REWARD_ITEM, TASK, FINISH_REQUEST, FINISH_RESULT
from x2server.messages.lobby import LOBBY_SCHEMAS, MISSION_PAIR, MISSION_TYPE
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY
from .task_calendar import task_period
from .battle_entry import BattleEntryCatalog
from .equipment_factory import EquipmentInstanceFactory, materialize_instances
from .reward_system import (ReportCurrencyResolver, RewardGrant, RuntimeDropResolver,
                            SectionRewardCatalog, audit_grants, sum_grants)
from x2server.messages.equipment import EQUIP_PARAM, HERO_EQUIP


class UnresolvedEconomy(ValueError):
    """The entire operation must be withheld, never partially granted."""


class EconomyService:
    POWER_RECOVER_SECONDS = 225  # Client ServerData default 300s; user policy: 25% faster.
    # Item.EffData -> BaseInfoProto; only supported currency destinations.
    CURRENCIES = {1237901: "gold", 1237902: "crystal", 1237906: "equip_exp", 1237907: "hero_exp",
                  1237908: "exp", 1237910: "daily_activity", 1237911: "week_activity"}
    STACKABLE_REWARD_TYPES = frozenset((5, 12, 13, 14, 17, 22, 23, 24, 25, 33, 34, 40, 41))

    def __init__(self, store, clock=time.time):
        self.store = store
        self.clock = clock
        self.catalog = json.loads(files("x2server").joinpath("data/economy_catalog.json").read_text(encoding="utf-8"))
        battle_rewards = json.loads(files("x2server").joinpath("data/battle_rewards_catalog.json").read_text(encoding="utf-8"))
        recovered_groups = {row["GiftGroup"] for row in battle_rewards["gifts"]}
        self.catalog["gifts"] = battle_rewards["gifts"] + [row for row in self.catalog["gifts"]
            if row["GiftGroup"] not in recovered_groups]
        recovered_items = {row["ItemID"] for row in battle_rewards["items"]}
        self.catalog["items"] = battle_rewards["items"] + [row for row in self.catalog["items"]
            if row["ItemID"] not in recovered_items]
        reward_items = json.loads(files("x2server").joinpath("data/reward_items.json").read_text(encoding="utf-8"))
        existing_items = {row["ItemID"] for row in self.catalog["items"]}
        self.catalog["items"].extend(row for row in reward_items if row["ItemID"] not in existing_items)
        self.sections = {r["SectionID"]: r for r in self.catalog["sections"]}
        self.daily_sections = {r["SectionID"]: r for r in self.catalog.get("daily_sections", [])}
        self.reward_sections = {**self.sections, **self.daily_sections}
        self.entry_catalog = BattleEntryCatalog()
        self.reward_sections.update(self.entry_catalog.sections)
        self.section_rewards = SectionRewardCatalog()
        self.tasks = {r["DailyTaskID"]: r for r in self.catalog["tasks"] if r.get("IsUse", {}).get("value") == 1}
        self.items = {r["ItemID"]: r for r in self.catalog["items"]}
        player_levels = json.loads(files("x2server").joinpath("data/progression_catalog.json").read_text(encoding="utf-8"))["player_level"]
        self.power_caps = {row["level"]: row["power_cap"] for row in player_levels}
        self.equipment_factory = EquipmentInstanceFactory()
        report_map = json.loads(files("x2server").joinpath("data/report_currency_map.json").read_text(encoding="utf-8"))
        self.report_currency = ReportCurrencyResolver(report_map)
        self.runtime_drops = RuntimeDropResolver(self.items, self.equipment_factory.is_drop_equipment,
                                                 self.report_currency)
        self.shops = {r["ShopID"]: r for r in self.catalog["shops"]}
        with store.db:
            store.db.execute("""CREATE TABLE IF NOT EXISTS economy_grants (
                player_id INTEGER NOT NULL, source TEXT NOT NULL, rewards TEXT NOT NULL,
                created_at INTEGER NOT NULL, PRIMARY KEY(player_id, source))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS inventory (
                player_id INTEGER NOT NULL, item_id INTEGER NOT NULL, quantity INTEGER NOT NULL CHECK(quantity>=0),
                PRIMARY KEY(player_id,item_id))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS economy_tasks (
                player_id INTEGER NOT NULL, task_id INTEGER NOT NULL, progress INTEGER NOT NULL DEFAULT 0,
                claimed INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(player_id,task_id))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS economy_events (
                player_id INTEGER NOT NULL, event_key TEXT NOT NULL, PRIMARY KEY(player_id,event_key))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS battle_unresolved_rewards (
                uuid TEXT NOT NULL, player_id INTEGER NOT NULL, section_id INTEGER NOT NULL,
                reward_group INTEGER NOT NULL, reason TEXT NOT NULL,
                PRIMARY KEY(uuid,reward_group))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS economy_clears (
                player_id INTEGER NOT NULL, section_id INTEGER NOT NULL, first_uuid TEXT NOT NULL,
                PRIMARY KEY(player_id,section_id))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS economy_runs (
                uuid TEXT PRIMARY KEY, player_id INTEGER NOT NULL, session_id TEXT NOT NULL,
                section_id INTEGER NOT NULL, settled INTEGER NOT NULL DEFAULT 0)""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS economy_checkouts (
                player_id INTEGER NOT NULL, digest TEXT NOT NULL, uuid TEXT NOT NULL UNIQUE,
                PRIMARY KEY(player_id,digest))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS task_periods (
                player_id INTEGER NOT NULL, kind INTEGER NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL,
                PRIMARY KEY(player_id,kind))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS task_history (
                player_id INTEGER NOT NULL, kind INTEGER NOT NULL, start INTEGER NOT NULL,
                task_id INTEGER NOT NULL, progress INTEGER NOT NULL, claimed INTEGER NOT NULL,
                PRIMARY KEY(player_id,kind,start,task_id))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS battle_costs (
                uuid TEXT PRIMARY KEY, player_id INTEGER NOT NULL, amount INTEGER NOT NULL,
                refunded INTEGER NOT NULL DEFAULT 0)""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS pending_rewards (
                player_id INTEGER NOT NULL, source TEXT NOT NULL, item_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL, reason TEXT NOT NULL,
                PRIMARY KEY(player_id,source,item_id))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS reward_settlement_audit (
                run_id TEXT PRIMARY KEY, player_id INTEGER NOT NULL, section_id INTEGER NOT NULL,
                sources TEXT NOT NULL, blocked TEXT NOT NULL, created_at INTEGER NOT NULL)""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS pending_reward_instances (
                run_id TEXT NOT NULL, ordinal INTEGER NOT NULL, player_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL, quantity INTEGER NOT NULL, quality INTEGER NOT NULL,
                e_num INTEGER NOT NULL, reason TEXT NOT NULL,
                PRIMARY KEY(run_id,ordinal))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS sweep_receipts (
                request_key TEXT PRIMARY KEY, player_id INTEGER NOT NULL,
                section_id INTEGER NOT NULL, response BLOB NOT NULL)""")
            # Phase19 recorded clears but did not advance BaseInfo. Adopt only
            # existing consecutive clears, without replaying rewards or charges.
            for player in store.db.execute("SELECT id FROM players").fetchall():
                snapshot = store.get(player[0])["snapshot"]
                current = snapshot.get("main_section")
                cleared = {r[0] for r in store.db.execute("SELECT section_id FROM economy_clears WHERE player_id=?", (player[0],))}
                seen = set()
                while current in self.sections and current not in seen:
                    seen.add(current)
                    following = self.sections[current].get("NextSectionID")
                    if following not in cleared or following not in self.sections:
                        break
                    current = following
                if current is not None and current != snapshot.get("main_section"):
                    snapshot.update(main_section=current, main_chapter=self.sections[current]["ChapterID"])
                    self.save_snapshot(player[0], snapshot)

    @contextmanager
    def transaction(self):
        # Nested reward/task operations must never commit the battle receipt early.
        import uuid
        savepoint = "economy_" + uuid.uuid4().hex
        self.store.db.execute("SAVEPOINT " + savepoint)
        try:
            yield
        except BaseException:
            self.store.db.execute("ROLLBACK TO " + savepoint)
            self.store.db.execute("RELEASE " + savepoint)
            raise
        else:
            self.store.db.execute("RELEASE " + savepoint)

    def ensure_periods(self, player_id):
        """Lazy rollover at login or the first online operation after a boundary."""
        with self.transaction():
            snapshot = self.store.get(player_id)["snapshot"]
            changed = False
            for kind, field in ((1, "daily_activity"), (2, "week_activity")):
                start, end = task_period(kind, int(self.clock()))
                previous = self.store.db.execute("SELECT start,end FROM task_periods WHERE player_id=? AND kind=?", (player_id, kind)).fetchone()
                if previous and previous[0] >= start:
                    continue  # Clock rollback must not mint a second period.
                ids = [i for i, t in self.tasks.items() if t["RefreshCycle"]["value"] == kind]
                if previous:
                    for task_id in ids:
                        self.store.db.execute("""INSERT OR IGNORE INTO task_history
                            SELECT player_id,?,?,task_id,progress,claimed FROM economy_tasks WHERE player_id=? AND task_id=?""",
                            (kind, previous[0], player_id, task_id))
                        self.store.db.execute("DELETE FROM economy_tasks WHERE player_id=? AND task_id=?", (player_id, task_id))
                    snapshot[field] = 0
                    changed = True
                # First migration adopts the existing initial claims and active
                # values, rather than paying the already claimed login task again.
                for task_id in ids:
                    if self.tasks[task_id]["AcceptLevel"] <= snapshot["level"]:
                        self.store.db.execute("INSERT OR IGNORE INTO economy_tasks(player_id,task_id) VALUES (?,?)", (player_id, task_id))
                self.store.db.execute("INSERT OR REPLACE INTO task_periods VALUES (?,?,?,?)", (player_id, kind, start, end))
            if changed:
                self.store.db.execute("UPDATE players SET snapshot=?,revision=revision+1 WHERE id=?", (json.dumps(snapshot, ensure_ascii=False, sort_keys=True), player_id))

    def login_event(self, player_id):
        self.refresh_stamina(player_id)
        self.ensure_periods(player_id)
        self.record_event(player_id, "login", 5)
        self.refresh_online_tasks(player_id)

    def refresh_online_tasks(self, player_id):
        """Credit a daily online task once when the player contacts the server in its window."""
        self.ensure_periods(player_id)
        hour = datetime.fromtimestamp(int(self.clock()), timezone(timedelta(hours=8))).hour
        for task_id, task in self.tasks.items():
            condition = self.catalog["task_conditions"][str(task_id)]
            if condition["CompleteType"]["value"] != 6 or task["RefreshCycle"]["value"] != 1:
                continue
            start, end = condition["CompleteValue1"][0], condition["CompleteValue2"][0]
            if start <= hour < end:
                self.record_event(player_id, f"online:{task_id}", 6, start)

    def gifts(self, groups, deferred=None, allow_daily_random=False):
        rewards = Counter()
        for group in groups:
            rows = [r for r in self.catalog["gifts"] if r["GiftGroup"] == group]
            if not rows:
                raise UnresolvedEconomy(f"missing Gift {group}")
            for row in rows:
                ids, nums = row.get("GiftValue", []), row.get("Num", [])
                kind = row.get("AwardType", {}).get("value")
                probability = row.get("Probability", [])
                if (kind not in (1, 2) or kind == 2 and not allow_daily_random
                        or kind == 1 and probability or len(ids) != len(nums) or not ids
                        or kind == 2 and (len(probability) != len(ids)
                                          or sum(probability) != 100 or any(type(p) is not int or p < 0 for p in probability))):
                    raise UnresolvedEconomy(f"non-fixed Gift {group}")
                if kind == 2:
                    draw = secrets.randbelow(100)
                    index = 0
                    for index, weight in enumerate(probability):
                        draw -= weight
                        if draw < 0:
                            break
                    ids, nums = [ids[index]], [nums[index]]
                for item, count in zip(ids, nums):
                    if item not in self.items or type(count) is not int or count < 0 or kind == 1 and count == 0:
                        raise UnresolvedEconomy(f"invalid Gift {group}")
                    if count == 0:
                        continue
                    item_kind = self.items[item].get("ItemType", {}).get("value")
                    account_currency = (item_kind == 16 and
                        self.items[item].get("ItemUseScence", {}).get("value") == 1)
                    if (item_kind not in self.STACKABLE_REWARD_TYPES
                            and item not in self.CURRENCIES and item != 1237900
                            and not account_currency):
                        if deferred is not None:
                            deferred[item] += count
                            continue
                        raise UnresolvedEconomy(f"unrecovered reward destination {item}")
                    rewards[item] += count
        return dict(rewards)

    def validate_daily_fixed_rewards(self, section):
        """Reject unresolved Daily destinations before consuming entry stamina."""
        config = self.daily_sections.get(section)
        if config is None:
            raise UnresolvedEconomy("missing Daily reward section")
        groups = list(config.get("VReward", [])) + list(config.get("FirVReward", []))
        for group in groups:
            rows = [r for r in self.catalog["gifts"] if r["GiftGroup"] == group]
            if not rows:
                raise UnresolvedEconomy(f"missing Gift {group}")
            for row in rows:
                ids, nums = row.get("GiftValue", []), row.get("Num", [])
                kind = row.get("AwardType", {}).get("value")
                probability = row.get("Probability", [])
                if (kind not in (1, 2) or not ids or len(ids) != len(nums)
                        or kind == 1 and probability
                        or kind == 2 and (len(probability) != len(ids) or sum(probability) != 100)):
                    raise UnresolvedEconomy(f"unresolved Gift {group}")
                for item, count in zip(ids, nums):
                    if (item not in self.items or type(count) is not int or count < 0
                            or kind == 1 and count == 0):
                        raise UnresolvedEconomy(f"invalid Gift {group}")
                    destination = self.items[item].get("ItemType", {}).get("value")
                    if destination == 10 or destination == 16 and item not in self.CURRENCIES and item != 1237900:
                        raise UnresolvedEconomy(f"unresolved Daily reward destination {item}")
        # A Daily battle must not be denied merely because its runtime drop
        # amount cannot be inferred from the UI preview.

    @staticmethod
    def reward_bytes(rewards, reward_equips=()):
        return REWARD.encode({"rewardItem": [REWARD_ITEM.encode({"itemId": i, "itemNum": n, "transform": False})
            for i, n in sorted(rewards.items())],
            "rewardEquip": reward_equips})

    def _grant(self, player_id, source, rewards):
        """Called inside the owner's transaction; never commits independently."""
        existing = self.store.db.execute("SELECT rewards FROM economy_grants WHERE player_id=? AND source=?",
                                         (player_id, source)).fetchone()
        if existing:
            return {int(i): n for i, n in json.loads(existing[0]).items()}
        player = self.store.get(player_id)
        snapshot = player["snapshot"]
        for item, count in rewards.items():
            if type(count) is not int or count <= 0 or item not in self.items:
                raise UnresolvedEconomy("invalid reward")
            kind = self.items[item].get("ItemType", {}).get("value")
            if item in self.CURRENCIES:
                field = self.CURRENCIES[item]
                snapshot[field] = snapshot.get(field, 0) + count
                if snapshot[field] > 2**31 - 1:
                    raise UnresolvedEconomy("currency overflow")
            elif item == 1237900:
                if "mobility" not in snapshot:
                    raise UnresolvedEconomy("missing mobility state")
                snapshot["mobility"]["power"] += count
                if snapshot["mobility"]["power"] > 2**31 - 1:
                    raise UnresolvedEconomy("power overflow")
            elif (kind == 16 and
                  self.items[item].get("ItemUseScence", {}).get("value") == 1):
                self.store.db.execute("""INSERT INTO inventory VALUES (?,?,?)
                    ON CONFLICT(player_id,item_id) DO UPDATE SET quantity=quantity+excluded.quantity""", (player_id, item, count))
                quantity = self.store.db.execute("SELECT quantity FROM inventory WHERE player_id=? AND item_id=?",
                    (player_id, item)).fetchone()[0]
                if quantity > 2**31 - 1:
                    raise UnresolvedEconomy("currency overflow")
            elif kind not in self.STACKABLE_REWARD_TYPES:
                raise UnresolvedEconomy("unrecovered reward destination")
            else:
                self.store.db.execute("""INSERT INTO inventory VALUES (?,?,?)
                    ON CONFLICT(player_id,item_id) DO UPDATE SET quantity=quantity+excluded.quantity""", (player_id, item, count))
                quantity = self.store.db.execute("SELECT quantity FROM inventory WHERE player_id=? AND item_id=?", (player_id, item)).fetchone()[0]
                if quantity > 2**31 - 1:
                    raise UnresolvedEconomy("item overflow")
        if 1237908 in rewards:
            from .progression import advance_player, catalog
            before_level = snapshot["level"]
            advance_player(snapshot)
            for row in catalog()["player_level"]:
                if before_level < row["level"] <= snapshot["level"]:
                    for material in row["reward"]:
                        self.store.db.execute("INSERT OR IGNORE INTO pending_rewards VALUES (?,?,?,?,?)",
                            (player_id, f"level:{row['level']}", material["material_item_id"], material["material_num"], "level gift delivery timing unconfirmed"))
        self.store.db.execute("UPDATE players SET snapshot=?, revision=revision+1 WHERE id=?",
            (json.dumps(snapshot, ensure_ascii=False, sort_keys=True), player_id))
        self.store.db.execute("INSERT INTO economy_grants VALUES (?,?,?,?)",
            (player_id, source, json.dumps(rewards, sort_keys=True), int(time.time())))
        return rewards

    def inventory_values(self, player_id):
        return {"items": [ITEM.encode({"id": r[0], "num": r[1], "locked": False, "dayGet": 0})
            for r in self.store.db.execute("SELECT item_id,quantity FROM inventory WHERE player_id=? ORDER BY item_id", (player_id,))]}

    def task_values(self, player_id, kind):
        self.refresh_online_tasks(player_id)
        self.ensure_periods(player_id)
        level = self.store.get(player_id)["snapshot"]["level"]
        result = []
        for task_id, task in self.tasks.items():
            if task["RefreshCycle"]["value"] != kind or task["AcceptLevel"] > level:
                continue
            row = self.store.db.execute("SELECT progress,claimed FROM economy_tasks WHERE player_id=? AND task_id=?",
                                        (player_id, task_id)).fetchone()
            if not row:
                continue  # Eligibility is captured when this period is created.
            progress, claimed = tuple(row)
            period_end = self.store.db.execute("SELECT end FROM task_periods WHERE player_id=? AND kind=?", (player_id, kind)).fetchone()[0]
            target = self.catalog["task_conditions"][str(task_id)]["CompleteNum"]
            result.append(TASK.encode({"taskId": task_id, "taskStatus": 4 if claimed else 3 if progress >= target else 2,
                "taskProgress": min(progress, target), "taskRefreshTime": period_end, "finishTimes": int(bool(claimed)), "stage": 0}))
        return {"code": 10, "type": kind, "taskList": result}

    def record_event(self, player_id, key, condition_type, value=0, amount=1, value2=0):
        """Internal authoritative events only. No client-supplied progress endpoint."""
        if amount <= 0:
            raise ValueError("positive event amount required")
        self.ensure_periods(player_id)
        with self.transaction():
            self._event(player_id, key, condition_type, value, amount, value2)

    def _event(self, player_id, key, condition_type, value, amount, value2=0):
        self.ensure_periods(player_id)
        active_kinds = set()
        for row in self.store.db.execute("SELECT kind,start FROM task_periods WHERE player_id=?", (player_id,)).fetchall():
            inserted = self.store.db.execute("INSERT OR IGNORE INTO economy_events VALUES (?,?)", (player_id, f"{row[0]}:{row[1]}:{key}"))
            if inserted.rowcount:
                active_kinds.add(row[0])
        level = self.store.get(player_id)["snapshot"]["level"]
        for task_id, task in self.tasks.items():
            condition = self.catalog["task_conditions"][str(task_id)]
            if (task["RefreshCycle"]["value"] not in active_kinds or task["AcceptLevel"] > level or condition["CompleteType"]["value"] != condition_type
                    or condition.get("CompleteValue1", [0]) not in ([0], []) and value not in condition["CompleteValue1"]
                    or condition_type != 6 and condition.get("CompleteValue2", [0]) not in ([0], [])
                    and value2 not in condition["CompleteValue2"]):
                continue
            self.store.db.execute("UPDATE economy_tasks SET progress=MIN(?,progress+?) WHERE player_id=? AND task_id=?",
                (condition["CompleteNum"], amount, player_id, task_id))

    def claim(self, player_id, task_id, kind):
        self.ensure_periods(player_id)
        self.refresh_online_tasks(player_id)
        task = self.tasks.get(task_id)
        result = {"code": 13, "taskId": task_id, "type": kind, "rewardData": b""}
        if not task or task["RefreshCycle"]["value"] != kind or task["AcceptLevel"] > self.store.get(player_id)["snapshot"]["level"]:
            return result
        try:
            rewards = self.gifts([task["GiftGroup"]])
            with self.transaction():
                row = self.store.db.execute("SELECT progress,claimed FROM economy_tasks WHERE player_id=? AND task_id=?", (player_id, task_id)).fetchone()
                if not row or row[0] < self.catalog["task_conditions"][str(task_id)]["CompleteNum"]:
                    return result
                start = self.store.db.execute("SELECT start FROM task_periods WHERE player_id=? AND kind=?", (player_id, kind)).fetchone()[0]
                # Adopt a pre-calendar claim without paying it a second time.
                legacy = self.store.db.execute("SELECT rewards FROM economy_grants WHERE player_id=? AND source=?", (player_id, f"task:initial:{task_id}")).fetchone()
                if row[1] and legacy and not self.store.db.execute("SELECT 1 FROM task_history WHERE player_id=? AND task_id=?", (player_id, task_id)).fetchone():
                    rewards = {int(i): n for i, n in json.loads(legacy[0]).items()}
                else:
                    rewards = self._grant(player_id, f"task:{kind}:{start}:{task_id}", rewards)
                self.store.db.execute("UPDATE economy_tasks SET claimed=1 WHERE player_id=? AND task_id=?", (player_id, task_id))
                result.update(code=10, rewardData=self.reward_bytes(rewards))
            return result
        except UnresolvedEconomy:
            return result

    def settle(self, player_id, run_uuid, section, success, section_type=0, outside_items=()):
        """Part of BattleService's receipt transaction, including first-clear key."""
        profile = self.section_rewards.get(section)
        config = self.reward_sections.get(section)
        run = self.store.db.execute("SELECT * FROM economy_runs WHERE uuid=?", (run_uuid,)).fetchone()
        if (profile is None or config is None or profile["section_type"] != section_type
                or run is None or run["player_id"] != player_id or run["section_id"] != section
                or run["settled"]):
            raise UnresolvedEconomy("unclassified, mismatched or settled run")
        grants, pending_instances, blocked, equipment_specs = self.runtime_drops.resolve(
            run=run, profile=profile, outside_items=outside_items, success=success)
        reward_equips: list = []
        sources = {name: [] for name in ("FIRST_CLEAR_FIXED", "NORMAL_CLEAR_FIXED",
            "RUNTIME_BATTLE_DROP", "REPORT_CURRENCY", "SWEEP_REWARD", "EXTRA_DROP",
            "COMPAT_REWARD", "EQUIP_INSTANCE")}
        if success:
            pending = Counter()
            first = not self.store.db.execute(
                "SELECT 1 FROM economy_clears WHERE player_id=? AND section_id=?", (player_id, section)).fetchone()
            for source, groups in (("NORMAL_CLEAR_FIXED", profile["normal_reward"]),
                                   ("FIRST_CLEAR_FIXED", profile["first_reward"] if first else [])):
                for group in groups:
                    local_pending = Counter()
                    try:
                        resolved = self.gifts([group], deferred=local_pending,
                                              allow_daily_random=section_type != 0)
                    except UnresolvedEconomy as exc:
                        self.store.db.execute("INSERT OR IGNORE INTO battle_unresolved_rewards VALUES (?,?,?,?,?)",
                            (run_uuid, player_id, section, group, str(exc)))
                        blocked.append({"gift_group": group, "reason": str(exc)})
                        continue
                    grants.extend(RewardGrant(source, section, run_uuid, item, count,
                        reason=f"SectionTable GiftGroup {group}") for item, count in resolved.items())
                    pending.update(local_pending)
            if profile["drop_value_id"]:
                self.store.db.execute("INSERT OR IGNORE INTO battle_unresolved_rewards VALUES (?,?,?,?,?)",
                    (run_uuid, player_id, section, -2, "server DropValueID mapping unverified; client outsideItems used"))
            for grant in grants:
                key = "COMPAT_REWARD" if grant.source == "COMPAT_GOLD_DUNGEON" else grant.source
                sources[key].append(grant.__dict__)
            rewards = self._grant(player_id, f"battle:{run_uuid}", sum_grants(grants))
            if pending:
                for item, count in pending.items():
                    self.store.db.execute("INSERT OR IGNORE INTO pending_rewards VALUES (?,?,?,?,?)",
                        (player_id, f"battle:{run_uuid}", item, count, "unrecovered item instance or currency destination"))
                    blocked.append({"item_id": item, "quantity": count,
                                    "reason": "UNRESOLVED_INSTANCE_DELIVERY"})
            for ordinal, grant in enumerate(pending_instances):
                self.store.db.execute("INSERT INTO pending_reward_instances VALUES (?,?,?,?,?,?,?,?)",
                    (run_uuid, ordinal, player_id, grant.item_id, grant.quantity, grant.quality,
                     grant.e_num, "UNRESOLVED_INSTANCE_DELIVERY"))
            reward_equips, equip_ordinal = [], 0
            for spec in equipment_specs:
                instances = materialize_instances(
                    self.store.db, player_id, spec["item_id"], spec["quality"], spec["quantity"],
                    run_uuid, self.equipment_factory, equip_ordinal)
                equip_ordinal += spec["quantity"]
                for instance in instances:
                    wire = {k: v for k, v in instance.items() if k != "marker"}
                    reward_equips.append(HERO_EQUIP.encode(
                        {**wire, "param": EQUIP_PARAM.encode(instance["param"])}))
                    sources["EQUIP_INSTANCE"].append(
                        {"instance_id": instance["id"], "type_id": instance["typeId"],
                         "star": instance["star"], "marker": instance["marker"]})
            self.mark_section_cleared(player_id, section, run_uuid, section_type)
            self._event(player_id, f"clear:{run_uuid}", 3, section, 1)
            spent = self.store.db.execute("SELECT amount FROM battle_costs WHERE uuid=? AND player_id=?",
                (run_uuid, player_id)).fetchone()
            if spent and spent[0]:
                self._event(player_id, f"power:{run_uuid}", 10, 900, spent[0])
        else:
            rewards = {}
            reward_equips = []
            self.refund_battle(player_id, run_uuid)
        self.store.db.execute("INSERT INTO reward_settlement_audit VALUES (?,?,?,?,?,?)",
            (run_uuid, player_id, section, json.dumps(sources, ensure_ascii=False, sort_keys=True),
             json.dumps(blocked, ensure_ascii=False, sort_keys=True), int(time.time())))
        self.store.db.execute("UPDATE economy_runs SET settled=1 WHERE uuid=?", (run_uuid,))
        logging.getLogger("x2.rewards").info("RewardSettlement run=%s section=%s sources=%s blocked=%s final_grants=%s",
            run_uuid, section, {k: len(v) for k, v in sources.items()}, blocked, rewards)
        return self.reward_bytes(rewards, reward_equips), reward_equips

    def settle_sweep(self, player_id, section, count, request_key):
        """Only MopReward; the stage must already be cleared and cost is per sweep."""
        self.refresh_stamina(player_id)
        if type(count) is not int or not 1 <= count <= 10:
            raise UnresolvedEconomy("invalid sweep count")
        profile = self.section_rewards.get(section)
        config = self.reward_sections.get(section)
        if not profile or not config or not profile["sweep_reward"]:
            raise UnresolvedEconomy("section has no confirmed MopReward")
        if not self.store.db.execute("SELECT 1 FROM economy_clears WHERE player_id=? AND section_id=?",
                                     (player_id, section)).fetchone():
            raise UnresolvedEconomy("section not cleared for sweep")
        cost = config.get("ManualValue")
        if type(cost) is not int or cost < 0:
            raise UnresolvedEconomy("sweep cost unknown")
        snapshot = self.store.get(player_id)["snapshot"]
        if snapshot.get("mobility", {}).get("power", 0) < cost * count:
            raise UnresolvedEconomy("insufficient sweep stamina")
        pending = Counter()
        grants = []
        for _ in range(count):
            for group in profile["sweep_reward"]:
                resolved = self.gifts([group], deferred=pending,
                                      allow_daily_random=profile["section_type"] != 0)
                grants.extend(RewardGrant("SWEEP_REWARD", section, request_key, item, amount,
                    reason=f"SectionTable MopReward GiftGroup {group}") for item, amount in resolved.items())
        snapshot["mobility"]["power"] -= cost * count
        self.save_snapshot(player_id, snapshot)
        rewards = self._grant(player_id, f"sweep:{request_key}", sum_grants(grants))
        for item, amount in pending.items():
            self.store.db.execute("INSERT OR IGNORE INTO pending_rewards VALUES (?,?,?,?,?)",
                (player_id, f"sweep:{request_key}", item, amount, "UNRESOLVED_INSTANCE_DELIVERY"))
        self._event(player_id, f"sweep:{request_key}", 3, section, count)
        if cost:
            self._event(player_id, f"sweep-power:{request_key}", 10, 900, cost * count)
        self.store.db.execute("INSERT INTO reward_settlement_audit VALUES (?,?,?,?,?,?)",
            (request_key, player_id, section, json.dumps({"SWEEP_REWARD": audit_grants(grants)},
             ensure_ascii=False), json.dumps({"pending": dict(pending)}), int(time.time())))
        return self.reward_bytes(rewards)

    def mark_section_cleared(self, player_id, section, run_uuid, section_type):
        """Shared clear record with a type-specific frontier policy."""
        self.store.db.execute("INSERT OR IGNORE INTO economy_clears VALUES (?,?,?)", (player_id, section, run_uuid))
        if section_type == 0:
            snapshot = self.store.get(player_id)["snapshot"]
            route = list(self.sections)
            current = snapshot.get("main_section")
            if section in route and (current not in route or route.index(section) > route.index(current)):
                snapshot.update(main_section=section, main_chapter=self.sections[section]["ChapterID"])
                self.save_snapshot(player_id, snapshot)

    def mission_values(self, player_id):
        clears = {row[0] for row in self.store.db.execute(
            "SELECT section_id FROM economy_clears WHERE player_id=?", (player_id,))}
        daily_frontiers = []
        for dungeon_id, dungeon in sorted(self.entry_catalog.daily_dungeons.items()):
            frontier = None
            for section in dungeon["SectionID"]:
                if section not in clears or section not in self.daily_sections:
                    break
                frontier = section
            if frontier is not None:
                daily_frontiers.append(MISSION_PAIR.encode({"Key": dungeon_id, "Value": frontier}))
        other = []
        if daily_frontiers:
            other.append(MISSION_TYPE.encode({"type": 3, "missionData": daily_frontiers}))
        chapter_frontiers = {}
        for section in clears:
            row = self.entry_catalog.sections.get(section)
            if not row or row["Type"] in (0, 3):
                continue
            key = (row["Type"], row["ChapterID"])
            chapter_frontiers[key] = max(section, chapter_frontiers.get(key, 0))
        by_type = {}
        for (section_type, chapter), frontier in sorted(chapter_frontiers.items()):
            by_type.setdefault(section_type, []).append(MISSION_PAIR.encode({"Key": chapter, "Value": frontier}))
        other.extend(MISSION_TYPE.encode({"type": section_type, "missionData": pairs})
                     for section_type, pairs in sorted(by_type.items()))
        return {"mainMission": sorted(clears & self.sections.keys()), "OtherChapter": other}

    def save_snapshot(self, player_id, snapshot):
        self.store.db.execute("UPDATE players SET snapshot=?,revision=revision+1 WHERE id=?",
            (json.dumps(snapshot, ensure_ascii=False, sort_keys=True), player_id))

    def refresh_stamina(self, player_id):
        """Settle earned points once, retaining the partial interval in the save."""
        now = int(self.clock())
        with self.transaction():
            snapshot = self.store.get(player_id)["snapshot"]
            mobility = snapshot.get("mobility")
            if mobility is None:
                return
            cap = self.power_caps.get(snapshot["level"])
            if cap is None:
                return
            anchor = mobility.get("recover_anchor")
            if mobility["power"] >= cap or type(anchor) is not int or anchor <= 0 or anchor > now:
                if anchor != now:
                    mobility["recover_anchor"] = now
                    self.save_snapshot(player_id, snapshot)
                return
            earned = (now - anchor) // self.POWER_RECOVER_SECONDS
            if earned:
                mobility["power"] = min(cap, mobility["power"] + earned)
                mobility["recover_anchor"] = (now if mobility["power"] == cap
                    else anchor + earned * self.POWER_RECOVER_SECONDS)
                self.save_snapshot(player_id, snapshot)

    def charge_battle(self, player_id, run_uuid, section, amount=None):
        # BattleEntryContext supplies an explicit policy cost for non-main modes.
        # MainMission keeps the confirmed SectionTable ManualValue behavior.
        amount = self.sections[section]["ManualValue"] if amount is None else amount
        if type(amount) is not int or amount < 0:
            raise UnresolvedEconomy("invalid battle cost")
        self.refresh_stamina(player_id)
        snapshot = self.store.get(player_id)["snapshot"]
        if snapshot.get("mobility", {}).get("power", 0) < amount:
            raise UnresolvedEconomy("insufficient stamina")
        if amount:
            snapshot["mobility"]["power"] -= amount
            self.save_snapshot(player_id, snapshot)
        self.store.db.execute("INSERT INTO battle_costs(uuid,player_id,amount) VALUES (?,?,?)", (run_uuid, player_id, amount))

    def refund_battle(self, player_id, run_uuid):
        cost = self.store.db.execute("SELECT amount,refunded FROM battle_costs WHERE uuid=? AND player_id=?", (run_uuid, player_id)).fetchone()
        if cost and not cost[1]:
            self.refresh_stamina(player_id)
            snapshot = self.store.get(player_id)["snapshot"]
            snapshot["mobility"]["power"] += cost[0]
            self.save_snapshot(player_id, snapshot)
            self.store.db.execute("UPDATE battle_costs SET refunded=1 WHERE uuid=?", (run_uuid,))

    def pushes(self, player_id):
        from .login import LoginService
        self.refresh_stamina(player_id)
        self.ensure_periods(player_id)
        return (LoginService.snapshot_push(self.store.get(player_id), self.store),
            OutboundMessage("L2C_ItemUpdate", {"code": 10, **self.inventory_values(player_id)}),
            *(OutboundMessage("L2C_TaskUpdate", {"type": k, "taskList": self.task_values(player_id, k)["taskList"]}) for k in (1, 2)))

    def handlers(self):
        return {name: self.handle for name in ("C2L_ItemAll", "C2L_ShopGoods", "C2L_RefreshShop", "C2L_BuyGoods",
            "C2L_QueryGoodsInfo", "C2L_GameTask", "C2L_DailyAndWeekTask", "C2L_FinishGameTask",
            "C2L_FinishGameTaskAsync", "C2L_PickTreasureBox", "C2L_QueryMission")}

    async def handle(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("economy requested before login")
        self.ensure_periods(player_id)
        name = CORE_MESSAGE_REGISTRY.name_for(packet.message_id)
        logging.getLogger("x2.economy").info("economy request %s player=%s", name, player_id)
        request = (ECONOMY_SCHEMAS if name in ECONOMY_SCHEMAS else LOBBY_SCHEMAS)[name].decode(packet.body)
        response_name = name.replace("C2L_", "L2C_", 1)
        if name == "C2L_ItemAll":
            return OutboundMessage(response_name, self.inventory_values(player_id))
        if name == "C2L_QueryMission":
            return OutboundMessage(response_name, self.mission_values(player_id))
        if name in ("C2L_GameTask", "C2L_DailyAndWeekTask"):
            kind = request.get("type", 0)
            return OutboundMessage("L2C_GameTask", self.task_values(player_id, kind) if kind in (1, 2)
                else {"code": 10, "type": kind, "chapterId": request.get("chapterId", 0)})
        if name in ("C2L_FinishGameTask", "C2L_FinishGameTaskAsync"):
            requests = [FINISH_REQUEST.decode(b) for b in request.get("data", [])] if name == "C2L_FinishGameTask" else [request]
            if len(requests) > 40:
                raise ProtocolError("too many task claims")
            results = [FINISH_RESULT.encode(self.claim(player_id, r.get("taskId", 0), r.get("type", 0))
                if not r.get("activityId") else {"code": 13, "taskId": r.get("taskId", 0), "type": r.get("type", 0)}) for r in requests]
            return OutboundMessage(response_name, {"data": results if name == "C2L_FinishGameTask" else results[0]}, pushes=self.pushes(player_id))
        if name == "C2L_ShopGoods":
            shop = request.get("shopId", 0)
            # Client 2.4 dereferences a null goods list on success. With no fully
            # confirmed goods, reject the query before that success-only path.
            return OutboundMessage(response_name, {"code": 13, "shopId": shop})
        if name == "C2L_PickTreasureBox":
            return OutboundMessage(response_name, {"code": 13, **request, "rewardData": b""})
        # Known shop routes reply explicitly, never time out or charge for unknown data.
        return OutboundMessage(response_name, {"code": 13, **{k: v for k, v in request.items() if k in ("shopId", "goodsId", "buyNum")}})
