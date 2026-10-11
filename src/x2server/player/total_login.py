"""降临纪念 / 累计登录 (GameActivity 100004): C2L_TotalLoginReward 816 / L2C_ 817。

页面「时间出错」和「没记录上时间」是同一个断层的两半 (抓包 + 反汇编取证):

* 客户端 CumulateLoginItem_SetData 从**自己**的 GameActivity 100004 行取
  RegistrationDay[index] 当天数文案, 再从 PlayerData.Daily 取
  ``TotalLoginDays`` 判「天数够没够」(反汇编
  CumulateLoginModule_RefreshRedPoint 0x01853B1C-0x01853B34)。
  这一半此前从来没下发过, 于是页面天数恒 0, 就是「时间出错」。本模块补这一个字段。
* 816/817 此前只有消息号, 没有 schema 也没有 handler, 点「领取」服务端不回包 ->
  客户端等到超时再重连。

口径照离线端 x2offline/src/server/router.cpp:4555-4640: 累计登录天数从**创号那
一刻**起算 (``(now - created_at) / 86400 + 1``), 不做任何提前; 已领档位按 0-based
下标落库, 用来给领取去重。

**不要**把已领档位写进 Daily.f22: 该字段客户端只认 wire type 2 且按
ContainerIntIntProto 解, 逐元素 varint 会被静默跳过 -> 列表为 null -> RefreshRedPoint
的 List.Contains 抛 NRE -> 客户端卡在「开始跃迁」进不去游戏。

奖励组 760121/760122 由 EconomyService 用既有的 gift_contents 展开并真发货
(原版奖励, 不做任何替换)。
"""
import json
import logging
from importlib.resources import files

from x2server.messages.lobby import LOBBY_SCHEMAS
from x2server.network.dispatcher import OutboundMessage
from x2server.player.economy import UnresolvedEconomy
from x2server.protocol.errors import ProtocolError

LOGGER = logging.getLogger("x2.total_login")

CODE_OK = 10
CODE_ERROR_OPT = 13
SECONDS_PER_DAY = 86400


def ensure_schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS player_total_login_claimed (
        player_id INTEGER NOT NULL, slot INTEGER NOT NULL,
        PRIMARY KEY(player_id,slot))""")


def _has_table(db):
    return bool(db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='player_total_login_claimed'").fetchone())


def claimed_slots(db, player_id):
    """已领取的 0-based 档位下标 (升序)。"""
    if db is None or not _has_table(db):
        return []
    return sorted(int(row[0]) for row in db.execute(
        "SELECT slot FROM player_total_login_claimed WHERE player_id=? ORDER BY slot", (player_id,)))


def login_days(created_at, now) -> int:
    """累计登录天数: 创号当天算第 1 天。

    与离线端 router.cpp:4591 / protocol_builders.cpp:502 同式。创号时刻未知
    (旧存档或缺列) 时回 0, 页面显示「未开始」而不是一个凭空的数字。
    """
    created, current = int(created_at or 0), int(now)
    if created <= 0 or current < created:
        return 0
    return (current - created) // SECONDS_PER_DAY + 1


class TotalLoginService:
    """降临纪念 (累计登录) 的已领状态机 + 领取发货。"""

    ACTIVITY = 100004

    def __init__(self, economy):
        self.economy, self.store = economy, economy.store
        data = json.loads(files("x2server").joinpath(
            "data/activity_center.json").read_text(encoding="utf-8"))
        row = data["totalLoginActivity"]
        self.days = [int(v) for v in row["registrationDay"]]
        self.gifts = [int(v) for v in row["registrationGift"]]
        self.levels = [int(v) for v in row["conditionLevel"]]
        with self.store.db:
            ensure_schema(self.store.db)

    def handlers(self):
        return {"C2L_TotalLoginReward": self.claim}

    async def claim(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("total login reward requested before login")
        days_index = int(LOBBY_SCHEMAS["C2L_TotalLoginReward"].decode(
            packet.body).get("daysIndex", -1))
        player = self.store.get(player_id)
        snapshot = player["snapshot"]
        now = int(self.economy.clock())
        # daysIndex 既可能是档位下标(0-based), 也可能是 RegistrationDay 的值(36/81),
        # 与离线端 router.cpp:4582 同一口径, 两种都认。
        slot = -1
        for index, value in enumerate(self.days):
            if value == days_index or index == days_index:
                slot = index
                break
        already = slot >= 0 and slot in claimed_slots(self.store.db, player_id)
        reason = None
        if slot < 0 or len(self.gifts) != len(self.days):
            reason = f"unknown slot {days_index}"
        elif already:
            reason = "already claimed"
        elif login_days(player.get("created_at"), now) < self.days[slot]:
            reason = "login days below the gate"
        elif slot < len(self.levels) and int(snapshot.get("level", 1)) < self.levels[slot]:
            reason = "level below the gate"
        if reason is not None:
            LOGGER.info("total login refused player=%s index=%s reason=%s",
                        player_id, days_index, reason)
            # 已领过按离线端回 Ok (客户端自己的领取状态早就把这个档位画成
            # 已领取, 不会重复点); 其余拒绝回 E_ERROR_OPT, 客户端弹提示而不是卡住。
            return OutboundMessage("L2C_TotalLoginReward", {
                "code": CODE_OK if already else CODE_ERROR_OPT,
                "daysIndex": days_index})
        try:
            rewards = self.economy.gifts([self.gifts[slot]])
        except UnresolvedEconomy as exc:
            LOGGER.warning("total login refused player=%s slot=%s reason=%s",
                           player_id, slot, exc)
            return OutboundMessage("L2C_TotalLoginReward", {
                "code": CODE_ERROR_OPT, "daysIndex": days_index})
        if not rewards:
            LOGGER.warning("total login refused player=%s slot=%s: gift %s expands to nothing",
                           player_id, slot, self.gifts[slot])
            return OutboundMessage("L2C_TotalLoginReward", {
                "code": CODE_ERROR_OPT, "daysIndex": days_index})
        with self.economy.transaction():
            # 发货与去重交给上游的 EconomyService._grant (它按 (player_id, source)
            # 幂等, 并在同一事务里落快照), 不再逐件 _credit + 手写快照。
            self.economy._grant(player_id, f"total-login:{slot}", rewards)
            self.store.db.execute(
                "INSERT OR IGNORE INTO player_total_login_claimed VALUES (?,?)",
                (player_id, slot))
        LOGGER.info("total login claimed player=%s slot=%s day=%s delivered=%s",
                    player_id, slot, self.days[slot], sorted(rewards.items()))
        return OutboundMessage("L2C_TotalLoginReward", {
            "code": CODE_OK, "daysIndex": days_index,
            "rewardData": self.economy.reward_bytes(dict(rewards))},
            pushes=self.economy.pushes(player_id))
