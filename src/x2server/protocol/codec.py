"""Bridge registered protobuf message values and complete X2 packets."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from x2server.messages.core import CORE_SCHEMAS

from .errors import UnknownMessageError
from .framing import decode_packet, encode_packet
from .headers import RequestHeader, ResponseHeader
from .protobuf import ProtoSchema
from .registry import CORE_MESSAGE_REGISTRY, Direction, MessageRegistry
from .types import DecodedPacket, HeaderClass, PacketHeader


@dataclass(frozen=True, slots=True)
class DecodedMessage:
    """A framed packet with its registered protobuf values."""

    packet: DecodedPacket
    message_name: str
    values: dict[str, Any]


class ProtocolCodec:
    """Stateless message↔packet codec with no business dependencies."""

    def __init__(
        self,
        registry: MessageRegistry = CORE_MESSAGE_REGISTRY,
        schemas: Mapping[str, ProtoSchema] = CORE_SCHEMAS,
    ) -> None:
        self._registry = registry
        self._schemas = dict(schemas)

    def _schema_for(self, message_name: str) -> ProtoSchema:
        try:
            return self._schemas[message_name]
        except KeyError as exc:
            raise UnknownMessageError(f"no M1 schema registered for {message_name}") from exc

    def encode(
        self,
        message_name: str,
        values: Mapping[str, Any],
        header: PacketHeader,
    ) -> bytes:
        """Serialize registered values and frame them with the matching header direction."""
        entry = self._registry.entry_for_name(message_name)
        if entry.direction is Direction.CLIENT_TO_SERVER and not isinstance(header, RequestHeader):
            raise TypeError(f"{message_name} requires RequestHeader")
        if entry.direction is Direction.SERVER_TO_CLIENT and not isinstance(header, ResponseHeader):
            raise TypeError(f"{message_name} requires ResponseHeader")
        body = self._schema_for(message_name).encode(values)
        return encode_packet(header, entry.message_id, body)

    def decode(self, data: bytes, header_type: HeaderClass) -> DecodedMessage:
        """Decode one frame, resolve its message ID and deserialize registered values."""
        packet = decode_packet(data, header_type)
        entry = self._registry.entry_for_id(packet.message_id)
        expected = (
            Direction.CLIENT_TO_SERVER if header_type is RequestHeader else Direction.SERVER_TO_CLIENT
        )
        if entry.direction is not expected:
            raise UnknownMessageError(
                f"message {entry.name} direction {entry.direction.value} conflicts with header"
            )
        values = self._schema_for(entry.name).decode(packet.body)
        return DecodedMessage(packet, entry.name, values)

