"""学院炼金 (白夜行星·浮士德的炼金实验室) 的完整实现。

补齐 12 对消息 + 617 推送 (messages/alchemy.py 声明契约):

    590 AlchemyMainData     读全量状态 (配方经验/顾客/产槽/元素/增益)
    592 SingleCustomerInfo  给某个顾客槽生成/读取一位顾客 (CollegeCustomer+CollegeQuest)
    594 MakeItem            按 CollegeRecipe 扣金币/元素/材料, 写产槽 (WaitTimes 秒)
    596 MakIngSpeed         按挡位扣资源, 让产槽立刻到时
    598 AlchemyFinish       顾客交易: 服务端按 CollegeQuest 表重算奖励 (不信客户端)
    600 AlchemyButtonClick  换委托/委派: 花星能, 顾客改要「建议」产物 (action!=1 回 13)
    602 AlchemyCollect      到时收取产物 + 配方经验 (每件 +1, 达阈值级联解锁后续配方)
    604 AlchemyBuy          买元素 (记 buyTimesDay, 超日限回 13)
    729/731 交易活动         无表数据 → 安全空列表 + code 10
    824 AlchemyMakeCancel   取消产槽, 按比例退还
    826 AlchemyOnekeyCollect 对给定槽位逐个收取
    617 (推送)              elements/starEnergy/starGainTime/buffType/buffCount

数值口径: 表内值 (Gold/Pay/ItemGroup/ItemNum/ProductID/ProductNum/WaitTimes/Exp,
CollegeQuest 的 AwardType/AwardGroup) 严格照表。槽位数与元素恢复参数取自客户端表
GlobalParamString (AlchemyNum=8 产槽, AlchemyCustomerNum=5 顾客槽, Element01..06=1800
恢复间隔, Element01..06Param=100|100|3 即 初始100|上限100|每间隔恢复3), 落在
data/alchemy_catalog.json 的 slots 与 elements 行。买元素/加速挡位、每日限购、
取消退还比例在客户端表里没有闭环证据, 仍是 **Revival 兼容常量** (SERVER_ONLY_UNKNOWN),
见 compat 节与 provenance, 不声称官方数值。

元素按本地时间恢复 (恢复间隔 recoverSec, 上限 cap, 每次恢复 recoverNum), 跨天
(本工程 00:00 日界) 重置 buyTimesDay。所有读写入口先做一次惰性结算, 与离线端口径一致。
"""

from __future__ import annotations

import json
import logging
import math
from functools import lru_cache
from importlib.resources import files

from x2server.messages.alchemy import (ALCHEMY_IDS, ALCHEMY_RECIPE_BAR_DATA,
                                       ALCHEMY_SCHEMAS, CUSTOMER_INFO, ELEMENT,
                                       PRODUCTION_BAR)
from x2server.messages.economy import REWARD
from x2server.messages.lobby import MISSION_PAIR as KEY_VALUE_PAIR
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY
from .college import settle_star_energy
from .economy import UnresolvedEconomy
from .server_clock import ServerClock, day_index, day_period

LOGGER = logging.getLogger("x2.alchemy")

# 状态码, 与离线端 x2offline/src/offline/mission.hpp 的 kCollege* 常量同一组。
ALCHEMY_OK = 10
ALCHEMY_ERROR_OPT = 13
ALCHEMY_MAX_LEVEL = 14
ALCHEMY_NO_ITEM = 22
ALCHEMY_CONFIG = 29
ALCHEMY_LIMIT_GOLD = 35
ALCHEMY_BUSY = 55
# 换委托 (600) 星能不够。离线端 mission.hpp 的 kCollege* 里没有 38, 这个号是照上游
# college_alchemy.py _suggest/_trade 的 `code=38` 取的, 属于「表里没有闭环证据」的一档。
ALCHEMY_NO_ENERGY = 38

STAMINA_ITEM = 1237900
GOLD_ITEM = 1237901

# 炼金元素币 1237991..1237996 是元素 991..996 的货币化表示 (客户端 Item.json: ItemType:16,
# FunctionEff:2, EffData:[991..996], 与金币 1237901→901 完全同构)。客户端算元素「拥有」用的
# 就是元素池数量, 所以配方材料里的这几号必须从元素池结算, 而不是查背包。
ELEMENT_ITEM_MIN = 1237991
ELEMENT_ITEM_MAX = 1237996
ELEMENT_ID_MIN = 991


def element_currency_id(item_id: int) -> int | None:
    """元素币 id → 元素 id (991..996); 非元素币返回 None。"""
    if ELEMENT_ITEM_MIN <= item_id <= ELEMENT_ITEM_MAX:
        return ELEMENT_ID_MIN + (item_id - ELEMENT_ITEM_MIN)
    return None


@lru_cache(maxsize=1)
def catalog() -> dict:
    """data/alchemy_catalog.json (由 work/make_alchemy_catalog.py 生成)。"""
    return json.loads(files("x2server").joinpath(
        "data/alchemy_catalog.json").read_text(encoding="utf-8"))


def _compat() -> dict:
    return catalog()["compat"]


def element_rows() -> list[dict]:
    return catalog()["elements"]


# 配方经验: 每收取 1 件产物加 1 点 —— 官方 Exp 向量是**阈值**而不是增益值
# (客户端 GetExpPhase 拿它数「已满足几档」), 与 work/_up_college_alchemy.py 的
# EXPERIENCE_PER_ITEM 同一口径。旧实现误把 exp[0] (=3) 当每次增益, 三倍速冲进度。
EXPERIENCE_PER_ITEM = 1
# RecipeEffect{index} 里 kind==3 的槽 = 达到该阶段后解锁的后续配方 id。
UNLOCK_EFFECT = 3


def recipe_phase(recipe: dict, exp: int) -> int:
    """已达阶段 = 满足的经验阈值个数 (上限 len-1), 对齐客户端 GetExpPhase。"""
    thresholds = [int(t) for t in (recipe.get("exp") or [])]
    if not thresholds:
        return 0
    return min(sum(int(exp) >= t for t in thresholds), len(thresholds) - 1)


def unlocked_recipes(recipe: dict, exp: int) -> list[str]:
    """该配方在当前经验下解锁的后续配方 id (字符串形态, 与 catalog 键一致)。"""
    ids: list[str] = []
    slots = recipe.get("effects") or []
    for index in range(1, recipe_phase(recipe, exp) + 1):
        if index - 1 < len(slots) and int(slots[index - 1][0]) == UNLOCK_EFFECT:
            ids.extend(str(int(v)) for v in slots[index - 1][1])
    return ids


def normalize_recipe_exp(recipe_exp: dict) -> dict:
    """从 RecipeLevel==1 出发按解锁链级联算出解锁集合; 未解锁的配方**不入表**。

    下发时未解锁取 -1 (与官方 CollegeRecipe 快照同口径)。已解锁配方保留原经验。
    这同时是一次迁移: 旧实现对全部 60 条配方无条件 seed 0, 这里会丢掉不可达的键,
    使「做了三次才该解锁」恢复成官方节奏。
    """
    recipes = catalog()["recipes"]
    out: dict[str, int] = {}
    pending: list[str] = []
    for key, recipe in recipes.items():
        if int(recipe["level"]) == 1:
            out[key] = max(0, int(recipe_exp.get(key, 0)))
            pending.append(key)
    while pending:
        key = pending.pop()
        for rid in unlocked_recipes(recipes[key], out[key]):
            if rid in recipes and rid not in out:
                out[rid] = max(0, int(recipe_exp.get(rid, 0)))
                pending.append(rid)
    return out


