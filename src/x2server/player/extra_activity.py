"""星之特权 (特别课程 100002) 与 积分活动 (100000) 的本地实现。

两条都是「活动点了没反应」的直接病灶:
  * 721 C2L_ReciveStarPrivilegeReward 以前没有 handler -> dispatcher 判
    unimplemented -> 服务端不回包 -> 客户端一直等到超时再重连。表现就是「点了没反应」。
  * 986 C2L_QuerySimpleActivity 恒回 code=208 (活动未开启) -> 积分活动页永远空白;
    988 (领取) / 1013 (进度刷新) 以前只有消息号, 同样等到超时。

口径 USER_DECISION 2026-10-09: 用户拍板本地「一律点开就能领」, 不要求真的充值。
这与离线端 x2offline/src/server/router.cpp 的 special course 分支一致
(那边 723 也恒置 buyTime=当前时间, 视为「已购买」)。

数据来自客户端自己的表 (GameActivity 100002 / SimpleActivity 100000 /
SimpleActivityAction), 见 data/activity_center.json。奖励组 id 由 EconomyService
用既有的 gift_contents 展开并真发货 (原版奖励, 不做任何替换), 所以「领取」不是空点。
"""
import json
import logging
import time
from collections import Counter
from importlib.resources import files

from x2server.messages.lobby import LOBBY_SCHEMAS, MISSION_PAIR, STAR_PRIVILEGE_REWARD
from x2server.network.dispatcher import OutboundMessage
from x2server.player.economy import UnresolvedEconomy
from x2server.protocol.errors import ProtocolError
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY

# SimpleActivityOptType (protocol/commandx2_messages.md 5294 行):
#   UNLOCK_FUN=0 / REWARD_MAIN=1 / REWARD_EXTRA=2
OPT_UNLOCK_FUN = 1
OPT_REWARD_MAIN = 2
OPT_REWARD_EXTRA = 3

CODE_OK = 10
CODE_ERROR_OPT = 13

# 活动表只在导入时读一次: __init__ 与下面的 BaseInfo 助手都要用。
ACTIVITY_CENTER = json.loads(files("x2server").joinpath(
    "data/activity_center.json").read_text(encoding="utf-8"))


