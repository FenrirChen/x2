"""Confirmed message ID registry from Phase 5 ERequestTypes evidence."""

from __future__ import annotations

from x2server.messages.lobby import LOBBY_IDS

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
        MessageEntry("C2L_Login", 54, Direction.CLIENT_TO_SERVER),
        *(entry for name, request_id, response_id in LOBBY_IDS for entry in (
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
        MessageEntry("L2C_FightData", 130, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_CheckoutMainMission", 150, Direction.CLIENT_TO_SERVER),
        MessageEntry("C2L_PrepareMainMission", 151, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_CheckoutMainMission", 152, Direction.SERVER_TO_CLIENT),
        MessageEntry("L2C_PrepareMainMission", 153, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_FightDropData", 264, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_FightDropData", 266, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_GuideStep", 374, Direction.CLIENT_TO_SERVER),
        MessageEntry("L2C_GuideStep", 375, Direction.SERVER_TO_CLIENT),
        MessageEntry("L2C_ItemUpdate", 553, Direction.SERVER_TO_CLIENT),
        MessageEntry("L2C_ItemAll", 555, Direction.SERVER_TO_CLIENT),
        MessageEntry("C2L_ItemAll", 556, Direction.CLIENT_TO_SERVER),
        MessageEntry("C2L_CheckoutMainMissionSign", 887, Direction.CLIENT_TO_SERVER),
    )
)