def advice_energy(gold: int) -> int:
    """换委托 (600) 的星能成本 = ceil(Gold / denominator * amount)。

    表内值: 客户端 GlobalParamString 的 AlchemyAdviceParam = "10000|2" (即 1 万金币
    折 2 星能), 与上游 college_alchemy.py 的 price_param 同一口径、同一条表项。
    """
    param = _compat()["advice_star_energy"]
    denominator = int(param["denominator"])
    amount = int(param["amount"])
    if denominator <= 0 or amount <= 0:
        return 0
    return -(-int(gold) * amount // denominator)


# 顾客交易的计价开关 (C2L_AlchemyFinish 的 plusPrice / discountPrice), 表值同样取自客户端
# GlobalParamString, 与上游 college_alchemy.py 的 _trade / price_param 一一对应:
#   AlchemyPriceParam    = "5000|15"  加价收星能 = ceil(base_gold / 5000 * 15)
#   AlchemyDiscountParam = "2500|5"   打折得默契 = ceil(base_gold / (2500*2) * 5)
#   AlchemyPriceNum      = 2000       加价金币倍率 = 2000 * 0.001 = ×2.0
#   AlchemyDiscountNum   = 500        打折金币倍率 = 500 * 0.001 = ×0.5
# base_gold 是 CollegeQuest.AwardGroup[0] —— 这位顾客的**基础**金币奖励 (未乘倍率)。
TRADE_PRICE_PARAM = (5000, 15)
TRADE_DISCOUNT_PARAM = (2500, 5)
TRADE_PRICE_MULTIPLIER = 2.0
TRADE_DISCOUNT_MULTIPLIER = 0.5
# 打折加默契随 L2C_FavorChangeInfo 下发, type 取上游 _trade 实际用的 13 (客户端 AddFavorType
# 这一档未命名)。与送礼/触摸的 6/7/0 区分开, 客户端据此播对应的提示。
ADD_FAVOR_TYPE_ALCHEMY_DISCOUNT = 13


def trade_price_param(price: int, param: tuple[int, int], divisor: int = 1) -> int:
    """``ceil(price / (denominator * divisor) * amount)``, 与上游 ``price_param`` 同口径。

    原生 ``GetAddPriceStarEnergy`` / ``GetDiscountFavory`` 走 float32 除乘后 ``CeilToInt``,
    对表里这组整数而言与整数向上取整完全一致 (上游的 f32 版见 work/_up_college_alchemy.py)。
    """
    denominator, amount = param
    if denominator <= 0 or amount <= 0:
        return 0
    return -(-int(price) * amount // (denominator * divisor))


class AlchemyStateRepository:
    """炼金的三张表: 元素/配方经验/增益 (state)、产槽 (production)、顾客 (customers)。

    ``peek``/``stage`` 是不带 ``with self.store.db`` 的裸读写版本 —— AlchemyService
    已经在 ``economy.transaction()`` 里, 内层 commit 会提前释放 savepoint
    (与 player/college.py 的同一约定)。
    """

    def __init__(self, store, clock=None):
        self.store = store
        self.clock = clock or ServerClock()
        with store.db:
            store.db.execute("""CREATE TABLE IF NOT EXISTS alchemy_state (
                player_id INTEGER PRIMARY KEY REFERENCES players(id),
                element_num_json TEXT NOT NULL, element_recover_at_json TEXT NOT NULL,
                element_buy_day_json TEXT NOT NULL, element_buy_count_json TEXT NOT NULL,
                recipe_exp_json TEXT NOT NULL, buff_type INTEGER NOT NULL,
                buff_count INTEGER NOT NULL, buff_at INTEGER NOT NULL,
                created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS alchemy_production (
                player_id INTEGER NOT NULL, slot INTEGER NOT NULL,
                recipe_id INTEGER NOT NULL, start_at INTEGER NOT NULL,
                end_at INTEGER NOT NULL, buffs_json TEXT NOT NULL,
                PRIMARY KEY (player_id, slot))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS alchemy_customers (
                player_id INTEGER NOT NULL, slot INTEGER NOT NULL,
                quest_id INTEGER NOT NULL, item_json TEXT NOT NULL,
                item_num_json TEXT NOT NULL, type INTEGER NOT NULL,
                advise_item_id INTEGER NOT NULL, param INTEGER NOT NULL,
                result INTEGER NOT NULL, transaction_num INTEGER NOT NULL,
                transaction_recover_at INTEGER NOT NULL,
                PRIMARY KEY (player_id, slot))""")

    # ---- state -----------------------------------------------------------

    def initial_state(self, now: int) -> dict:
        ids = [str(row["id"]) for row in element_rows()]
        cap = {str(row["id"]): int(row["cap"]) for row in element_rows()}
        day = day_index(now)
        return {
            "element_num": dict(cap),
            "element_recover_at": {key: now for key in ids},
            "element_buy_day": {key: day for key in ids},
            "element_buy_count": {key: 0 for key in ids},
            "recipe_exp": normalize_recipe_exp({}),
            "buff_type": 0, "buff_count": 0, "buff_at": 0,
        }

    def peek(self, player_id: int) -> dict:
        now = self.clock.now()
        columns = ("""SELECT element_num_json, element_recover_at_json,
            element_buy_day_json, element_buy_count_json, recipe_exp_json,
            buff_type, buff_count, buff_at FROM alchemy_state WHERE player_id=?""")
        row = self.store.db.execute(columns, (player_id,)).fetchone()
        if row is None:
            # 只在真正缺行时写: 已存在时 peek 必须是**纯读**, 否则在事务外调用
            # (push_growth_base_alchemy) 会因为这条 INSERT OR IGNORE 开启一个未提交的
            # 写事务, 把库锁住, 让别的连接 (modifier/邮件推送) 报 "database is locked"。
            seed = self.initial_state(now)
            self.store.db.execute("""INSERT INTO alchemy_state
                (player_id,element_num_json,element_recover_at_json,element_buy_day_json,
                 element_buy_count_json,recipe_exp_json,buff_type,buff_count,buff_at,
                 created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (player_id, json.dumps(seed["element_num"], sort_keys=True),
                 json.dumps(seed["element_recover_at"], sort_keys=True),
                 json.dumps(seed["element_buy_day"], sort_keys=True),
                 json.dumps(seed["element_buy_count"], sort_keys=True),
                 json.dumps(seed["recipe_exp"], sort_keys=True),
                 0, 0, 0, now, now))
            row = self.store.db.execute(columns, (player_id,)).fetchone()
        state = {
            "element_num": json.loads(row[0]),
            "element_recover_at": json.loads(row[1]),
            "element_buy_day": json.loads(row[2]),
            "element_buy_count": json.loads(row[3]),
            "recipe_exp": json.loads(row[4]),
            "buff_type": int(row[5]), "buff_count": int(row[6]), "buff_at": int(row[7]),
        }
        # 解锁集合由 level 1 配方 + 经验阈值级联推出; 未解锁的配方不入表 (下发时 -1)。
        state["recipe_exp"] = normalize_recipe_exp(state["recipe_exp"])
        for key in state["element_num"]:
            state["element_recover_at"].setdefault(key, now)
            state["element_buy_day"].setdefault(key, day_index(now))
            state["element_buy_count"].setdefault(key, 0)
        return state

    def stage(self, player_id: int, state: dict) -> None:
        self.store.db.execute("""UPDATE alchemy_state SET
            element_num_json=?, element_recover_at_json=?, element_buy_day_json=?,
            element_buy_count_json=?, recipe_exp_json=?, buff_type=?, buff_count=?,
            buff_at=?, updated_at=? WHERE player_id=?""",
            (json.dumps(state["element_num"], sort_keys=True),
             json.dumps(state["element_recover_at"], sort_keys=True),
             json.dumps(state["element_buy_day"], sort_keys=True),
             json.dumps(state["element_buy_count"], sort_keys=True),
             json.dumps(state["recipe_exp"], sort_keys=True),
             int(state["buff_type"]), int(state["buff_count"]), int(state["buff_at"]),
             self.clock.now(), player_id))

    def credit_elements(self, player_id: int, deltas: dict[int, int]) -> None:
        """把探索等玩法产出的元素记入元素池 (逐元素按上限截断)。

        上游旧实现把这些元素写进 ``college_state`` 快照的 ``alchemy.elements``,
        新实现元素池在 ``alchemy_state`` 表里, 所以探索结算改走这里, 否则元素奖励会
        落在一个没人读的字段上。
        """
        if not deltas:
            return
        now = self.clock.now()
        state = self.peek(player_id)
        settle_elements(state, now)
        keys = {str(row["id"]): int(row["cap"]) for row in element_rows()}
        for element_id, count in deltas.items():
            key = str(int(element_id))
            if key not in keys or count <= 0:
                continue
            state["element_num"][key] = min(keys[key],
                                           int(state["element_num"].get(key, 0)) + int(count))
        self.stage(player_id, state)

    # ---- production / customers -----------------------------------------

    def production_rows(self, player_id: int) -> dict[int, dict]:
        rows = self.store.db.execute("""SELECT slot,recipe_id,start_at,end_at,buffs_json
            FROM alchemy_production WHERE player_id=?""", (player_id,)).fetchall()
        return {int(r[0]): {"recipeId": int(r[1]), "startAt": int(r[2]),
                            "endAt": int(r[3]), "buffs": json.loads(r[4])} for r in rows}

    def put_production(self, player_id: int, slot: int, recipe_id: int,
                       start_at: int, end_at: int, buffs=()) -> None:
        self.store.db.execute("""INSERT INTO alchemy_production
            (player_id,slot,recipe_id,start_at,end_at,buffs_json) VALUES (?,?,?,?,?,?)
            ON CONFLICT(player_id,slot) DO UPDATE SET recipe_id=excluded.recipe_id,
            start_at=excluded.start_at,end_at=excluded.end_at,buffs_json=excluded.buffs_json""",
            (player_id, slot, recipe_id, start_at, end_at, json.dumps(list(buffs))))

    def drop_production(self, player_id: int, slot: int) -> None:
        self.store.db.execute("DELETE FROM alchemy_production WHERE player_id=? AND slot=?",
                              (player_id, slot))

    def customer_rows(self, player_id: int) -> dict[int, dict]:
        rows = self.store.db.execute("""SELECT slot,quest_id,item_json,item_num_json,type,
            advise_item_id,param,result,transaction_num,transaction_recover_at
            FROM alchemy_customers WHERE player_id=?""", (player_id,)).fetchall()
        return {int(r[0]): {"questId": int(r[1]), "itemId": json.loads(r[2]),
                            "itemNum": json.loads(r[3]), "type": int(r[4]),
                            "adviseItemId": int(r[5]), "param": int(r[6]),
                            "result": int(r[7]), "transactionNum": int(r[8]),
                            "transactionRecoverAt": int(r[9])} for r in rows}

    def put_customer(self, player_id: int, slot: int, row: dict) -> None:
        self.store.db.execute("""INSERT INTO alchemy_customers
            (player_id,slot,quest_id,item_json,item_num_json,type,advise_item_id,param,
             result,transaction_num,transaction_recover_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(player_id,slot) DO UPDATE SET quest_id=excluded.quest_id,
            item_json=excluded.item_json,item_num_json=excluded.item_num_json,
            type=excluded.type,advise_item_id=excluded.advise_item_id,param=excluded.param,
            result=excluded.result,transaction_num=excluded.transaction_num,
            transaction_recover_at=excluded.transaction_recover_at""",
            (player_id, slot, row["questId"], json.dumps(row["itemId"]),
             json.dumps(row["itemNum"]), row["type"], row["adviseItemId"], row["param"],
             row["result"], row["transactionNum"], row["transactionRecoverAt"]))


def settle_elements(state: dict, now: int) -> None:
    """惰性恢复元素 + 跨天重置 buyTimesDay (就地改 state)。"""
    compat = _compat()
    recover = int(compat["element_recover_sec"])
    for row in element_rows():
        key = str(row["id"])
        cap = int(row["cap"])
        gain = int(row["recoverNum"])
        num = int(state["element_num"].get(key, 0))
        at = int(state["element_recover_at"].get(key, now)) or now
        if num >= cap:
            state["element_recover_at"][key] = now
        elif recover > 0 and now >= at + recover:
            ticks = (now - at) // recover
            num = min(cap, num + ticks * gain)
            state["element_recover_at"][key] = now if num >= cap else at + ticks * recover
        state["element_num"][key] = num
        if int(state["element_buy_day"].get(key, -1)) != day_index(now):
            state["element_buy_day"][key] = day_index(now)
            state["element_buy_count"][key] = 0


class AlchemyService:
    """12 对炼金消息 + 617 推送的真实现; 口径见本模块 docstring。"""

    def __init__(self, repository: AlchemyStateRepository, economy, college=None, clock=None):
        self.repo = repository
        self.economy = economy
        # 617 里的 starEnergy/starGainTime 属于学院快照, 由 player/college.py 提供。
        self.college = college
        self.clock = clock or ServerClock()

    def handlers(self):
        return {"C2L_" + name: self.handle for name, _, _ in ALCHEMY_IDS}

    # ---- internals -------------------------------------------------------

    def _inventory_quantity(self, player_id: int, item_id: int) -> int | None:
        row = self.repo.store.db.execute(
            "SELECT quantity FROM inventory WHERE player_id=? AND item_id=?",
            (player_id, item_id)).fetchone()
        return None if row is None else int(row[0])

    def _pay(self, player_id: int, snapshot: dict, costs, elements: dict | None = None) -> int:
        """先整单校验再扣 (拒绝时不留半截扣费); 返回 0 或错误码。

        ``elements`` 非空时, 成本里的炼金元素币 (1237991..1237996) 改从**元素池**结算,
        而不是查背包 —— 客户端正是用元素池数量算「拥有」并点亮制作按钮的。
        """
        for item_id, num in costs:
            if num <= 0:
                continue
            element_id = element_currency_id(item_id) if elements is not None else None
            if element_id is not None:
                if int(elements.get(str(element_id), 0)) < num:
                    return ALCHEMY_NO_ITEM
            elif item_id in self.economy.CURRENCIES:
                if int(snapshot.get(self.economy.CURRENCIES[item_id], 0)) < num:
                    return ALCHEMY_LIMIT_GOLD
            elif item_id == STAMINA_ITEM:
                if int(snapshot.get("mobility", {}).get("power", 0)) < num:
                    return ALCHEMY_LIMIT_GOLD
            else:
                have = self._inventory_quantity(player_id, item_id)
                if have is None or have < num:
                    return ALCHEMY_NO_ITEM
        for item_id, num in costs:
            if num <= 0:
                continue
            element_id = element_currency_id(item_id) if elements is not None else None
            if element_id is not None:
                elements[str(element_id)] = int(elements.get(str(element_id), 0)) - num
            else:
                self.economy._spend(player_id, snapshot, item_id, num)
        self.economy.save_snapshot(player_id, snapshot)
        return 0

    def _quest_outcome(self, quest_id: int):
        """按 CollegeQuest 表算出一位顾客的产出: (item->count, buff | None)。"""
        quest = catalog()["quests"].get(str(quest_id))
        if quest is None:
            return {}, None
        kind, group = quest["awardType"], quest["awardGroup"]
        if kind == 2 and group:
            return {GOLD_ITEM: int(group[0])}, None
        if kind == 3 and len(group) >= 2:
            return {}, {"type": int(group[0]), "count": int(group[1])}
        if kind == 1 and group:
            try:
                return dict(self.economy.gifts(list(group))), None
            except UnresolvedEconomy as exc:
                LOGGER.info("alchemy customer quest %s gift group unresolved: %s", quest_id, exc)
        return {}, None

    def _grant(self, player_id: int, source: str, rewards: dict) -> dict:
        if not rewards:
            return {}
        return self.economy._grant(player_id, source, rewards)

    def _settle(self, player_id: int, state: dict, now: int) -> None:
        settle_elements(state, now)

    def _element_values(self, state: dict) -> list[bytes]:
        return [ELEMENT.encode({"elementId": int(row["id"]),
                                "num": int(state["element_num"].get(str(row["id"]), 0)),
                                "lastRecoverTime": int(state["element_recover_at"].get(str(row["id"]), 0)),
                                "buyTimesDay": int(state["element_buy_count"].get(str(row["id"]), 0))})
                for row in element_rows()]

    def _customer_info(self, row: dict) -> bytes:
        return CUSTOMER_INFO.encode({
            "questId": int(row["questId"]),
            "itemId": [int(v) for v in row["itemId"]],
            "itemNum": [int(v) for v in row["itemNum"]],
            "type": int(row["type"]), "adviseItemId": int(row["adviseItemId"]),
            "param": int(row["param"]), "result": int(row["result"])})

    def _production_bar(self, row: dict) -> bytes:
        return PRODUCTION_BAR.encode({
            "recipeId": int(row["recipeId"]), "endTime": int(row["endAt"]),
            "buffId": [int(v) for v in row.get("buffs", ())]})

    def _customer_stale(self, row: dict | None, now: int) -> bool:
        """陈旧/占位数据判定: 为真则就地重建该顾客。

        questId==0 是空槽占位。其它两种情况来自早先写错的生成逻辑, 存档里会一直留着,
        客户端于是「图标空白、点开没有内容」:
          - adviseItemId==0 或 itemId 为空 —— 旧版没有交付物;
          - itemId[0] 反查不到任何 CollegeRecipe 的产物 —— 旧版把**奖励** (如金币
            1237901) 当成交付物写了进去。客户端 OnRefrshNeedInfo 拿 itemId[0] 查配方,
            查不到就点不开、也算不出「需求/拥有」。

        最后一条是**跨日即陈旧**: 顾客行里的 transactionRecoverAt 记的是「生成当天的
        日末」(见 _new_customer 的 day_end, 与离线端 day_end_unix 同口径)。到点就换一批
        人, 否则顾客一旦生成就被 put_customer 持久化, 5 个槽位会永远锁定同一批顾客 ——
        CollegeCustomer 里 38 位 Type==1 的顾客根本轮不到, 用户看到的就成了「来来回回就
        这五个」。
        """
        if row is None or int(row["questId"]) == 0:
            return True
        if int(row["adviseItemId"]) == 0 or not row["itemId"]:
            return True
        # 已结算 (完成/拒绝过一次) 也算陈旧: 旧实现只把 result 置 1 就不管了, 顾客行又不会
        # 轮换, 于是这个槽当天彻底点不动 —— 客户端再点「完成/拒绝」服务端恒回 13 (操作失败)。
        # 判为陈旧后该槽就地换下一位顾客, 槽位永远可交易。
        if int(row["result"]) != 0:
            return True
        if now >= int(row.get("transactionRecoverAt", 0)):
            return True
        # type 必须是 2 (普通交易顾客)。客户端 CollegeShopMain_CustomerNode_Refresh 只在
        # type==2 时把 mTradeIcon 设为「所需道具的图标」, 其余类型显示 mLargeQuestion
        # (感叹号占位); CollegeAlchemyModule_GetTradeCustomerCount / GetNextCustormer 也只
        # 统计 type==2 —— type!=2 时"提交委托"的顾客计数恒为 0, 按钮不可用。旧版生成逻辑
        # 写了 CollegeCustomer.Type (=1), 存档里会一直留着, 这里就地重建。
        if int(row["type"]) != 2:
            return True
        products = {int(recipe["productId"]) for recipe in catalog()["recipes"].values()}
        if int(row["itemId"][0]) not in products:
            return True
        # adviseItemId == itemId[0] 时「换委托/委派」(600) 没有可换的替代品, 客户端点下去
        # 只会拿到 13 —— 旧生成逻辑正是这么写的 (adviseItemId 直接抄了 itemId[0]), 就地
        # 重建成本次修复后的顾客行 (adviseItemId 是 likes 里的另一条配方产物)。
        return int(row["adviseItemId"]) == int(row["itemId"][0])

    def _customer_delivery(self, likes) -> tuple[int, int] | None:
        """顾客 Like(f6) 里的元素 (991..996) 与 CollegeRecipe.RecipeType(f2) 同域。取顾客喜欢的
        元素对应的配方里 level(f3) 最低的一条, 返回它的产物 (ProductID, ProductNum) —— 这就是
        委托要交付的东西 (客户端拿它算「需求/拥有」)。对齐 cpp customer_delivery (219-237)。
        """
        if not likes:
            return None
        best: tuple[int, int] | None = None
        best_level = 0
        for recipe in catalog()["recipes"].values():
            if int(recipe["type"]) not in likes:
                continue
            product_id = int(recipe["productId"])
            product_num = int(recipe["productNum"])
            if product_id <= 0 or product_num <= 0:
                continue
            level = int(recipe["level"])
            if best is None or level < best_level:
                best = (product_id, product_num)
                best_level = level
        return best

    def _customer_advise(self, likes, current_product: int) -> tuple[int, int] | None:
        """顾客「建议」的替代产物 —— 换委托 (600) 之后顾客改为要的东西。

        对齐上游 college.py `_customer_for` 的 `adviseItemId = recipes[element]['2']`:
        同一位顾客的**下一条配方** (上游取同元素第二级; 我们按 level 升序找与当前交付物
        不同的那条, 于是 991/992 两位元素都喜欢的顾客会拿到另一元素的同级产物)。
        找不到替代品 (理论上不会: 每个元素有 8 级配方) 时返回 None, 调用方退回原产物,
        此时 600 会按上游语义回 13 (无可换的委托)。
        """
        if not likes:
            return None
        best: tuple[int, int] | None = None
        best_level = 0
        for recipe in catalog()["recipes"].values():
            if int(recipe["type"]) not in likes:
                continue
            product_id = int(recipe["productId"])
            product_num = int(recipe["productNum"])
            if product_id <= 0 or product_num <= 0 or product_id == int(current_product):
                continue
            level = int(recipe["level"])
            if best is None or level < best_level:
                best = (product_id, product_num)
                best_level = level
        return best

    def _new_customer(self, player_id: int, slot: int, now: int,
                      avoid_param: int = 0) -> dict:
        """按 cpp new_customer (239-298) 生成缺省顾客。

        只收 Type==1 的炼金顾客: Type 2 是活动特殊顾客, 名下没有正式委托, 抽到只会白图标 +
        奖励 0。分布按「账号 + 槽位*3 + 游戏日*13」确定: 同槽当日内稳定、每天轮换, 相邻槽位
        不撞同一位。委托只收 QuestType==1 且 AwardType==1 且 Gift 能展出的那条; itemId/itemNum
        是「要交付的产物」而不是奖励 (客户端 OnRefrshNeedInfo 用它算需求/拥有, itemId[0] 还要能
        反查到 CollegeRecipe)。

        avoid_param = 正被替换掉的那位顾客的 param。只按 (账号, 槽位, 游戏日) 取种子是**确定性**
        的 —— 结算/拒绝后重建拿到的还是同一位, 玩家看到的就是「来来回回就那五个」。带上它会
        强制换人; 顺延过程中没有合格委托的顾客也跳过, 不会留出空槽 (questId==0)。

        另外要跳过**已在别的槽位出现**的顾客 (param 相同即同一位神格): 顺延只管「不换回刚走
        的那位」, 落点仍可能撞上旁边槽里的人, 玩家看到的就是「同一个神格来了两次」。

        注意: 这里挑的是**表** CollegeCustomer.Type==1 的顾客行, 而写进 CustomerInfo 的
        ``type`` 字段固定为 **2** —— 客户端把 CustomerInfo.type==2 当作"普通交易委托"
        (见 _customer_stale 的说明), 与表里的 CollegeCustomer.Type 不是同一套取值。
        """
        day_end = int(day_period(now)[1])
        empty = {"questId": 0, "itemId": [], "itemNum": [], "type": 0,
                 "adviseItemId": 0, "param": 0, "result": 0,
                 "transactionNum": 0, "transactionRecoverAt": day_end}
        customers = catalog()["customers"]
        params = {int(key): int(value["param"]) for key, value in customers.items()
                  if int(value["type"]) == 1}
        ids = sorted(params)
        if not ids:
            return empty
        # 其它槽位上已经站着的顾客 (param == 神格 id)。本槽自己的旧行不算, 它正是被换掉的
        # 那位。逐槽重建时调用方已经 put 过前面几槽, 所以这里现读一次就能拿到最新分布。
        present = {int(row["param"]) for other, row in self.repo.customer_rows(player_id).items()
                   if other != slot and int(row["param"]) > 0}
        # 起点: 首次生成用当日确定种子 (同槽当日内稳定、相邻槽位错开); 换人时从"被换掉那位"
        # 在候选环里的**下一位**开始扫。只靠 avoid_param 跳过而不前进的话, 连续结算会在第
        # 0/1 位之间来回弹 (实测 7 次结算只在 2 位顾客之间循环), 38 位顾客永远轮不到。
        start = player_id + slot * 3 + day_index(now) * 13
        if avoid_param:
            for index, item in enumerate(ids):
                if params[item] == int(avoid_param):
                    start = index + 1
                    break
        fallback: dict | None = None
        for step in range(len(ids)):
            seed = start + step
            built = self._build_customer(customers[str(ids[seed % len(ids)])], seed, day_end)
            if built["questId"] == 0:
                continue
            if int(built["param"]) in present:
                # 全场都是熟人 (理论上 38 位顾客 vs 5 个槽不可能) 时才退回第一个合格项,
                # 至少保证槽里有委托可做, 不会留空。
                if fallback is None:
                    fallback = built
                continue
            return built
        return fallback if fallback is not None else empty

    def _build_customer(self, customer: dict, seed: int, day_end: int) -> dict:
        """把一条 CollegeCustomer 表行摊成可交易的委托; 名下没有合格委托时 questId 留 0。"""
        base = {"questId": 0, "itemId": [], "itemNum": [],
                "type": 2, "adviseItemId": 0,
                "param": int(customer["param"]), "result": 0,
                # 592 的 transactionNum 照上游 college.py `_single_customer` 回 1 (旧实现回 0)。
                # 反汇编核实: 客户端里这个字段只被 PlayerDbDataMerge_Merge 读走, 并不是
                # 「换委托/委派」(mbtnSuggest) 的开关 —— 那个开关是同一条包里
                # itemId[0] == adviseItemId (见 CollegeCustomerDetil_Refresh)。这里改成 1
                # 只是为了与老大那份**实测可用**的服务端口径一致, 不是委派能用的原因。
                "transactionNum": 1, "transactionRecoverAt": day_end}
        quests = catalog()["quests"]
        order_qids = []
        for qid in customer["quests"]:
            quest = quests.get(str(qid))
            if quest is None:
                continue
            if int(quest["type"]) != 1 or int(quest["awardType"]) != 1:
                continue
            rewards, _ = self._quest_outcome(int(qid))
            if not rewards:
                continue
            order_qids.append(int(qid))
        if not order_qids:
            return base
        order_qids.sort()
        base["questId"] = order_qids[seed % len(order_qids)]
        delivery = self._customer_delivery(customer["like"])
        if delivery is not None:
            base["itemId"] = [delivery[0]]
            base["itemNum"] = [delivery[1]]
            advise = self._customer_advise(customer["like"], delivery[0])
            base["adviseItemId"] = advise[0] if advise is not None else delivery[0]
        return base

    # ---- the single entry point -----------------------------------------

    async def handle(self, context, packet) -> OutboundMessage:
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("alchemy requested before login")
        name = CORE_MESSAGE_REGISTRY.name_for(packet.message_id)
        request = ALCHEMY_SCHEMAS[name].decode(packet.body)
        response = name.replace("C2L_", "L2C_", 1)
        now = self.clock.now()
        values: dict = {"code": ALCHEMY_OK}
        before: list[OutboundMessage] = []
        try:
            with self.economy.transaction():
                state = self.repo.peek(player_id)
                self._settle(player_id, state, now)
                self._dispatch(player_id, name, request, state, now, values, before)
                self.repo.stage(player_id, state)
        except UnresolvedEconomy as exc:
            LOGGER.info("alchemy denied player=%s message=%s reason=%s", player_id, name, exc)
            return OutboundMessage(response, {"code": ALCHEMY_ERROR_OPT})
        LOGGER.info("alchemy player=%s message=%s values=%s", player_id, name, values)
        pushes = list(self.economy.pushes(player_id))
        pushes.append(self.push_growth_base_alchemy(player_id))
        return OutboundMessage(response, values, before_response=tuple(before),
                               pushes=tuple(pushes))

    def _dispatch(self, player_id, name, request, state, now, values, before) -> None:
        method = getattr(self, "_" + name[len("C2L_"):], None)
        if method is None:
            values["code"] = ALCHEMY_CONFIG
            return
        method(player_id, request, state, now, values, before)

    # ---- 590 -------------------------------------------------------------

    def _AlchemyMainData(self, player_id, request, state, now, values, before) -> None:
        customer_rows = self.repo.customer_rows(player_id)
        production_rows = self.repo.production_rows(player_id)
        customers = int(_compat()["customer_slots"])
        productions = int(_compat()["production_slots"])
        # 顾客槽必须全发真顾客: 发空 message 时客户端会回落成「实验室主人」占位 (浮士德 +
        # 白卡无图标)。缺槽 / quest_id==0 的旧占位就地重新生成并入档 (本方法在事务内)。
        customeres = []
        for slot in range(customers):
            row = customer_rows.get(slot)
            if self._customer_stale(row, now):
                row = self._new_customer(player_id, slot, now,
                                         avoid_param=int(row["param"]) if row else 0)
                self.repo.put_customer(player_id, slot, row)
            customeres.append(self._customer_info(row))
        recipes = catalog()["recipes"]
        values.update(
            # 全量下发, 未解锁配方取 -1 (官方快照口径): 客户端据此把该配方置灰。
            recipeIdExp=[KEY_VALUE_PAIR.encode({
                "Key": int(rid), "Value": int(state["recipe_exp"].get(rid, -1))})
                for rid in sorted(recipes, key=int)],
            customeres=customeres,
            productionBars=[self._production_bar(production_rows[slot]) if slot in production_rows else b""
                            for slot in range(productions)],
            elements=self._element_values(state),
            buffType=int(state["buff_type"]), buffCount=int(state["buff_count"]))

    # ---- 592 -------------------------------------------------------------

    def _SingleCustomerInfo(self, player_id, request, state, now, values, before) -> None:
        slot = int(request.get("posIndex", -1))
        values.update(posIndex=slot, transactionNum=0, transactionLastRecoverTime=0)
        if not 0 <= slot < int(_compat()["customer_slots"]):
            values["code"] = ALCHEMY_ERROR_OPT
            return
        rows = self.repo.customer_rows(player_id)
        row = rows.get(slot)
        if self._customer_stale(row, now):
            row = self._new_customer(player_id, slot, now,
                                     avoid_param=int(row["param"]) if row else 0)
        self.repo.put_customer(player_id, slot, row)
        values.update(customere=self._customer_info(row), transactionNum=int(row["transactionNum"]),
                      transactionLastRecoverTime=int(row["transactionRecoverAt"]))

    # ---- 594 MakeItem ----------------------------------------------------

    def _MakeItem(self, player_id, request, state, now, values, before) -> None:
        slot = int(request.get("posIndex", -1))
        recipe_id = int(request.get("recipeId", 0))
        values.update(posIndex=slot, productionBar=b"")
        if not 0 <= slot < int(_compat()["production_slots"]):
            values["code"] = ALCHEMY_ERROR_OPT
            return
        recipe = catalog()["recipes"].get(str(recipe_id))
        if recipe is None:
            values["code"] = ALCHEMY_CONFIG
            return
        if slot in self.repo.production_rows(player_id):
            values["code"] = ALCHEMY_BUSY
            return
        if int(state["recipe_exp"].get(str(recipe_id), -1)) < 0:
            # 未解锁的配方 (客户端不会提供入口; 伪造请求也一律拒绝)。
            values["code"] = ALCHEMY_ERROR_OPT
            return
        element_key = str(recipe["type"])
        pay = int(recipe["pay"])
        if int(state["element_num"].get(element_key, 0)) < pay:
            values["code"] = ALCHEMY_NO_ITEM
            return
        costs = [[GOLD_ITEM, int(recipe["gold"])]]
        costs += [[int(item), int(num)] for item, num in zip(recipe["itemGroup"], recipe["itemNum"])]
        snapshot = self.repo.store.get(player_id)["snapshot"]
        # 元素币材料 (1237991..1237996) 从元素池扣, 其余走背包/货币。
        error = self._pay(player_id, snapshot, costs, state["element_num"])
        if error:
            values["code"] = error
            return
        state["element_num"][element_key] = int(state["element_num"].get(element_key, 0)) - pay
        end_at = now + int(recipe["waitSec"])
        self.repo.put_production(player_id, slot, recipe_id, now, end_at)
        values["productionBar"] = self._production_bar(
            {"recipeId": recipe_id, "endAt": end_at, "buffs": ()})

    # ---- 596 MakIngSpeed -------------------------------------------------

    def _MakIngSpeed(self, player_id, request, state, now, values, before) -> None:
        slot = int(request.get("posIndex", -1))
        kind = int(request.get("type", 0))
        values.update(posIndex=slot)
        rows = self.repo.production_rows(player_id)
        row = rows.get(slot)
        if row is None:
            values["code"] = ALCHEMY_ERROR_OPT
            return
        tier = next((t for t in _compat()["speed_tiers"] if int(t["type"]) == kind), None)
        if tier is None:
            values["code"] = ALCHEMY_CONFIG
            return
        snapshot = self.repo.store.get(player_id)["snapshot"]
        error = self._pay(player_id, snapshot, [[int(tier["itemId"]), int(tier["num"])]])
        if error:
            values["code"] = error
            return
        self.repo.put_production(player_id, slot, row["recipeId"], row["startAt"], now, row["buffs"])

    # ---- 598 AlchemyFinish ----------------------------------------------

    def _AlchemyFinish(self, player_id, request, state, now, values, before) -> None:
        kind = int(request.get("type", 0))
        slot = int(request.get("posIndex", -1))
        values.update(type=kind, posIndex=slot, rewardData=REWARD.encode({}), alchemyType=kind)
        rows = self.repo.customer_rows(player_id)
        row = rows.get(slot)
        if row is None:
            values["code"] = ALCHEMY_ERROR_OPT
            return
        if int(row["result"]) != 0:
            # 该槽的委托已经结算过了 (客户端重复点「完成/拒绝」, 或它拿的还是旧卡片)。
            # 不重复发奖、也不再回 13 (那是用户看到的「操作失败」), 只把槽换成下一位顾客
            # 后回成功, 让客户端刷新成可交易的委托。
            self.repo.put_customer(player_id, slot, self._new_customer(
                player_id, slot, now, avoid_param=int(row["param"])))
            return
        if kind == 2:
            # 拒绝委托: 不交付产物、不发放奖励, 顾客离场 (result=1 -> 下次读取时换人)。
            row["result"] = 1
            self.repo.put_customer(player_id, slot, row)
            return
        # 计价开关 (客户端 598 的 plusPrice / discountPrice)。两者互斥: 同时为真视为非法
        # 请求 (与上游 _trade 的 `plus and discount` 判定一致)。口径取自 GlobalParamString:
        #   plus     加价: 按 AlchemyPriceParam 收星能 (不足整单拒绝回 38), 金币 ×2.0
        #   discount 打折: 金币 ×0.5, 并按 AlchemyDiscountParam 给这位顾客对应的神格加默契
        plus = bool(request.get("plusPrice", False))
        discount = bool(request.get("discountPrice", False))
        if plus and discount:
            values["code"] = ALCHEMY_ERROR_OPT
            return
        rewards, buff = self._quest_outcome(int(row["questId"]))
        base_gold = int(rewards.get(GOLD_ITEM, 0))
        # 星能不足要在**扣交付物之前**就拒绝 (上游同序): 否则玩家付了产物却拿不到加价。
        if plus and not self._spend_star_energy(
                player_id, now, trade_price_param(base_gold, TRADE_PRICE_PARAM)):
            values["code"] = ALCHEMY_NO_ENERGY
            return
        # 完成委托 = 交付顾客要求的产物 (CustomerInfo.itemId/itemNum), 换 CollegeQuest 的奖励。
        # 客户端 CollegeCustomerDetil_OnSendTransaction 也是先 CheckItemEnough 再发本消息的,
        # 所以这里必须真扣 —— 否则「拥有」永远停在 1/1, 就是用户看到的「数额对不上」。
        need = [(int(item), int(num))
                for item, num in zip(row["itemId"], row["itemNum"]) if int(num) > 0]
        if need:
            snapshot = self.repo.store.get(player_id)["snapshot"]
            error = self._pay(player_id, snapshot, need)
            if error:
                values["code"] = error
                return
        if base_gold > 0 and (plus or discount):
            multiplier = TRADE_PRICE_MULTIPLIER if plus else TRADE_DISCOUNT_MULTIPLIER
            rewards = dict(rewards)
            rewards[GOLD_ITEM] = math.floor(base_gold * multiplier)
        source = "alchemy-finish:%s:%s:%s" % (player_id, slot, row["questId"])
        self._grant(player_id, source, rewards)
        if buff is not None:
            state["buff_type"] = buff["type"]
            state["buff_count"] = buff["count"]
            state["buff_at"] = now
        if discount:
            # 打折加默契的基数与上游 _trade 的 base_gold 同口径: 客人要的每件产物按它配方的
            # **基础**售价 (CollegeRecipe.Gold) 乘件数求和。不能复用上面的 base_gold(= CollegeQuest
            # 的金币奖励): Chip 类委托 (AwardType=1) 的奖励是神格碎片不是金币, 取它恒为 0,
            # 于是 trade_price_param 算出 0 -> grant_favor 静默跳过, 表现为「打折从来不加默契」。
            favor_base = 0
            products = {int(recipe["productId"]): recipe
                        for recipe in catalog()["recipes"].values()}
            for item, quantity in zip(row["itemId"], row["itemNum"]):
                recipe = products.get(int(item))
                if recipe is None:
                    continue
                favor_base += int(recipe["gold"]) * (int(quantity) // max(1, int(recipe["productNum"])))
            # 给这位顾客对应的神格 (CollegeQuest.hero) 加默契, 走 FavorService 的官方曲线。
            # commit=False 是因为外层 economy.transaction() 已经开着 (见 favor.write_favor 的约定)。
            # 无英雄 / 零增益时 grant_favor 自己就不推送。
            hero_id = int((catalog()["quests"].get(str(row["questId"])) or {}).get("hero", 0))
            favor = getattr(self.economy, "favor", None)
            if favor is not None and hero_id > 0:
                before.extend(favor.grant_favor(
                    player_id, hero_id,
                    trade_price_param(favor_base, TRADE_DISCOUNT_PARAM, divisor=2),
                    commit=False, change_type=ADD_FAVOR_TYPE_ALCHEMY_DISCOUNT))
        # 每日/周常 炼金任务 (economy_catalog.json 的 task_conditions):
        #   630027/630113「在炼金实验室完成 N 次交易」 E_AlchemyDealTask=75
        #   630028/630114「在炼金实验室完成 N 次任务」 E_AlchemyQuestTask=76
        # 本服务端的顾客一律是 CustomerInfo.type==2 的「普通交易委托」: 客户端把它标成
        # AlchemyType.TRANSACTION(交易), 名下委托又取自 CollegeQuest.QuestType==1 (E_Chip,
        # 碎片任务)。一次成交同时满足「交易」与「完成任务」两种读法 (与 economy 里「一次购买
        # 既算 E_BuyGood 又算 E_BuyGold」同一设计), 所以两个条件一起记, 让这 4 条任务都能涨。
        # key 复用 source (含 slot/questId), 重放同一请求不会重复计数。
        if self.economy is not None:
            self.economy.record_event(
                player_id, source + ":deal", self.economy.TASK_EVENT_ALCHEMY_DEAL, 0, 1)
            self.economy.record_event(
                player_id, source + ":quest", self.economy.TASK_EVENT_ALCHEMY_QUEST, 0, 1)
        row["result"] = 1
        self.repo.put_customer(player_id, slot, row)
        values["rewardData"] = self.economy.reward_bytes_visible(rewards)
        values["alchemyType"] = int(row["type"]) if int(row["type"]) else kind

    # ---- 600 AlchemyButtonClick -----------------------------------------

    def _AlchemyButtonClick(self, player_id, request, state, now, values, before) -> None:
        """换委托 / 委派: 花星能, 让这位顾客改成要「建议」的那件产物。

        逐条对齐上游 college_alchemy.py 的 _suggest (只认 action==1):
          1. 顾客的 adviseItemId 反查 CollegeRecipe, 按 AlchemyAdviceParam 收星能 (不足回 38);
          2. itemId 换成建议产物, adviseItemId 记成刚才要的那件 (两件对调);
          3. 601 的 result 回**旧** itemId[0] —— 客户端 Refresh 正是拿它去查 Item[result]
             来画图标和读 Used[0] 算这个按钮的星能价格。
        其余 action (对话框等) 上游一律回 13, 这里同样。
        """
        slot = int(request.get("posIndex", -1))
        kind = int(request.get("type", 0))
        values.update(type=kind, posIndex=slot, result=0, param=0)
        if kind != 1 or not 0 <= slot < int(_compat()["customer_slots"]):
            values["code"] = ALCHEMY_ERROR_OPT
            return
        rows = self.repo.customer_rows(player_id)
        row = rows.get(slot)
        if self._customer_stale(row, now):
            row = self._new_customer(player_id, slot, now,
                                     avoid_param=int(row["param"]) if row else 0)
            self.repo.put_customer(player_id, slot, row)
        old_item = int(row["itemId"][0]) if row["itemId"] else 0
        recommendation = int(row["adviseItemId"])
        recipe = next((r for r in catalog()["recipes"].values()
                       if int(r["productId"]) == recommendation), None)
        if int(row["type"]) != 2 or recipe is None or recommendation == old_item:
            values["code"] = ALCHEMY_ERROR_OPT
            return
        if not self._spend_star_energy(player_id, now, advice_energy(int(recipe["gold"]))):
            values["code"] = ALCHEMY_NO_ENERGY
            return
        row["itemId"] = [recommendation]
        row["itemNum"] = [int(recipe["productNum"])]
        row["adviseItemId"] = old_item
        self.repo.put_customer(player_id, slot, row)
        values["result"] = old_item

    def _spend_star_energy(self, player_id: int, now: int, amount: int) -> bool:
        """扣星能 (不足返回 False)。星能属学院快照, 这里在同一个经济事务里读改写。

        用 college 的 ``peek``/``stage`` 而不是 ``load``/``save``: 后者带
        ``with self.store.db``, 会把外层 economy savepoint 提前提交
        (与 CollegeStateRepository 自己的约定一致)。
        """
        if amount <= 0:
            return True
        if self.college is None:
            return False
        college_state = self.college.peek(player_id)
        settle_star_energy(college_state, now)
        if int(college_state.get("star_energy", 0)) < amount:
            return False
        college_state["star_energy"] = int(college_state["star_energy"]) - amount
        self.college.stage(player_id, college_state)
        return True

    # ---- 602 AlchemyCollect ---------------------------------------------

    def _AlchemyCollect(self, player_id, request, state, now, values, before) -> None:
        slot = int(request.get("posIndex", -1))
        values.update(posIndex=slot, recipeId=0, exp=0, rewardData=REWARD.encode({}))
        rewarded = self._collect(player_id, state, slot, now, values)
        if rewarded is None:
            values["code"] = ALCHEMY_ERROR_OPT

    def _collect(self, player_id, state, slot, now, values) -> dict | None:
        """收一个到期的产槽; 成功返回奖励 dict, 未就绪返回 None。"""
        rows = self.repo.production_rows(player_id)
        row = rows.get(slot)
        if row is None or now < int(row["endAt"]):
            return None
        recipe = catalog()["recipes"].get(str(row["recipeId"]))
        if recipe is None:
            self.repo.drop_production(player_id, slot)
            return {}
        rewards = {int(recipe["productId"]): int(recipe["productNum"])}
        self._grant(player_id, "alchemy-collect:%s:%s:%s" % (player_id, slot, row["endAt"]), rewards)
        # 每件产物 +1 点经验, 上限 = Exp 向量最后一档 (官方 AlchemyCollect 口径)。
        exp_track = [int(t) for t in (recipe["exp"] or [0])]
        cap = exp_track[-1]
        gain = int(recipe["productNum"]) * EXPERIENCE_PER_ITEM
        before_exp = int(state["recipe_exp"].get(str(row["recipeId"]), 0))
        after_exp = min(cap, before_exp + gain)
        state["recipe_exp"][str(row["recipeId"])] = after_exp
        # 达阈值即级联解锁后续配方 (RecipeEffect 里 kind==3 的槽)。
        state["recipe_exp"] = normalize_recipe_exp(state["recipe_exp"])
        self.repo.drop_production(player_id, slot)
        values["recipeId"] = int(row["recipeId"])
        values["exp"] = after_exp
        values["rewardData"] = self.economy.reward_bytes_visible(rewards)
        return rewards

    # ---- 604 AlchemyBuy --------------------------------------------------

    def _AlchemyBuy(self, player_id, request, state, now, values, before) -> None:
        element = int(request.get("type", 0))
        type_id = int(request.get("typeId", 0))
        tier = next((t for t in _compat()["element_buy_tiers"] if int(t["typeId"]) == type_id), None)
        if tier is None or str(element) not in state["element_num"]:
            values["code"] = ALCHEMY_ERROR_OPT
            return
        if int(state["element_buy_count"].get(str(element), 0)) >= int(_compat()["element_buy_daily_limit"]):
            values["code"] = ALCHEMY_ERROR_OPT
            return
        snapshot = self.repo.store.get(player_id)["snapshot"]
        error = self._pay(player_id, snapshot, [[GOLD_ITEM, int(tier["gold"])]])
        if error:
            values["code"] = error
            return
        cap = int(next(r["cap"] for r in element_rows() if int(r["id"]) == element))
        state["element_num"][str(element)] = min(
            cap, int(state["element_num"].get(str(element), 0)) + int(tier["num"]))
        state["element_buy_count"][str(element)] = int(state["element_buy_count"].get(str(element), 0)) + 1

    # ---- 729 / 731 交易活动 ---------------------------------------------

    def _QueryAlchemyTrade(self, player_id, request, state, now, values, before) -> None:
        # activityId 语义未证实 (SERVER_ONLY_UNKNOWN): 没有交易表, 安全空列表 + code 10。
        values.update(activityId=int(request.get("activityId", 0)),
                      alchemyTrades=[b""], tradeTableData=[b""])

    def _AlchemyTrade(self, player_id, request, state, now, values, before) -> None:
        values.update(alchemyTrades=[b""], rewardData=REWARD.encode({}))

    # ---- 824 AlchemyMakeCancel ------------------------------------------

    def _AlchemyMakeCancel(self, player_id, request, state, now, values, before) -> None:
        slot = int(request.get("posIndex", -1))
        values.update(posIndex=slot, rewardData=REWARD.encode({}))
        rows = self.repo.production_rows(player_id)
        row = rows.get(slot)
        if row is None:
            values["code"] = ALCHEMY_ERROR_OPT
            return
        recipe = catalog()["recipes"].get(str(row["recipeId"]))
        refunds: dict[int, int] = {}
        if recipe is not None:
            ratio = float(_compat()["cancel_refund_ratio"])
            for item, num in zip(recipe["itemGroup"], recipe["itemNum"]):
                back = int(int(num) * ratio)
                if back > 0:
                    refunds[int(item)] = refunds.get(int(item), 0) + back
            gold_back = int(int(recipe["gold"]) * ratio)
            if gold_back > 0:
                refunds[GOLD_ITEM] = refunds.get(GOLD_ITEM, 0) + gold_back
            element_key = str(recipe["type"])
            pay_back = int(int(recipe["pay"]) * ratio)
            cap = int(next(r["cap"] for r in element_rows() if int(r["id"]) == int(recipe["type"])))
            state["element_num"][element_key] = min(
                cap, int(state["element_num"].get(element_key, 0)) + pay_back)
        self._grant(player_id, "alchemy-cancel:%s:%s:%s" % (player_id, slot, row["startAt"]), refunds)
        self.repo.drop_production(player_id, slot)
        values["rewardData"] = self.economy.reward_bytes_visible(refunds)

    # ---- 826 AlchemyOnekeyCollect ---------------------------------------

    def _AlchemyOnekeyCollect(self, player_id, request, state, now, values, before) -> None:
        slots = [int(v) for v in (request.get("posIndex") or [])]
        total: dict[int, int] = {}
        bars: list[bytes] = []
        for slot in slots:
            inner: dict = {}
            exp_before = 0
            recipe_id = 0
            rows = self.repo.production_rows(player_id)
            row = rows.get(slot)
            if row is not None:
                recipe_id = int(row["recipeId"])
                exp_before = int(state["recipe_exp"].get(str(recipe_id), 0))
            got = self._collect(player_id, state, slot, now, inner)
            if got is None:
                continue
            for item, num in (got or {}).items():
                total[int(item)] = total.get(int(item), 0) + int(num)
            bars.append(ALCHEMY_RECIPE_BAR_DATA.encode({
                "recipeId": recipe_id, "expBefore": exp_before,
                "exp": int(state["recipe_exp"].get(str(recipe_id), exp_before)),
                "posIndex": [slot]}))
        values.update(rewardData=self.economy.reward_bytes_visible(total), barData=bars or [b""])

    # ---- 617 push --------------------------------------------------------

    def push_growth_base_alchemy(self, player_id: int) -> OutboundMessage:
        # 只读 + 在内存里结算: 不写库。此方法在 handle() 的事务**外**调用, 若在这里
        # UPDATE 会留下一个未提交的隐式事务 (与 college 的快照推送同一约定)。
        # 元素恢复是惰性的, 不落盘也不会丢——下次请求用存着的 recover_at 重算即可。
        state = self.repo.peek(player_id)
        settle_elements(state, self.clock.now())
        star_energy, star_gain = 0, 0
        if self.college is not None:
            college_state = self.college.load(player_id)
            star_energy = int(college_state.get("star_energy", 0))
            star_gain = int(college_state.get("star_gain_time", 0))
        return OutboundMessage("L2C_QueryGrowthBaseAlchemy", {
            "code": ALCHEMY_OK, "elements": self._element_values(state),
            "starEnergy": star_energy, "starGainTime": star_gain,
            "buffType": int(state["buff_type"]), "buffCount": int(state["buff_count"])})