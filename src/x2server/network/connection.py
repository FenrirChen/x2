"""Lifecycle for one TCP byte stream."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from time import monotonic
from typing import Any

from x2server.config.settings import Settings
from x2server.protocol.codec import ProtocolCodec
from x2server.protocol.errors import ProtocolError
from x2server.protocol.framing import PacketStreamDecoder
from x2server.protocol.headers import RequestHeader, ResponseHeader

from .dispatcher import DispatchContext, Dispatcher, OutboundMessage
from .session import SessionState

LOGGER = logging.getLogger("x2.network.connection")
CloseCallback = Callable[[str], None]


class X2Connection:
    """Own one accepted stream, decoder, session metadata and close path."""

    def __init__(
        self,
        connection_id: str,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        dispatcher: Dispatcher,
        settings: Settings,
        on_closed: CloseCallback,
    ) -> None:
        self.connection_id = connection_id
        self.reader = reader
        self.writer = writer
        self.dispatcher = dispatcher
        self.settings = settings
        self.session = SessionState(connection_id)
        self.decoder = PacketStreamDecoder(
            RequestHeader, max_packet_size=settings.max_packet_size
        )
        self.peer = self._format_peer(writer.get_extra_info("peername"))
        self.created_at = monotonic()
        self.last_activity_at = self.created_at
        self.closed = False
        self._on_closed = on_closed

    @staticmethod
    def _format_peer(peer: Any) -> str:
        if isinstance(peer, tuple) and len(peer) >= 2:
            return f"{peer[0]}:{peer[1]}"
        return str(peer or "unknown")

    def _extra(
        self, message_id: int | str = "-", message_name: str = "-", request_id: int = 0
    ) -> dict[str, str | int]:
        return {
            "connection_id": self.connection_id,
            "peer": self.peer,
            "message_id": message_id,
            "message_name": message_name,
            "request_id": request_id,
            "player_id": self.session.player_id,
        }

    async def run(self) -> None:
        """Read, incrementally frame and dispatch until EOF, timeout or protocol failure."""
        LOGGER.info("connection opened", extra=self._extra())
        try:
            while not self.closed:
                timeout = min(self.settings.read_timeout, self.settings.idle_timeout)
                async with asyncio.timeout(timeout):
                    data = await self.reader.read(self.settings.read_chunk_size)
                if not data:
                    if self.decoder.buffered_bytes:
                        LOGGER.warning(
                            "EOF with incomplete packet bytes",
                            extra=self._extra(),
                        )
                    break
                self.last_activity_at = monotonic()
                for packet in self.decoder.feed(data):
                    LOGGER.info("request received body_bytes=%s", len(packet.body),
                                extra=self._extra(packet.message_id, "-", packet.header.request_id))
                    if os.getenv("X2_BATTLE_PROBE") == "1" and packet.message_id in (126, 150, 264, 316, 323, 399, 887):
                        LOGGER.info("battle probe body=%s", packet.body.hex(),
                                    extra=self._extra(packet.message_id, "battle-probe", packet.header.request_id))
                    self.session.record_request(
                        packet.header.request_id, packet.header.session_id
                    )
                    context = DispatchContext(self.connection_id, self.peer, self.session, self.send_response)
                    outcome = await self.dispatcher.dispatch(context, packet)
                    LOGGER.info("handler status=%s response=%s code=%s pushes=%s", outcome.status.value,
                                outcome.response.message_name if outcome.response else "-",
                                outcome.response.values.get("code", outcome.response.values.get("result", "-")) if outcome.response else "-",
                                ",".join(p.message_name for p in outcome.response.pushes) if outcome.response else "-",
                                extra=self._extra(packet.message_id, outcome.message_name or "-", packet.header.request_id))
                    if outcome.response is not None:
                        await self.send_response(outcome.response, packet.header.request_id)
        except TimeoutError:
            LOGGER.warning("connection read/idle timeout", extra=self._extra())
        except (ConnectionError, BrokenPipeError) as exc:
            LOGGER.warning("connection transport error: %s", exc, extra=self._extra())
        except ProtocolError as exc:
            LOGGER.warning("connection protocol error: %s", exc, extra=self._extra())
        finally:
            await self.close()

    async def send_response(self, response: OutboundMessage, request_id: int) -> None:
        """Encode a registered response, write it and await transport backpressure."""
        if self.closed:
            raise ConnectionError("cannot send on a closed connection")
        for push in response.before_response:
            await self.send_response(push, 0)
        header = ResponseHeader(
            request_id=request_id,
            session_id=self.session.session_id,
            data_version=response.data_version,
        )
        packet = ProtocolCodec().encode(response.message_name, response.values, header)
        LOGGER.info("response sent code=%s bytes=%s", response.values.get("code", response.values.get("result", "-")), len(packet),
                    extra=self._extra(response.message_name, response.message_name, request_id))
        self.writer.write(packet)
        async with asyncio.timeout(self.settings.write_timeout):
            await self.writer.drain()
        for push in response.pushes:
            await self.send_response(push, 0)

    async def close(self) -> None:
        """Idempotently close the stream and release server ownership."""
        if self.closed:
            return
        self.closed = True
        self.writer.close()
        try:
            await self.writer.wait_closed()
        except (ConnectionError, BrokenPipeError):
            pass
        self._on_closed(self.connection_id)
        LOGGER.info("connection closed", extra=self._extra())
