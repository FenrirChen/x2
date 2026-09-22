import pytest

from x2server.protocol.errors import (
    ChecksumMismatchError,
    IncompletePacketError,
    MalformedPacketError,
)
from x2server.protocol.framing import PacketStreamDecoder, decode_packet, encode_packet
from x2server.protocol.headers import RequestHeader, ResponseHeader
from x2server.protocol.packint import decode_packint, encode_packint


def request_header() -> RequestHeader:
    return RequestHeader(request_id=7, session_id="synthetic-session", ack_data_version=3, unit_id=42)


def test_request_packet_round_trip_and_lengths() -> None:
    body = b"\x08\xa3\xa4\x01\x10\x02"
    encoded = encode_packet(request_header(), 374, body)
    total_length, content_offset = decode_packint(encoded)
    header_length, header_offset = decode_packint(encoded, content_offset)
    packet = decode_packet(encoded, RequestHeader)

    assert total_length == len(encoded) - content_offset
    assert header_length == len(packet.header.to_bytes())
    assert header_offset + header_length < len(encoded)
    assert packet.message_id == 374
    assert packet.body == body
    assert packet.header.request_id == 7
    assert packet.header.session_id == "synthetic-session"


def test_response_packet_round_trip() -> None:
    header = ResponseHeader(request_id=7, session_id="s", data_version=4, errno=0, errinfo="")
    packet = decode_packet(encode_packet(header, 375, b"\x08\x00"), ResponseHeader)
    assert packet.header == header
    assert packet.message_id == 375
    assert packet.body == b"\x08\x00"


def test_checksum_mismatch_is_rejected() -> None:
    encoded = bytearray(encode_packet(request_header(), 374, b"\x08\x01"))
    encoded[-1] ^= 0x01
    with pytest.raises(ChecksumMismatchError):
        decode_packet(bytes(encoded), RequestHeader)


def test_incomplete_outer_packet_is_explicit() -> None:
    encoded = encode_packet(request_header(), 374, b"abc")
    with pytest.raises(IncompletePacketError):
        decode_packet(encoded[:-1], RequestHeader)


def test_negative_and_oversized_lengths_are_rejected() -> None:
    with pytest.raises(MalformedPacketError, match="negative"):
        decode_packet(encode_packint(-1), RequestHeader)
    with pytest.raises(MalformedPacketError, match="maximum"):
        decode_packet(encode_packint(101), RequestHeader, max_packet_size=100)


def test_head_length_larger_than_frame_is_rejected() -> None:
    content = encode_packint(100)
    malformed = encode_packint(len(content)) + content
    with pytest.raises(MalformedPacketError, match="headLen"):
        decode_packet(malformed, RequestHeader)


def test_single_packet_in_one_feed() -> None:
    encoded = encode_packet(request_header(), 374, b"one")
    decoder = PacketStreamDecoder(RequestHeader)
    assert [packet.body for packet in decoder.feed(encoded)] == [b"one"]
    assert decoder.buffered_bytes == 0


def test_packet_fragmented_across_three_feeds() -> None:
    encoded = encode_packet(request_header(), 374, b"fragmented")
    decoder = PacketStreamDecoder(RequestHeader)
    first, second = len(encoded) // 3, (len(encoded) * 2) // 3
    assert decoder.feed(encoded[:first]) == []
    assert decoder.feed(encoded[first:second]) == []
    assert [packet.body for packet in decoder.feed(encoded[second:])] == [b"fragmented"]


def test_two_packets_in_one_feed() -> None:
    one = encode_packet(request_header(), 374, b"one")
    two = encode_packet(request_header(), 374, b"two")
    decoder = PacketStreamDecoder(RequestHeader)
    assert [packet.body for packet in decoder.feed(one + two)] == [b"one", b"two"]


def test_full_packet_plus_partial_next_packet() -> None:
    one = encode_packet(request_header(), 374, b"one")
    two = encode_packet(request_header(), 374, b"two")
    split = len(two) // 2
    decoder = PacketStreamDecoder(RequestHeader)
    assert [packet.body for packet in decoder.feed(one + two[:split])] == [b"one"]
    assert decoder.buffered_bytes == split
    assert [packet.body for packet in decoder.feed(two[split:])] == [b"two"]

