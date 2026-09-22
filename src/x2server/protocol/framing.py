"""Packet framing and incremental TCP stream decoding."""

from __future__ import annotations

from .crc import body_crc32
from .errors import ChecksumMismatchError, IncompletePacketError, MalformedPacketError
from .headers import RequestHeader, ResponseHeader
from .packint import decode_packint, encode_packint
from .types import DecodedPacket, HeaderClass, PacketHeader
from x2server.config.settings import DEFAULT_MAX_PACKET_SIZE


def encode_packet(header: PacketHeader, message_id: int, body: bytes) -> bytes:
    """Encode one complete packet; request checksum is calculated automatically."""
    if message_id < 0:
        raise ValueError("message ID cannot be negative")
    encoded_header = header.with_body_checksum(body) if isinstance(header, RequestHeader) else header
    header_bytes = encoded_header.to_bytes()
    payload = encode_packint(len(header_bytes)) + header_bytes + encode_packint(message_id) + body
    # CONFIRMED: totalLen excludes its own PackInt prefix.
    return encode_packint(len(payload)) + payload


def decode_packet(
    data: bytes,
    header_type: HeaderClass,
    *,
    max_packet_size: int = DEFAULT_MAX_PACKET_SIZE,
    verify_checksum: bool = True,
) -> DecodedPacket:
    """Decode exactly one packet from bytes and reject trailing or truncated data."""
    try:
        total_length, content_offset = decode_packint(data)
    except IncompletePacketError:
        raise
    if total_length < 0:
        raise MalformedPacketError("negative totalLen")
    if total_length > max_packet_size:
        raise MalformedPacketError(
            f"totalLen {total_length} exceeds configured maximum {max_packet_size}"
        )
    frame_end = content_offset + total_length
    if frame_end > len(data):
        raise IncompletePacketError(
            f"packet declares {total_length} content bytes, only {len(data) - content_offset} available"
        )
    if frame_end < len(data):
        raise MalformedPacketError("decode_packet accepts exactly one packet; trailing bytes found")

    try:
        header_length, offset = decode_packint(data, content_offset)
        if header_length < 0:
            raise MalformedPacketError("negative headLen")
        header_end = offset + header_length
        if header_end > frame_end:
            raise MalformedPacketError("headLen exceeds totalLen")
        header = header_type.from_bytes(data[offset:header_end])
        message_id, body_offset = decode_packint(data, header_end)
    except IncompletePacketError as exc:
        # The outer length said this frame was complete, so an inner truncation is malformed.
        raise MalformedPacketError("complete frame contains a truncated inner value") from exc
    if message_id < 0:
        raise MalformedPacketError("negative message ID")
    if body_offset > frame_end:
        raise MalformedPacketError("message ID exceeds packet boundary")
    body = data[body_offset:frame_end]

    if isinstance(header, RequestHeader) and verify_checksum:
        expected = body_crc32(body)
        if header.sign != expected:
            raise ChecksumMismatchError(
                f"request body CRC32 mismatch: header=0x{header.sign:08x}, body=0x{expected:08x}"
            )
    return DecodedPacket(total_length, header_length, header, message_id, body)


class PacketStreamDecoder:
    """Incrementally recover packets from arbitrarily fragmented TCP bytes."""

    def __init__(
        self,
        header_type: HeaderClass,
        *,
        max_packet_size: int = DEFAULT_MAX_PACKET_SIZE,
        verify_checksum: bool = True,
    ) -> None:
        self._header_type = header_type
        self._max_packet_size = max_packet_size
        self._verify_checksum = verify_checksum
        self._buffer = bytearray()

    @property
    def buffered_bytes(self) -> int:
        """Number of incomplete bytes retained for the next feed call."""
        return len(self._buffer)

    def feed(self, data: bytes) -> list[DecodedPacket]:
        """Append stream bytes and return every newly completed packet."""
        self._buffer.extend(data)
        packets: list[DecodedPacket] = []
        while self._buffer:
            try:
                total_length, prefix_end = decode_packint(self._buffer)
            except IncompletePacketError:
                break
            if total_length < 0:
                raise MalformedPacketError("negative totalLen")
            if total_length > self._max_packet_size:
                raise MalformedPacketError(
                    f"totalLen {total_length} exceeds configured maximum {self._max_packet_size}"
                )
            packet_end = prefix_end + total_length
            if packet_end > len(self._buffer):
                break
            packet_bytes = bytes(self._buffer[:packet_end])
            del self._buffer[:packet_end]
            packets.append(
                decode_packet(
                    packet_bytes,
                    self._header_type,
                    max_packet_size=self._max_packet_size,
                    verify_checksum=self._verify_checksum,
                )
            )
        return packets

