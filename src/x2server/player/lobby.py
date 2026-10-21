"""Explicit local empty-state queries; no purchases, rewards or progression mutations."""
import logging
import time
import json
from importlib.resources import files
from .server_clock import ServerClock

from x2server.messages.lobby import (LOBBY_IDS, LOBBY_SCHEMAS, growth_base_values, ACTIVITY_DATA,
                                     MISSION_PAIR, UNLOCK_EXPLORE_RUIN)
from x2server.network.dispatcher import DispatchContext, OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY
from x2server.protocol.types import DecodedPacket


class LobbyService:
    # 活动中心里会改写玩家状态 (发奖/记签到) 的消息, 本文件的空态兜底答不了, 交给
    # 各自的服务: 星相屋 -> DivinationService; 特别课程/积分活动/献祭福利/自选三星 ->
    # ExtraActivityService; 降临纪念 -> TotalLoginService; 首充 -> EconomyService。
    # (这些名字在 messages/lobby.py 的 LOBBY_IDS 里, 必须在派发表里让位, 否则空态
    # 的 CObserve 回复会盖掉真实现。)
    DELEGATED = frozenset((
        "QueryDivination", "Divination",
        "QueryStarPrivilegeReward", "ReciveStarPrivilegeReward", "QueryStarPrivilegeInfo",
        "QuerySimpleActivity", "SimpleActivityOpt", "SimpleActivityNotice",
        "ReciveNoviceSign", "ExchangeItemActivity",
        "TotalLoginReward",
        "QueryFirstReCharge", "ReciveFirstReCharge",
    ))

    def __init__(self, clock=None, college=None, *, sweep_enabled=True):
        self.clock = clock or ServerClock()
        self.college = college
        # USER_DECISION 2026-10-21: reopen the recovered sweep activity.
        # Defaults must match the production startup, not only opt-in tests.
        self.sweep_enabled = sweep_enabled

    def handlers(self):
        return {"C2L_" + name: self.query for name, _, _ in LOBBY_IDS
                if name not in self.DELEGATED}

    def sweep_activity_row(self, player=None):
        # 活动中心扫荡入口 (actType 71 E_ActivityMop) 的唯一一行。生产环境里
        # C2L_QueryActivity 由 ActivityRuntime 应答, 本文件的空态分支会被覆盖,
        # 所以这行必须能被 ActivityService 复用并拼进目录 (见 player/activity.
        # query_activity), 否则扫荡页入口会凭空消失。sweep_enabled=False 时返回
        # None，仅供显式关闭入口的配置使用。
        if not self.sweep_enabled:
            return None
        row = json.loads(files("x2server").joinpath("data/sweep_activity.json").read_text(encoding="utf-8"))
        # Revive only the client's sweep tab; the original event dates expired.
        values = {"actId": row["ActivityID"], "state": 1,
            "activityParentType": row["ActivityParentType"]["value"],
            "actType": row["ActivityType"]["value"], "startTime": 1, "endTime": 2147483647,
            "openLever": row["OpenLever"], "activityShow": row["ActivityShow"],
            "activityGroup": row["ActivityGroup"], "activityName": row["ActivityName"],
            "param1": row["ActivityParam1"], "activityTaps": row["ActivityTaps"],
            "activityDescription": row["ActivityDescription"]}
        logging.getLogger("x2.lobby").info("sweep activity advertised player=%s activity=%s type=%s",
            player, values["actId"], values["actType"])
        return ACTIVITY_DATA.encode(values)

    async def query(self, context: DispatchContext, packet: DecodedPacket) -> OutboundMessage:
        if context.session.player_id is None:
            raise ProtocolError("lobby query requested before login")
        name = CORE_MESSAGE_REGISTRY.name_for(packet.message_id)
        if name == "C2L_UnlockStory":
            # EconomyService owns this mutation in production. Standalone lobby
            # servers must refuse it instead of indexing an absent query schema.
            return OutboundMessage("L2C_UnlockStory", {"code": 13})
        request = LOBBY_SCHEMAS[name].decode(packet.body)
        if name == "C2L_QueryGrowthBase":
            growth = (self.college.growth_base(context.session.player_id)
                      if self.college else growth_base_values())
            return OutboundMessage("L2C_QueryGrowthBase", growth)
        if name == "C2L_UnlockExploreRuin":
            # 623 behaves as a query: native audit 0x1AFE168 replaces the client
            # ruin cache with a non-null list and shows a bubble for any code
            # other than 10. Idempotent; no unlock mutation until dispatch lands.
            ruins = (self.college.unlock_ruins(context.session.player_id)
                     if self.college else [])
            # Absent repeated field would decode to a null list client-side;
            # keep one zero-filled idle ruin entry when none are unlocked.
            rows = [UNLOCK_EXPLORE_RUIN.encode(row) for row in ruins]
            return OutboundMessage("L2C_UnlockExploreRuin", {
                "code": 10,
                "unlockExploreRuin": rows or [UNLOCK_EXPLORE_RUIN.encode({})]})
        if name == "C2L_QueryActivity":
            entry = self.sweep_activity_row(context.session.player_id)
            if entry is None:
                return OutboundMessage('L2C_QueryActivity', {'code': 10})
            return OutboundMessage("L2C_QueryActivity", {"code": 10, "activityData": [entry]})
        if name == "C2L_QueryWorldBossOpenTime":
            # USER_DECISION 2026-10-01: temporal gate stays open all day.
            return OutboundMessage("L2C_QueryWorldBossOpenTime", {"code": 10})
        # These describe a dedicated local account with no online activities.
        states = {
            "C2L_QueryTelInfo": {"code": 10, "telNumber": "", "lastBindTime": 0},
            "C2L_SeasonIcon": {"code": 10, "putOnHeadIcon": 0, "putOnSceneIcon": 0},
            "C2L_QueryItemLimitTime": {"code": 10},
            "C2L_QueryDivination": {"id": 0, "blessing": b"", "checkIn": 0, "lastDivinationTime": 0, "validDate": 0},
            "C2L_QueryNotic": {"code": 10, "version": 0},
            "C2L_NoticPushInfo": {"code": 10},
            "C2L_QueryReturnInfo": {"code": 10, "hasReturn": False, "hasReciveReward": False, "hasDraw": False},
            "C2L_SystemInfo": {"code": 10, "serverTime": self.clock.now()},
            "C2L_GameTask": {"code": 10, "type": request.get("type", 0), "chapterId": request.get("chapterId", 0)},
            # MainModule.InitServerFunctionOpenData: Value=2 closes a function.
            # ActivityNoticeModule.Show checks function 19 before opening UI.
            "C2L_EntryidStatus": {"code": 10, "entryidStatus": [] if self.sweep_enabled else
                [MISSION_PAIR.encode({'Key': 19, 'Value': 2})]},
            "C2L_EquipAll": {},
            "C2L_QueryMission": {},
            "C2L_QueryCollectionAward": {},
            "C2L_QueryActivityDrawInfo": {"code": 10},
            "C2L_QueryStarPrivilegeReward": {"code": 10},
            "C2L_QueryStarPrivilegeInfo": {"code": 10, "id": 0, "buyTime": 0},
            "C2L_QueryIllustrationData": {"code": 10},
            "C2L_AccountBuffAutoStop": {"code": 10},  # No active local buffs to stop.
            "C2L_ReceiveGiftRew": {"code": 13, "type": request.get("type", 0)},  # Unsupported grant: E_ERROR_OPT.
            "C2L_QuerySimpleActivity": {"code": 208},
            "C2L_QuerySharedMessage": {"code": 10},
            "C2L_AccountBuffData": {"code": 10, "buffId": request.get("buffId", [])},
            "C2L_ButtonClick": {"code": 10},
            "C2L_Logout": {"code": 10},  # Acknowledge telemetry only; no guide/reward mutation.
            "C2L_CheckFightProfile": {"code": 10, "isProfileExist": False,
                                      "isProfileValid": False},  # No saved battle profile.
            "C2L_CommercialShopGoods": {"code": 10, "shopType": request.get("shopType", 0)},
            "C2L_QueryGiftPackage": {"code": 10},  # No local gift packages.
        }
        logging.getLogger("x2.lobby").info("local empty-state query %s", name)
        return OutboundMessage(name.replace("C2L_", "L2C_", 1), states[name])
