"""Confirmed message ID registry from Phase 5 ERequestTypes evidence."""

from __future__ import annotations

from x2server.messages.lobby import LOBBY_IDS
from x2server.messages.chat import CHAT_IDS
from x2server.messages.economy import ECONOMY_IDS
from x2server.messages.achievements import ACHIEVEMENT_IDS
from x2server.messages.favor import FAVOR_IDS
from x2server.messages.appearance import APPEARANCE_IDS
from x2server.messages.mail import MAIL_IDS
from x2server.messages.terminal import TERMINAL_IDS
from x2server.messages.star_chart import STAR_CHART_IDS
from x2server.messages.world_boss import WORLD_BOSS_IDS

from dataclasses import dataclass
from enum import Enum

from .errors import UnknownMessageError


class Direction(Enum):
    """Logical direction encoded by an X2 message name."""

    CLIENT_TO_SERVER = "client_to_server"
    SERVER_TO_CLIENT = "server_to_client"


@dataclass(frozen=True, slots=True)
class MessageEntry:
    """One confirmed message-name/ID association."""

    name: str
    message_id: int
    direction: Direction


class MessageRegistry:
    """Strict bidirectional lookup for confirmed message IDs."""

    def __init__(self, entries: tuple[MessageEntry, ...]) -> None:
        self._by_name = {entry.name: entry for entry in entries}
        self._by_id = {entry.message_id: entry for entry in entries}
        if len(self._by_name) != len(entries):
            raise ValueError("duplicate message name")
        if len(self._by_id) != len(entries):
            raise ValueError("duplicate message ID")

    def entry_for_name(self, name: str) -> MessageEntry:
        """Return an entry or raise instead of silently returning an empty value."""
        try:
            return self._by_name[name]
        except KeyError as exc:
            raise UnknownMessageError(f"unknown message name: {name}") from exc

    def entry_for_id(self, message_id: int) -> MessageEntry:
        """Return an entry or raise for an unknown numeric ID."""
        try:
            return self._by_id[message_id]
        except KeyError as exc:
            raise UnknownMessageError(f"unknown message ID: {message_id}") from exc

    def id_for(self, name: str) -> int:
        """Resolve message name to numeric ID."""
        return self.entry_for_name(name).message_id

    def name_for(self, message_id: int) -> str:
        """Resolve numeric ID to message name."""
        return self.entry_for_id(message_id).name


