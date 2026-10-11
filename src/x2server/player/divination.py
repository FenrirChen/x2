"""星相屋 / 每日占卜 (DivinationModule): 576 查询, 362 领取。

之前这对消息在 protocol/registry.py 里只登记了名字, 没有 schema 也没有
handler, C2L_QueryDivination 一直由 player/lobby.py 的空态兜底 (id=0)。客户端
拿不到 id / checkIn, 星相屋整页是空的, 点格子也领不到东西。

口径照离线端 x2offline/src/offline/mission.cpp:1801 claim_divination 与
divination_view:
  * level >= 8 (FunctionOpen.json 21913 星相屋的 OpenLevel) 才可领;
  * 日历按北京时间, 换月清零 check_mask, 同一天再领回 101;
  * 当天礼物组取 ConstellationGift 首行 (非月卡那一版) 的第 month 个
    "<Month>Gift" 列表的 day-1 项 (见 data/divination_catalog.json);
  * 奖励按原版发货 (不替换任何物品)。
"""
import json
import logging
from datetime import datetime
from functools import lru_cache
from importlib.resources import files

from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from .economy import UnresolvedEconomy
from .server_clock import BEIJING

LOGGER = logging.getLogger("x2.divination")

LEVEL_GATE = 8
CODE_ALREADY = 101


@lru_cache(maxsize=1)
def catalog():
    return json.loads(files("x2server").joinpath("data/divination_catalog.json").read_text(encoding="utf-8"))


def daily_group(now):
    """今天该发的 Gift 组 (ConstellationGift 首行的第 month 个列表, 按 day 取)。"""
    today = datetime.fromtimestamp(int(now), BEIJING)
    groups = catalog()["monthly_gift"].get(str(today.month)) or []
    return int(groups[today.day - 1]) if today.day <= len(groups) else 0


class DivinationService:
    def __init__(self, store, economy):
        self.store, self.economy = store, economy
        with store.db:
            store.db.execute("""CREATE TABLE IF NOT EXISTS player_divination (
                player_id INTEGER PRIMARY KEY,
                stamp INTEGER NOT NULL DEFAULT 0,
                check_mask INTEGER NOT NULL DEFAULT 0,
                last_time INTEGER NOT NULL DEFAULT 0)""")

    def handlers(self):
        return {"C2L_QueryDivination": self.query, "C2L_Divination": self.claim}

    def _row(self, player_id, now):
        """(stamp, check_mask, last_time) with this month's mask applied.

        Reads only; the month rollover is persisted by ``claim`` (and by ``query``,
        which the client calls first and which therefore owns the write).
        """
        today = datetime.fromtimestamp(int(now), BEIJING)
        # stamp 存的是 month*100+day, 所以它的「月」是 stamp//100 (不是 month*100)。
        month = today.month
        row = self.store.db.execute(
            "SELECT stamp,check_mask,last_time FROM player_divination WHERE player_id=?",
            (player_id,)).fetchone()
        stamp, mask, last = (0, 0, 0) if row is None else (int(row[0]), int(row[1]), int(row[2]))
        if stamp // 100 != month:
            mask = 0
        return stamp, mask, last

    async def query(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("divination query requested before login")
        now = int(self.economy.clock())
        today = datetime.fromtimestamp(now, BEIJING)
        stamp = today.month * 100 + today.day
        _, mask, last = self._row(player_id, now)
        with self.store.db:
            self.store.db.execute(
                "INSERT INTO player_divination VALUES (?,?,?,?) "
                "ON CONFLICT(player_id) DO UPDATE SET stamp=excluded.stamp, check_mask=excluded.check_mask",
                (player_id, stamp, mask, 0))
        # id 必须和 validDate 同月, 否则红点永远不灭 (玩家报的"签到后还有红点")。
        # 客户端把 id 和 validDate 各自除以 100 再比较, 不等就把 mCheckIn 清零:
        # DivinationModule_OnQueryDivinationMsg(0x014AD87C)、DivinationPage_RefreshUIData
        # (0x014AF280) 与另外两处换日刷新都是这段逻辑, 而红点 =
        # (1 << (validDate % 100 - 1)) & mCheckIn —— mCheckIn 被清零, 红点自然亮着。
        # 旧实现把 id 发成"所在星座区间的起始 MMDD"(如今天 10/09 落在 923~1023 ->
        # id=923), 923/100=9 != 1009/100=10, 于是每次查询都被清零。
        # 客户端读 id(结构体偏移 0x28) 的地方只有这几处比较, 星座显示走的是
        # Birthday -> DivinationModule_GetShowConstellation, 与 id 无关, 所以把 id
        # 发成今天的 MMDD(即与 validDate 相同) 不会影响星座展示。
        values = {"id": stamp, "blessing": b"", "checkIn": mask, "validDate": stamp}
        if last > 0:
            values["lastDivinationTime"] = last
        return OutboundMessage("L2C_QueryDivination", values)

    async def claim(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("divination requested before login")
        now = int(self.economy.clock())
        today = datetime.fromtimestamp(now, BEIJING)
        stamp = today.month * 100 + today.day
        snapshot = self.store.get(player_id)["snapshot"]
        _, mask, _ = self._row(player_id, now)
        bit = 1 << (today.day - 1)
        group = daily_group(now)
        reason = None
        if int(snapshot.get("level", 1)) < LEVEL_GATE:
            reason = f"level below {LEVEL_GATE}"
        elif mask & bit:
            # 客户端把 101 认成「今天已经领过」，弹的是提示而不是错误。
            return OutboundMessage("L2C_Divination", {"code": CODE_ALREADY})
        elif group <= 0:
            reason = "no gift group for today"
        if reason:
            LOGGER.info("divination refused player=%s reason=%s", player_id, reason)
            return OutboundMessage("L2C_Divination", {"code": 13})
        try:
            with self.economy.transaction():
                rewards = self.economy.gifts([group])
                self.economy._grant(player_id, f"divination:{stamp}", rewards)
                self.store.db.execute(
                    "INSERT INTO player_divination VALUES (?,?,?,?) "
                    "ON CONFLICT(player_id) DO UPDATE SET stamp=excluded.stamp, "
                    "check_mask=excluded.check_mask, last_time=excluded.last_time",
                    (player_id, stamp, mask | bit, now))
        except UnresolvedEconomy as exc:
            LOGGER.warning("divination refused player=%s reason=%s", player_id, exc)
            return OutboundMessage("L2C_Divination", {"code": 13})
        LOGGER.info("divination claimed player=%s stamp=%s group=%s delivered=%s",
                    player_id, stamp, group, sorted(rewards.items()))
        return OutboundMessage("L2C_Divination", {
            "code": 10, "rewardData": self.economy.reward_bytes(dict(rewards))},
            pushes=self.economy.pushes(player_id))
