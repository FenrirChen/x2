"""Explicit local empty-state queries; no purchases, rewards or progression mutations."""
import logging
import time
import json
from importlib.resources import files
from .server_clock import ServerClock

from x2server.messages.lobby import LOBBY_IDS, LOBBY_SCHEMAS, growth_base_values, ACTIVITY_DATA, MISSION_PAIR
from x2server.network.dispatcher import DispatchContext, OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY
from x2server.protocol.types import DecodedPacket


class LobbyService:
    def __init__(self, clock=None, college=None, *, sweep_enabled=False):
        self.clock = clock or ServerClock()
        self.college = college
        # USER_DECISION 2026-10-01: disable the activity entry for now, retain
        # the recovered sweep implementation for a future explicit reopening.
        self.sweep_enabled = sweep_enabled

    def handlers(self):
        return {"C2L_" + name: self.query for name, _, _ in LOBBY_IDS}

    async def query(self, context: DispatchContext, packet: DecodedPacket) -> OutboundMessage:
        if context.session.player_id is None:
            raise ProtocolError("lobby query requested before login")
        name = CORE_MESSAGE_REGISTRY.name_for(packet.message_id)
        request = LOBBY_SCHEMAS[name].decode(packet.body)
        if name == "C2L_QueryGrowthBase":
            growth = (self.college.growth_base(context.session.player_id)
                      if self.college else growth_base_values())
            return OutboundMessage("L2C_QueryGrowthBase", growth)
        if name == "C2L_UnlockExploreRuin":
            return OutboundMessage("L2C_UnlockExploreRuin", {"code": 13})
        if name == "C2L_QueryWorldBossOpenTime":
            # Main-screen 时序之门 is WorldBoss, not EndlessWeekly.
            # WorldBossModule.OnHandleQueryOpenState treats code=10 as Open;
            # the 17:00-23:00 text is the client's fallback for any other code.
            # USER_DECISION 2026-10-01: keep this entry open all day.
            logging.getLogger("x2.lobby").info(
                "temporal gate WorldBoss open query player=%s policy=always-open",
                context.session.player_id)
            return OutboundMessage("L2C_QueryWorldBossOpenTime", {"code": 10})
        if name == "C2L_QueryActivity":
            if not self.sweep_enabled:
                return OutboundMessage('L2C_QueryActivity', {'code': 10})
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
                context.session.player_id, values["actId"], values["actType"])
            return OutboundMessage("L2C_QueryActivity", {"code": 10,
                "activityData": [ACTIVITY_DATA.encode(values)]})
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
            "C2L_MoonEquip": {"code": 10},
            "C2L_QuerySimpleActivity": {"code": 208},
            "C2L_QuerySharedMessage": {"code": 10},
            "C2L_AccountBuffData": {"code": 10, "buffId": request.get("buffId", [])},
            "C2L_ButtonClick": {"code": 10},  # Acknowledge telemetry only; no guide/reward mutation.
            "C2L_CheckFightProfile": {"code": 10, "isProfileExist": False,
                                      "isProfileValid": False},  # No saved battle profile.
            "C2L_CommercialShopGoods": {"code": 10, "shopType": request.get("shopType", 0)},
            "C2L_QueryGiftPackage": {"code": 10},  # No local gift packages.
        }
        logging.getLogger("x2.lobby").info("local empty-state query %s", name)
        return OutboundMessage(name.replace("C2L_", "L2C_", 1), states[name])
