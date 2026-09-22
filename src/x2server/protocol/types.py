"""Shared protocol value types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from .headers import RequestHeader, ResponseHeader

PacketHeader: TypeAlias = RequestHeader | ResponseHeader
HeaderClass: TypeAlias = type[RequestHeader] | type[ResponseHeader]


@dataclass(frozen=True, slots=True)
class DecodedPacket:
    """One complete framed packet before business-message decoding."""

    total_length: int
    header_length: int
    header: PacketHeader
    message_id: int
    body: bytes

