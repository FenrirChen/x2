"""Confirmed rewards and tasks with the user-defined Revival calendar."""
from collections import Counter
import hashlib
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
from .activity_daily_tasks import task_open as activity_daily_open, repair as repair_activity_daily
from .transactions import transaction
from .battle_entry import BattleEntryCatalog
from .equipment_factory import EquipmentInstanceFactory, materialize_instances
from .reward_system import (ReportCurrencyResolver, RewardGrant, RuntimeDropResolver,
                            SectionRewardCatalog, audit_grants, sum_grants)
from x2server.messages.equipment import EQUIP_PARAM, HERO_EQUIP


class UnresolvedEconomy(ValueError):
    """The entire operation must be withheld, never partially granted."""



class EconomyService:
    CAUSALITY_CARDS = {1202010: 10, 1202011: 20, 1202012: 30,
                       1202013: 60, 1202014: 100}  # Item.Used -> Gift.Num
    # 神格碎片「转化」的兑出货币: Item.Return[0] is a table/CurrencyType TpyeId and
    # that row's ItemID is the item that actually lands in the bag. Only the
    # currency this route really pays is listed; an unknown type is refused rather
    # than guessed. 927 = E_FragmentMoney -> 1237927 神笺 (login.py serves it as
    # BaseInfo field 66, FragmentMoney).
    RETURN_CURRENCY_ITEMS = {927: 1237927}
    # 背包-分解「分解」的兑出货币: Item.Recover[0] is likewise a table/CurrencyType
    # TpyeId and that row's ItemID is the item that lands in the bag. Only the two
    # fragment currencies this route really pays are listed (the gems and 宝石姬 it
    # decomposes, both ItemType 11); an unknown type is refused rather than guessed.
    # 904 = E_BaoShi -> 1237904 宝石碎片, 905 = E_BaoShiJi -> 1237905 宝石姬碎片.
    # Equipment (ItemType 10) carries Recover [906, 1] as well, but equips are
    # reclaimed through C2L_EquipReclaim / BagModule_RecycleEquips, not this op.
    RECOVER_CURRENCY_ITEMS = {904: 1237904, 905: 1237905}
    POWER_RECOVER_SECONDS = 225  # Client ServerData default 300s; user policy: 25% faster.
    # Item.EffData -> BaseInfoProto; only supported currency destinations.
    CURRENCIES = {1237901: "gold", 1237902: "crystal", 1237906: "equip_exp", 1237907: "hero_exp",
                  1237908: "exp", 1237910: "daily_activity", 1237911: "week_activity"}
    STACKABLE_REWARD_TYPES = frozenset((5, 12, 13, 14, 17, 18, 20, 22, 23, 24, 25, 26, 33, 34, 36, 37, 38, 39, 40, 41, 42, 43))
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
    TASK_EVENT_HERO_ADVENTURE = 16     # E_HeroAdventure
    TASK_EVENT_HERO_TRAIN = 17         # E_HeroTrain: 光之密室神格训练次数
    TASK_EVENT_HERO_INTERACTIVE = 19   # E_HeroInteractive
    TASK_EVENT_BUY_GOOD = 24           # E_BuyGood
    TASK_EVENT_ACCOUNT_LEVEL = 43      # E_AccountLevel: progress is the player's level
    TASK_EVENT_HERO_REACH_STAR_LEVEL = 44  # E_HeroReachStarAndLevel: 达标的英雄数
    TASK_EVENT_WISH = 45               # E_Wish
    TASK_EVENT_ITEM_STAR_ID = 47       # E_ItemStarAndID: 已拥有的清单内道具数
    TASK_EVENT_BASE_BLESS = 48         # E_BaseBless: 奇迹祈神次数
    TASK_EVENT_EQUIP_EQUIP = 49        # E_EquipEquip
    TASK_EVENT_LOGIN_DAY = 58          # E_LoginDay: one per local day the player logs in
    TASK_EVENT_FAVORABILITY_LEVEL = 73  # E_FavorabilityLevel: 好感等级达标的英雄数
    # 炼金实验室 的两条日常/周常条件 (economy_catalog.json task_conditions):
    #   630027/630113「完成 N 次交易」 E_AlchemyDealTask=75
    #   630028/630114「完成 N 次任务」 E_AlchemyQuestTask=76
    # 由 player/college_alchemy.py 的 598 AlchemyFinish 成交路径记录。
    TASK_EVENT_ALCHEMY_DEAL = 75       # E_AlchemyDealTask: 完成交易次数
    TASK_EVENT_ALCHEMY_QUEST = 76      # E_AlchemyQuestTask: 完成任务次数
    TASK_EVENT_CUSTOMS_ENTRY = 87      # E_CustomsEntry
    TASK_EVENT_KILL_MONSTER_TYPE = 2   # E_KillMonsterType: 击杀累计，value 是 UnitBase.UnitType
    # 成就 662710/662720/662730「累计击败 普通/精英/BOSS 怪物」的计数器。击杀上报
    # 只带 UnitType（battle.py 的 kills:{uuid}:type:{kind}），而 achievement_events 按
    # event_type 汇总，所以镜像时把 UnitType 拆成三个互不相同的成就事件号。
    # 类别取自 UnitBase：2=Monster(普通, 244/298 在 unit/Monster)、3=Monster(精英)、
    # 4=BOSS(352/375 在 unit/BOSS)。
    ACHV_EVENT_KILL = {2: 622710, 3: 622720, 4: 622730}
    # Internal counters keep achievement sources narrower than shared task types.
    ACHV_EVENT_COLLEGE_EXPLORE = 622310
    ACHV_EVENT_SUPPLY_PURCHASE = 622700
    # 成就 662300「在炼金实验室中，收获金币数量达到 N」: 这条条件的量是**金币数**而不是
    # 次数, 客户端 E_ 枚举里没有对应项。自定一个只喂这条成就的 event_type, 数字沿用客户端
    # 的成就条件号 622300 (与 E_ 枚举的小整数不会撞号)。生产者见 player/college_alchemy.py
    # 的 _trade 成交路径, amount = 本单实际发出的金币。
    ACHV_EVENT_ALCHEMY_GOLD = 622300
    # 成就 660010「累计获得友情点 N 点」: E_ 枚举里 71 (E_GiveFriendCoin) 的语义只是
    # 「赠送」, 那一条要留给每日任务 630023, 收取友情点不能再记 71, 否则会被顶掉。所以
    # 自定事件号沿用成就条件号620010；统一_grant按实际入账点数记录，
    # 覆盖赠收与其他发奖来源，不与每日赠送次数重复计数。
    ACHV_EVENT_FRIEND_COIN = 620010
    # GameTaskType.CHALLENGE: 60 tasks in 10 groups, no period, no rollover.
    CHALLENGE_KIND = 3
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
    # 首充奖品: GameActivity 100001 的 RegistrationGift = [783023] (离线端 router.cpp:4330
    # 同源)。FirstRechargePage_Init 正是读这一行的 RegistrationGift 展开成展示列表,
    # 所以「领取」必须真发这一组 (原版奖励, 不做替换), 否则玩家看到列表却拿不到东西。
    FIRST_RECHARGE_GIFT = 783023
    # 购买因果 (134/137) 的成交价 —— 2026-10-31 修复: 必须与页面显示价同源。
    # 显示价是客户端自己算的: PowerModule_GetPrice (0x015C4F3C) 读
    # MainModule_ServerData 的 PowerPrice / PowerTimesInterval (由
    # L2C_ServerTableConfig 下发), 缺省值 (ServerData..ctor 0x13CD7D0) 是
    # [60,60,60,60,60] 与 {1,2,4,6,10} → 每一档都显示 60。
    # 旧的 20 档阶梯 (20/20/40/60/80/…/220/…/1000) 与显示价不符: 第 5 次起就比
    # 显示价贵, 第 10 次 220、第 20 次 1000 —— 玩家看到的正是「写着 60 实际扣得
    # 更多, 买超过 10 次才明显, 一次扣了一千多」。现在固定 60, 并把同一组表
    # 由 server_config (login.py) 下发给客户端, 显示价 == 扣费。
    POWER_BUY_PRICES = (60, 60, 60, 60, 60)
    POWER_BUY_INTERVALS = (1, 2, 4, 6, 10)

    def __init__(self, store, clock=time.time, *, resource_double_drop=False):
        self.store = store
        self.clock = clock
        # Eligibility, official resource targets and quotas are governed by
        # the same activity 71004 controller advertised in QueryActivity.
        self.resource_double_drop = bool(resource_double_drop)
        self.catalog = json.loads(files("x2server").joinpath("data/economy_catalog.json").read_text(encoding="utf-8"))
        # 挑战任务 (ChallengeTask): 60 rows in 10 groups of 6, keyed to the client's
        # own ChallengeTask/TaskCondition tables. Boxes 1..10 are the group ids.
        challenge_path = files("x2server").joinpath("data/challenge_tasks.json")
        challenge = (json.loads(challenge_path.read_text(encoding="utf-8"))
                     if challenge_path.is_file() else None)
        self.challenge_tasks = {int(k): v for k, v in (challenge or {}).get("tasks", {}).items()}
        self.challenge_boxes = {int(k): v for k, v in (challenge or {}).get("boxes", {}).items()}
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
        # Item.Return is the 「转化」 rate: [currencyType, amount] per item. The
        # curated economy_catalog has it for the chips it happens to list, while
        # the reward_items export carries no Return column at all (1201041, client
        # Return [927, 5], only exists there), so restore the whole column from its
        # own export, exactly like Item.Used above. Without it an exchange on such
        # a chip is refused as "no rate".
        return_path = files("x2server").joinpath("data/item_return_catalog.json")
        if return_path.is_file():
            returned = json.loads(return_path.read_text(encoding="utf-8"))["items"]
            for row in self.catalog["items"]:
                entry = returned.get(str(row["ItemID"]))
                if entry and not row.get("Return"):
                    row["Return"] = entry
        # Item.Recover is the 背包-分解 rate: [currencyType, amount] per item, paid as
        # `amount` copies of the currency whose CurrencyType TpyeId == currencyType.
        # The client draws the page's preview straight from this column, so the server
        # has to settle from it too (BagDecomposePage_RefreshCurrency 0x19A6354 reads
        # Item+0x78, takes [0] as the type and [1] as the per-item amount, and
        # multiplies by the entered count). The gems and 宝石姬 the page decomposes are
        # not in the curated economy_catalog at all (only 1250011 is, and the bag list
        # never needs them: inventory_values serves the ids the client's own table
        # renders), so the rate is keyed off its own export instead of a column on
        # self.items.
        recover_path = files("x2server").joinpath("data/item_recover_catalog.json")
        self.recover_items = ({int(k): list(v) for k, v in
            json.loads(recover_path.read_text(encoding="utf-8"))["items"].items()}
            if recover_path.is_file() else {})
        # Item.FunctionEff == E_AutoUsed(7): the row is a receipt for its
        # Item.EffData Gift group and opens the moment it is acquired. It carries
        # no Item.Used, so the client can never open it and _grant would otherwise
        # park a dead receipt in the bag (e.g. the red packet's 光能 receipts).
        # reward_items omits FunctionEff/EffData, so restore the links from their
        # own catalog, mirroring item_used_catalog above.
        auto_path = files("x2server").joinpath("data/item_auto_used_catalog.json")
        auto_used = json.loads(auto_path.read_text(encoding="utf-8")) if auto_path.is_file() else {}
        self.auto_used_items = {int(k): list(v) for k, v in auto_used.get("items", {}).items()}
        # 凭据自己写明的星级: 6★随机兽主 (1203023) 的客户端描述就写死「必定获得一件6★兽主」,
        # 而它的 Gift 组只给部位 type_id, 星级只能作为数据记下来, 由 receipt 自己决定。
        self.receipt_stars = {int(k): int(v) for k, v in auto_used.get("stars", {}).items()}
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
            # 首充领取状态: 0=未充过 1=可领取 2=已领取 (客户端 L2C_QueryFirstReCharge.state)。
            store.db.execute("""CREATE TABLE IF NOT EXISTS recharge_first (
                player_id INTEGER NOT NULL PRIMARY KEY, state INTEGER NOT NULL DEFAULT 0)""")
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
            # Server-owned quota survives archive import; one row per account.
            store.db.execute("""CREATE TABLE IF NOT EXISTS server_sweep_limits (
                player_id INTEGER PRIMARY KEY, day INTEGER NOT NULL,
                used INTEGER NOT NULL CHECK(used>=0 AND used<=30))""")
            sweep_schema = store.db.execute("SELECT sql FROM sqlite_master WHERE name='server_sweep_limits'").fetchone()[0]
            if 'used<=15' in sweep_schema.replace(' ', '').replace('\n', ''):
                # Atomic migration: preserve today's usage, never reset quota.
                store.db.execute('SAVEPOINT sweep_quota_upgrade')
                try:
                    store.db.execute("""CREATE TABLE server_sweep_limits_v30 (
                        player_id INTEGER PRIMARY KEY, day INTEGER NOT NULL,
                        used INTEGER NOT NULL CHECK(used>=0 AND used<=30))""")
                    store.db.execute('INSERT INTO server_sweep_limits_v30 SELECT * FROM server_sweep_limits')
                    store.db.execute('DROP TABLE server_sweep_limits')
                    store.db.execute('ALTER TABLE server_sweep_limits_v30 RENAME TO server_sweep_limits')
                except BaseException:
                    store.db.execute('ROLLBACK TO sweep_quota_upgrade')
                    store.db.execute('RELEASE sweep_quota_upgrade')
                    raise
                else:
                    store.db.execute('RELEASE sweep_quota_upgrade')
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
        # 星之特权 (特别课程 100002) 与 积分活动 (100000), 另加献祭福利 (100003) 与
        # 自选三星 (100005)。只依赖 store, 自建领取状态表并真发货 (见 player/extra_activity.py)。
        from .extra_activity import ExtraActivityService
        self.extra_activity = ExtraActivityService(self)
        from .season import SeasonService
        self.season = SeasonService(self)
        from .terminal_wish import TerminalWishService
        self.terminal_wish = TerminalWishService(self)
        from .moon import MoonService
        self.moon = MoonService(self)
        # 降临纪念 / 累计登录 (100004): 按创号时刻判天数门槛并真发货 (见 player/total_login.py)。
        from .total_login import TotalLoginService
        self.total_login = TotalLoginService(self)
        from .element_compose import ElementComposeService
        self.element_compose = ElementComposeService(self)
        from .pending_delivery import recover
        for row in store.db.execute("SELECT id FROM players").fetchall():
            recover(self, row[0])
            from .bag_items import recover_hero_boxes
            recover_hero_boxes(self, row[0])
        # Counts live in the existing exported activity_state table.
        from .extra_drop import ExtraDropService
        self.extra_drop = ExtraDropService(self, enabled=self.resource_double_drop)

    def transaction(self):
        return transaction(self.store.db)

    def ensure_periods(self, player_id):
        """Lazy rollover at login or the first online operation after a boundary."""
        db = self.store.db
        starts = tuple(task_period(k, int(self.clock()))[0] for k in (1, 2))
        cache = getattr(self, '_task_period_checks', None)
        if cache is None:
            self._task_period_checks = cache = {}
        # Cache only a completed consistency check, not task progress. SQLite's
        # data_version invalidates external imports/admin writes; total_changes
        # invalidates local writes. Never reuse/store a check inside a transaction
        # that could still roll back. Clock boundaries are part of the key.
        def version():
            return (db.total_changes, db.execute('PRAGMA data_version').fetchone()[0], starts)
        if not db.in_transaction and cache.get(player_id) == version():
            return
        with self.transaction():
            snapshot = self.store.get(player_id)["snapshot"]
            changed = False
            for kind, field in ((1, "daily_activity"), (2, "week_activity")):
                start, end = task_period(kind, int(self.clock()))
                previous = self.store.db.execute("SELECT start,end FROM task_periods WHERE player_id=? AND kind=?", (player_id, kind)).fetchone()
                if previous and previous[0] >= start:
                    # Read live state once; never cache player progress across
                    # imports/rollovers, and never rewrite unchanged rows.
                    current = {r[0]: (r[1], r[2]) for r in self.store.db.execute(
                        'SELECT task_id,progress,claimed FROM economy_tasks WHERE player_id=?', (player_id,))}
                    prefix = f'task:{kind}:{previous[0]}:'
                    grants = {r[0] for r in self.store.db.execute(
                        'SELECT source FROM economy_grants WHERE player_id=? AND source>=? AND source<?',
                        (player_id, prefix, prefix + '\uffff'))}
                    missing, updates = [], []
                    for task_id, task in self.tasks.items():
                        if task['RefreshCycle']['value'] != kind or task['AcceptLevel'] > snapshot['level']:
                            continue
                        row = current.get(task_id)
                        if row is None:
                            missing.append((player_id, task_id))
                        progress, claimed = row or (0, 0)
                        claimed_new = int(bool(claimed) or prefix + str(task_id) in grants)
                        target = self.catalog['task_conditions'][str(task_id)]['CompleteNum']
                        progress_new = max(progress, target if claimed_new else 0)
                        if (progress_new, claimed_new) != (progress, claimed):
                            updates.append((progress_new, claimed_new, player_id, task_id))
                    self.store.db.executemany('INSERT OR IGNORE INTO economy_tasks(player_id,task_id) VALUES (?,?)', missing)
                    self.store.db.executemany('UPDATE economy_tasks SET progress=?,claimed=? WHERE player_id=? AND task_id=?', updates)
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

        if not db.in_transaction:
            if len(cache) >= 256 and player_id not in cache:
                cache.pop(next(iter(cache)))
            cache[player_id] = version()

    def login_event(self, player_id):
        from .bag_items import recover_hero_boxes
        recover_hero_boxes(self, player_id)
        # 老版本把 FE7 凭据原样入库 (807 社团宝箱/6★随机兽主), 玩家手里那张凭据点不开;
        # 登录时按凭据自己的礼包内容补开一次 (幂等)。equipAll/itemAll 都在本调用之后
        # 取值, 所以补出来的实例和道具会照常出现在本次登录响应里。
        self.repair_parked_receipts(player_id)
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

    def expand_auto_used(self, rewards):
        """Convert Item.FunctionEff == E_AutoUsed(7) receipts into their Gift.

        The receipt row is a wrapper: it exposes no Item.Used, so the client can
        never open it and a stored receipt loses the reward entirely (the red
        packet's 光能 receipts). Resolve each receipt through the
        same ``gifts`` path a manual box uses, recursively, because a receipt may
        itself yield another receipt. A group that is not recovered yet keeps its
        receipt untouched rather than silently dropping the reward.
        """
        resolved = Counter()
        for item, count in rewards.items():
            groups = self.auto_used_items.get(item)
            if not groups:
                resolved[item] += count
                continue
            try:
                contents = self.gifts(groups, allow_daily_random=True)
            except UnresolvedEconomy:
                resolved[item] += count
                continue
            for produced, amount in self.expand_auto_used(contents).items():
                resolved[produced] += amount * count
        return resolved

    def grant_auto_used_receipt(self, player_id, source, rewards, star=None):
        """Open an E_AutoUsed receipt on the spot and deliver what its Gift names.

        A receipt carries no Item.Used, so the client can never open it: parking one in
        the bag is exactly the "paid, nothing arrived" report (club shop 807's 社团宝箱
        1203022 and 6★随机兽主 1203023). Call inside the owner's transaction. Stacked and
        currency destinations go through ``_grant`` as usual; an equipment destination
        (ItemType 10) needs an instance, so it is materialized at the star the receipt
        itself states - without that evidence the purchase refuses instead of handing the
        player a dead receipt. Returns (granted rewards, rewardEquip bytes).
        """
        # Shop retries use their persisted response before reaching this helper.
        # Never reroll random equipment under an already committed grant source.
        if self.store.db.execute('SELECT 1 FROM economy_grants WHERE player_id=? AND source=?',
                                 (player_id, source)).fetchone():
            raise UnresolvedEconomy('automatic receipt source already delivered')
        deferred, contents = Counter(), Counter()
        for item, count in rewards.items():
            # One draw per copy: each receipt is opened on its own, so two copies of a
            # blind box are two outcomes, not one outcome paid twice.
            for _ in range(count):
                for produced, amount in self.gifts(self.auto_used_items[item],
                        deferred=deferred, allow_daily_random=True).items():
                    contents[produced] += amount
        specs = []
        for item, amount in deferred.items():
            if not self.equipment_factory.is_drop_equipment(item):
                # No EquibBase row: hand it back to _grant, which rejects a destination
                # with nowhere to go rather than guessing one here.
                contents[item] += amount
                continue
            if type(star) is not int:
                raise UnresolvedEconomy(f"receipt equipment {item} lacks star evidence")
            while amount:
                chunk = min(amount, 99)
                specs.append({"item_id": item, "star": star, "quantity": chunk})
                amount -= chunk
        granted = self._grant(player_id, source, contents)
        equips = self.materialize_equipment(player_id, source, specs)
        logging.getLogger("x2.economy").info(
            "auto-used receipt opened player=%s source=%s rewards=%s equips=%s",
            player_id, source, dict(granted), len(equips))
        return granted, tuple(equips)

    def repair_parked_receipts(self, player_id):
        """Open the E_AutoUsed receipts a pre-fix purchase parked in the bag (idempotent).

        Before the club-shop fix, buying 807's 社团宝箱/6★随机兽主 stored the receipt
        itself, so an affected player still holds one dead receipt they can never open.
        Open it once at login, using the receipt's own star evidence. A receipt whose
        contents cannot be fully delivered is left exactly as it is - a repair must never
        make an already-delivered reward smaller.
        """
        rows = self.store.db.execute(
            "SELECT item_id,quantity FROM inventory WHERE player_id=? AND quantity>0",
            (player_id,)).fetchall()
        for item_id, quantity in rows:
            if item_id not in self.auto_used_items:
                continue
            source = f"receipt-repair:{player_id}:{item_id}"
            if self.store.db.execute("SELECT 1 FROM economy_grants WHERE player_id=? AND source=?",
                                     (player_id, source)).fetchone():
                # 该账号这一项已经补过一次: 再出现的凭据按原样保留, 不猜、不重复发。
                logging.getLogger("x2.economy").info(
                    "parked receipt kept player=%s item=%s reason=already repaired",
                    player_id, item_id)
                continue
            try:
                with self.transaction():
                    opened, equips = self.grant_auto_used_receipt(player_id, source,
                        {item_id: quantity}, self.receipt_stars.get(item_id))
                    removed = self.store.db.execute("UPDATE inventory SET quantity=quantity-? "
                        "WHERE player_id=? AND item_id=? AND quantity>=?",
                        (quantity, player_id, item_id, quantity))
                    if not removed.rowcount:
                        # 计数在读取与扣减之间变了: 整笔回滚, 下次登录再看。
                        raise UnresolvedEconomy("parked receipt count changed mid-repair")
            except UnresolvedEconomy as exc:
                logging.getLogger("x2.economy").info(
                    "parked receipt kept player=%s item=%s reason=%s", player_id, item_id, exc)
                continue
            logging.getLogger("x2.economy").info(
                "parked receipt repaired player=%s item=%s x%s rewards=%s equips=%s",
                player_id, item_id, quantity, dict(opened), len(equips))

    def _grant(self, player_id, source, rewards, *, stackable_types=()):
        """Called inside the owner's transaction; never commits independently."""
        existing = self.store.db.execute("SELECT rewards FROM economy_grants WHERE player_id=? AND source=?",
                                         (player_id, source)).fetchone()
        if existing:
            return {int(i): n for i, n in json.loads(existing[0]).items()}
        if self.auto_used_items and any(item in self.auto_used_items for item in rewards):
            rewards = self.expand_auto_used(rewards)
        from .daily_pickups import capped_pickups
        rewards = capped_pickups(self, player_id, source, rewards)
        if getattr(self, "moon", None):
            rewards = self.moon.accept_reward(player_id, source, rewards)
        if getattr(self, "season", None):
            rewards = self.season.accept_reward(player_id, source, rewards)
        if getattr(self,'endless',None):
            rewards=self.endless.battle_rewards(player_id,source,rewards)
        from .friend_currency import capped_rewards
        rewards = capped_rewards(self.store, player_id, rewards)
        player = self.store.get(player_id)
        snapshot = player["snapshot"]
        for item, count in rewards.items():
            if type(count) is not int or count <= 0 or item not in self.items:
                raise UnresolvedEconomy("invalid reward")
            kind = self.items[item].get("ItemType", {}).get("value")
            if self.season.active(player_id) and item in (self.season.EXP_ITEM, self.season.POINT_ITEM, self.season.ACTIVE_ITEM):
                continue  # Already consumed by the period-scoped season ledger.
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
        if rewards.get(1237917) and getattr(self,'achievements',None):
            self.achievements.record(player_id,'friendcoin:'+source,
                                     self.ACHV_EVENT_FRIEND_COIN,rewards[1237917])
        return rewards

    def materialize_equipment(self, player_id, run_uuid, specs):
        """Roll and persist the specs' equipment instances; returns wire-ready HeroEquip bytes.

        与本地同名实现一致: 逐条 spec 用 materialize_instances 落库 (marker 幂等),
        再把实例编码成客户端 rewardData.rewardEquip 认的 HeroEquip 字节。活动中心
        (player/extra_activity.py) 发货时用它接住 ItemType 10 的奖励 —— 裸 1240xxx id
        直接进奖励列表会让客户端断线, 只能作为实例落地再经 rewardEquip 下发。
        """
        equips, ordinal = [], 0
        for spec in specs:
            instances = materialize_instances(self.store.db, player_id, spec["item_id"],
                                              spec["star"], spec["quantity"], run_uuid,
                                              self.equipment_factory, ordinal)
            ordinal += spec["quantity"]
            for instance in instances:
                wire = {k: v for k, v in instance.items() if k != "marker"}
                equips.append(HERO_EQUIP.encode({**wire, "param": EQUIP_PARAM.encode(instance["param"])}))
        if equips:
            logging.getLogger("x2.economy").info(
                "equipment instances materialized run=%s player=%s equips=%s",
                run_uuid, player_id,
                [(e["id"], e["typeId"], e["star"]) for e in (HERO_EQUIP.decode(b) for b in equips)])
        return equips

    def inventory_values(self, player_id):
        from .friend_currency import repair
        repair(self.store, player_id)
        from .appearance import avatar_frames
        items = dict(self.store.db.execute("SELECT item_id,quantity FROM inventory WHERE player_id=? AND quantity>0", (player_id,)))
        for frame in avatar_frames():
            items[frame] = max(1, items.get(frame, 0))
        activity = getattr(self, 'activity', None)
        day_counts = activity.gameplay_day_counts(player_id) if activity else {}
        for item, count in day_counts.items():
            if count:
                items.setdefault(item, 0)  # Used gifts still carry their daily acquisition count.
        return {"items": [ITEM.encode({"id": r[0], "num": r[1], "locked": False, "dayGet": day_counts.get(r[0], 0)})
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
            current = dict(self.store.db.execute('SELECT task_id,progress FROM economy_tasks WHERE player_id=?', (player_id,)))
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
                row = (current[task_id],) if task_id in current else None
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
        current = {r[0]: (r[1],r[2]) for r in self.store.db.execute(
            'SELECT task_id,progress,claimed FROM economy_tasks WHERE player_id=?', (player_id,))}
        groups = {}
        for tid, entry in self.challenge_tasks.items():
            groups.setdefault(entry['group'], []).append(tid)
        done_groups = {g for g, ids in groups.items() if ids and all(current.get(tid,(0,0))[1] == 1 for tid in ids)}
        tasks = []
        for task_id, entry in sorted(self.challenge_tasks.items()):
            progress, claimed = current.get(task_id, (0, 0))
            target = entry["completeNum"]
            tasks.append(TASK.encode({"taskId": task_id,
                "taskStatus": 4 if claimed else 3 if progress >= target else 2,
                "taskProgress": min(progress, target), "taskRefreshTime": 0,
                "finishTimes": int(bool(claimed)), "stage": 0}))
        picked = {r[0] for r in self.store.db.execute(
            "SELECT box_id FROM task_boxes WHERE player_id=? AND kind=?", (player_id, self.CHALLENGE_KIND))}
        boxes = [TREASURE_BOX.encode({"boxId": group, "activityId": 0,
            "pickStatus": 2 if group in picked else 1 if group in done_groups else 0})
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
            extra.append(OutboundMessage("L2C_HeroUpdate", {"code": 10, "heros": [encode_hero_data(h, season=self.season, player_id=player_id) for h in self.store.get(player_id)["snapshot"]["heroes"]]}))
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
        if kind == 1:
            repair_activity_daily(self, player_id)
        level = self.store.get(player_id)["snapshot"]["level"]
        current = {r[0]: (r[1],r[2]) for r in self.store.db.execute(
            'SELECT task_id,progress,claimed FROM economy_tasks WHERE player_id=?', (player_id,))}
        period = self.store.db.execute('SELECT end FROM task_periods WHERE player_id=? AND kind=?',
                                       (player_id, kind)).fetchone()
        result = []
        for task_id, task in self.tasks.items():
            if (task["RefreshCycle"]["value"] != kind or task["AcceptLevel"] > level
                    or not activity_daily_open(self, task_id)):
                continue
            row = current.get(task_id)
            if row is None:
                continue
            progress, claimed = row
            period_end = period[0]
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
        if getattr(self, 'terminal_wish', None):
            self.terminal_wish.event(player_id, key, condition_type, value, amount, value2)
        if getattr(self, "season", None):
            self.season.event(player_id, key, condition_type, value, amount, value2)
        activity = getattr(self, 'activity', None)
        if activity:
            period = None
            if key.startswith(('entry:', 'clear:', 'kills:', 'power:')):
                period = activity.rotation.run_period(player_id, key.split(':')[1])
            activity.event(player_id, key, condition_type, value, amount, value2, period=period)
        self.ensure_periods(player_id)
        active_kinds = set()
        for row in self.store.db.execute("SELECT kind,start FROM task_periods WHERE player_id=?", (player_id,)).fetchall():
            inserted = self.store.db.execute("INSERT OR IGNORE INTO economy_events VALUES (?,?)", (player_id, f"{row[0]}:{row[1]}:{key}"))
            if inserted.rowcount:
                active_kinds.add(row[0])
        level = self.store.get(player_id)["snapshot"]["level"]
        for task_id, task in self.tasks.items():
            condition = self.catalog["task_conditions"][str(task_id)]
            if (task["RefreshCycle"]["value"] not in active_kinds or task["AcceptLevel"] > level
                    or not activity_daily_open(self, task_id) or condition["CompleteType"]["value"] != condition_type
                    or condition.get("CompleteValue1", [0]) not in ([0], []) and value not in condition["CompleteValue1"]
                    or condition_type != 6 and condition.get("CompleteValue2", [0]) not in ([0], [])
                    and value2 not in condition["CompleteValue2"]):
                continue
            self.store.db.execute("UPDATE economy_tasks SET progress=MIN(?,progress+?) WHERE player_id=? AND task_id=?",
                (condition["CompleteNum"], amount, player_id, task_id))
        self._challenge_event(player_id, key, condition_type, value, amount, value2)
        # Stable battle/job/order IDs are lifetime occurrences, even across midnight.
        achv_event = condition_type
        if condition_type == self.TASK_EVENT_KILL_MONSTER_TYPE:
            achv_event = self.ACHV_EVENT_KILL.get(value, 0)
        elif condition_type == self.TASK_EVENT_HERO_ADVENTURE:
            achv_event = self.ACHV_EVENT_COLLEGE_EXPLORE if key.startswith('college-explore:') else 0
        elif condition_type == self.TASK_EVENT_BUY_GOOD:
            # Every supply tab counts; purchases in unrelated activity systems do not.
            achv_event = self.ACHV_EVENT_SUPPLY_PURCHASE if key.startswith(('shop-buy:', 'compat-shop:')) else 0
        if achv_event in self.achievements.event_types:
            event_key = f"event:{condition_type}:{key}"
            # Login deliberately reuses a key; touch, power, job and order keys
            # already carry their day, sequence or globally unique occurrence ID.
            if key == 'login':
                event_key += ':' + str(task_period(1, int(self.clock()))[0])
            self.achievements.record(player_id, event_key, achv_event, amount)

    def claim(self, player_id, task_id, kind):
        self.ensure_periods(player_id)
        self.refresh_online_tasks(player_id)
        if kind == 1:
            repair_activity_daily(self, player_id)
        task = self.tasks.get(task_id)
        result = {"code": 13, "taskId": task_id, "type": kind, "rewardData": b""}
        if (not task or task["RefreshCycle"]["value"] != kind
                or task["AcceptLevel"] > self.store.get(player_id)["snapshot"]["level"]
                or not activity_daily_open(self, task_id)):
            return result
        try:
            group = self.season.daily_gift(player_id, task_id, task["GiftGroup"])
            rewards = self.gifts([group])
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

    def challenge_chest_for_run(self, player_id, run_uuid, profile):
        """SectionTable chest fields are bag items, selected by admitted expertMode."""
        if profile['section_type'] != 2:
            return None
        entry = self.store.db.execute('SELECT response FROM battle_entries WHERE uuid=? AND player_id=?',
                                      (run_uuid, player_id)).fetchone()
        if not entry:
            return None
        from x2server.messages.battle import BATTLE_SCHEMAS, FIGHT_DATA
        admitted = BATTLE_SCHEMAS['L2C_FightData'].decode(entry[0])
        expert = FIGHT_DATA.decode(admitted.get('data', b'')).get('expertMode', False)
        field = 'ExpertChestReward' if expert else 'ChestReward'
        item = int(profile.get('special_reward_fields', {}).get(field, 0) or 0)
        if not item:
            return None
        if (self.items.get(item, {}).get('ItemType', {}).get('value') != 18
                or not self.bag_catalog['items'].get(str(item), {}).get('used')):
            raise UnresolvedEconomy('unresolved challenge chest item')
        return item, expert, field

    def settle(self, player_id, run_uuid, section, success, section_type=0,
               outside_items=(), maze_items=(), extra_data=(), surviving_heroes=()):
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
        activity = getattr(self, 'activity', None)
        activity_period = activity.rotation.run_period(player_id, run_uuid) if activity else None
        gameplay_rewards = (activity.gameplay_rewards(player_id, activity_period, section, extra_data)
                            if activity_period and section_type == 16 else {})
        if activity_period and section_type == 16:
            # Exchange outputs come only from the currency report, not a second
            # client-supplied outsideItems claim for the same packet.
            outputs = {item for row in activity_period.theme['activities']
                       if row['ActivityType'].get('value') == 28
                       and config['ChapterID'] in row.get('ActivityParam1', [])
                       for item in row.get('ActivityParam4', [])}
            outside_items = [raw for raw in outside_items if OUTSIDE_ITEM.decode(raw).get('id') not in outputs]
        chest = self.challenge_chest_for_run(player_id, run_uuid, profile) if success else None
        if chest:
            # This fixed clear reward has one authoritative source. Ignore client
            # echoes of either configured chest, including an inflated quantity.
            chest_ids = {int(profile.get('special_reward_fields', {}).get(f, 0) or 0)
                         for f in ('ChestReward', 'ExpertChestReward')}
            outside_items = [raw for raw in outside_items
                             if OUTSIDE_ITEM.decode(raw).get('id') not in chest_ids]
        grants, pending_instances, blocked, equipment_specs = self.runtime_drops.resolve(
            run=run, profile=profile, outside_items=outside_items, success=success)
        if success and section_type == 7:
            # 周常「乌洛波罗斯」的元素合成产物: 客户端把它们放进 FightItemBag 时
            # source=COMPOSE, 而 SetCheckout_BattleItem 只上报 source==FIGHT, 因此
            # outsideItems 里永远没有它们。按本局合成记录补发 (useScene==1 的产物,
            # 光能代理折成账号光能), 否则玩家局内合成的东西结算后就丢了。
            grants.extend(self.element_compose.settle_grants(player_id, run_uuid, section))
        if chest:
            grants.append(RewardGrant('NORMAL_CLEAR_FIXED', section, run_uuid, chest[0], 1,
                                      reason=f'SectionTable.{chest[2]}'))
        reward_equips: list = []
        sources = {name: [] for name in ("FIRST_CLEAR_FIXED", "NORMAL_CLEAR_FIXED",
            "RUNTIME_BATTLE_DROP", "REPORT_CURRENCY", "SWEEP_REWARD", "EXTRA_DROP",
            "COMPAT_REWARD", "EQUIP_INSTANCE", "RELIC_COLLECTION", "ACTIVITY_GAMEPLAY")}
        for item, quantity in gameplay_rewards.items():
            grant = RewardGrant('ACTIVITY_GAMEPLAY', section, run_uuid, item, quantity,
                                reason='ActivityReal maze currency exchange')
            grants.append(grant)
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
                    (player_id,item_id,quantity) VALUES (?,?,1)
                    ON CONFLICT(player_id,item_id) DO UPDATE SET quantity=1 WHERE inventory.quantity<1""", (player_id, item_id))
                if inserted.rowcount:
                    sources["RELIC_COLLECTION"].append({"item_id": item_id,
                        "source": "checkout mazeItems"})
            pending = Counter()
            first = not self.store.db.execute(
                "SELECT 1 FROM economy_clears WHERE player_id=? AND section_id=?", (player_id, section)).fetchone()
            # USER_DECISION: reset the eight named activities each period.
            # Only a run explicitly bound by ActivityRotation can override this
            # gate. Normal stages keep the original lifetime first-clear rule.
            if section_type == 20 and self.season.active(player_id):
                first = not self.store.db.execute('SELECT 1 FROM season_runs WHERE player_id=? AND instance_id=? AND section_id=? AND success=1', (player_id, self.season.instance, section)).fetchone()
            if activity_period:
                first = not activity.rotation.get(player_id, activity_period, 'clear', section, 0)
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
            if activity_period:
                extra = activity.runtime.extra_rewards(player_id, run_uuid, section, sum_grants(grants))
                grants.extend(RewardGrant('EXTRA_DROP', section, run_uuid, item, count,
                    reason='current activity ExtraDroop/AccountBuff') for item, count in extra.items())
                sources['EXTRA_DROP'].extend({'item_id': i, 'quantity': n} for i, n in extra.items())
            base = sum_grants([grant for grant in grants if grant.source != 'EXTRA_DROP'])
            for item, count in self.extra_drop.rewards(player_id, section, base).items():
                grants.append(RewardGrant('EXTRA_DROP', section, run_uuid, item, count,
                    reason='resource activity 71004 +100%'))
                sources['EXTRA_DROP'].append({'item_id':item,'quantity':count})
            if activity:
                chapter_rewards = activity.pov_chapter_rewards(player_id, section)
                for item, count in chapter_rewards.items():
                    grant = RewardGrant('FIRST_CLEAR_FIXED', section, run_uuid, item, count,
                                        reason='POVChapterInfo.ClearReward')
                    grants.append(grant)
                    sources['FIRST_CLEAR_FIXED'].append(grant.__dict__)
            rewards = self._grant(player_id, f"battle:{run_uuid}", sum_grants(grants))
            if activity_period:
                activity.obtained(player_id, activity_period, rewards, f'battle:{run_uuid}')
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
            if chest and chest[1]:
                self._event(player_id, f'expert-chest:{run_uuid}', 42, 0, 1)
            self.mark_section_cleared(player_id, section, run_uuid, section_type)
            if section_type == 7 or activity_period:
                team_row = self.store.db.execute('SELECT team_json FROM battle_entries WHERE uuid=? AND player_id=?',
                                                 (run_uuid, player_id)).fetchone()
                team = json.loads(team_row[0]) if team_row else []
                survivors = set(surviving_heroes) & set(team)
                self.endless.completed(player_id, run_uuid, section, survivors)
                if activity_period:
                    activity.event(player_id, f'three-hero:{run_uuid}', 63, section, 1,
                                   len(survivors), period=activity_period)
            self.dp.equipment(player_id, config["ChapterID"], run_uuid,
                [{"star": spec["quality"], "item_id": spec["item_id"]} for spec in equipment_specs for _ in range(spec["quantity"])])
            self.dp.refresh(player_id, config["ChapterID"])
            self._event(player_id, f"clear:{run_uuid}", 3, section, 1)
            self.terminal_wish.battle(player_id, run_uuid, section)
            spent = self.store.db.execute("SELECT amount FROM battle_costs WHERE uuid=? AND player_id=?",
                (run_uuid, player_id)).fetchone()
            if spent and spent[0]:
                self._event(player_id, f"power:{run_uuid}", 10, 900, spent[0])
        else:
            rewards = (self._grant(player_id, f'battle:{run_uuid}', gameplay_rewards)
                       if gameplay_rewards else {})
            if activity_period and rewards:
                activity.obtained(player_id, activity_period, rewards, f'battle:{run_uuid}')
                sources['ACTIVITY_GAMEPLAY'].extend(grant.__dict__ for grant in grants
                                                   if grant.source == 'ACTIVITY_GAMEPLAY')
            reward_equips = []
            self.refund_battle(player_id, run_uuid)
        self.store.db.execute("INSERT INTO reward_settlement_audit VALUES (?,?,?,?,?,?)",
            (run_uuid, player_id, section, json.dumps(sources, ensure_ascii=False, sort_keys=True),
             json.dumps(blocked, ensure_ascii=False, sort_keys=True), int(time.time())))
        self.store.db.execute("UPDATE economy_runs SET settled=1 WHERE uuid=?", (run_uuid,))
        if getattr(self, 'activity', None) and section in self.activity.rotation.section_groups:
            self.activity.complete(player_id, run_uuid, section, success)
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
        # Atomic with stamina, reward delivery and the transport receipt.
        today = (int(self.clock()) + 8 * 3600) // 86400
        charged = self.store.db.execute("""INSERT INTO server_sweep_limits
            (player_id,day,used) SELECT ?,?,? WHERE ?<=30
            ON CONFLICT(player_id) DO UPDATE SET
              day=excluded.day,
              used=CASE WHEN server_sweep_limits.day=excluded.day
                        THEN server_sweep_limits.used+excluded.used ELSE excluded.used END
            WHERE server_sweep_limits.day!=excluded.day
               OR server_sweep_limits.used+excluded.used<=30""",
            (player_id, today, count, count))
        if not charged.rowcount:
            raise UnresolvedEconomy('daily shared sweep limit 30 exceeded')
        self.refresh_stamina(player_id)
        snapshot = self.store.get(player_id)["snapshot"]
        if snapshot.get("mobility", {}).get("power", 0) < cost * count:
            raise UnresolvedEconomy("insufficient sweep stamina")
        pending = Counter()
        grants = []
        for _ in range(count):
            per_run = Counter()
            for group in profile["sweep_reward"]:
                per_run.update(self.gifts([group], deferred=pending,
                    allow_daily_random=profile["section_type"] != 0))
            grants.extend(RewardGrant("SWEEP_REWARD", section, request_key, item, amount,
                reason='SectionTable MopReward') for item, amount in per_run.items())
            grants.extend(RewardGrant("EXTRA_DROP", section, request_key, item, amount,
                reason='resource activity 71004 +100%')
                for item, amount in self.extra_drop.rewards(player_id, section, per_run).items())
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
            (request_key, player_id, section, json.dumps({
                "SWEEP_REWARD": audit_grants([g for g in grants if g.source == "SWEEP_REWARD"]),
                **({"EXTRA_DROP": audit_grants([g for g in grants if g.source == "EXTRA_DROP"])}
                   if any(g.source == "EXTRA_DROP" for g in grants) else {})},
             ensure_ascii=False), json.dumps({"pending": dict(pending)}), int(time.time())))
        return self.reward_bytes(rewards)

    def mark_section_cleared(self, player_id, section, run_uuid, section_type):
        """Shared clear record with a type-specific frontier policy."""
        if section_type == 20:
            return  # Season progression lives in its instance, never the lifetime clear table.
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
        """Settle earned points once, retaining the partial interval in the save.

        ``recover_anchor`` stays the server-authoritative anchor (field name kept to
        avoid churn), but two things happen alongside it:

        * 镜像 —— 只要改动了 ``recover_anchor``, 就把 ``mobility["shop_power_fetch_time"]``
          写成同一个值 (客户端 Mobility.ShopPowerFetchTime)。客户端 CollegeModule.RefreshPower
          正是用它外推启明之塔 702 的显示值, 起点与服务端一致才不会重复计数 (结算完的瞬间
          外推项 = floor(余数/周期 × 转化率) = 0)。
        * 溢出进塔 —— 体力条填满之后剩下的 ``earned`` 整期交给启明之塔 702 存储
          (``college.credit_overflow``)。``college`` 由 run_server 注入 (``self.college``),
          未接线时退化为"只回体力、不进塔"(不依赖学院的单测仍能过)。
        """
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
            if type(anchor) is not int or anchor <= 0 or anchor > now:
                # 客户端 PowerModule_CheckPowerRecover 在 ShopPowerFetchTime <= 0 时完全不
                # 恢复, 所以无效锚点只能按 now 起算; 同时镜像外推起点。
                if anchor != now:
                    mobility["recover_anchor"] = now
                    mobility["shop_power_fetch_time"] = now
                    self.save_snapshot(player_id, snapshot)
                return
            earned = (now - anchor) // self.POWER_RECOVER_SECONDS
            if not earned:
                return
            room = max(0, cap - mobility["power"])
            filled = min(earned, room)
            mobility["power"] += filled
            overflow = earned - filled
            college = getattr(self, "college", None)
            if overflow and college is not None:
                college.credit_overflow(player_id, overflow)
            mobility["recover_anchor"] = (now if mobility["power"] == cap and not overflow
                else anchor + earned * self.POWER_RECOVER_SECONDS)
            mobility["shop_power_fetch_time"] = mobility["recover_anchor"]
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
        activity = getattr(self, 'activity', None)
        if activity:
            permanent.update(item for item, count in activity.gameplay_day_counts(player_id).items() if count)
        removed = [row[0] for row in self.store.db.execute(
            "SELECT item_id FROM inventory WHERE player_id=? AND quantity<=0 ORDER BY item_id", (player_id,))
            if row[0] not in permanent]
        return (LoginService.snapshot_push(self.store.get(player_id), self.store, int(self.clock())),
            OutboundMessage("L2C_ItemUpdate", {"code": 10, **self.inventory_values(player_id)}),
            *((OutboundMessage("L2C_ItemRemove", {"ids": removed}),) if removed else ()),
            *(OutboundMessage("L2C_TaskUpdate", {"type": k, "taskList": self.task_values(player_id, k)["taskList"]}) for k in (1, 2)),
            OutboundMessage("L2C_TaskUpdate", {"type": 3, "taskList": self.challenge_values(player_id)["taskList"]}),
            self.achievements.update(player_id), *self.season.pushes(player_id),
            *self.terminal_wish.pushes(player_id))

    # ---- 首充 ------------------------------------------------------------
    #
    # USER_DECISION: 本地「一律点开就能领」。首充以前要先去充值页点一个档位才解锁
    # (state 0 -> 1); 离线端 (x2offline/src/server/router.cpp:4314) 的口径也是「未领过
    # 一律回 state=1」, 所以这里 state 0/1 都当可领取, 只有领过 (2) 才不可领。

    def _first_recharge_state(self, player_id: int) -> int:
        """0/1 都当「可领取」, 只有领过 (2) 才不可领。"""
        row = self.store.db.execute(
            "SELECT state FROM recharge_first WHERE player_id=?", (player_id,)).fetchone()
        state = int(row[0]) if row else 0
        return 1 if state == 0 else state

    def query_first_recharge(self, player_id: int) -> OutboundMessage:
        """L2C_QueryFirstReCharge: 0=未充过 1=可领取 2=已领取。"""
        return OutboundMessage("L2C_QueryFirstReCharge",
                               {"code": 10, "state": self._first_recharge_state(player_id)})

    def receive_first_recharge(self, player_id: int) -> OutboundMessage:
        """领取首充奖励: 真发首充礼包 FIRST_RECHARGE_GIFT (783023)。

        口径照离线端 router.cpp:4329 recive-first-recharge: 状态必须为 1 (未领过),
        在事务里 _grant 发货 (幂等去重 + 落快照), 再把状态推进到 2。旧实现只推状态、
        不发货 —— 但首充列表是客户端从 GameActivity 100001 自己读出来的, 明细它早就
        有了, 不发等于白点一次。
        """
        state = self._first_recharge_state(player_id)
        if state != 1:
            return OutboundMessage("L2C_ReciveFirstReCharge", {"code": 13})
        try:
            with self.transaction():
                rewards = self.gifts([self.FIRST_RECHARGE_GIFT])
                self._grant(player_id, "first-recharge", rewards)
                self.store.db.execute("""INSERT INTO recharge_first VALUES (?,2)
                    ON CONFLICT(player_id) DO UPDATE SET state=2""", (player_id,))
        except UnresolvedEconomy as exc:
            logging.getLogger("x2.economy").warning(
                "first recharge claim refused player=%s reason=%s", player_id, exc)
            return OutboundMessage("L2C_ReciveFirstReCharge", {"code": 13})
        logging.getLogger("x2.economy").info(
            "first recharge claimed player=%s delivered=%s", player_id, sorted(rewards.items()))
        return OutboundMessage("L2C_ReciveFirstReCharge",
                               {"code": 10, "rewardData": self.reward_bytes(dict(rewards))},
                               pushes=self.pushes(player_id))

    def handlers(self):
        from .bag_items import BagItemService
        from .medals import MedalService
        handlers = {**self.season.handlers(), **self.world_boss.handlers(), **self.endless.handlers(), **self.element_compose.handlers(), **MedalService(self).handlers(), **BagItemService(self.store, self).handlers(), **self.achievements.handlers(),
                "C2L_FetchMobilityPower": self.fetch_mobility_power,
                **{name: self.handle for name in ("C2L_ItemAll", "C2L_ItemOpt", "C2L_ItemExchangeCurrency",
            "C2L_ShopGoods", "C2L_RefreshShop", "C2L_BuyGoods",
            "C2L_QueryGoodsInfo", "C2L_GameTask", "C2L_DailyAndWeekTask", "C2L_FinishGameTask",
            "C2L_FinishGameTaskAsync", "C2L_PickTreasureBox", "C2L_QueryMission",
            "C2L_UnlockStory", "C2L_QueryFirstReCharge", "C2L_ReciveFirstReCharge")}}
        # 活动中心: 星之特权/积分活动/献祭福利/自选三星 (ExtraActivityService) 与
        # 降临纪念 (TotalLoginService) 各答自己的请求。
        handlers.update(self.extra_activity.handlers())
        handlers.update(self.total_login.handlers())
        handlers.update(self.terminal_wish.handlers())
        handlers.update(self.moon.handlers())
        return handlers

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
            # 台账: 旧阶梯没有价格日志, 补偿只能靠 economy_events 的序号回放
            # (见 player/power_refund.py); 这里补上价格, 以后核对不用再猜。
            logging.getLogger("x2.economy").info(
                "power purchase player=%s tier=%s price=%s granted=%s power=%s",
                player_id, count, price, self.POWER_BUY_AMOUNT, mobility["power"])
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
        # 首充这两个请求体都是空结构, 在 decode 前就地应答: C2L_QueryFirstReCharge 的
        # schema 由 COLLEGE_IDS/messages.college 提供, 不在 LOBBY_SCHEMAS 里。
        if name == "C2L_QueryFirstReCharge":
            return self.query_first_recharge(player_id)
        if name == "C2L_ReciveFirstReCharge":
            return self.receive_first_recharge(player_id)
        request = (ECONOMY_SCHEMAS if name in ECONOMY_SCHEMAS else LOBBY_SCHEMAS)[name].decode(packet.body)
        response_name = name.replace("C2L_", "L2C_", 1)
        if name == "C2L_ItemOpt":
            item_id = request.get("id", 0)
            logging.getLogger("x2.economy").info(
                "item opt player=%s item=%s opt=%s count=%s", player_id,
                item_id, request.get("opt", 0), request.get("count", 0))
            # opt 1 is 背包-分解 and only that: BagModule_RecycleItem (0x19AA26C) sends
            # it as a constant, and the page's own reply handler
            # BagDecomposePage_OnItemOptMsg (0x19A6E64) refreshes on `cmp w1, #1`
            # alone. opt 0 keeps the 使用 routes below.
            if request.get("opt", 0) == 1:
                return self.recycle_bag_item(context, packet, request)
            if item_id in (self.season.EXP_ITEM, self.season.POINT_ITEM) and self.season.active(player_id):
                return self.season.use_item(context, packet, request)
            if item_id in self.CAUSALITY_CARDS:
                return self.use_causality_card(context, packet, request)
            return self.use_bag_item(context, packet, request)
        if name == "C2L_ItemExchangeCurrency":
            return self.exchange_item_currency(context, packet, request)
        if name == "C2L_ItemAll":
            return OutboundMessage(response_name, self.inventory_values(player_id))
        if name == "C2L_QueryMission":
            # ChapterModule fires a global RefreshPage even while the hidden
            # ChapterInfoView is being initialized. Client 2.4 can throw there;
            # let this refresh finish before delivering the following queries.
            return OutboundMessage(response_name, self.mission_values(player_id), dispatch_gap=0.05)
        if name == "C2L_UnlockStory":
            return self.unlock_story(player_id, request)
        if name in ("C2L_GameTask", "C2L_DailyAndWeekTask"):
            kind = request.get("type", 0)
            if kind in self.moon.KINDS:
                return OutboundMessage('L2C_GameTask', self.moon.task_values(player_id, kind))
            if kind == 6:
                return self.terminal_wish.query(context, packet, request)
            if kind == 15:
                return OutboundMessage("L2C_GameTask", self.season.task_values(player_id))
            # Only the separately verified activity task types are routed here;
            # ordinary daily, weekly, challenge and chapter tasks stay below.
            if kind in (9, 20) and getattr(self, 'activity', None):
                return OutboundMessage('L2C_GameTask', self.activity.task_values(
                    player_id, kind, request.get('extraType', 0)))
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
            return OutboundMessage("L2C_GameTask", self.task_values(player_id, kind) if kind in (1, 2)
                else self.challenge_values(player_id) if kind == 3
                else {"code": 10, "type": kind, "chapterId": request.get("chapterId", 0)})
        if name in ("C2L_FinishGameTask", "C2L_FinishGameTaskAsync"):
            favor_changes = []
            requests = [FINISH_REQUEST.decode(b) for b in request.get("data", [])] if name == "C2L_FinishGameTask" else [request]
            if len(requests) > 40:
                raise ProtocolError("too many task claims")
            results = [FINISH_RESULT.encode(
                self.moon.claim_task(player_id, r.get('taskId', 0), r.get('type', 0)) if r.get('type', 0) in self.moon.KINDS else
                self.terminal_wish.claim(player_id, r.get('taskId', 0), favor_changes) if r.get('type', 0) == 6 and not r.get('activityId') else
                self.activity.claim_task(player_id, r.get('taskId', 0), r.get('type', 0), r.get('activityId', 0)) if r.get('type', 0) in (9, 20) and getattr(self, 'activity', None) else
                self.season.claim_task_response(player_id, r.get("taskId", 0), context.session.session_id + ":" + str(packet.header.request_id) + ":" + hashlib.sha256(packet.body).hexdigest() + ":" + str(r.get("taskId", 0))) if r.get("type", 0) == 15 else
                self.endless.claim(player_id, r.get("taskId", 0), context.session.session_id + ":" + str(packet.header.request_id)) if r.get("type", 0) == 12 else
                self.claim_challenge(player_id, r.get("taskId", 0)) if r.get("type", 0) == 3 else
                self.claim(player_id, r.get("taskId", 0), r.get("type", 0))
                if not r.get("activityId") else {"code": 13, "taskId": r.get("taskId", 0), "type": r.get("type", 0)}) for r in requests]
            return OutboundMessage(response_name, {"data": results if name == "C2L_FinishGameTask" else results[0]},
                before_response=self.moon.claim_pushes(results),
                pushes=((OutboundMessage('L2C_FavorChangeInfo', {'data': favor_changes}),) if favor_changes else ()) + self.pushes(player_id))
        if name == "C2L_ShopGoods":
            shop = request.get("shopId", 0)
            # Client 2.4 dereferences a null goods list on success. With no fully
            # confirmed goods, reject the query before that success-only path.
            return OutboundMessage(response_name, {"code": 13, "shopId": shop})
        if name == "C2L_PickTreasureBox":
            if request.get("type", 0) == self.season.TASK_KIND:
                return self.season.claim_weekly_box(context, packet, request)
            if request.get('type', 0) in (9, 20) and getattr(self, 'activity', None):
                try:
                    token = hashlib.sha256(f'{context.session.session_id}:{packet.header.request_id}:{name}'.encode()
                                           + packet.body).hexdigest()
                    with self.transaction():
                        period = self.activity.period(player_id)
                        cached = self.store.db.execute('SELECT period,message,response FROM activity_receipts '
                            'WHERE player_id=? AND request_key=?', (player_id, token)).fetchone()
                        if cached:
                            if cached['period'] != period.index or cached['message'] != response_name:
                                raise UnresolvedEconomy('activity box receipt belongs to another period')
                            values = ECONOMY_SCHEMAS[response_name].decode(cached['response'])
                        else:
                            rewards = self.activity.claim_task_box(player_id, request.get('activityId', 0),
                                request.get('boxId', -1), request['type'])
                            values = {'code': 10, **request, 'rewardData': self.reward_bytes(rewards)}
                            self.store.db.execute('INSERT INTO activity_receipts VALUES (?,?,?,?,?)',
                                (player_id, token, period.index, response_name, ECONOMY_SCHEMAS[response_name].encode(values)))
                    return OutboundMessage(response_name, values, before_response=self.pushes(player_id))
                except UnresolvedEconomy:
                    return OutboundMessage(response_name, {'code': 13, **request})
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
                    from .bag_items import bag_pushes, bag_reward_view
                    values = ECONOMY_SCHEMAS["L2C_ItemOpt"].decode(row[0])
                    values['rewardData'] = bag_reward_view(values.get('rewardData', b''))
                    return OutboundMessage("L2C_ItemOpt", values,
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
                if 1237900 in rewards:
                    # Regeneration belongs to the old balance. Applying it after
                    # a box's power reward can clip the reward at the normal cap.
                    self.refresh_stamina(player_id)
                reward_data = grant_bag_rewards(self, player_id, f"item-opt:{key}", rewards, item_id)
                activity = getattr(self, 'activity', None)
                period = activity.rotation.at() if activity else None
                if period:
                    activity.obtained(player_id, period, rewards, f'bag-use:{key}')
                values = {"code": 10, "opt": 0, "itemId": item_id,
                          "rewardData": reward_data}
                self.store.db.execute("INSERT INTO item_opt_receipts VALUES (?,?,?)",
                                      (key, player_id, ECONOMY_SCHEMAS["L2C_ItemOpt"].encode(values)))
        except UnresolvedEconomy as exc:
            logging.getLogger("x2.economy").info("item use rejected item=%s player=%s reason=%s", item_id, player_id, exc)
            return rejected
        from .bag_items import bag_pushes
        return OutboundMessage("L2C_ItemOpt", values, before_response=bag_pushes(self, player_id))

    def recycle_bag_item(self, context, packet, request):
        """背包-分解: spend item(s) for the fragments named by Item.Recover.

        The page's numbers come from that same column: BagDecomposePage_RefreshCurrency
        (0x19A6354) reads Item+0x78, takes [0] as the currency type and [1] as the
        per-item amount, and multiplies by the count the player entered. Its 分解
        button (BagDecomposePage_OnBottomSellBtnClick 0x19A9D00 -> BagModule_RecycleItem
        0x19AA26C) then sends C2L_ItemOpt with opt 1, so the rate has to be settled
        here from the identical column or the page and the bag disagree. A row with no
        Recover, or one whose type is not a known fragment currency, is refused rather
        than paid at an invented rate.
        """
        player_id = context.session.player_id
        item_id, count = request.get("id", 0), request.get("count", 0)
        rejected = OutboundMessage("L2C_ItemOpt", {"code": 13, "opt": request.get("opt", 0), "itemId": item_id})
        recovered = self.recover_items.get(item_id)
        if (request.get("opt", 0) != 1 or type(count) is not int or not 1 <= count <= 999
                or not recovered or len(recovered) != 2 or type(recovered[1]) is not int
                or recovered[1] <= 0 or recovered[0] not in self.RECOVER_CURRENCY_ITEMS):
            return rejected
        payout = self.RECOVER_CURRENCY_ITEMS[recovered[0]]
        key = hashlib.sha256(f"{player_id}:{context.session.session_id}:{packet.header.request_id}:item-opt".encode()
                             + packet.body).hexdigest()
        try:
            return self._recycle_bag_item(player_id, item_id, count, recovered[1] * count, payout, key, rejected)
        except UnresolvedEconomy:
            return rejected

    def _recycle_bag_item(self, player_id, item_id, count, amount, payout, key, rejected):
        with self.transaction():
            row = self.store.db.execute("SELECT response FROM item_opt_receipts WHERE request_key=? AND player_id=?",
                                        (key, player_id)).fetchone()
            if row:
                return OutboundMessage("L2C_ItemOpt", ECONOMY_SCHEMAS["L2C_ItemOpt"].decode(row[0]),
                                       before_response=self.pushes(player_id))
            charged = self.store.db.execute("UPDATE inventory SET quantity=quantity-? "
                "WHERE player_id=? AND item_id=? AND quantity>=?", (count, player_id, item_id, count))
            if not charged.rowcount:
                return rejected
            granted = self._grant(player_id, f"item-recycle:{key}", {payout: amount})
            values = {"code": 10, "opt": 1, "itemId": item_id, "rewardData": self.reward_bytes(granted)}
            self.store.db.execute("INSERT INTO item_opt_receipts VALUES (?,?,?)",
                                  (key, player_id, ECONOMY_SCHEMAS["L2C_ItemOpt"].encode(values)))
        return OutboundMessage("L2C_ItemOpt", values, before_response=self.pushes(player_id))

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

    def exchange_item_currency(self, context, packet, request):
        """神格碎片「转化」: spend ItemType 12 chips for the currency in Item.Return.

        The button that lands here is ItemInfoWnd_OnUseBtnClick (0x16ED7F0) /
        BagModule_ItemExchangeCurrency (0x19C6688), and the client shows nothing
        that came from itself: ItemInfoWnd_ShowNum (0x16ED730) only sets the
        stepper's max to the owned count, the 1 -> N rate is drawn from the
        RewardData below. Every pair is validated before anything is written; a
        refusal is an explicit code 13, never a silent drop, because the client
        keeps re-sending a request it got no reply for.
        """
        player_id = context.session.player_id
        plan = []
        entries = request.get("items", [])
        if not 0 < len(entries) <= 128:
            return OutboundMessage("L2C_ItemExchangeCurrency", {"code": 13})
        for raw in entries:
            pair = MISSION_PAIR.decode(raw)
            item_id, count = pair.get("Key", 0), pair.get("Value", 0)
            row = self.items.get(item_id) or {}
            returned = row.get("Return")
            # ItemType 12 is the only type BagModule_ItemType2SelectType maps to
            # 「转化」. 1201000 万能神格碎片 has no Return at all, so it is refused
            # as "no rate" instead of paying something invented.
            if (row.get("ItemType", {}).get("value") != 12 or not returned
                    or len(returned) != 2 or type(returned[1]) is not int or returned[1] <= 0
                    or type(count) is not int or not 1 <= count <= 2**31 - 1
                    or returned[0] not in self.RETURN_CURRENCY_ITEMS):
                return OutboundMessage("L2C_ItemExchangeCurrency", {"code": 13})
            plan.append((item_id, count, self.RETURN_CURRENCY_ITEMS[returned[0]], int(returned[1])))
        if not plan or sum(count for _, count, _, _ in plan) > 2**31 - 1:
            return OutboundMessage("L2C_ItemExchangeCurrency", {"code": 13})
        key = hashlib.sha256(f"{player_id}:{context.session.session_id}:{packet.header.request_id}:item-exchange".encode()
                             + packet.body).hexdigest()
        try:
            return self._exchange_item_currency(player_id, plan, key)
        except UnresolvedEconomy as exc:
            logging.getLogger("x2.economy").info(
                "item exchange rejected player=%s reason=%s", player_id, exc)
            return OutboundMessage("L2C_ItemExchangeCurrency", {"code": 13})

    def _exchange_item_currency(self, player_id, plan, key):
        with self.transaction():
            row = self.store.db.execute("SELECT response FROM item_opt_receipts WHERE request_key=? AND player_id=?",
                                        (key, player_id)).fetchone()
            if row:
                return OutboundMessage("L2C_ItemExchangeCurrency",
                                       ECONOMY_SCHEMAS["L2C_ItemExchangeCurrency"].decode(row[0]),
                                       before_response=self.pushes(player_id))
            for item_id, count, _, _ in plan:
                spent = self.store.db.execute("UPDATE inventory SET quantity=quantity-? "
                    "WHERE player_id=? AND item_id=? AND quantity>=?", (count, player_id, item_id, count))
                # The whole order clears or none of it does: raising rolls the
                # savepoint back instead of charging for a partly served list.
                if not spent.rowcount:
                    raise UnresolvedEconomy(f"insufficient chip {item_id}")
            rewards = Counter()
            for _, count, payout, amount in plan:
                rewards[payout] += amount * count
            granted = self._grant(player_id, f"item-exchange:{key}", rewards)
            values = {"code": 10, "rewardData": self.reward_bytes(granted)}
            self.store.db.execute("INSERT INTO item_opt_receipts VALUES (?,?,?)",
                                  (key, player_id, ECONOMY_SCHEMAS["L2C_ItemExchangeCurrency"].encode(values)))
        return OutboundMessage("L2C_ItemExchangeCurrency", values, before_response=self.pushes(player_id))
