"""Minimal message-ID dispatcher with explicit unimplemented behavior."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeAlias

from x2server.protocol.errors import UnknownMessageError
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY, MessageRegistry
from x2server.protocol.types import DecodedPacket

from .session import SessionState

LOGGER = logging.getLogger("x2.network.dispatcher")


@dataclass(frozen=True, slots=True)
class DispatchContext:
    """Connection metadata available to a handler; no player identity is implied."""

    connection_id: str
    peer: str
    session: SessionState
    send: Any = None


@dataclass(frozen=True, slots=True)
class OutboundMessage:
    """One registered response requested by a handler."""

    message_name: str
    values: Mapping[str, Any]
    data_version: int = 0
    pushes: tuple[OutboundMessage, ...] = ()
    before_response: tuple[OutboundMessage, ...] = ()


Handler: TypeAlias = Callable[
    [DispatchContext, DecodedPacket], Awaitable[OutboundMessage | None]
]


class DispatchStatus(Enum):
    HANDLED = "handled"
    UNIMPLEMENTED = "unimplemented"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class DispatchOutcome:
    """Observable dispatcher decision used by the connection layer and tests."""

    status: DispatchStatus
    message_name: str | None
    response: OutboundMessage | None = None


class Dispatcher:
    """Resolve packet IDs and invoke only explicitly registered handlers."""

    def __init__(
        self,
        handlers: Mapping[str, Handler] | None = None,
        registry: MessageRegistry = CORE_MESSAGE_REGISTRY,
    ) -> None:
        self._handlers = dict(handlers or {})
        self._registry = registry

    async def dispatch(
        self, context: DispatchContext, packet: DecodedPacket
    ) -> DispatchOutcome:
        """Dispatch one packet; known messages without handlers receive no response."""
        extra = {
            "connection_id": context.connection_id,
            "peer": context.peer,
            "player_id": context.session.player_id,
            "message_id": packet.message_id,
            "request_id": packet.header.request_id,
            "message_name": "unknown",
        }
        try:
            entry = self._registry.entry_for_id(packet.message_id)
        except UnknownMessageError:
            LOGGER.warning("unknown message ID; no response body_bytes=%s decode=unavailable",
                           len(packet.body), extra=extra)
            return DispatchOutcome(DispatchStatus.UNKNOWN, None)

        extra["message_name"] = entry.name
        handler = self._handlers.get(entry.name)
        if handler is None:
            from x2server.messages.core import CORE_SCHEMAS
            schema = CORE_SCHEMAS.get(entry.name)
            if schema is None:
                decoded = "schema_unavailable"
            else:
                try:
                    schema.decode(packet.body)
                    decoded = "ok"
                except Exception:
                    decoded = "invalid"
            LOGGER.info("known message has no implemented handler; no response body_bytes=%s decode=%s",
                        len(packet.body), decoded, extra=extra)
            return DispatchOutcome(DispatchStatus.UNIMPLEMENTED, entry.name)
        response = await handler(context, packet)
        return DispatchOutcome(DispatchStatus.HANDLED, entry.name, response)