def _has_table(db, name) -> bool:
    return bool(db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def novice_sign_values(db, player_id, now, created_at) -> dict:
    """献祭福利写在 BaseInfoProto 上的三个字段 (53/54/55), 供每次 player_data 推送。

    取证见 messages/core.py 字段 53/54/55 的注释。这里只读不写 (推送跑在
    EconomyService.transaction() 的 savepoint 里, ``with db:`` 会提前提交):

    * NoviceSignInStartTime (55): 窗口起算点 = 创号时刻; 若 start + 窗口长度 已经
      走完, 则顺延到当前时间, 让老账号也「点开就能领」(本地口径: 活动不关)。
    * NoviceSignInCount (53) / NoviceLastSignInTime (54): 领取时落库的已签到天数与
      上次签到时刻, 没记录就是 0。
    """
    keep = int(ACTIVITY_CENTER["noviceSignActivity"]["registrationKeepTime"]) * 86400
    now = int(now)
    count = last = 0
    if db is not None and _has_table(db, "player_novice_sign"):
        row = db.execute(
            "SELECT sign_count,last_sign_time FROM player_novice_sign WHERE player_id=?",
            (player_id,)).fetchone()
        if row:
            count, last = int(row[0]), int(row[1])
    start = int(created_at or 0) or now
    if start + keep <= now:
        start = now
    values = {"NoviceSignInCount": count, "NoviceSignInStartTime": start}
    if last > 0:
        values["NoviceLastSignInTime"] = last
    return values


def exchange_count(db, player_id) -> int:
    """自选三星 (GameActivity 100005) 的已兑换次数, 供 BaseInfoProto 字段 61 下发。

    客户端 ExchangeModule/ExchangePage 读 BaseInfo.ForeverExchangeCount; 只读
    (推送跑在 EconomyService.transaction() 的 savepoint 里), 写动作在
    ExtraActivityService.exchange_item_activity。
    """
    if db is None or not _has_table(db, "activity_exchange_stats"):
        return 0
    row = db.execute("SELECT exchange_count FROM activity_exchange_stats WHERE player_id=?",
                     (player_id,)).fetchone()
    return int(row[0]) if row else 0


class ExtraActivityService:
    """星之特权 (特别课程) 与 积分活动 两条本地活动的读取/领取状态机。

    两边的「可领取」都按用户口径直接放开, 但领取记录持久化, 所以不会重复发货。
    """

    # 客户端 FirstRechargePage / SpecialCoursesModule 用 GameActivity 的行 id 定位活动;
    # 100002 = 特别课程 (星之特权), 100000 = 积分活动。
    COURSE_ACTIVITY = 100002
    # mainRewards/extraRewards/unlockInfo 上「什么都不回」的占位值。空 repeated 字段
    # 在线上不存在, 客户端会解成 null 并在渲染时炸; -1 不是任何有效档位, 客户端会跳过。
    _EMPTY_MARKER = -1

    def __init__(self, economy):
        self.economy, self.store = economy, economy.store
        data = ACTIVITY_CENTER
        self.course = data["courseActivity"]
        self.activity = data["simpleActivity"]
        self.novice = data["noviceSignActivity"]
        self.exchange = data["exchangeActivity"]
        self.novice_days = [int(v) for v in self.novice["registrationDay"]]
        self.novice_gifts = [int(v) for v in self.novice["registrationGift"]]
        self.gates = [int(g) for g in self.course["gates"]]
        self._gate_index = {level: index for index, level in enumerate(self.gates)}
        store = economy.store
        # 特别课程: 免费列与付费列各记各的 (同离线端 course_levels / course_paid_levels)。
        store.db.execute("""CREATE TABLE IF NOT EXISTS course_claims (
            player_id INTEGER NOT NULL, level INTEGER NOT NULL, track INTEGER NOT NULL,
            PRIMARY KEY(player_id,level,track))""")
        # 积分活动: 已解锁的动作档位与两列奖励的领取记录。
        store.db.execute("""CREATE TABLE IF NOT EXISTS simple_activity_unlocks (
            player_id INTEGER NOT NULL, level INTEGER NOT NULL,
            PRIMARY KEY(player_id,level))""")
        store.db.execute("""CREATE TABLE IF NOT EXISTS simple_activity_claims (
            player_id INTEGER NOT NULL, track INTEGER NOT NULL, level INTEGER NOT NULL,
            PRIMARY KEY(player_id,track,level))""")
        # 献祭福利 (限时签到 100003): 每个玩家一行, sign_count = 已签到天数 (= 下一个
        # 0-based 档位), last_sign_time 供客户端判「今天还能不能签」(RefreshTime=5)。
        store.db.execute("""CREATE TABLE IF NOT EXISTS player_novice_sign (
            player_id INTEGER PRIMARY KEY, sign_count INTEGER NOT NULL DEFAULT 0,
            last_sign_time INTEGER NOT NULL DEFAULT 0)""")
        # 自选三星 (GameActivity 100005): 每个玩家一行, exchange_count = 已兑换次数,
        # 经 BaseInfoProto.ForeverExchangeCount (字段 61) 下发, 与离线端
        # account_state.hpp 的同名计数一致。放在独立表而不是快照里, 是因为发货
        # (_grant) 自己会重读并保存快照, 就地改外层快照会被它覆盖。
        store.db.execute("""CREATE TABLE IF NOT EXISTS activity_exchange_stats (
            player_id INTEGER PRIMARY KEY, exchange_count INTEGER NOT NULL DEFAULT 0)""")

    def handlers(self):
        return {
            "C2L_QueryStarPrivilegeReward": self.handle,
            "C2L_ReciveStarPrivilegeReward": self.handle,
            "C2L_QueryStarPrivilegeInfo": self.handle,
            "C2L_QuerySimpleActivity": self.handle,
            "C2L_SimpleActivityOpt": self.handle,
            "C2L_SimpleActivityNotice": self.handle,
            "C2L_ReciveNoviceSign": self.handle,
            "C2L_ExchangeItemActivity": self.handle,
        }

    async def handle(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("extra activity requested before login")
        name = CORE_MESSAGE_REGISTRY.name_for(packet.message_id)
        if name == "C2L_QueryStarPrivilegeReward":
            return self.query_star_privilege(player_id)
        if name == "C2L_ReciveStarPrivilegeReward":
            request = LOBBY_SCHEMAS[name].decode(packet.body)
            return self.recive_star_privilege(player_id, request.get("reciveLevelList") or [])
        if name == "C2L_QueryStarPrivilegeInfo":
            return self.query_star_privilege_info()
        if name == "C2L_QuerySimpleActivity":
            return self.query_simple_activity(player_id)
        if name == "C2L_SimpleActivityOpt":
            request = LOBBY_SCHEMAS[name].decode(packet.body)
            return self.simple_activity_opt(player_id, request)
        if name == "C2L_SimpleActivityNotice":
            return self.simple_activity_notice(player_id)
        if name == "C2L_ReciveNoviceSign":
            request = LOBBY_SCHEMAS[name].decode(packet.body)
            return self.recive_novice_sign(player_id, int(request.get("SignCount", 0)))
        if name == "C2L_ExchangeItemActivity":
            return self.exchange_item_activity(player_id)
        raise ProtocolError(f"unrouted extra activity {name}")

    # -- 奖励发货 (两条活动共用) -------------------------------------------

    def _grant_groups(self, player_id, groups, source, marker):
        """展开奖励组并真发货; 返回 ``(rewards, reward_equips)``。

        组的展开走 ``EconomyService.gifts``, 但 ItemType 10 (分部级装备/兽主) 会被
        ``deferred`` 接住而不是抛 ``UnresolvedEconomy``: 一个裸 1240xxx id 直接进奖励
        列表会让客户端断线, 它只能作为 ``equipment_instances`` 实例落地, 再经
        ``rewardData.rewardEquip`` 下发。课程兽主星级取原表 GiftShow 对应物品的
        ItemQuality（4/5/6星），不能用普通物品数量或固定的1星替代。

        没有装备工厂、或不是分部级装备的 id 写进 ``pending_rewards`` 记账, 不阻断其余
        奖励 —— 免费列 710050/710051 就是两条这样的装备组, 修好之前它们会让整个等级
        领不到东西。

        发货与去重交给上游的 ``EconomyService._grant`` (它按 ``(player_id, source)``
        幂等, 并在同一事务里落快照), 不再逐件 ``_credit`` + 手写快照。
        """
        rewards = Counter()
        factory = getattr(self.economy, "equipment_factory", None)
        specs = []
        for group in groups:
            pending = Counter()
            rewards.update(self.economy.gifts([group], deferred=pending))
            for item, count in sorted(pending.items()):
                if factory is not None and factory.is_drop_equipment(item):
                    stars = self.course['equipmentGiftStars'].get(str(group), {})
                    specs.append({"item_id": item, "quantity": count,
                                  "star": stars.get(str(item), 1)})
                else:
                    self.store.db.execute(
                        "INSERT OR IGNORE INTO pending_rewards VALUES (?,?,?,?,?)",
                        (player_id, source, item, count, "unrecovered activity reward"))
        reward_equips = self.economy.materialize_equipment(player_id, marker, specs) if specs else []
        self.economy._grant(player_id, source, rewards)
        return rewards, reward_equips

    def equipment_pushes(self, player_id, equips):
        # ShowGetAwardItem renders a reward window; it does not synchronize
        # BagModule.AllEquipDataDic. Send the actual instances separately.
        return self.economy.pushes(player_id) + ((OutboundMessage(
            'L2C_EquipUpdate', {'code': CODE_OK, 'equip': equips}),) if equips else ())

    def repair_course_equipment(self, player_id):
        """Repair identifiable, unenhanced old one-star course grants in place."""
        changed = []
        with self.economy.transaction():
            for index, level in enumerate(self.gates):
                if level not in self._claimed_levels(player_id, 0):
                    continue
                for group in self.course['freeGiftGroups'][index]:
                    for item, star in self.course['equipmentGiftStars'].get(str(group), {}).items():
                        rows = self.store.db.execute('''SELECT id FROM equipment_instances
                            WHERE player_id=? AND type_id=? AND star=1 AND level=0
                            AND marker LIKE ?''',
                            (player_id, int(item), f'drop:star-privilege:{player_id}:{level}:%')).fetchall()
                        for row in rows:
                            param = self.economy.equipment_factory.roll_param(int(item), star)
                            self.store.db.execute('UPDATE equipment_instances SET star=?,param=? WHERE id=? AND player_id=?',
                                (star, json.dumps(param, sort_keys=True), row[0], player_id))
                            changed.append(row[0])
        if changed:
            logging.getLogger('x2.extra_activity').info('course equipment quality repaired player=%s ids=%s', player_id, changed)
        return changed

    # -- 星之特权 (特别课程 100002) ----------------------------------------

    def _claimed_levels(self, player_id, track) -> set:
        return {int(r[0]) for r in self.store.db.execute(
            "SELECT level FROM course_claims WHERE player_id=? AND track=?", (player_id, track))}

    def _star_privilege_list(self, player_id):
        free = self._claimed_levels(player_id, 0)
        paid = self._claimed_levels(player_id, 1)
        return [STAR_PRIVILEGE_REWARD.encode({
            "level": level,
            "reciveFreeReward": 1 if level in free else 0,
            "recivePrivilegeReward": 1 if level in paid else 0}) for level in self.gates]

    def query_star_privilege(self, player_id) -> OutboundMessage:
        """L2C_QueryStarPrivilegeReward (720): 每个等级门槛的免费/付费领取状态。

        整份列表都下发 (不是只发已领的), 因为空 repeated 字段在线上不存在, 客户端会
        把 privilegeRewardList 解成 null —— 本项目反复踩过的坑。flags=0 的条目客户端
        读作「可领取」, 与离线端「列表里没有的等级 = 可领」等价但更明确。
        """
        values = self._star_privilege_list(player_id)
        logging.getLogger("x2.extra_activity").info(
            "star privilege reward served player=%s levels=%s", player_id, len(values))
        return OutboundMessage("L2C_QueryStarPrivilegeReward",
                               {"code": CODE_OK, "privilegeRewardList": values})

    def recive_star_privilege(self, player_id, levels) -> OutboundMessage:
        """L2C_ReciveStarPrivilegeReward (722): 领取门槛已达成的免费 + 付费两列奖励。

        离线端 router.cpp:4139 的口径: 请求里的每个等级, 两列各自判「领没领过」, 只要
        还有一列没领就发货; 两列都领过 / 等级不在表里 / 玩家等级不够 -> 该等级跳过。
        一个都没领到时回 E_ERROR_OPT(13), 客户端会弹「不可领取」而不是卡住。
        """
        snapshot = self.store.get(player_id)["snapshot"]
        player_level = int(snapshot.get("level", 0))
        free = self._claimed_levels(player_id, 0)
        paid = self._claimed_levels(player_id, 1)
        wanted = []
        for raw in levels:
            level = int(raw)
            index = self._gate_index.get(level)
            if index is None or level > player_level:
                continue
            want_free = level not in free
            want_paid = level not in paid
            if not want_free and not want_paid:
                continue
            groups = []
            if want_free:
                groups += self.course["freeGiftGroups"][index]
            if want_paid:
                groups += self.course["paidGiftGroups"][index]
            wanted.append((level, want_free, want_paid, groups))
        if not wanted:
            logging.getLogger("x2.extra_activity").info(
                "star privilege claim refused player=%s levels=%s", player_id, list(levels))
            return OutboundMessage("L2C_ReciveStarPrivilegeReward", {"code": CODE_ERROR_OPT})
        rewards = {}
        reward_equips = []
        try:
            with self.economy.transaction():
                for level, want_free, want_paid, groups in wanted:
                    marker = f"star-privilege:{player_id}:{level}"
                    part, equips = self._grant_groups(player_id, groups, marker, marker)
                    for item_id, num in part.items():
                        rewards[item_id] = rewards.get(item_id, 0) + num
                    reward_equips += equips
                    for track, is_wanted in ((0, want_free), (1, want_paid)):
                        if is_wanted:
                            self.store.db.execute(
                                "INSERT OR IGNORE INTO course_claims VALUES (?,?,?)",
                                (player_id, level, track))
        except UnresolvedEconomy as exc:
            logging.getLogger("x2.extra_activity").warning(
                "star privilege claim refused player=%s reason=%s", player_id, exc)
            return OutboundMessage("L2C_ReciveStarPrivilegeReward", {"code": CODE_ERROR_OPT})
        logging.getLogger("x2.extra_activity").info(
            "star privilege claimed player=%s levels=%s delivered=%s",
            player_id, [w[0] for w in wanted], sorted(rewards.items()))
        return OutboundMessage("L2C_ReciveStarPrivilegeReward", {
            "code": CODE_OK, "privilegeRewardList": self._star_privilege_list(player_id),
            "rewardData": self.economy.reward_bytes(rewards, reward_equips)},
            pushes=self.equipment_pushes(player_id, reward_equips))

    def query_star_privilege_info(self) -> OutboundMessage:
        """L2C_QueryStarPrivilegeInfo (724): 本期特权的购买信息。

        buyTime 非 0 客户端才解锁「付费那列」奖励, 所以本地恒置「已购买」(离线端
        router.cpp:4121 同样恒回当前时间)。旧空态回 id=0/buyTime=0, 表现是整页付费
        课程点不动。
        """
        return OutboundMessage("L2C_QueryStarPrivilegeInfo", {
            "code": CODE_OK, "id": int(self.course["id"]), "buyTime": int(time.time())})

    # -- 积分活动 (100000) -------------------------------------------------

    def _activity_claimed(self, player_id, track) -> set:
        return {int(r[0]) for r in self.store.db.execute(
            "SELECT level FROM simple_activity_claims WHERE player_id=? AND track=?",
            (player_id, track - 1))}

    def _activity_unlocked(self, player_id) -> set:
        return {int(r[0]) for r in self.store.db.execute(
            "SELECT level FROM simple_activity_unlocks WHERE player_id=?", (player_id,))}

    def _activity_lists(self, player_id):
        """mainRewards/extraRewards/unlockInfo —— 986/989/1014 都有的三个字段。

        回的是「已领取/已解锁」的档位下标。空列表在线上不存在会被解成 null, 所以永远
        至少回一条 (用 -1 当空占位, 客户端不会把它当有效档位)。
        """
        return {
            "mainRewards": sorted(self._activity_claimed(player_id, OPT_REWARD_MAIN)) or [self._EMPTY_MARKER],
            "extraRewards": sorted(self._activity_claimed(player_id, OPT_REWARD_EXTRA)) or [self._EMPTY_MARKER],
            "unlockInfo": sorted(self._activity_unlocked(player_id)) or [self._EMPTY_MARKER],
        }

    def _activity_progress(self):
        """totalProgress/subProgress —— 只有 986/1014 有这两个字段 (989 没有)。

        本服没有可统计的线下行为, 按用户口径把进度直接置为满分: totalProgress =
        ScoreList 的最后一档, subProgress 每条动作给满 (ParmMax)。这样客户端会把
        ScoreList 里所有档位都判为「已达成, 可领取」。
        """
        return {
            "totalProgress": int(self.activity["scores"][-1]),
            "subProgress": [MISSION_PAIR.encode({"Key": int(a["id"]), "Value": int(a["parmMax"])})
                            for a in self.activity["actions"]],
        }

    def _activity_values(self, player_id):
        """积分活动的完整进度载荷 (986 / 1014 共用)。"""
        return {**self._activity_progress(), **self._activity_lists(player_id)}

    def query_simple_activity(self, player_id) -> OutboundMessage:
        """L2C_QuerySimpleActivity (987): code=Ok + 进度。以前恒回 208 让整页空白。"""
        values = self._activity_values(player_id)
        logging.getLogger("x2.extra_activity").info(
            "simple activity served player=%s progress=%s", player_id, values["totalProgress"])
        return OutboundMessage("L2C_QuerySimpleActivity", {"code": CODE_OK, **values})

    def simple_activity_notice(self, player_id) -> OutboundMessage:
        """L2C_SimpleActivityNotice (1014): 客户端主动刷进度时回同一份数据。"""
        return OutboundMessage("L2C_SimpleActivityNotice", {
            "code": CODE_OK, "id": int(self.activity["id"]), **self._activity_values(player_id)})

    def simple_activity_opt(self, player_id, request) -> OutboundMessage:
        """L2C_SimpleActivityOpt (989): UNLOCK_FUN / REWARD_MAIN / REWARD_EXTRA。

        param 是要操作的档位下标 (客户端 ScoreList/GiftList 的下标)。重复领取回
        E_ERROR_OPT(13), 客户端弹提示而不是卡住。
        """
        activity_id = int(request.get("id", 0))
        opt = int(request.get("opt", -1))
        index = int(request.get("param", 0))
        scores, gifts, extras = (self.activity["scores"], self.activity["giftList"],
                                 self.activity["extraGiftList"])
        if activity_id not in (0, int(self.activity["id"])):
            return OutboundMessage("L2C_SimpleActivityOpt", {"code": CODE_ERROR_OPT})
        if not 0 <= index < len(scores):
            return OutboundMessage("L2C_SimpleActivityOpt", {"code": CODE_ERROR_OPT})
        if opt == OPT_UNLOCK_FUN:
            with self.economy.transaction():
                self.store.db.execute(
                    "INSERT OR IGNORE INTO simple_activity_unlocks VALUES (?,?)",
                    (player_id, index))
            logging.getLogger("x2.extra_activity").info(
                "simple activity unlocked player=%s index=%s", player_id, index)
            return OutboundMessage("L2C_SimpleActivityOpt", {"code": CODE_OK,
                                                             **self._activity_lists(player_id)})
        if opt not in (OPT_REWARD_MAIN, OPT_REWARD_EXTRA):
            return OutboundMessage("L2C_SimpleActivityOpt", {"code": CODE_ERROR_OPT})
        claimed = self._activity_claimed(player_id, opt)
        if index in claimed:
            return OutboundMessage("L2C_SimpleActivityOpt", {"code": CODE_ERROR_OPT})
        gift_id = (gifts if opt == OPT_REWARD_MAIN else extras)[index]
        # Preserve pre-fix database tracks and grant keys (main=1, extra=2).
        track = opt - 1
        try:
            with self.economy.transaction():
                rewards, reward_equips = self._grant_groups(
                    player_id, [gift_id], f"simple-activity:{player_id}:{track}:{index}",
                    f"simple-activity:{player_id}:{track}:{index}")
                self.store.db.execute(
                    "INSERT OR IGNORE INTO simple_activity_claims VALUES (?,?,?)",
                    (player_id, track, index))
        except UnresolvedEconomy as exc:
            logging.getLogger("x2.extra_activity").warning(
                "simple activity claim refused player=%s reason=%s", player_id, exc)
            return OutboundMessage("L2C_SimpleActivityOpt", {"code": CODE_ERROR_OPT})
        logging.getLogger("x2.extra_activity").info(
            "simple activity claimed player=%s opt=%s index=%s gift=%s delivered=%s",
            player_id, opt, index, gift_id, sorted(rewards.items()))
        return OutboundMessage("L2C_SimpleActivityOpt", {
            "code": CODE_OK, **self._activity_lists(player_id),
            "rewardData": self.economy.reward_bytes(rewards, reward_equips)},
            pushes=self.equipment_pushes(player_id, reward_equips))

    # -- 献祭福利 (限时签到 100003) ----------------------------------------

    def _novice_sign_state(self, player_id):
        """``(已签到天数, 上次签到时刻)``; 没记录则 ``(0, 0)``。"""
        row = self.store.db.execute(
            "SELECT sign_count,last_sign_time FROM player_novice_sign WHERE player_id=?",
            (player_id,)).fetchone()
        return (0, 0) if row is None else (int(row[0]), int(row[1]))

    def recive_novice_sign(self, player_id, sign_count) -> OutboundMessage:
        """L2C_ReciveNoviceSign (775): 献祭福利按顺序签下一天。

        与离线端 router.cpp:4467-4553 同口径: 请求里的 SignCount 既可能是已签到数
        (0-based 的下一个档位) 也可能是 1-based 第几天, 两种都认; 只接受「正好是下一个
        未签档位」; 门槛用真实累计登录天数 (RegistrationDay = [1,2,3,4,5])。回包
        {1 code, 2 SignCount(新的已签到天数), 3 rewardData}, SignCount 客户端存回
        BaseInfo.NoviceSignInCount 并刷新页面进度。领不到回 E_ERROR_OPT(13), 客户端弹
        提示而不是卡住。奖励组走 _grant_groups, 与另外两条活动同一套发货口径。
        """
        from .total_login import login_days
        days, gifts = self.novice_days, self.novice_gifts
        player = self.store.get(player_id)
        now = int(self.economy.clock())
        count, _ = self._novice_sign_state(player_id)
        login_days_now = login_days(player.get("created_at"), now)
        slot = -1
        for cand in (sign_count - 1, sign_count):
            if 0 <= cand < len(days) and cand == count and login_days_now >= days[cand]:
                slot = cand
                break
        if slot < 0 or len(gifts) != len(days):
            logging.getLogger("x2.extra_activity").info(
                "novice sign refused player=%s req=%s count=%s login_days=%s",
                player_id, sign_count, count, login_days_now)
            return OutboundMessage("L2C_ReciveNoviceSign", {"code": CODE_ERROR_OPT})
        gift_id = gifts[slot]
        try:
            with self.economy.transaction():
                rewards, reward_equips = self._grant_groups(
                    player_id, [gift_id], f"novice-sign:{player_id}:{slot}",
                    f"novice-sign:{player_id}:{slot}")
                self.store.db.execute(
                    "INSERT OR REPLACE INTO player_novice_sign VALUES (?,?,?)",
                    (player_id, slot + 1, now))
        except UnresolvedEconomy as exc:
            logging.getLogger("x2.extra_activity").warning(
                "novice sign refused player=%s reason=%s", player_id, exc)
            return OutboundMessage("L2C_ReciveNoviceSign", {"code": CODE_ERROR_OPT})
        logging.getLogger("x2.extra_activity").info(
            "novice sign claimed player=%s slot=%s day=%s delivered=%s",
            player_id, slot, days[slot], sorted(rewards.items()))
        return OutboundMessage("L2C_ReciveNoviceSign", {
            "code": CODE_OK, "SignCount": slot + 1,
            "rewardData": self.economy.reward_bytes(rewards, reward_equips)},
            pushes=self.equipment_pushes(player_id, reward_equips))

    # -- 自选三星 (GameActivity 100005, 890/891) ---------------------------

    def exchange_item_activity(self, player_id) -> OutboundMessage:
        """L2C_ExchangeItemActivity (891): 「自选三星」兑换。

        客户端 ExchangeModule 完全由 GameActivity[100005] 驱动 (见
        data/activity_center.json 的 exchangeActivity 与它的 _source): 花 20
        许愿币 (物品 1237914) 换 1 个 1290001 自选3★神格, 门槛是等级 30。请求体是
        空结构, 所以不看 request。与离线端 x2offline/src/server/router.cpp:4386-4465
        同口径:

            可兑换 = 等级 >= 30 且 许愿币 >= 20 且 奖励组能展开

        成功: 扣 20 许愿币 -> 发货 1 个自选3★神格 -> 已兑换次数 +1 -> 回
        {code:10, rewardData}。任一不满足回 E_ERROR_OPT(13), 客户端弹提示而不是
        卡住。旧兜底只回 code=10 且不带 rewardData, 客户端拿到 null 奖励 ->
        「能点开但换不了」。
        """
        snapshot = self.store.get(player_id)["snapshot"]
        level_need = int(self.exchange.get("level", 0))
        price = int(self.exchange.get("price", 0))
        item_id = int(self.exchange["currencyItem"])
        gift = int(self.exchange["giftGroup"])
        allowed = price > 0 and int(snapshot.get("level", 0)) >= level_need
        if not allowed:
            logging.getLogger("x2.extra_activity").info(
                "exchange refused player=%s level=%s need=%s", player_id,
                snapshot.get("level", 0), level_need)
            return OutboundMessage("L2C_ExchangeItemActivity", {"code": CODE_ERROR_OPT})
        # 兑换可重复; 发货 source 必须每次都唯一, 否则 EconomyService._grant 会按
        # (player_id, source) 判定「已发过」而不再发货。用当前已兑换次数当序号。
        n = exchange_count(self.store.db, player_id)
        try:
            with self.economy.transaction():
                # 1237914 是背包物品 (不在 EconomyService.CURRENCIES 里), 直接
                # UPDATE inventory 扣费, 不碰快照; 快照由下面的 _grant_groups 自己读取并保存。
                charged = self.store.db.execute(
                    "UPDATE inventory SET quantity=quantity-? WHERE player_id=? AND item_id=? AND quantity>=?",
                    (price, player_id, item_id, price))
                if not charged.rowcount:
                    return OutboundMessage("L2C_ExchangeItemActivity", {"code": CODE_ERROR_OPT})
                rewards, reward_equips = self._grant_groups(
                    player_id, [gift], f"exchange-3star:{n}", f"exchange-3star:{n}")
                self.store.db.execute(
                    "INSERT INTO activity_exchange_stats VALUES (?,1)"
                    " ON CONFLICT(player_id) DO UPDATE SET exchange_count=exchange_count+1",
                    (player_id,))
        except UnresolvedEconomy as exc:
            logging.getLogger("x2.extra_activity").warning(
                "exchange refused player=%s reason=%s", player_id, exc)
            return OutboundMessage("L2C_ExchangeItemActivity", {"code": CODE_ERROR_OPT})
        logging.getLogger("x2.extra_activity").info(
            "exchange claimed player=%s cost=%s delivered=%s",
            player_id, (item_id, price), sorted(rewards.items()))
        return OutboundMessage("L2C_ExchangeItemActivity", {
            "code": CODE_OK,
            "rewardData": self.economy.reward_bytes(rewards, reward_equips)},
            pushes=self.equipment_pushes(player_id, reward_equips))
