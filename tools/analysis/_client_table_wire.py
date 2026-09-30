"""Client Resources.ConvertDataBytes and strict protobuf table framing.

Preserved from the project's phase3_protobuf.py reverse engineering helper.
The first RSA block and the power-of-two XOR positions must be decoded before
reading rows; scanning the encrypted tail produces false 'damaged byte' reports.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

PUBLIC_KEY_DER_B64 = (
    "MIGdMA0GCSqGSIb3DQEBAQUAA4GLADCBhwKBgQCyJiTzABL2wironv9+4wnZTg7J"
    "Xr1ekiMA3RdL2e+W8kEtyZgghb5KBBAASKuiGNxhadrnSgC8+h1r7B/JLudatvdl"
    "zwyy1gAs/mbVYHd7x1WoBfzDpWkZX8bhDO/uX4GnBhWAmtapbbjVGOAVIuaIV8lB"
    "zNXJ30mJPDI4wKc7/QIBAw=="
)


def _tlv(data: bytes, pos: int):
    tag = data[pos]
    pos += 1
    length = data[pos]
    pos += 1
    if length & 0x80:
        n = length & 0x7F
        length = int.from_bytes(data[pos:pos + n], "big")
        pos += n
    return tag, data[pos:pos + length], pos + length


def public_numbers():
    der = base64.b64decode(PUBLIC_KEY_DER_B64)
    _, spki, _ = _tlv(der, 0)
    _, _, p = _tlv(spki, 0)  # AlgorithmIdentifier
    _, bitstr, _ = _tlv(spki, p)
    _, rsa_seq, _ = _tlv(bitstr[1:], 0)  # skip unused-bits byte
    _, modulus, p = _tlv(rsa_seq, 0)
    _, exponent, _ = _tlv(rsa_seq, p)
    return int.from_bytes(modulus, "big"), int.from_bytes(exponent, "big")


def rsa_public_unpad(block: bytes) -> bytes:
    n, e = public_numbers()
    if len(block) != 128:
        raise ValueError(f"expected 128-byte RSA block, got {len(block)}")
    plain = pow(int.from_bytes(block, "big"), e, n).to_bytes(128, "big")
    if plain[0] == 0:
        plain = plain[1:]
    if not plain or plain[0] not in (1, 2):
        raise ValueError(f"unexpected PKCS#1 block type: {plain[:8].hex()}")
    sep = plain.find(b"\0", 1)
    if sep < 10:
        raise ValueError("invalid PKCS#1 v1.5 padding")
    return plain[sep + 1:]


def convert_data_bytes(data: bytes) -> bytes:
    """Reproduce LogicX2.Resources.ConvertDataBytes without executing game code."""
    if len(data) < 128:
        raise ValueError("table payload shorter than RSA block")
    out = bytearray(rsa_public_unpad(data[:128]) + data[128:])
    delta = 0
    index = 1
    while index < len(out):
        out[index] ^= (delta + index) & 0xFF
        index <<= 1
        delta -= 1
    index = len(out) - 1
    delta = 0
    while index > 0:
        out[index] ^= (delta + index) & 0xFF
        index >>= 1
        delta -= 1
    return bytes(out)


class WireError(ValueError):
    pass


def read_varint(data: bytes, pos: int, end: int | None = None):
    if end is None:
        end = len(data)
    value = 0
    shift = 0
    start = pos
    while pos < end and shift < 70:
        b = data[pos]
        pos += 1
        value |= (b & 0x7F) << shift
        if not b & 0x80:
            return value, pos
        shift += 7
    raise WireError(f"bad varint at 0x{start:x}")


@dataclass
class WireValue:
    field: int
    wire: int
    value: int | bytes
    start: int
    end: int


def parse_message(data: bytes, start: int = 0, end: int | None = None):
    if end is None:
        end = len(data)
    pos = start
    values: list[WireValue] = []
    while pos < end:
        field_start = pos
        tag, pos = read_varint(data, pos, end)
        field, wire = tag >> 3, tag & 7
        if field == 0:
            raise WireError(f"field zero at 0x{field_start:x}")
        if wire == 0:
            value, pos = read_varint(data, pos, end)
        elif wire == 1:
            if pos + 8 > end:
                raise WireError(f"truncated fixed64 at 0x{field_start:x}")
            value = data[pos:pos + 8]
            pos += 8
        elif wire == 2:
            length, pos = read_varint(data, pos, end)
            if pos + length > end:
                raise WireError(f"truncated bytes at 0x{field_start:x}: {length}")
            value = data[pos:pos + length]
            pos += length
        elif wire == 5:
            if pos + 4 > end:
                raise WireError(f"truncated fixed32 at 0x{field_start:x}")
            value = data[pos:pos + 4]
            pos += 4
        else:
            raise WireError(f"unsupported wire {wire} at 0x{field_start:x}")
        values.append(WireValue(field, wire, value, field_start, pos))
    return values, pos


def parse_table_array(data: bytes):
    values, consumed = parse_message(data)
    keys = [v.value for v in values if v.field == 1 and v.wire == 0]
    items = [v.value for v in values if v.field == 2 and v.wire == 2]
    unknown = [v for v in values if not ((v.field == 1 and v.wire == 0) or (v.field == 2 and v.wire == 2))]
    return keys, items, unknown, consumed


def parse_table_container(encrypted: bytes):
    plain = convert_data_bytes(encrypted)
    if len(plain) >= 4:
        count = int.from_bytes(plain[:4], "little")
        if 0 <= count <= 1_000_000:
            try:
                keys, items, unknown, consumed = parse_table_array(plain[4:])
                if not unknown and consumed == len(plain) - 4 and len(keys) == len(items) == count:
                    return {"kind": "array", "declared_count": count, "keys": keys, "items": items,
                            "unknown_wrapper_fields": 0, "consumed": len(plain), "plain": plain}
            except WireError:
                pass
    values, consumed = parse_message(plain)
    if all(v.field == 1 and v.wire == 2 for v in values):
        return {"kind": "list", "declared_count": len(values), "keys": [],
                "items": [v.value for v in values], "unknown_wrapper_fields": 0,
                "consumed": consumed, "plain": plain}
    return {"kind": "unknown", "declared_count": None, "keys": [], "items": [],
            "unknown_wrapper_fields": len(values), "consumed": consumed, "plain": plain}


if __name__ == "__main__":
    import sys
    for arg in sys.argv[1:]:
        path = Path(arg)
        plain = convert_data_bytes(path.read_bytes())
        parsed = parse_table_container(path.read_bytes())
        keys, items = parsed["keys"], parsed["items"]
        print(path.name, "plain", len(plain), "kind", parsed["kind"], "keys", len(keys), "items", len(items), "unknown", parsed["unknown_wrapper_fields"], "consumed", parsed["consumed"])
        if parsed["items"]:
            fields, used = parse_message(parsed["items"][0])
            print(" first item", len(items[0]), "used", used, "tags", [(x.field, x.wire) for x in fields[:20]])
