"""Confirmed fixed rewards and persistent tasks; missing rules fail closed.

No inferred shop quantities, random drops, calendar or automatic level-ups.
The initial task instance is deliberately NOT reset until its calendar is known.
"""
from collections import Counter
from importlib.resources import files
import json
import logging
import time

from x2server.messages.economy import ECONOMY_SCHEMAS, ITEM, REWARD, REWARD_ITEM, TASK, FINISH_REQUEST, FINISH_RESULT
from x2server.messages.lobby import LOBBY_SCHEMAS
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY


class UnresolvedEconomy(ValueError):
    """The entire operation must be withheld, never partially granted."""


class EconomyService:
    # Item.EffData -> BaseInfoProto; only supported currency destinations.
    CURRENCIES = {1237901: "gold", 1237902: "crystal", 1237907: "hero_exp",
                  1237908: "exp", 1237910: "daily_activity", 1237911: "week_activity"}

    def __init__(self, store):
        self.store = store
        self.catalog = json.loads(files("x2server").joinpath("data/economy_catalog.json").read_text(encoding="utf-8"))
        self.sections = {r["SectionID"]: r for r in self.catalog["sections"]}
        self.tasks = {r["DailyTaskID"]: r for r in self.catalog["tasks"] if r.get("IsUse", {}).get("value") == 1}
        self.items = {r["ItemID"]: r for r in self.catalog["items"]}
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
            store.db.execute("""CREATE TABLE IF NOT EXISTS economy_clears (
                player_id INTEGER NOT NULL, section_id INTEGER NOT NULL, first_uuid TEXT NOT NULL,
                PRIMARY KEY(player_id,section_id))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS economy_runs (
                uuid TEXT PRIMARY KEY, player_id INTEGER NOT NULL, session_id TEXT NOT NULL,
                section_id INTEGER NOT NULL, settled INTEGER NOT NULL DEFAULT 0)""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS economy_checkouts (
                player_id INTEGER NOT NULL, digest TEXT NOT NULL, uuid TEXT NOT NULL UNIQUE,
                PRIMARY KEY(player_id,digest))""")

    def gifts(self, groups):
        rewards = Counter()
        for group in groups:
            rows = [r for r in self.catalog["gifts"] if r["GiftGroup"] == group]
            if not rows:
                raise UnresolvedEconomy(f"missing Gift {group}")
            for row in rows:
                ids, nums = row.get("GiftValue", []), row.get("Num", [])
                if (row.get("AwardType", {}).get("value") != 1 or row.get("Probability")
                        or len(ids) != len(nums) or not ids):
                    raise UnresolvedEconomy(f"non-fixed Gift {group}")
                for item, count in zip(ids, nums):
                    if item not in self.items or type(count) is not int or count <= 0:
                        raise UnresolvedEconomy(f"invalid Gift {group}")
                    kind = self.items[item].get("ItemType", {}).get("value")
                    if kind == 10 or (kind == 16 and item not in self.CURRENCIES and item != 1237900):
                        raise UnresolvedEconomy(f"unrecovered reward destination {item}")
                    rewards[item] += count
        return dict(rewards)

    @staticmethod
    def reward_bytes(rewards):
        return REWARD.encode({"rewardItem": [REWARD_ITEM.encode({"itemId": i, "itemNum": n, "transform": False})
            for i, n in sorted(rewards.items())]})

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
            elif kind in (10, 16):
                raise UnresolvedEconomy("unrecovered reward destination")
            else:
                self.store.db.execute("""INSERT INTO inventory VALUES (?,?,?)
                    ON CONFLICT(player_id,item_id) DO UPDATE SET quantity=quantity+excluded.quantity""", (player_id, item, count))
                quantity = self.store.db.execute("SELECT quantity FROM inventory WHERE player_id=? AND item_id=?", (player_id, item)).fetchone()[0]
                if quantity > 2**31 - 1:
                    raise UnresolvedEconomy("item overflow")
        self.store.db.execute("UPDATE players SET snapshot=?, revision=revision+1 WHERE id=?",
            (json.dumps(snapshot, ensure_ascii=False, sort_keys=True), player_id))
        self.store.db.execute("INSERT INTO economy_grants VALUES (?,?,?,?)",
            (player_id, source, json.dumps(rewards, sort_keys=True), int(time.time())))
        return rewards

    def inventory_values(self, player_id):
        return {"items": [ITEM.encode({"id": r[0], "num": r[1], "locked": False, "dayGet": 0})
            for r in self.store.db.execute("SELECT item_id,quantity FROM inventory WHERE player_id=? ORDER BY item_id", (player_id,))]}

    def task_values(self, player_id, kind):
        level = self.store.get(player_id)["snapshot"]["level"]
        result = []
        for task_id, task in self.tasks.items():
            if task["RefreshCycle"]["value"] != kind or task["AcceptLevel"] > level:
                continue
            row = self.store.db.execute("SELECT progress,claimed FROM economy_tasks WHERE player_id=? AND task_id=?",
                                        (player_id, task_id)).fetchone()
            progress, claimed = tuple(row) if row else (0, 0)
            target = self.catalog["task_conditions"][str(task_id)]["CompleteNum"]
            result.append(TASK.encode({"taskId": task_id, "taskStatus": 4 if claimed else 3 if progress >= target else 2,
                "taskProgress": min(progress, target), "taskRefreshTime": 0, "finishTimes": int(bool(claimed)), "stage": 0}))
        return {"code": 10, "type": kind, "taskList": result}

    def record_event(self, player_id, key, condition_type, value=0, amount=1):
        """Internal authoritative events only. No client-supplied progress endpoint."""
        if amount <= 0:
            raise ValueError("positive event amount required")
        with self.store.db:
            self._event(player_id, key, condition_type, value, amount)

    def _event(self, player_id, key, condition_type, value, amount):
        inserted = self.store.db.execute("INSERT OR IGNORE INTO economy_events VALUES (?,?)", (player_id, key))
        if not inserted.rowcount:
            return
        level = self.store.get(player_id)["snapshot"]["level"]
        for task_id, task in self.tasks.items():
            condition = self.catalog["task_conditions"][str(task_id)]
            if (task["AcceptLevel"] > level or condition["CompleteType"]["value"] != condition_type
                    or condition.get("CompleteValue1", [0]) not in ([0], []) and value not in condition["CompleteValue1"]
                    or condition.get("CompleteValue2", [0]) not in ([0], [])):
                continue
            self.store.db.execute("""INSERT INTO economy_tasks(player_id,task_id,progress) VALUES (?,?,?)
                ON CONFLICT(player_id,task_id) DO UPDATE SET progress=MIN(?,progress+excluded.progress)""",
                (player_id, task_id, min(amount, condition["CompleteNum"]), condition["CompleteNum"]))

    def claim(self, player_id, task_id, kind):
        task = self.tasks.get(task_id)
        result = {"code": 13, "taskId": task_id, "type": kind, "rewardData": b""}
        if not task or task["RefreshCycle"]["value"] != kind or task["AcceptLevel"] > self.store.get(player_id)["snapshot"]["level"]:
            return result
        try:
            rewards = self.gifts([task["GiftGroup"]])
            with self.store.db:
                row = self.store.db.execute("SELECT progress,claimed FROM economy_tasks WHERE player_id=? AND task_id=?", (player_id, task_id)).fetchone()
                if not row or row[0] < self.catalog["task_conditions"][str(task_id)]["CompleteNum"]:
                    return result
                # Claim key remains stable across reconnects/restarts; no guessed reset.
                rewards = self._grant(player_id, f"task:initial:{task_id}", rewards)
                self.store.db.execute("UPDATE economy_tasks SET claimed=1 WHERE player_id=? AND task_id=?", (player_id, task_id))
                result.update(code=10, rewardData=self.reward_bytes(rewards))
            return result
        except UnresolvedEconomy:
            return result

    def settle(self, player_id, run_uuid, section, success):
        """Part of BattleService's receipt transaction, including first-clear key."""
        rewards = {}
        if success:
            groups = list(self.sections[section].get("VReward", []))
            if not self.store.db.execute("SELECT 1 FROM economy_clears WHERE player_id=? AND section_id=?", (player_id, section)).fetchone():
                groups += self.sections[section].get("FirVReward", [])
            rewards = self.gifts(groups)
            rewards = self._grant(player_id, f"battle:{run_uuid}", rewards)
            self.store.db.execute("INSERT OR IGNORE INTO economy_clears VALUES (?,?,?)", (player_id, section, run_uuid))
            self._event(player_id, f"clear:{run_uuid}", 3, section, 1)
        self.store.db.execute("UPDATE economy_runs SET settled=1 WHERE uuid=?", (run_uuid,))
        return self.reward_bytes(rewards)

    def pushes(self, player_id):
        from .login import LoginService
        return (LoginService.snapshot_push(self.store.get(player_id)),
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
        name = CORE_MESSAGE_REGISTRY.name_for(packet.message_id)
        logging.getLogger("x2.economy").info("economy request %s player=%s", name, player_id)
        request = (ECONOMY_SCHEMAS if name in ECONOMY_SCHEMAS else LOBBY_SCHEMAS)[name].decode(packet.body)
        response_name = name.replace("C2L_", "L2C_", 1)
        if name == "C2L_ItemAll":
            return OutboundMessage(response_name, self.inventory_values(player_id))
        if name == "C2L_QueryMission":
            return OutboundMessage(response_name, {"mainMission": [r[0] for r in self.store.db.execute(
                "SELECT section_id FROM economy_clears WHERE player_id=? ORDER BY section_id", (player_id,))]})
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