# CONFIRMED: Phase 5 message_registry.csv / ERequestTypes.
# Deliberately absent: L2C_CheckoutMainMissionSign does not exist in the client.
CORE_MESSAGE_REGISTRY = MessageRegistry(
    (
        *(MessageEntry(name, pid, Direction.CLIENT_TO_SERVER if name.startswith(("C2L_", "C2W_"))
                        else Direction.SERVER_TO_CLIENT) for name, pid in WORLD_BOSS_IDS),
        *(MessageEntry(name, pid, Direction.CLIENT_TO_SERVER if name.startswith("C2L_")
                        else Direction.SERVER_TO_CLIENT) for name, pid in STAR_CHART_IDS),
        MessageEntry("C2L_MedalOpt", 411, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_MedalOpt", 412, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_Login", 54, Direction.CLIENT_TO_SERVER),
        MessageEntry("C2L_HeroOpt", 109, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_HeroOpt", 110, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_UpHeroSkill", 131, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_UpHeroSkill", 132, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_HeroGodLike", 931, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_HeroGodLike", 932, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_GodSlotLock", 1030, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_GodSlotLock", 1031, Direction.SERVER_TO_CLIENT),
        MessageEntry("L2C_HeroUpdate", 549, Direction.SERVER_TO_CLIENT),
        MessageEntry("L2C_TreasureBoxUpdate", 567, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_BuyGiftPackage", 542, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_BuyGiftPackage", 543, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_RechargeGoodsInfo", 659, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_RechargeGoodsInfo", 660, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_GetCollectionAward", 588, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_GetCollectiontAward", 589, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_Artifact", 143, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_Artifact", 146, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_DoEquip", 118, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_DoEquip", 120, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_DoUnEquip", 540, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_DoUnEquip", 541, Direction.SERVER_TO_CLIENT),
        MessageEntry("L2C_EquipUpdate", 536, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_EquipStrengthen", 115, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_EquipStrengthen", 117, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_EquipReclaim", 114, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_EquipReclaim", 116, Direction.SERVER_TO_CLIENT),
        MessageEntry("L2C_EquipRemove", 537, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_LockEquip", 883, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_LockEquip", 884, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_CardPool", 305, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_CardPool", 307, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_LuckDraw", 303, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_LuckDraw", 304, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_RequestDrawResult", 381, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_RequestDrawResult", 382, Direction.SERVER_TO_CLIENT),
        MessageEntry("L2C_UpdatePlayerLevel", 508, Direction.SERVER_TO_CLIENT),
        *(entry for name, request_id, response_id in (*LOBBY_IDS, *CHAT_IDS, *ECONOMY_IDS, *FAVOR_IDS, *APPEARANCE_IDS, *MAIL_IDS, *TERMINAL_IDS, *ACHIEVEMENT_IDS) for entry in (
            MessageEntry("C2L_" + name, request_id, Direction.CLIENT_TO_SERVER),
            MessageEntry("L2C_" + name, response_id, Direction.SERVER_TO_CLIENT))),
        MessageEntry("L2C_Login", 79, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_HeroAll", 546, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_HeroAll", 547, Direction.SERVER_TO_CLIENT),
        MessageEntry("PlayerDataProto", 1000, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_ReConnect", 337, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_ReConnect", 338, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_ServerTableConfig", 945, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_ServerTableConfig", 946, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_FightData", 126, Direction.CLIENT_TO_SERVER),
        MessageEntry("C2L_DelFightProfile", 399, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_DelFightProfile", 398, Direction.SERVER_TO_CLIENT),
        MessageEntry("L2C_FightData", 130, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_CheckoutMainMission", 150, Direction.CLIENT_TO_SERVER),
        MessageEntry("C2L_PrepareMainMission", 151, Direction.CLIENT_TO_SERVER),
        MessageEntry("C2L_RequestInsideBattleShop", 157, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_RequestInsideBattleShop", 160, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_BuyInsideBattleShopItems", 155, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_BuyInsideBattleShopItems", 158, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_RecordInsideBattleItems", 156, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_RecordInsideBattleItems", 159, Direction.SERVER_TO_CLIENT),
        MessageEntry("L2C_CheckoutMainMission", 152, Direction.SERVER_TO_CLIENT),
        MessageEntry("L2C_PrepareMainMission", 153, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_FightDropData", 264, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_FightDropData", 266, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_FightKillInfo", 316, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_FightKillInfo", 318, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_GuideStep", 374, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_GuideStep", 375, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_FillBirthday", 364, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_FillBirthday", 365, Direction.SERVER_TO_CLIENT),
        MessageEntry("L2C_ItemUpdate", 553, Direction.SERVER_TO_CLIENT),
        MessageEntry("L2C_ItemRemove", 554, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_DailyAndWeekTask", 681, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_TaskUpdate", 558, Direction.SERVER_TO_CLIENT),
        MessageEntry("L2C_AchvUpdate", 565, Direction.SERVER_TO_CLIENT),
        MessageEntry("L2C_ItemAll", 555, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_HeroSkinAll", 632, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_HeroSkinAll", 570, Direction.SERVER_TO_CLIENT),
        MessageEntry("L2C_HeroSkinUpdate", 571, Direction.SERVER_TO_CLIENT),
        MessageEntry("L2C_FavorChangeInfo", 497, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_ItemAll", 556, Direction.CLIENT_TO_SERVER),
        MessageEntry("C2L_CheckoutMainMissionSign", 887, Direction.CLIENT_TO_SERVER),
        MessageEntry("C2L_SecSweep", 1027, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_SecSweep", 1028, Direction.SERVER_TO_CLIENT),
    )
)

