"""X2 signed PackInt codec recovered from ``marsnet.Encoding``.

The public decoder returns ``(value, new_offset)``. PackInt is not protobuf
varint: it uses int32 zigzag followed by a big-endian prefix-length encoding.
"""

from __future__ import annotations

from collections.abc import Buffer

from .errors import IncompletePacketError, MalformedPacketError

INT32_MIN = -(1 << 31)
INT32_MAX = (1 << 31) - 1


def _zigzag_encode(value: int) -> int:
    return ((value << 1) ^ (value >> 31)) & 0xFFFFFFFF


def _zigzag_decode(value: int) -> int:
    return (value >> 1) ^ -(value & 1)


def encode_packint(value: int) -> bytes:
    """Encode one signed int32 using the confirmed X2 PackInt representation."""
    if not INT32_MIN <= value <= INT32_MAX:
        raise ValueError(f"PackInt value outside int32 range: {value}")

    encoded = _zigzag_encode(value)
    if encoded < 0x80:
        return bytes((encoded,))
    if encoded < 0x4000:
        return bytes((0x80 | (encoded >> 8), encoded & 0xFF))
    if encoded < 0x200000:
        return bytes((0xC0 | (encoded >> 16), (encoded >> 8) & 0xFF, encoded & 0xFF))
    if encoded < 0x10000000:
        return bytes(
            (
                0xE0 | (encoded >> 24),
                (encoded >> 16) & 0xFF,
                (encoded >> 8) & 0xFF,
                encoded & 0xFF,
            )
        )
    return bytes(
        (
            0xF0,
            (encoded >> 24) & 0xFF,
            (encoded >> 16) & 0xFF,
            (encoded >> 8) & 0xFF,
            encoded & 0xFF,
        )
    )


def decode_packint(data: Buffer, offset: int = 0) -> tuple[int, int]:
    """Decode one PackInt and return its value plus the offset after it."""
    view = memoryview(data).cast("B")
    if offset < 0 or offset > len(view):
        raise ValueError(f"offset outside buffer: {offset}")
    if offset == len(view):
        raise IncompletePacketError("missing PackInt prefix")

    first = view[offset]
    if first < 0x80:
        width = 1
        encoded = first
    elif first < 0xC0:
        width = 2
        encoded = first & 0x3F
    elif first < 0xE0:
        width = 3
        encoded = first & 0x1F
    elif first < 0xF0:
        width = 4
        encoded = first & 0x0F
    elif first == 0xF0:
        width = 5
        encoded = 0
    else:
        raise MalformedPacketError(f"invalid PackInt prefix 0x{first:02x}")

    end = offset + width
    if end > len(view):
        raise IncompletePacketError(f"truncated {width}-byte PackInt")
    for position in range(offset + 1, end):
        encoded = (encoded << 8) | view[position]
    return _zigzag_decode(encoded), end

