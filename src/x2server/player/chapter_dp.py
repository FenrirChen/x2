"""Official chapter objectives, persisted from idempotent real event sources.

Cumulative client reports use per-run high water marks. They never grant items.
Historical clears/inventory can restore provable objectives, not fabricated kills.
"""
from importlib.resources import files
from collections import Counter
import json

from x2server.messages.economy import TASK


class ChapterDP:
    def __init__(self, economy):
        self.economy, self.db = economy, economy.store.db
        self.chapters = json.loads(files("x2server").joinpath("data/chapter_dp_tasks.json").read_text(encoding="utf-8"))["chapters"]
        self.boxes = json.loads(files("x2server").joinpath("data/dp_box_contents.json").read_text(encoding="utf-8"))["boxes"]
        with self.db:
            self.db.execute("""CREATE TABLE IF NOT EXISTS chapter_objectives (
                player_id INTEGER, chapter_id INTEGER, task_id INTEGER, progress INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(player_id,chapter_id,task_id))""")
            self.db.execute("""CREATE TABLE IF NOT EXISTS chapter_signals (
                player_id INTEGER, chapter_id INTEGER, source TEXT, kind TEXT, subject INTEGER,
                scope INTEGER, amount INTEGER, PRIMARY KEY(player_id,chapter_id,source,kind,subject,scope))""")
            self.db.execute("""CREATE TABLE IF NOT EXISTS chapter_dp_migrations (
                player_id INTEGER PRIMARY KEY, legacy_floors TEXT NOT NULL)""")

    def observe(self, player, chapter, source, kind, subject, amount, scope=0):
        if str(chapter) not in self.chapters or not 0 <= amount <= 10**7:
            return
        # The run key survives reconnects/request-id changes. A smaller repeated
        # tally cannot lower the mark and then inflate a later report.
        self.db.execute("""INSERT INTO chapter_signals VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(player_id,chapter_id,source,kind,subject,scope)
            DO UPDATE SET amount=MAX(amount,excluded.amount)""",
            (player, chapter, source, kind, subject, scope, amount))

    def refresh(self, player, chapter):
        if not self.db.execute("SELECT 1 FROM chapter_dp_migrations WHERE player_id=?", (player,)).fetchone():
            # Restore only evidence actually present in the current settlement
            # audit, not a guessed historical kill/shop total.
            for row in self.db.execute("SELECT run_id,section_id,sources FROM reward_settlement_audit WHERE player_id=?", (player,)):
                static = self.economy.entry_catalog.sections.get(row[1], {})
                evidence = json.loads(row[2]).get("EQUIP_INSTANCE", [])
                self.equipment(player, static.get("ChapterID", 0), row[0],
                    [{"star": i["star"], "item_id": i["type_id"]} for i in evidence])
            # A lost task_boxes row must not permit a second payment if the old
            # permanent grant ledger still proves that box was already paid.
            for row in self.db.execute("SELECT source FROM economy_grants WHERE player_id=? AND source LIKE 'chapterdp:%'", (player,)):
                parts = row[0].split(":")
                if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                    self.db.execute("INSERT OR IGNORE INTO task_boxes VALUES (?,7,?,?)", (player, int(parts[1]), int(parts[2])))
        entries = self.chapters.get(str(chapter), {}).get("tasks", [])
        signals = self.db.execute("SELECT source,kind,subject,scope,amount FROM chapter_signals WHERE player_id=? AND chapter_id=?", (player, chapter)).fetchall()
        clears = {r[0] for r in self.db.execute("SELECT section_id FROM economy_clears WHERE player_id=?", (player,))}
        bag = dict(self.db.execute("SELECT item_id,quantity FROM inventory WHERE player_id=?", (player,)))
        def total(kind, subject, scope=None):
            return sum(r[4] for r in signals if r[1] == kind and (subject == -1 or r[2] == subject) and (scope is None or r[3] == scope))
        for task in entries:
            kind = task.get("completeType")
            subject = int(task.get("completeValue1", 0))
            if subject >= 2**63:
                subject = -1
            second = int(task.get("completeValue2", 0))
            target = task.get("completeNum", 1)
            value = 0
            if kind == "E_BeatSection":
                value = int(subject in clears)
            elif kind == "E_KillMonster":
                value = total("kill", subject)
            elif kind == "E_KillMonsterInSan":
                value = total("san_kill", second, subject)
            elif kind == "E_ShopBuyItem":
                value = total("buy", subject)
            elif kind == "E_ShopSpendMoney":
                value = total("spend", subject)
            elif kind == "E_NPCInteraction":
                value = total("npc", subject)
            elif kind == "E_GetItemID":
                value = max(bag.get(subject, 0), total("item", subject))
            elif kind == "E_GetMoneyPer":
                value = max((r[4] for r in signals if r[1] == "money" and r[2] == 903), default=0)
            elif kind in ("E_GetItemQuality", "E_GetItemQualityPer"):
                by_run = Counter()
                for r in signals:
                    if r[1] == "quality" and r[2] >= subject and r[3] == second:
                        by_run[r[0]] += r[4]
                value = max(by_run.values(), default=0) if kind.endswith("Per") else sum(by_run.values())
            self.db.execute("""INSERT INTO chapter_objectives VALUES (?,?,?,?)
                ON CONFLICT(player_id,chapter_id,task_id) DO UPDATE SET progress=MAX(progress,excluded.progress)""",
                (player, chapter, task["taskId"], min(value, target)))
        # Archive the old operator floors exactly once. They no longer contribute
        # points to the official aggregate; claims remain in the existing ledger.
        floors = dict(self.db.execute("SELECT chapter_id,minimum_dp FROM chapter_dp_floors WHERE player_id=?", (player,)))
        self.db.execute("INSERT OR IGNORE INTO chapter_dp_migrations VALUES (?,?)", (player, json.dumps(floors)))

    def points(self, player, chapter):
        with self.economy.transaction():
            self.refresh(player, chapter)
            progress = dict(self.db.execute("SELECT task_id,progress FROM chapter_objectives WHERE player_id=? AND chapter_id=?", (player, chapter)))
        return sum(t["dp"] for t in self.chapters.get(str(chapter), {}).get("tasks", []) if t.get("completeType") and progress.get(t["taskId"], 0) >= t.get("completeNum", 1))

    def task_list(self, player, chapter):
        self.points(player, chapter)
        progress = dict(self.db.execute("SELECT task_id,progress FROM chapter_objectives WHERE player_id=? AND chapter_id=?", (player, chapter)))
        return [TASK.encode({"taskId": t["taskId"], "taskProgress": progress.get(t["taskId"], 0),
            "taskStatus": 3 if t.get("completeType") and progress.get(t["taskId"], 0) >= t.get("completeNum", 1) else 2})
            for t in self.chapters.get(str(chapter), {}).get("tasks", [])]

    def report(self, player, chapter, run, values):
        from x2server.messages.battle import DROP_REPORT_ITEM, DROP_REPORT_NPC, DROP_REPORT_SPAN
        for raw in values.get("npcData", []):
            row = DROP_REPORT_NPC.decode(raw)
            self.observe(player, chapter, run, "npc", row.get("id", 0), row.get("count", 0))
        for raw in values.get("currency", []):
            row = DROP_REPORT_SPAN.decode(raw)
            self.observe(player, chapter, run, "money", row.get("field4", 0), row.get("field3", 0))
        relics = set(values.get("relicList", []))
        items, qualities = Counter(), Counter()
        for raw in values.get("dropItem", []):
            row = DROP_REPORT_ITEM.decode(raw)
            # Candidate pools are not pickups. Count only entries carried in the
            # reported relic list; no bag/inventory/reward is changed here.
            if row.get("itemId") in relics:
                items[row["itemId"]] += 1
                qualities[row.get("value", 0)] += 1
        for item, count in items.items():
            self.observe(player, chapter, run, "item", item, count)
        for quality, count in qualities.items():
            self.observe(player, chapter, run, "quality", quality, count, 4)
        self.refresh(player, chapter)

    def equipment(self, player, chapter, run, instances):
        counts = Counter(i["star"] for i in instances)
        for star, count in counts.items():
            self.observe(player, chapter, run, "quality", star, count, 10)
        items = Counter(i["item_id"] for i in instances if i.get("item_id"))
        for item, count in items.items():
            self.observe(player, chapter, run, "item", item, count)

    def shop(self, player, item, currency, quantity, cost, key):
        # Lobby purchases have no battle chapter. They apply to each chapter's
        # shopping objectives, once per persisted purchase receipt.
        for chapter in map(int, self.chapters):
            self.observe(player, chapter, key, "buy", item, quantity)
            self.observe(player, chapter, key, "spend", currency, cost)
            self.refresh(player, chapter)

    def grant_box(self, player, chapter, index, item_id):
        from .economy import UnresolvedEconomy
        from .reward_system import RewardGrant, sum_grants
        from .equipment_factory import materialize_instances
        from x2server.messages.equipment import HERO_EQUIP, EQUIP_PARAM
        box = self.boxes.get(str(item_id))
        if not box or not box.get("supported"):
            raise UnresolvedEconomy("DP box contents unavailable")
        source = f"chapterdp:{chapter}:{index}"
        grants = [RewardGrant("CHAPTER_DP_BOX", 0, source, row["itemId"], row["num"], reason=f"DP box {item_id}") for row in box["contents"]]
        equips = []
        spec = box.get("equib")
        if spec:
            factory = self.economy.equipment_factory
            parts = {row["part"]: int(key) for key, row in factory.data["equib_base"].items() if row["suit"] == spec["suit"]}
            if len(parts) != 6 or any(part not in parts for part in spec["parts"]):
                raise UnresolvedEconomy("DP equipment suit unavailable")
            for ordinal, part in enumerate(spec["parts"]):
                instances = materialize_instances(self.db, player, parts[part], spec["star"], 1, source, factory, ordinal)
                equips.extend(HERO_EQUIP.encode({**{k: v for k, v in i.items() if k not in ("param", "marker")},
                    "param": EQUIP_PARAM.encode(i["param"])}) for i in instances)
        rewards = self.economy._grant(player, source, sum_grants(grants))
        raw = self.economy.reward_bytes(rewards, equips)
        if any(1211000 <= item < 1212000 for item in rewards):
            from .wish import WishService
            raw = WishService._reward_with_transform_heroes(raw)
        return raw
