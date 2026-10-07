"""Confirmed rewards and tasks with the user-defined Revival calendar."""
from collections import Counter
import hashlib
from contextlib import contextmanager
from importlib.resources import files
import json
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone

from x2server.messages.economy import ECONOMY_SCHEMAS, ITEM, REWARD, REWARD_ITEM, TASK, TREASURE_BOX, FINISH_REQUEST, FINISH_RESULT
from x2server.messages.battle import OUTSIDE_ITEM
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


# 北京时区的「本地日」整数键: 恰好在北京时间的 00:00 翻页, 用于好感日常任务的按日落库
# (favor_daily_tasks.day)。favor.py 里那份按天的计数表用的是同样一条日界线。
DAY_SECONDS = 86400
BEIJING_OFFSET = 8 * 3600


def day_index(now: int) -> int:
    return (int(now) + BEIJING_OFFSET) // DAY_SECONDS


class EconomyService:
    CAUSALITY_CARDS = {1202010: 10, 1202011: 20, 1202012: 30,
                       1202013: 60, 1202014: 100}  # Item.Used -> Gift.Num
    POWER_RECOVER_SECONDS = 225  # Client ServerData default 300s; user policy: 25% faster.
    # Item.EffData -> BaseInfoProto; only supported currency destinations.
    CURRENCIES = {1237901: "gold", 1237902: "crystal", 1237906: "equip_exp", 1237907: "hero_exp",
                  1237908: "exp", 1237910: "daily_activity", 1237911: "week_activity"}
    STACKABLE_REWARD_TYPES = frozenset((5, 12, 13, 14, 17, 18, 20, 22, 23, 24, 25, 26, 33, 34, 40, 41))
    ACTIVITY_FIELDS = {1: "daily_activity", 2: "week_activity"}
    MAP_TYPE_CHALLENGE = 2  # 现世复刻: the difficulty stages of a chapter
    # TaskCondition CompleteType enums that server events can authoritatively fire.
    TASK_EVENT_CUSTOMS_PASS = 3        # E_CustomsPass
    TASK_EVENT_SIGN_IN_GAME = 5        # E_SignInGame
    TASK_EVENT_APPOINT_TIME_ONLINE = 6  # E_AppointTimeOnLine
    TASK_EVENT_HERO_LEVEL_UP = 7       # E_HeroLevelUp
    TASK_EVENT_BUY_POWER = 8           # E_BuyPower
    TASK_EVENT_BUY_GOLD = 9            # E_BuyGold
    TASK_EVENT_CONSUME_POWER_TODAY = 10  # E_ConsumePowerToday
    TASK_EVENT_UPGRADE_EQUIPMENT = 12  # E_UpgradeEquipment
    TASK_EVENT_UPGRADE_SKILL = 13      # E_UpgradeSkill
    TASK_EVENT_UPGRADE_ARTIFACT = 14   # E_UpgradeArtifact
    TASK_EVENT_HERO_INTERACTIVE = 19   # E_HeroInteractive
    TASK_EVENT_BUY_GOOD = 24           # E_BuyGood
    TASK_EVENT_ACCOUNT_LEVEL = 43      # E_AccountLevel: progress is the player's level
    TASK_EVENT_HERO_REACH_STAR_LEVEL = 44  # E_HeroReachStarAndLevel: 达标的英雄数
    TASK_EVENT_WISH = 45               # E_Wish
    TASK_EVENT_ITEM_STAR_ID = 47       # E_ItemStarAndID: 已拥有的清单内道具数
    TASK_EVENT_EQUIP_EQUIP = 49        # E_EquipEquip
    TASK_EVENT_LOGIN_DAY = 58          # E_LoginDay: one per local day the player logs in
    TASK_EVENT_FAVORABILITY_LEVEL = 73  # E_FavorabilityLevel: 好感等级达标的英雄数
    TASK_EVENT_CUSTOMS_ENTRY = 87      # E_CustomsEntry
    TASK_EVENT_FAVORABILITY_DAILY_TASK = 72  # E_FavorabilityDailyTask: 完成一次心愿任务
    # 好感日常任务(心愿任务)自己的两个条件类型 (data/favor_task_catalog.json 的 track=event):
    #   11 E_CarryHeroCustomsPass    通关结算时队伍里带着指定英雄
    #   68 E_SendDesignativeHeroGift 给指定英雄送指定的礼物
    TASK_EVENT_CARRY_HERO_CUSTOMS_PASS = 11
    TASK_EVENT_SEND_DESIGNATIVE_HERO_GIFT = 68
    # GameTaskType.CHALLENGE: 60 tasks in 10 groups, no period, no rollover.
    CHALLENGE_KIND = 3
    # GameTaskType.FAVORDAILY. 心愿任务由玩家在许愿页签自己选(客户端的选择页 ->
    # C2L_AcceptFavorTask), 不像每日/周常那样按等级自动开行; 接取记录按本地日存, 00:00
    # 自动翻页, 所以不需要定时任务。
    FAVOR_DAILY_KIND = 6
    # QueryExtraType.GENMIND. C2L_GameTask(type=6) 的 extraType 把同一个请求分成两问:
    # 0 = 我已接的心愿任务, 1 = 「开始分析」按钮生成的候选。见 favor_task_values。
    QUERY_EXTRA_GENMIND = 1
    # GameTaskType.CHAPTER (7): the chapter DP query and its DP 宝箱 claims.
    CHAPTER_DP_KIND = 7
    POWER_BUY_ITEM = 1237900
    POWER_BUY_AMOUNT = 120
    POWER_BUY_CURRENCY = 1237902
    # 星图 -> 剧情回顾 -> 主线: every ChapterInfo/POVChapterInfo row carries
    # ReviewUnlockRequest=1237916 (技能点, the currency StarChartsSkill already
    # spends), RequestNum=1 and ReviewUnlocAward=760066 (Gift -> 1x 许愿币).
    STORY_REVIEW_UNLOCK_ITEM = 1237916
    STORY_REVIEW_UNLOCK_NUM = 1
    STORY_REVIEW_AWARD = 760066
    # REVIVAL_COMPATIBILITY ladder retained from the community fix package.
    POWER_BUY_PRICES = (20, 20, 40, 60, 80, 100, 120, 150, 180, 220,
                        260, 300, 350, 400, 460, 520, 600, 700, 800, 1000)

    def __init__(self, store, clock=time.time):
        self.store = store
        self.clock = clock
        self.catalog = json.loads(files("x2server").joinpath("data/economy_catalog.json").read_text(encoding="utf-8"))
        # 挑战任务 (ChallengeTask): 60 rows in 10 groups of 6, keyed to the client's
        # own ChallengeTask/TaskCondition tables. Boxes 1..10 are the group ids.
        challenge_path = files("x2server").joinpath("data/challenge_tasks.json")
        challenge = (json.loads(challenge_path.read_text(encoding="utf-8"))
                     if challenge_path.is_file() else None)
        self.challenge_tasks = {int(k): v for k, v in (challenge or {}).get("tasks", {}).items()}
        self.challenge_boxes = {int(k): v for k, v in (challenge or {}).get("boxes", {}).items()}
        # 好感日常任务 (心愿任务). 345 条 (39 英雄各 8~9 条), 由玩家的 C2L_AcceptFavorTask
        # 决定今天做哪几条, 所以它和挑战任务一样有自己的存储与下发方法, 不走 self.tasks
        # 那套「按等级自动开行」的每日/周常机制。favor_task_catalog.json 从客户端自己的
        # FavorabilityTask / TaskCondition 两张表生成, 只保留服务端能亲眼见证的条件。
        favor_path = files("x2server").joinpath("data/favor_task_catalog.json")
        favor = (json.loads(favor_path.read_text(encoding="utf-8"))
                 if favor_path.is_file() else None)
        self.favor_tasks = {int(k): v for k, v in (favor or {}).get("tasks", {}).items()}
        self.favor_task_daily_limit = int((favor or {}).get("dailyLimit", 0))
        # FavorService (player/favor.py). 任务的 FavorabilityGift 要加到英雄身上, 而好感
        # 曲线与落库都在那边; tools/local_game_server.py 在两边都建好之后挂上来, 与
        # achievements 同一种接线。None 时只发道具奖、不发好感。
        self.favor = None
        # Chapter DP gates and thresholds, from the client's own ChapterInfo table.
        dp_path = files("x2server").joinpath("data/chapter_dp.json")
        self.chapter_dp_catalog = (json.loads(dp_path.read_text(encoding="utf-8"))["chapters"]
                                   if dp_path.is_file() else {})
        # Full recovered Gift table (10.7k groups) backing bag-item use: the
        # Item.Used column names groups like 72xxxx/702xxx that the curated
        # economy_catalog does not carry.
        contents_path = files("x2server").joinpath("data/gift_contents.json")
        self.gift_contents = (json.loads(contents_path.read_text(encoding="utf-8"))["gifts"]
                              if contents_path.is_file() else {})
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
        # The compact reward_items export omits Item.Used. Restore item-to-Gift
        # links as data so every card uses the same receipt path.
        used_path = files("x2server").joinpath("data/item_used_catalog.json")
        if used_path.is_file():
            used = json.loads(used_path.read_text(encoding="utf-8"))["items"]
            for row in self.catalog["items"]:
                if str(row["ItemID"]) in used and not row.get("Used"):
                    row["Used"] = used[str(row["ItemID"])]["used"]
        self.sections = {r["SectionID"]: r for r in self.catalog["sections"]}
        self.daily_sections = {r["SectionID"]: r for r in self.catalog.get("daily_sections", [])}
        self.reward_sections = {**self.sections, **self.daily_sections}
        self.entry_catalog = BattleEntryCatalog()
        self.reward_sections.update(self.entry_catalog.sections)
        self.section_rewards = SectionRewardCatalog()
        self.tasks = {r["DailyTaskID"]: r for r in self.catalog["tasks"] if r.get("IsUse", {}).get("value") == 1}
        self.items = {r["ItemID"]: r for r in self.catalog["items"]}
        self.bag_catalog = json.loads(files("x2server").joinpath("data/bag_client_catalog.json").read_text(encoding="utf-8"))
        for item_id, link in self.bag_catalog["items"].items():
            self.items[int(item_id)]["Used"] = link["used"]
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
            store.db.execute("""CREATE TABLE IF NOT EXISTS item_opt_receipts (
                request_key TEXT PRIMARY KEY, player_id INTEGER NOT NULL, response BLOB NOT NULL)""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS economy_tasks (
                player_id INTEGER NOT NULL, task_id INTEGER NOT NULL, progress INTEGER NOT NULL DEFAULT 0,
                claimed INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(player_id,task_id))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS economy_events (
                player_id INTEGER NOT NULL, event_key TEXT NOT NULL, PRIMARY KEY(player_id,event_key))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS task_boxes (
                player_id INTEGER NOT NULL, kind INTEGER NOT NULL, period_start INTEGER NOT NULL,
                box_id INTEGER NOT NULL, PRIMARY KEY(player_id,kind,period_start,box_id))""")
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
            # 好感日常任务: 今天接了哪几条、做到哪、领没领。键含本地日(day_index), 所以
            # 00:00 自动翻页、同日重启结果不变, 与 favor_touch_log 同一套写法。任务 id 是
            # 635xxx, 与 economy_tasks 里的每日/周常/挑战 id 不重叠, 但也不能混进那张表:
            # ensure_periods / _event 只按 self.tasks 和 challenge_tasks 扫表, 混进去会被
            # 误扫误删。
            store.db.execute("""CREATE TABLE IF NOT EXISTS favor_daily_tasks (
                player_id INTEGER NOT NULL, day INTEGER NOT NULL, task_id INTEGER NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0, claimed INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(player_id,day,task_id))""")
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
            store.db.execute("""CREATE TABLE IF NOT EXISTS chapter_dp_floors (
                player_id INTEGER NOT NULL, chapter_id INTEGER NOT NULL,
                minimum_dp INTEGER NOT NULL CHECK(minimum_dp>=0), reason TEXT NOT NULL,
                PRIMARY KEY(player_id,chapter_id))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS story_reviews (
                player_id INTEGER NOT NULL, chapter_id INTEGER NOT NULL,
                PRIMARY KEY(player_id,chapter_id))""")
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

        from .chapter_dp import ChapterDP
        self.dp = ChapterDP(self)
        from .achievements import AchievementService
        self.achievements = AchievementService(self)
        from .endless import EndlessService
        self.endless = EndlessService(self)
        from .world_boss import WorldBossService
        self.world_boss = WorldBossService(self)
        from .pending_delivery import recover
        for row in store.db.execute("SELECT id FROM players").fetchall():
            recover(self, row[0])

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
                    for task_id, task in self.tasks.items():
                        if task["RefreshCycle"]["value"] == kind and task["AcceptLevel"] <= snapshot["level"]:
                            self.store.db.execute("INSERT OR IGNORE INTO economy_tasks(player_id,task_id) VALUES (?,?)", (player_id, task_id))
                            if self.store.db.execute("SELECT 1 FROM economy_grants WHERE player_id=? AND source=?", (player_id, f"task:{kind}:{previous[0]}:{task_id}")).fetchone():
                                self.store.db.execute("UPDATE economy_tasks SET claimed=1 WHERE player_id=? AND task_id=?", (player_id, task_id))
                            self.store.db.execute("UPDATE economy_tasks SET progress=MAX(progress,CASE WHEN claimed<>0 THEN ? ELSE 0 END),claimed=CASE WHEN claimed<>0 THEN 1 ELSE 0 END WHERE player_id=? AND task_id=?",
                                                  (self.catalog["task_conditions"][str(task_id)]["CompleteNum"], player_id, task_id))
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
        self.achievements.login(player_id)
        self.refresh_stamina(player_id)
        self.ensure_periods(player_id)
        self.record_event(player_id, "login", 5)
        self.repair_challenge(player_id)
        self.record_challenge_login_day(player_id)
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

    def _gift_rows(self, group):
        """Curated catalog rows first, then the full recovered Gift table."""
        rows = [r for r in self.catalog["gifts"] if r["GiftGroup"] == group]
        if rows:
            return rows
        entry = self.gift_contents.get(str(group))
        if entry is None:
            return []
        return [{"GiftGroup": group, "AwardType": {"value": entry["awardType"]},
                 "GiftValue": [item for item, _ in entry["items"]],
                 "Num": [num for _, num in entry["items"]],
                 "Probability": list(entry.get("weights") or []),
                 "source": "gift_contents"}]

    def gifts(self, groups, deferred=None, allow_daily_random=False):
        rewards = Counter()
        for group in groups:
            rows = self._gift_rows(group)
            if not rows:
                raise UnresolvedEconomy(f"missing Gift {group}")
            for row in rows:
                ids, nums = row.get("GiftValue", []), row.get("Num", [])
                kind = row.get("AwardType", {}).get("value")
                probability = row.get("Probability", [])
                # gift_contents weights do not share one scale, so the draw
                # normalizes over whatever total the row ships instead of
                # requiring a sum of 100.
                if (kind not in (1, 2) or kind == 2 and not allow_daily_random
                        or kind == 1 and probability or len(ids) != len(nums) or not ids
                        or kind == 2 and (len(probability) != len(ids)
                                          or sum(probability) <= 0 or any(type(p) is not int or p < 0 for p in probability))):
                    raise UnresolvedEconomy(f"non-fixed Gift {group}")
                if kind == 2:
                    draw = secrets.randbelow(sum(probability))
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
                    if (item_kind not in self.STACKABLE_REWARD_TYPES and item != 1260015
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

    def _grant(self, player_id, source, rewards, *, stackable_types=()):
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
            if kind == 20:
                snapshot.setdefault("medal_earned", {}).setdefault(str(item), int(self.clock()))
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
            elif (kind not in self.STACKABLE_REWARD_TYPES and kind not in stackable_types
                    and item != 1260015 and not (kind == 11 and source.startswith("chapterdp:"))):
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
        from .appearance import avatar_frames
        items = dict(self.store.db.execute("SELECT item_id,quantity FROM inventory WHERE player_id=? AND quantity>0", (player_id,)))
        for frame in avatar_frames():
            items[frame] = max(1, items.get(frame, 0))
        return {"items": [ITEM.encode({"id": r[0], "num": r[1], "locked": False, "dayGet": 0})
            for r in sorted(items.items())]}

    # -- 挑战任务 (challenge, GameTaskType 3) ------------------------------
    #
    # 60 tasks in 10 groups of 6 (data/challenge_tasks.json). The series is not
    # periodic, so unlike 每日/周常 it has no task_periods row and no rollover;
    # ensure_periods only ever touches the daily/weekly ids in self.tasks. The
    # client decides what the page shows by itself: it sorts boxList, takes the
    # first box whose pickStatus is not 2 (已领取), and keeps every TaskData whose
    # group equals that box's boxId. Two consequences the server has to respect:
    #
    # * boxId must be the group id 1..10, not a 0-based cell index: the client
    #   compares it against ChallengeTask.TaskGroupID.
    # * a group's box only becomes claimable once all six of its tasks are 已领取,
    #   so one un-completable task blocks the whole chain behind it. Tasks whose
    #   condition has no server-side event source are therefore minted already at
    #   their target (track "served" in the catalog) - a deliberate compatibility
    #   choice, recorded in the catalog's own provenance.
    def challenge_derived(self, player_id, entry):
        """Progress a challenge task reads from state the server already owns.

        "Reach N" conditions carry the requirement (star/level/item id) in
        value1/value2 and the count in CompleteNum; the answer is how many things
        already qualify. The value lists are read as *thresholds* (>=), not as the
        equality whitelist events apply: 达标/Reach semantics, inferred - recorded
        as provenance in data/challenge_tasks.json rather than claimed as
        recovered.
        """
        complete_type = entry["completeType"]
        if complete_type == self.TASK_EVENT_ACCOUNT_LEVEL:
            return self.store.get(player_id)["snapshot"]["level"]
        if complete_type == self.TASK_EVENT_HERO_REACH_STAR_LEVEL:
            star = entry["value1"][0] if entry["value1"] else 0
            level = entry["value2"][0] if entry["value2"] else 0
            return sum(1 for hero in self.store.get(player_id)["snapshot"].get("heroes", [])
                       if hero.get("state") == 2 and hero.get("star", 0) >= star
                       and hero.get("level", 0) >= level)
        if complete_type == self.TASK_EVENT_FAVORABILITY_LEVEL:
            level = entry["value2"][0] if entry["value2"] else 0
            return sum(1 for hero in self.store.get(player_id)["snapshot"].get("heroes", [])
                       if hero.get("state") == 2 and hero.get("favor", {}).get("level", 0) >= level)
        if complete_type == self.TASK_EVENT_ITEM_STAR_ID:
            owned = {row[0] for row in self.store.db.execute(
                "SELECT item_id FROM inventory WHERE player_id=?", (player_id,))}
            return sum(1 for item_id in entry["value1"] if item_id in owned)
        return 0

    def repair_challenge(self, player_id):
        """Mint the challenge rows and clamp derived progress up. Idempotent.

        Wrapped in a savepoint: this also runs while building task pushes, and a
        bare DML there would leave an uncommitted implicit transaction behind
        (in_transaction stuck True), which silently hides later saves from any
        other connection.
        """
        if not self.challenge_tasks:
            return
        with self.transaction():
            clears = {row[0] for row in self.store.db.execute(
                "SELECT section_id FROM economy_clears WHERE player_id=?", (player_id,))}
            for task_id, entry in self.challenge_tasks.items():
                target = entry["completeNum"]
                if entry["track"] == "served":
                    floor = target
                elif entry["track"] == "event" and entry["completeType"] == self.TASK_EVENT_CUSTOMS_PASS:
                    # 剧情关 cannot be re-entered, so a player who cleared the
                    # named stages before this system shipped must still get the
                    # credit: count their existing clears of the listed sections.
                    floor = min(sum(1 for section in entry["value1"] if section in clears), target)
                else:
                    floor = self.challenge_derived(player_id, entry)
                row = self.store.db.execute("SELECT progress FROM economy_tasks WHERE player_id=? AND task_id=?",
                                            (player_id, task_id)).fetchone()
                if row is None:
                    self.store.db.execute("INSERT INTO economy_tasks(player_id,task_id,progress) VALUES (?,?,?)",
                                          (player_id, task_id, floor))
                elif floor > row[0]:
                    self.store.db.execute("UPDATE economy_tasks SET progress=? WHERE player_id=? AND task_id=?",
                                          (floor, player_id, task_id))

    def _challenge_group_done(self, player_id, group):
        """Whether every task of one group has been claimed."""
        ids = [t for t, e in self.challenge_tasks.items() if e["group"] == group]
        if not ids:
            return False
        done = self.store.db.execute(
            "SELECT COUNT(*) FROM economy_tasks WHERE player_id=? AND claimed=1 AND task_id IN (%s)"
            % ",".join("?" * len(ids)), (player_id, *ids)).fetchone()[0]
        return done == len(ids)

    def challenge_values(self, player_id):
        """L2C_GameTask payload for type 3: all 60 tasks plus the 10 group boxes."""
        self.repair_challenge(player_id)
        tasks = []
        for task_id, entry in sorted(self.challenge_tasks.items()):
            row = self.store.db.execute("SELECT progress,claimed FROM economy_tasks WHERE player_id=? AND task_id=?",
                                        (player_id, task_id)).fetchone()
            progress, claimed = tuple(row) if row else (0, 0)
            target = entry["completeNum"]
            tasks.append(TASK.encode({"taskId": task_id,
                "taskStatus": 4 if claimed else 3 if progress >= target else 2,
                "taskProgress": min(progress, target), "taskRefreshTime": 0,
                "finishTimes": int(bool(claimed)), "stage": 0}))
        picked = {r[0] for r in self.store.db.execute(
            "SELECT box_id FROM task_boxes WHERE player_id=? AND kind=?", (player_id, self.CHALLENGE_KIND))}
        boxes = [TREASURE_BOX.encode({"boxId": group, "activityId": 0,
            "pickStatus": 2 if group in picked else 1 if self._challenge_group_done(player_id, group) else 0})
            for group in sorted(self.challenge_boxes)]
        return {"code": 10, "type": self.CHALLENGE_KIND, "taskList": tasks, "boxList": boxes}

    def claim_challenge(self, player_id, task_id):
        """Pay one challenge task's Gift group; once per task for the player's life."""
        entry = self.challenge_tasks.get(task_id)
        result = {"code": 13, "taskId": task_id, "type": self.CHALLENGE_KIND, "rewardData": b""}
        if entry is None:
            return result
        self.repair_challenge(player_id)
        try:
            rewards = self.gifts([entry["gift"]])
            with self.transaction():
                row = self.store.db.execute("SELECT progress,claimed FROM economy_tasks WHERE player_id=? AND task_id=?",
                                            (player_id, task_id)).fetchone()
                if not row or row[1] or row[0] < entry["completeNum"]:
                    return result
                self._grant(player_id, f"challenge:{task_id}", rewards)
                self.store.db.execute("UPDATE economy_tasks SET claimed=1 WHERE player_id=? AND task_id=?",
                                      (player_id, task_id))
                result.update(code=10, rewardData=self.reward_bytes(rewards))
        except UnresolvedEconomy:
            return result
        logging.getLogger("x2.economy").info("challenge task claimed task=%s player=%s",
                                             task_id, player_id)
        return result

    def pick_challenge_box(self, player_id, box_id, param=0, *, wire=False):
        """Open one 挑战宝箱; refused unless its whole group is already claimed.

        Picking the box is what advances the page: the client's next refresh takes
        the following boxId as the current phase, because this one now reads 已领取.
        """
        result = {"code": 13, "boxId": box_id, "type": self.CHALLENGE_KIND,
                  "rewardData": b"", "param": param, "activityId": 0}
        # The live 2.4 client sends boxId=0 for the first challenge phase,
        # although challenge_tasks.json numbers its groups from 1. Keep the
        # wire response's original index; persist the canonical group id.
        group_id = box_id + 1 if wire and 0 <= box_id < len(self.challenge_boxes) else box_id
        if group_id not in self.challenge_boxes and param in self.challenge_boxes:
            group_id = param
        group = self.challenge_boxes.get(group_id)
        if group is None:
            logging.getLogger("x2.economy").info(
                "challenge box rejected player=%s box=%s param=%s reason=unknown group",
                player_id, box_id, param)
            return OutboundMessage("L2C_PickTreasureBox", result)
        self.repair_challenge(player_id)
        try:
            rewards = self.gifts([group])
            with self.transaction():
                if self.store.db.execute("SELECT 1 FROM task_boxes WHERE player_id=? AND kind=? AND box_id=?",
                                         (player_id, self.CHALLENGE_KIND, group_id)).fetchone():
                    return OutboundMessage("L2C_PickTreasureBox", result)
                if not self._challenge_group_done(player_id, group_id):
                    logging.getLogger("x2.economy").info(
                        "challenge box rejected player=%s box=%s param=%s group=%s reason=tasks incomplete",
                        player_id, box_id, param, group_id)
                    return OutboundMessage("L2C_PickTreasureBox", result)
                self.store.db.execute("INSERT INTO task_boxes VALUES (?,?,?,?)",
                                      (player_id, self.CHALLENGE_KIND, 0, group_id))
                self._grant(player_id, f"challengebox:{group_id}", rewards)
                result.update(code=10, rewardData=self.reward_bytes(rewards))
        except UnresolvedEconomy as exc:
            logging.getLogger("x2.economy").info(
                "challenge box rejected player=%s box=%s param=%s group=%s reason=%s",
                player_id, box_id, param, group_id, exc)
            return OutboundMessage("L2C_PickTreasureBox", result)
        logging.getLogger("x2.economy").info("challenge box picked box=%s player=%s",
                                             group_id, player_id)
        return OutboundMessage("L2C_PickTreasureBox", result, pushes=self.pushes(player_id) + (
            OutboundMessage("L2C_TreasureBoxUpdate", {"type": self.CHALLENGE_KIND,
                "boxList": self.challenge_values(player_id)["boxList"]}),))

    def record_challenge_login_day(self, player_id):
        """Credit E_LoginDay once per local day, for the player's whole life."""
        if not self.challenge_tasks:
            return
        day = task_period(1, int(self.clock()))[0]
        with self.transaction():
            inserted = self.store.db.execute("INSERT OR IGNORE INTO economy_events VALUES (?,?)",
                (player_id, f"challenge:loginday:{day}:{self.TASK_EVENT_LOGIN_DAY}"))
            if not inserted.rowcount:
                return
            for task_id, entry in self.challenge_tasks.items():
                if entry["track"] != "loginday":
                    continue
                self.store.db.execute("UPDATE economy_tasks SET progress=MIN(?,progress+1) WHERE player_id=? AND task_id=?",
                                      (entry["completeNum"], player_id, task_id))

    def _challenge_event(self, player_id, key, condition_type, value, amount, value2=0):
        """Credit the same occurrence to the challenge tasks that count it.

        Caller must already be inside ``self.transaction()``. 挑战任务 have no
        period, so the dedup token is per player rather than per period: one clear
        of a stage pays its challenge task once, ever. The event is only recorded
        when a challenge task actually reads that type, so unrelated daily/weekly
        traffic does not grow the token table.
        """
        matched = [(task_id, e) for task_id, e in self.challenge_tasks.items()
                   if e["track"] == "event" and e["completeType"] == condition_type
                   and not self._excluded(e, "value1", value) and not self._excluded(e, "value2", value2)]
        if not matched:
            return
        inserted = self.store.db.execute("INSERT OR IGNORE INTO economy_events VALUES (?,?)",
                                         (player_id, f"challenge:{key}:{condition_type}"))
        if not inserted.rowcount:
            return
        for task_id, e in matched:
            self.store.db.execute("UPDATE economy_tasks SET progress=MIN(?,progress+?) WHERE player_id=? AND task_id=?",
                                  (e["completeNum"], amount, player_id, task_id))

    @staticmethod
    def _excluded(condition, field, value) -> bool:
        """Whether an event's value falls outside the condition's allowed list.

        An empty list or [0] means the condition does not filter on that
        dimension at all.
        """
        allowed = condition.get(field) or [0]
        return allowed not in ([0], []) and value not in allowed

    # -- 章节 DP (C2L_GameTask type 7 = GameTaskType.CHAPTER) ---------------
    #
    # The client refuses to enter chapter N+1 until the DP of ChapterInfo's
    # UnlockMapTypeID (the previous chapter) reaches UnlockDPRequest - the live
    # refusal reads "白夜崩解的DP到10才解锁", exactly chapter 2010300's gate
    # (after 2010200, DP 10). The DP it checks is L2C_GameTask.chapterTaskPoint.
    #
    # Official recovered objectives replace the old clear-count formula.
    # Existing box claims remain in task_boxes(kind=7, period_start=chapter).
    def chapter_dp(self, player_id, chapter) -> int:
        return self.dp.points(player_id, chapter)

    def chapter_dp_from_clears(self, clears, chapter) -> int:
        return sum(sum(t["dpPoints"]) for t in self.dp.chapters.get(str(chapter), {}).get("tasks", [])
                   if t.get("completeType") == "E_BeatSection" and t.get("completeValue1") in clears)

    def chapter_dp_capacity(self, chapter) -> int:
        """Most DP the chapter can reach under the same rule (the client's total)."""
        return sum(sum(t["dpPoints"]) for t in self.dp.chapters.get(str(chapter), {}).get("tasks", []))

    def chapter_dp_boxes(self, player_id, chapter) -> list:
        """The chapter page's DP 宝箱 (ChapterInfo.dpThresholds/dpRewards).

        boxId is the threshold index; pickStatus 2=已领取, 1=DP 已达标可领,
        0=未达标. Claims live in task_boxes(kind=7, period_start=chapterId).
        """
        entry = self.chapter_dp_catalog.get(str(chapter)) or {}
        thresholds = entry.get("dpThresholds") or []
        reward_ids = entry.get("dpRewards") or []
        if not thresholds or not reward_ids:
            return []
        picked = {r[0] for r in self.store.db.execute(
            "SELECT box_id FROM task_boxes WHERE player_id=? AND kind=? AND period_start=?",
            (player_id, self.CHAPTER_DP_KIND, chapter))}  # kind 7 = GameTaskType.CHAPTER
        dp = self.chapter_dp(player_id, chapter)
        return [TREASURE_BOX.encode({"boxId": index, "activityId": chapter,
            "pickStatus": 2 if index in picked else 1 if dp >= threshold and
                self.dp.boxes.get(str(reward_id), {}).get("supported") else 0})
            for index, (threshold, reward_id) in enumerate(zip(thresholds, reward_ids))]

    def pick_chapter_dp_box(self, player_id, request):
        """Claim one DP 宝箱: C2L_PickTreasureBox{type:7}.

        The client's wire shape sends the chapter id and the threshold index in
        boxId/param (GetBoxTreasure stores arg2->boxId, arg1->param), so accept
        either arrangement and normalize.
        """
        box_id, param = request.get("boxId", -1), request.get("param", 0)
        activity_id = request.get("activityId", 0)
        chapter = next((value for value in (param, activity_id, box_id)
                        if str(value) in self.chapter_dp_catalog), 0)
        small = [value for value in (box_id, param) if value != chapter]
        index = small[0] if small else -1
        entry = self.chapter_dp_catalog.get(str(chapter)) or {}
        thresholds = entry.get("dpThresholds") or []
        rewards = entry.get("dpRewards") or []
        result = {"code": 13, "boxId": box_id, "type": 7, "param": param,
                  "activityId": chapter, "rewardData": b""}
        if not thresholds or not 0 <= index < len(thresholds) or index >= len(rewards):
            return OutboundMessage("L2C_PickTreasureBox", result)
        try:
            with self.transaction():
                if self.store.db.execute(
                        "SELECT 1 FROM task_boxes WHERE player_id=? AND kind=? AND period_start=? AND box_id=?",
                        (player_id, 7, chapter, index)).fetchone():
                    return OutboundMessage("L2C_PickTreasureBox", result)
                if self.chapter_dp(player_id, chapter) < thresholds[index]:
                    return OutboundMessage("L2C_PickTreasureBox", result)
                if self.store.db.execute("SELECT 1 FROM economy_grants WHERE player_id=? AND source=?", (player_id, f"chapterdp:{chapter}:{index}")).fetchone():
                    return OutboundMessage("L2C_PickTreasureBox", result)
                reward_data = self.dp.grant_box(player_id, chapter, index, rewards[index])
                self.store.db.execute("INSERT OR IGNORE INTO task_boxes VALUES (?,?,?,?)",
                                      (player_id, 7, chapter, index))
                result.update(code=10, rewardData=reward_data)
        except UnresolvedEconomy:
            return OutboundMessage("L2C_PickTreasureBox", result)
        logging.getLogger("x2.economy").info(
            "chapter DP box claimed chapter=%s index=%s player=%s", chapter, index, player_id)
        from .hero import encode_hero_data
        reward = REWARD.decode(result["rewardData"])
        extra = [OutboundMessage("L2C_TreasureBoxUpdate", {"type": 7, "boxList": self.chapter_dp_boxes(player_id, chapter)})]
        if reward.get("rewardEquip"):
            extra.append(OutboundMessage("L2C_EquipUpdate", {"code": 10, "equip": reward["rewardEquip"]}))
        if reward.get("transformHero"):
            extra.append(OutboundMessage("L2C_HeroUpdate", {"code": 10, "heros": [encode_hero_data(h) for h in self.store.get(player_id)["snapshot"]["heroes"]]}))
        return OutboundMessage("L2C_PickTreasureBox", result, pushes=self.pushes(player_id) + tuple(extra))

    def challenge_chain(self, chapter) -> list:
        """A chapter's 现世复刻 difficulty rows, in difficulty order.

        Rows chain by NextSectionID; a row pointing into a chain already walked
        is a duplicate (chapter 2010800's unnamed 新月 row) and is skipped, so
        every real difficulty appears exactly once.
        """
        rows = [r for r in self.entry_catalog.sections.values()
                if r["Type"] == self.MAP_TYPE_CHALLENGE and r["ChapterID"] == chapter]
        ids = {r["SectionID"] for r in rows}
        following = {r["SectionID"]: r.get("NextSectionID") for r in rows}
        heads = sorted(i for i in ids if i not in set(following.values()))
        chain, seen = [], set()
        for head in heads:
            if head in seen or following.get(head) in seen:
                continue
            cursor = head
            while cursor in ids and cursor not in seen:
                chain.append(cursor)
                seen.add(cursor)
                cursor = following.get(cursor)
        return chain

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
        return {"code": 10, "type": kind, "taskList": result,
            "boxList": self.activity_boxes(player_id, kind)}

    def activity_config(self, kind):
        control = self.catalog["task_control"]
        if kind == 1:
            return control["DailyActiveValueNumber"], control["DailyGiftGroup"]
        if kind == 2:
            return control["WeeklyActiveValueNumber"], control["WeeklyGiftGroup"]
        return (), ()

    def activity_boxes(self, player_id, kind):
        self.ensure_periods(player_id)
        thresholds, _ = self.activity_config(kind)
        if not thresholds:
            return []
        period = self.store.db.execute("SELECT start FROM task_periods WHERE player_id=? AND kind=?",
                                       (player_id, kind)).fetchone()
        picked = {r[0] for r in self.store.db.execute(
            "SELECT box_id FROM task_boxes WHERE player_id=? AND kind=? AND period_start=?",
            (player_id, kind, period[0]))} if period else set()
        activity = self.store.get(player_id)["snapshot"].get(self.ACTIVITY_FIELDS[kind], 0)
        return [TREASURE_BOX.encode({"boxId": index, "pickStatus":
            2 if index in picked else 1 if activity >= threshold else 0, "activityId": 0})
            for index, threshold in enumerate(thresholds)]

    def pick_treasure_box(self, player_id, request):
        kind, box_id = request.get("type", 0), request.get("boxId", -1)
        result = {"code": 13, "boxId": box_id, "type": kind, "param": request.get("param", 0),
                  "activityId": request.get("activityId", 0), "rewardData": b""}
        thresholds, groups = self.activity_config(kind)
        if (box_id not in range(len(thresholds)) or request.get("activityId", 0)
                or request.get("param", 0)):
            return OutboundMessage("L2C_PickTreasureBox", result)
        try:
            rewards = self.gifts([groups[box_id]])
            with self.transaction():
                self.ensure_periods(player_id)
                period = self.store.db.execute("SELECT start FROM task_periods WHERE player_id=? AND kind=?",
                                               (player_id, kind)).fetchone()
                if not period or self.store.get(player_id)["snapshot"].get(self.ACTIVITY_FIELDS[kind], 0) < thresholds[box_id]:
                    return OutboundMessage("L2C_PickTreasureBox", result)
                inserted = self.store.db.execute("INSERT OR IGNORE INTO task_boxes VALUES (?,?,?,?)",
                    (player_id, kind, period[0], box_id))
                if not inserted.rowcount:
                    return OutboundMessage("L2C_PickTreasureBox", result)
                self._grant(player_id, f"box:{kind}:{period[0]}:{box_id}", rewards)
                result.update(code=10, rewardData=self.reward_bytes(rewards))
        except UnresolvedEconomy:
            return OutboundMessage("L2C_PickTreasureBox", result)
        return OutboundMessage("L2C_PickTreasureBox", result,
            pushes=self.pushes(player_id) + (OutboundMessage("L2C_TreasureBoxUpdate",
                {"type": kind, "boxList": self.activity_boxes(player_id, kind)}),))

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
        self._challenge_event(player_id, key, condition_type, value, amount, value2)

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

    # -- 心愿任务 (好感日常, GameTaskType 6) --------------------------------
    #
    # 终端 -> 神格心愿任务 Tab 的调用链:
    #
    #   打开 Tab      C2L_GameTask(type=6, extraType=0)   -> 已接的任务
    #   「开始分析」   C2L_GameTask(type=6, extraType=1)   -> 候选(生成)
    #   选中后确认     C2L_AcceptFavorTask(459, taskIds)  -> code=10 后客户端自己重查上一行
    #   领取           C2L_FinishGameTask(type=6)         -> 和每日/周常同一个协议
    #
    # extraType 不是可选参数, 它把同一个请求分成「我的任务」和「给候选」两问。
    #
    # 三件事让它自成一节:
    #
    # * 任务是玩家自己选的, 不像每日/周常按等级自动开行。345 条任务 id 是 635xxx, 落库
    #   用独立的 favor_daily_tasks(键含本地日), 00:00 自动翻页。
    # * 只有两种条件有服务端来源: 带指定英雄通关(11) 与 给指定英雄送指定礼物(68)。另外
    #   三种(67 远征 / 69 特训 / 25)没有可记账的事件, 进度只能是 0 - 见 catalog 的
    #   provenance。因此候选只从 track=="event" 里取, 不给玩家发一个永远做不完的任务。
    # * 领奖是「道具组 + 好感经验」两半: 道具组走 self.gifts/_grant, 好感那半归
    #   player/favor.py 的 grant_favor。

    def attach_favor(self, service) -> None:
        """Wire the 好感 service so a 心愿任务 claim can pay its FavorabilityGift.

        Same division as ``achievements``: economy owns *when* a reward is paid,
        player/favor.py owns the 好感 curve and the hero's own ``favor`` field. A
        claim pays two halves - the task's Gift group (an item group, paid here)
        and its own ``FavorabilityGift`` (50/60/75 好感经验, paid there) - so
        without this the claim still succeeds, it just pays the item half only.
        """
        self.favor = service

    def _favor_owned_heroes(self, player_id):
        """Hero ids this save actually owns (state 2)."""
        return {int(h.get("id", 0))
                for h in self.store.get(player_id)["snapshot"].get("heroes", [])
                if h.get("state") == 2 and int(h.get("id", 0)) > 0}

    def favor_accepted_ids(self, player_id, day=None):
        """Today's accepted 心愿任务 ids."""
        day = day_index(int(self.clock())) if day is None else day
        return {row[0] for row in self.store.db.execute(
            "SELECT task_id FROM favor_daily_tasks WHERE player_id=? AND day=?", (player_id, day))}

    def favor_candidates(self, player_id, day=None):
        """Today's candidate 心愿任务 ids; deterministic per (day, player).

        The official generation rule (候选数 / 概率 / 刷新时点) did not survive, so
        this is a local compatibility rule. The pool is every task whose hero the
        player owns and whose condition this server can witness, and the day's
        pick is a hash-ordered slice of it - same day, same answer, restart or
        not. Nothing is written, so the "generation" needs no table.
        """
        day = day_index(int(self.clock())) if day is None else day
        owned = self._favor_owned_heroes(player_id)
        taken = self.favor_accepted_ids(player_id, day)
        if 0 < self.favor_task_daily_limit <= len(taken):
            # 今天的名额已经接满。此时必须回空, 否则客户端会拿到一批「确认时一定被拒」
            # 的候选(accept_favor_tasks 按同一个上限设闸), 表现为点确认弹错误。
            return []
        pool = [task_id for task_id, entry in self.favor_tasks.items()
                if entry["track"] == "event" and entry["hero"] in owned and task_id not in taken]
        pool.sort(key=lambda task_id: hashlib.sha256(
            f"favortask:{day}:{player_id}:{task_id}".encode()).hexdigest())
        if self.favor_task_daily_limit <= 0:
            return pool
        return pool[:self.favor_task_daily_limit - len(taken)]

    def favor_task_values(self, player_id, extra_type, chapter_id=0):
        """The L2C_GameTask payload for type 6, both questions.

        ``extra_type == GENMIND`` is 「开始分析」: the candidate rows come back with
        ``taskStatus == 0``. That value is what the client's own page-state machine
        demands: FavorWishTab_CalPageState treats

            taskList empty                            -> 0 (开始页)
            每行 taskStatus == 0                       -> 1 (选择页)
            任一行 taskStatus != 0                     -> 2 (任务页)

        Only state 1 draws the choose page - the one with the confirm button that
        sends C2L_AcceptFavorTask (459). Sending the candidates as UNLOCK (1) put
        the client straight into the task page instead, so 459 was never sent and
        the page looked like it reset itself. When nothing can be generated the
        answer is E_NOT_GEN_MIND_TASK (173): the client handles that code for
        type 6 on the same path as code 10, so it lands on the start page instead
        of an error box.
        """
        day = day_index(int(self.clock()))
        values = {"type": self.FAVOR_DAILY_KIND, "chapterId": chapter_id}
        if extra_type == self.QUERY_EXTRA_GENMIND:
            candidates = self.favor_candidates(player_id, day)
            logging.getLogger("x2.economy").info(
                "favor candidates player=%s day=%s ids=%s", player_id, day, candidates)
            if not candidates:
                return {"code": 173, **values, "taskList": []}
            return {"code": 10, **values, "taskList": [
                TASK.encode({"taskId": task_id, "taskStatus": 0, "taskProgress": 0,
                             "taskRefreshTime": 0, "finishTimes": 0, "stage": 0})
                for task_id in candidates]}
        tasks = []
        for task_id in sorted(self.favor_accepted_ids(player_id, day)):
            entry = self.favor_tasks.get(task_id)
            row = self.store.db.execute(
                "SELECT progress,claimed FROM favor_daily_tasks"
                " WHERE player_id=? AND day=? AND task_id=?",
                (player_id, day, task_id)).fetchone()
            if entry is None or row is None:
                continue
            progress, claimed = tuple(row)
            target = entry["completeNum"]
            # 4 FINISH(已领取) / 3 REWARD(可领取) / 2 START(进行中) - 与每日/周常、
            # 挑战行同一个枚举。
            tasks.append(TASK.encode({"taskId": task_id,
                "taskStatus": 4 if claimed else 3 if progress >= target else 2,
                "taskProgress": min(progress, target), "taskRefreshTime": 0,
                "finishTimes": int(bool(claimed)), "stage": 0}))
        return {"code": 10, **values, "taskList": tasks}

    def accept_favor_tasks(self, player_id, task_ids):
        """Persist the player's 心愿任务 choice; returns the L2C_AcceptFavorTask code.

        The client only sends back ids it was shown, but the gate is kept here:
        today's cap (the catalog's dailyLimit) is what stops a player from accepting
        the whole 345-row table, and an id naming a hero the save does not hold is
        dropped rather than stored as a task nothing can ever progress. Re-sending
        an already-accepted id is idempotent, so a replayed confirm succeeds.
        """
        day = day_index(int(self.clock()))
        owned = self._favor_owned_heroes(player_id)
        accepted = self.favor_accepted_ids(player_id, day)
        limit = self.favor_task_daily_limit
        kept, fresh = [], []
        for task_id in dict.fromkeys(int(t) for t in task_ids):
            if task_id in accepted:
                kept.append(task_id)
                continue
            entry = self.favor_tasks.get(task_id)
            if entry is None or entry["hero"] not in owned:
                continue
            if limit > 0 and len(accepted) + len(fresh) >= limit:
                break
            fresh.append(task_id)
        if not kept and not fresh:
            logging.getLogger("x2.economy").info(
                "favor accept refused player=%s day=%s ids=%s", player_id, day, task_ids)
            return 13
        with self.transaction():
            for task_id in fresh:
                self.store.db.execute(
                    "INSERT OR IGNORE INTO favor_daily_tasks(player_id,day,task_id) VALUES (?,?,?)",
                    (player_id, day, task_id))
        logging.getLogger("x2.economy").info(
            "favor accepted player=%s day=%s kept=%s new=%s", player_id, day, kept, fresh)
        return 10

    def credit_favor_task(self, player_id, key, condition_type, hero_id, other=0, amount=1):
        """Credit one witnessed occurrence to today's accepted 心愿任务.

        Caller must already be inside a transaction (both sources - 通关结算 and 送礼
        - are). Mirrors ``_challenge_event``: these tasks have no ``task_periods`` row,
        so the dedup token lives in economy_events keyed by the local day, and the
        token is written only when some accepted task actually reads that condition.
        """
        day = day_index(int(self.clock()))
        matched = [(task_id, entry) for task_id, entry in self.favor_tasks.items()
                   if entry["track"] == "event" and entry["completeType"] == condition_type
                   and not self._excluded(entry, "value1", hero_id)
                   and not self._excluded(entry, "value2", other)]
        if not matched:
            return
        inserted = self.store.db.execute("INSERT OR IGNORE INTO economy_events VALUES (?,?)",
            (player_id, f"favortask:{day}:{key}:{condition_type}"))
        if not inserted.rowcount:
            return
        for task_id, entry in matched:
            # 只推今天接了、且还没领的那一行: 没接的任务不涨进度, 已经领过的不再涨。
            self.store.db.execute(
                "UPDATE favor_daily_tasks SET progress=MIN(?,progress+?)"
                " WHERE player_id=? AND day=? AND task_id=? AND claimed=0",
                (entry["completeNum"], amount, player_id, day, task_id))

    def claim_favor_task(self, player_id, task_id):
        """Pay one 心愿任务; returns ``(result dict, extra pushes)``.

        The result joins the generic L2C_FinishGameTask data list, and the pushes
        are the two things the page needs to repaint: the 角色页 bar
        (L2C_FavorChangeInfo, from FavorService) and the 心愿任务 list itself. The
        list matters because the client's FavorWishModule has no other refresh - a
        claimed row would otherwise stay 可领取 on screen.
        """
        day = day_index(int(self.clock()))
        result = {"code": 13, "taskId": task_id, "type": self.FAVOR_DAILY_KIND, "rewardData": b""}
        entry = self.favor_tasks.get(task_id)
        if entry is None:
            return result, ()
        row = self.store.db.execute(
            "SELECT progress,claimed FROM favor_daily_tasks"
            " WHERE player_id=? AND day=? AND task_id=?",
            (player_id, day, task_id)).fetchone()
        if not row or row[1] or row[0] < entry["completeNum"]:
            return result, ()
        extra = ()
        try:
            rewards = self.gifts([entry["gift"]])
            with self.transaction():
                rewards = self._grant(player_id, f"favortask:{day}:{task_id}", rewards)
                self.store.db.execute(
                    "UPDATE favor_daily_tasks SET claimed=1"
                    " WHERE player_id=? AND day=? AND task_id=?",
                    (player_id, day, task_id))
                if self.favor is not None:
                    extra = self.favor.grant_favor(player_id, entry["hero"], entry["favor"])
                # 心愿任务本身是每日/周常的一个条件: 通过终端完成 N 次心愿任务, 630024
                # (日, 1 次) 与 630109 (周, 12 次) 都是 E_FavorabilityDailyTask=72, 两个
                # 值列都是 [0] 即不筛维度。
                self._event(player_id, f"favortask:{day}:{task_id}",
                            self.TASK_EVENT_FAVORABILITY_DAILY_TASK, 0, 1)
                result.update(code=10, rewardData=self.reward_bytes(rewards))
        except UnresolvedEconomy:
            return result, ()
        logging.getLogger("x2.economy").info(
            "favor task claimed task=%s player=%s hero=%s rewards=%s favor=%s",
            task_id, player_id, entry["hero"], dict(sorted(rewards.items())), entry["favor"])
        pushes = tuple(extra) + (
            OutboundMessage("L2C_GameTask", self.favor_task_values(player_id, 0)),)
        return result, pushes

    def settle(self, player_id, run_uuid, section, success, section_type=0,
               outside_items=(), maze_items=(), carried_heroes=()):
        """Part of BattleService's receipt transaction, including first-clear key."""
        profile = self.section_rewards.get(section)
        config = self.reward_sections.get(section)
        run = self.store.db.execute("SELECT * FROM economy_runs WHERE uuid=?", (run_uuid,)).fetchone()
        if (section_type == 5 and run is not None and run['player_id'] == player_id
                and run['section_id'] == section and run['section_type'] == 5 and not run['settled']
                and self.entry_catalog.sections.get(section, {}).get('Type') == 5):
            # Training may echo transient battle pickups. They never become bag
            # items, relic collection unlocks, XP, DP or a main-mission clear.
            self.store.db.execute('UPDATE economy_runs SET settled=1 WHERE uuid=?', (run_uuid,))
            return self.reward_bytes({}), []
        if (profile is None or config is None or profile["section_type"] != section_type
                or run is None or run["player_id"] != player_id or run["section_id"] != section
                or run["settled"]):
            raise UnresolvedEconomy("unclassified, mismatched or settled run")
        grants, pending_instances, blocked, equipment_specs = self.runtime_drops.resolve(
            run=run, profile=profile, outside_items=outside_items, success=success)
        reward_equips: list = []
        sources = {name: [] for name in ("FIRST_CLEAR_FIXED", "NORMAL_CLEAR_FIXED",
            "RUNTIME_BATTLE_DROP", "REPORT_CURRENCY", "SWEEP_REWARD", "EXTRA_DROP",
            "COMPAT_REWARD", "EQUIP_INSTANCE", "RELIC_COLLECTION")}
        if success:
            # Relics carried out in the client's mazeItems (checkout field 12)
            # are collection unlocks, separate from outsideItems rewards.
            if len(maze_items) > 512:
                raise UnresolvedEconomy("too many mazeItems")
            for raw in maze_items:
                item = OUTSIDE_ITEM.decode(raw)
                item_id = item.get("id")
                if (self.items.get(item_id, {}).get("ItemType", {}).get("value") != 4
                        or item.get("num", 0) <= 0):
                    continue
                inserted = self.store.db.execute("""INSERT OR IGNORE INTO inventory
                    (player_id,item_id,quantity) VALUES (?,?,1)""", (player_id, item_id))
                if inserted.rowcount:
                    sources["RELIC_COLLECTION"].append({"item_id": item_id,
                        "source": "checkout mazeItems"})
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
                    # A fixed reward naming an 装备部件 (ItemType 10) is a real
                    # equipment piece (the gift row's own EquibNum says how many):
                    # materialize instances instead of parking the item forever.
                    for part_id, part_count in [entry for entry in list(local_pending.items())
                            if self.items.get(entry[0], {}).get("ItemType", {}).get("value") == 10]:
                        del local_pending[part_id]
                        catalogued = (self.equipment_factory is not None and
                                      str(part_id) in self.equipment_factory.data["equib_base"])
                        if catalogued:
                            for _ in range(part_count):
                                equipment_specs.append({"item_id": part_id, "quality": 1, "quantity": 1})
                        else:
                            pending[part_id] += part_count
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
            self.dp.equipment(player_id, config["ChapterID"], run_uuid,
                [{"star": spec["quality"], "item_id": spec["item_id"]} for spec in equipment_specs for _ in range(spec["quantity"])])
            self.dp.refresh(player_id, config["ChapterID"])
            self._event(player_id, f"clear:{run_uuid}", 3, section, 1)
            # 心愿任务 E_CarryHeroCustomsPass(11): 队伍里带着某位神格通关指定关卡。队伍来自
            # 本次 run 的 L2C_FightData(fightHeros), BattleService 解出来后随 checkout 传进来;
            # 条件是 (英雄, 关卡清单) 两个维度, 所以 section 走 value2 那一列。
            for hero_id in dict.fromkeys(carried_heroes):
                self.credit_favor_task(player_id, f"clear:{run_uuid}:{hero_id}",
                                       self.TASK_EVENT_CARRY_HERO_CUSTOMS_PASS, hero_id, section)
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
        # SectionSweepView.RefreshView 0x176dfb8 caps its quantity selector at 99.
        if type(count) is not int or not 1 <= count <= 99:
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
        self.refresh_stamina(player_id)
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
        # Explicit account fixture: expose selected challenge tiers for manual
        # testing without recording clears or consuming first-clear rewards.
        test_unlocks = {section for section in self.store.get(player_id)["snapshot"].get("test_challenge_unlocks", [])
                        if self.entry_catalog.sections.get(section, {}).get("Type") == self.MAP_TYPE_CHALLENGE}
        for section in clears | test_unlocks:
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
        # story: 星图 -> 剧情回顾 -> 主线. The client's ChapterModule keeps this
        # List<int32> and its CheckStoryOpen(id) is only `story.Contains(id)` - a
        # chapter whose id is absent is drawn locked behind the 解锁 button, and a
        # null list locks every chapter. Filling it here is what actually opens
        # 剧情回顾; the unlock reply (L2C_UnlockStory) repeats it for the row the
        # player just paid for.
        return {"mainMission": sorted(clears & self.sections.keys()), "OtherChapter": other,
                "story": self.story_ids(player_id)}

    def story_ids(self, player_id):
        """chapterIds whose 剧情回顾 has been unlocked, for ChapterModule.CheckStoryOpen.

        Deliberately NOT derived from economy_clears: the client already receives its
        own cleared list as mainMission, so a review state it could compute locally
        would not need a server field. ChapterInfo instead pairs ReviewUnlockRequest
        =1237916 (技能点, the currency StarChartsSkill spends) with ReviewUnlocAward
        =760066, i.e. a real pay-and-be-rewarded unlock, so a chapter only enters this
        list through C2L_UnlockStory - which is what the 解锁 button sends.
        """
        return sorted(row[0] for row in self.store.db.execute(
            "SELECT chapter_id FROM story_reviews WHERE player_id=? ORDER BY chapter_id",
            (player_id,)))

    def unlock_story(self, player_id, request):
        """C2L_UnlockStory (667) -> L2C_UnlockStory (668): pay 1 技能点, get 760066.

        Mirrors the client contract exactly: the reply must carry the same `story`
        list the query does, because the client stores it straight into its own
        chapter list - that reply is what makes the row just clicked replayable
        without waiting for the next query.
        """
        chapter_id = request.get("chapterId", 0)
        result = {"code": 13, "story": self.story_ids(player_id)}
        if chapter_id <= 0:
            return OutboundMessage("L2C_UnlockStory", result)
        try:
            rewards = self.gifts([self.STORY_REVIEW_AWARD])
            with self.transaction():
                if self.store.db.execute(
                        "SELECT 1 FROM story_reviews WHERE player_id=? AND chapter_id=?",
                        (player_id, chapter_id)).fetchone():
                    return OutboundMessage("L2C_UnlockStory", result)
                charged = self.store.db.execute("UPDATE inventory SET quantity=quantity-? "
                    "WHERE player_id=? AND item_id=? AND quantity>=?",
                    (self.STORY_REVIEW_UNLOCK_NUM, player_id, self.STORY_REVIEW_UNLOCK_ITEM,
                     self.STORY_REVIEW_UNLOCK_NUM))
                if not charged.rowcount:
                    return OutboundMessage("L2C_UnlockStory", result)
                self.store.db.execute("INSERT INTO story_reviews VALUES (?,?)", (player_id, chapter_id))
                rewards = self._grant(player_id, f"story:{chapter_id}", rewards)
                result.update(code=10, rewardData=self.reward_bytes(rewards))
        except UnresolvedEconomy:
            return OutboundMessage("L2C_UnlockStory", result)
        result["story"] = self.story_ids(player_id)
        logging.getLogger("x2.economy").info(
            "story review unlocked chapter=%s player=%s rewards=%s",
            chapter_id, player_id, dict(sorted(rewards.items())))
        return OutboundMessage("L2C_UnlockStory", result, pushes=self.pushes(player_id))

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
        # Keep zero rows as durable tombstones. Constructing (or discarding) a
        # push must never delete them or start an implicit SQLite transaction.
        # Repeating removal is safe; refilling the stack naturally ends it.
        from .appearance import avatar_frames
        permanent = set(avatar_frames())
        removed = [row[0] for row in self.store.db.execute(
            "SELECT item_id FROM inventory WHERE player_id=? AND quantity<=0 ORDER BY item_id", (player_id,))
            if row[0] not in permanent]
        return (LoginService.snapshot_push(self.store.get(player_id), self.store, int(self.clock())),
            OutboundMessage("L2C_ItemUpdate", {"code": 10, **self.inventory_values(player_id)}),
            *((OutboundMessage("L2C_ItemRemove", {"ids": removed}),) if removed else ()),
            *(OutboundMessage("L2C_TaskUpdate", {"type": k, "taskList": self.task_values(player_id, k)["taskList"]}) for k in (1, 2)),
            OutboundMessage("L2C_TaskUpdate", {"type": 3, "taskList": self.challenge_values(player_id)["taskList"]}),
            self.achievements.update(player_id))

    def handlers(self):
        from .bag_items import BagItemService
        from .medals import MedalService
        return {**self.world_boss.handlers(), **self.endless.handlers(), **MedalService(self).handlers(), **BagItemService(self.store, self).handlers(), **self.achievements.handlers(),
                "C2L_FetchMobilityPower": self.fetch_mobility_power,
                **{name: self.handle for name in ("C2L_ItemAll", "C2L_ItemOpt", "C2L_ShopGoods", "C2L_RefreshShop", "C2L_BuyGoods",
            "C2L_QueryGoodsInfo", "C2L_GameTask", "C2L_DailyAndWeekTask", "C2L_FinishGameTask",
            "C2L_FinishGameTaskAsync", "C2L_PickTreasureBox", "C2L_QueryMission",
            "C2L_AcceptFavorTask", "C2L_UnlockStory")}}

    async def fetch_mobility_power(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("power purchase before login")
        request = ECONOMY_SCHEMAS["C2L_FetchMobilityPower"].decode(packet.body)
        now = int(self.clock())
        day_start, _ = task_period(1, now)
        with self.transaction():
            snapshot = self.store.get(player_id)["snapshot"]
            mobility = snapshot.get("mobility")
            if not mobility:
                return OutboundMessage("L2C_FetchMobilityPower", {"result": 13})
            state = snapshot.get("power_buy") or {}
            count = int(state.get("count", 0)) if int(state.get("day", -1)) == day_start else 0
            price = self.POWER_BUY_PRICES[min(count, len(self.POWER_BUY_PRICES) - 1)]
            if snapshot.get("crystal", 0) < price:
                return OutboundMessage("L2C_FetchMobilityPower", {"result": 13})
            snapshot["crystal"] -= price
            mobility["power"] += self.POWER_BUY_AMOUNT
            snapshot["power_buy"] = {"day": day_start, "count": count + 1}
            self.save_snapshot(player_id, snapshot)
            self._event(player_id, f"power-buy:{day_start}:{count + 1}", self.TASK_EVENT_BUY_POWER, 900, 1)
        return OutboundMessage("L2C_FetchMobilityPower", {
            "result": 10,
            "rewardData": self.reward_bytes({self.POWER_BUY_ITEM: self.POWER_BUY_AMOUNT})},
            pushes=self.pushes(player_id))

    async def handle(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("economy requested before login")
        self.ensure_periods(player_id)
        name = CORE_MESSAGE_REGISTRY.name_for(packet.message_id)
        logging.getLogger("x2.economy").info("economy request %s player=%s", name, player_id)
        request = (ECONOMY_SCHEMAS if name in ECONOMY_SCHEMAS else LOBBY_SCHEMAS)[name].decode(packet.body)
        response_name = name.replace("C2L_", "L2C_", 1)
        if name == "C2L_ItemOpt":
            item_id = request.get("id", 0)
            logging.getLogger("x2.economy").info(
                "item opt player=%s item=%s opt=%s count=%s", player_id,
                item_id, request.get("opt", 0), request.get("count", 0))
            if item_id in self.CAUSALITY_CARDS:
                return self.use_causality_card(context, packet, request)
            return self.use_bag_item(context, packet, request)
        if name == "C2L_ItemAll":
            return OutboundMessage(response_name, self.inventory_values(player_id))
        if name == "C2L_QueryMission":
            return OutboundMessage(response_name, self.mission_values(player_id))
        if name == "C2L_UnlockStory":
            return self.unlock_story(player_id, request)
        if name in ("C2L_GameTask", "C2L_DailyAndWeekTask"):
            kind = request.get("type", 0)
            if kind == 12:
                return OutboundMessage("L2C_GameTask", self.endless.task_values(player_id, request.get("chapterId", 2060101)))
            if kind == 7:  # GameTaskType.CHAPTER: the DP the client's chapter gate reads
                chapter = request.get("chapterId", 0)
                values = {"code": 10, "type": kind, "chapterId": chapter,
                          "chapterTaskPoint": self.chapter_dp(player_id, chapter),
                          "chapterTaskTotalPoint": self.chapter_dp_capacity(chapter),
                          "taskList": self.dp.task_list(player_id, chapter),
                          "boxList": self.chapter_dp_boxes(player_id, chapter)}
                logging.getLogger("x2.economy").info(
                    "chapter DP served chapter=%s dp=%s/%s player=%s", chapter,
                    values["chapterTaskPoint"], values["chapterTaskTotalPoint"], player_id)
                return OutboundMessage("L2C_GameTask", values)
            if kind == self.FAVOR_DAILY_KIND:
                values = self.favor_task_values(player_id, request.get("extraType", 0),
                                                request.get("chapterId", 0))
                logging.getLogger("x2.economy").info(
                    "favor tasks served player=%s extra=%s code=%s rows=%s", player_id,
                    request.get("extraType", 0), values["code"], len(values.get("taskList", ())))
                return OutboundMessage("L2C_GameTask", values)
            return OutboundMessage("L2C_GameTask", self.task_values(player_id, kind) if kind in (1, 2)
                else self.challenge_values(player_id) if kind == 3
                else {"code": 10, "type": kind, "chapterId": request.get("chapterId", 0)})
        if name in ("C2L_FinishGameTask", "C2L_FinishGameTaskAsync"):
            requests = [FINISH_REQUEST.decode(b) for b in request.get("data", [])] if name == "C2L_FinishGameTask" else [request]
            if len(requests) > 40:
                raise ProtocolError("too many task claims")
            results, extra_pushes = [], []
            for r in requests:
                task_id, kind = r.get("taskId", 0), r.get("type", 0)
                if kind == 12:  # GameTaskType.ENDLESS: per-run objective
                    results.append(self.endless.claim(
                        player_id, task_id,
                        context.session.session_id + ":" + str(packet.header.request_id)))
                elif kind == self.CHALLENGE_KIND:
                    results.append(self.claim_challenge(player_id, task_id))
                elif kind == self.FAVOR_DAILY_KIND:
                    result, pushes = self.claim_favor_task(player_id, task_id)
                    results.append(result)
                    extra_pushes.extend(pushes)
                elif r.get("activityId"):
                    results.append({"code": 13, "taskId": task_id, "type": kind})
                else:
                    results.append(self.claim(player_id, task_id, kind))
            encoded = [FINISH_RESULT.encode(r) for r in results]
            return OutboundMessage(
                response_name,
                {"data": encoded if name == "C2L_FinishGameTask" else encoded[0]},
                pushes=tuple(extra_pushes) + tuple(self.pushes(player_id)))
        if name == "C2L_AcceptFavorTask":
            # 心愿任务的第二步(见 favor_task_values)。回包只有 code: 客户端拿到 10 之后
            # 自己重查 C2L_GameTask(type=6, extraType=0), 所以这里再推一份列表是多余的;
            # 失败码由客户端弹提示。
            code = self.accept_favor_tasks(player_id, list(request.get("taskIds", ())))
            return OutboundMessage(response_name, {"code": code})
        if name == "C2L_ShopGoods":
            shop = request.get("shopId", 0)
            # Client 2.4 dereferences a null goods list on success. With no fully
            # confirmed goods, reject the query before that success-only path.
            return OutboundMessage(response_name, {"code": 13, "shopId": shop})
        if name == "C2L_PickTreasureBox":
            logging.getLogger("x2.economy").info(
                "pick treasure box player=%s type=%s box=%s param=%s activity=%s",
                player_id, request.get("type", 0), request.get("boxId", -1),
                request.get("param", 0), request.get("activityId", 0))
            if request.get("type", 0) == self.CHALLENGE_KIND:
                return self.pick_challenge_box(player_id, request.get("boxId", -1),
                                               request.get("param", 0), wire=True)
            if request.get("type", 0) == self.CHAPTER_DP_KIND:
                return self.pick_chapter_dp_box(player_id, request)
            return self.pick_treasure_box(player_id, request)
        # Known shop routes reply explicitly, never time out or charge for unknown data.
        return OutboundMessage(response_name, {"code": 13, **{k: v for k, v in request.items() if k in ("shopId", "goodsId", "buyNum")}})

    def use_bag_item(self, context, packet, request):
        """Use any bag item whose Item.Used column names recoverable Gift groups.

        礼物盒/经验卡/宝箱 (ItemType 14/18) carry ``Used`` -> Gift groups: fixed
        Canonical groups resolve in full. An invalid group rolls back the whole
        use; never charge for a partially reconstructed box.
        """
        player_id = context.session.player_id
        item_id, count = request.get("id", 0), request.get("count", 0)
        rejected = OutboundMessage("L2C_ItemOpt", {"code": 13, "opt": request.get("opt", 0), "itemId": item_id})
        if (request.get("opt", 0) != 0 or type(count) is not int or not 1 <= count <= 999
                or item_id not in self.items):
            return rejected
        used_groups = self.items[item_id].get("Used") or []
        if not used_groups:
            return rejected
        key = hashlib.sha256(f"{player_id}:{context.session.session_id}:{packet.header.request_id}:item-opt".encode()
                             + packet.body).hexdigest()
        try:
            with self.transaction():
                row = self.store.db.execute("SELECT response FROM item_opt_receipts WHERE request_key=? AND player_id=?",
                                            (key, player_id)).fetchone()
                if row:
                    from .bag_items import bag_pushes
                    return OutboundMessage("L2C_ItemOpt", ECONOMY_SCHEMAS["L2C_ItemOpt"].decode(row[0]),
                                           before_response=bag_pushes(self, player_id))
                charged = self.store.db.execute("UPDATE inventory SET quantity=quantity-? "
                    "WHERE player_id=? AND item_id=? AND quantity>=?", (count, player_id, item_id, count))
                if not charged.rowcount:
                    return rejected
                rewards = Counter()
                from .bag_items import resolve_bag_gifts, grant_bag_rewards
                for _ in range(count):
                    rewards.update(resolve_bag_gifts(self, item_id, used_groups,
                        request.get("selectedItemIndexList", [])))
                # Canonical random Gifts can intentionally draw zero. Preserve
                # that outcome rather than rolling back into a free reroll.
                reward_data = grant_bag_rewards(self, player_id, f"item-opt:{key}", rewards, item_id)
                values = {"code": 10, "opt": 0, "itemId": item_id,
                          "rewardData": reward_data}
                self.store.db.execute("INSERT INTO item_opt_receipts VALUES (?,?,?)",
                                      (key, player_id, ECONOMY_SCHEMAS["L2C_ItemOpt"].encode(values)))
        except UnresolvedEconomy as exc:
            logging.getLogger("x2.economy").info("item use rejected item=%s player=%s reason=%s", item_id, player_id, exc)
            return rejected
        from .bag_items import bag_pushes
        return OutboundMessage("L2C_ItemOpt", values, before_response=bag_pushes(self, player_id))

    def use_causality_card(self, context, packet, request):
        player_id = context.session.player_id
        item_id, count = request.get("id", 0), request.get("count", 0)
        rejected = OutboundMessage("L2C_ItemOpt", {"code": 13, "opt": request.get("opt", 0), "itemId": item_id})
        if (request.get("opt", 0) != 0 or item_id not in self.CAUSALITY_CARDS
                or type(count) is not int or not 1 <= count <= 999):
            return rejected
        key = hashlib.sha256(f"{player_id}:{context.session.session_id}:{packet.header.request_id}:item-opt".encode()
                             + packet.body).hexdigest()
        try:
            return self._use_causality_card(player_id, item_id, count, key, rejected)
        except UnresolvedEconomy:
            return rejected

    def _use_causality_card(self, player_id, item_id, count, key, rejected):
        with self.transaction():
            row = self.store.db.execute("SELECT response FROM item_opt_receipts WHERE request_key=? AND player_id=?",
                                        (key, player_id)).fetchone()
            if row:
                return OutboundMessage("L2C_ItemOpt", ECONOMY_SCHEMAS["L2C_ItemOpt"].decode(row[0]),
                                       pushes=self.pushes(player_id))
            consumed = self.store.db.execute("UPDATE inventory SET quantity=quantity-? "
                "WHERE player_id=? AND item_id=? AND quantity>=?", (count, player_id, item_id, count))
            if not consumed.rowcount:
                return rejected
            amount = self.CAUSALITY_CARDS[item_id] * count
            self.refresh_stamina(player_id)
            rewards = self._grant(player_id, f"item-opt:{key}", {1237900: amount})
            values = {"code": 10, "opt": 0, "itemId": item_id,
                      "rewardData": self.reward_bytes(rewards)}
            self.store.db.execute("INSERT INTO item_opt_receipts VALUES (?,?,?)",
                                  (key, player_id, ECONOMY_SCHEMAS["L2C_ItemOpt"].encode(values)))
        return OutboundMessage("L2C_ItemOpt", values, pushes=self.pushes(player_id))
