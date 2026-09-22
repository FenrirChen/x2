import pytest

from x2server.protocol.errors import IncompletePacketError, MalformedPacketError
from x2server.protocol.packint import INT32_MAX, INT32_MIN, decode_packint, encode_packint


@pytest.mark.parametrize(
    ("value", "encoded"),
    [
        (0, b"\x00"),
        (-1, b"\x01"),
        (1, b"\x02"),
        (63, b"\x7e"),
        (-64, b"\x7f"),
        (64, b"\x80\x80"),
        (8191, b"\xbf\xfe"),
        (-8192, b"\xbf\xff"),
        (8192, b"\xc0\x40\x00"),
        (1_048_575, b"\xdf\xff\xfe"),
        (-1_048_576, b"\xdf\xff\xff"),
        (1_048_576, b"\xe0\x20\x00\x00"),
        (134_217_727, b"\xef\xff\xff\xfe"),
        (-134_217_728, b"\xef\xff\xff\xff"),
        (134_217_728, b"\xf0\x10\x00\x00\x00"),
        (INT32_MAX, b"\xf0\xff\xff\xff\xfe"),
        (INT32_MIN, b"\xf0\xff\xff\xff\xff"),
    ],
)
def test_confirmed_packint_vectors(value: int, encoded: bytes) -> None:
    assert encode_packint(value) == encoded
    assert decode_packint(encoded) == (value, len(encoded))


@pytest.mark.parametrize(
    "value",
    [INT32_MIN, -134_217_728, -8192, -64, -1, 0, 1, 63, 64, 8192, 134_217_728, INT32_MAX],
)
def test_packint_round_trip(value: int) -> None:
    encoded = b"prefix" + encode_packint(value) + b"suffix"
    decoded, offset = decode_packint(encoded, len(b"prefix"))
    assert decoded == value
    assert offset == len(b"prefix") + len(encode_packint(value))


@pytest.mark.parametrize("data", [b"", b"\x80", b"\xc0\x00", b"\xe0\x00\x00", b"\xf0\x00\x00\x00"])
def test_truncated_packint_is_explicit(data: bytes) -> None:
    with pytest.raises(IncompletePacketError):
        decode_packint(data)


def test_malformed_packint_prefix_is_explicit() -> None:
    with pytest.raises(MalformedPacketError):
        decode_packint(b"\xf1\x00\x00\x00\x00")


@pytest.mark.parametrize("value", [INT32_MIN - 1, INT32_MAX + 1])
def test_packint_rejects_values_outside_int32(value: int) -> None:
    with pytest.raises(ValueError):
        encode_packint(value)

