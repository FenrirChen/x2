"""Small protobuf-wire subset required by the confirmed M1 schemas.

This is intentionally not a generic protobuf framework. It supports the wire
types observed in selected X2 messages while keeping nested messages opaque.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .errors import ProtobufDecodeError


class FieldKind(Enum):
    """Supported protobuf scalar representations."""

    INT32 = "int32"
    UINT32 = "uint32"
    INT64 = "int64"
    BOOL = "bool"
    ENUM = "enum"
    STRING = "string"
    BYTES = "bytes"
    MESSAGE = "message"


@dataclass(frozen=True, slots=True)
class ProtoField:
    """One recovered protobuf field."""

    number: int
    name: str
    kind: FieldKind
    repeated: bool = False

    @property
    def wire_type(self) -> int:
        if self.kind in {
            FieldKind.INT32,
            FieldKind.UINT32,
            FieldKind.INT64,
            FieldKind.BOOL,
            FieldKind.ENUM,
        }:
            return 0
        return 2


def encode_varint(value: int) -> bytes:
    """Encode an unsigned protobuf varint."""
    if value < 0 or value > 0xFFFFFFFFFFFFFFFF:
        raise ValueError(f"protobuf varint outside uint64 range: {value}")
    output = bytearray()
    while value >= 0x80:
        output.append((value & 0x7F) | 0x80)
        value >>= 7
    output.append(value)
    return bytes(output)


def decode_varint(data: bytes | bytearray | memoryview, offset: int = 0) -> tuple[int, int]:
    """Decode a protobuf uint64 varint and return value plus new offset."""
    view = memoryview(data).cast("B")
    value = 0
    for index in range(10):
        position = offset + index
        if position >= len(view):
            raise ProtobufDecodeError("truncated protobuf varint")
        byte = view[position]
        if index == 9 and byte > 1:
            raise ProtobufDecodeError("protobuf varint exceeds uint64")
        value |= (byte & 0x7F) << (7 * index)
        if byte < 0x80:
            return value, position + 1
    raise ProtobufDecodeError("protobuf varint exceeds ten bytes")


def _encode_scalar(field: ProtoField, value: Any) -> bytes:
    if field.wire_type == 0:
        if field.kind is FieldKind.BOOL:
            integer = int(bool(value))
        else:
            integer = int(value)
            if integer < 0:
                integer &= 0xFFFFFFFFFFFFFFFF
        return encode_varint(integer)
    if field.kind is FieldKind.STRING:
        raw = str(value).encode("utf-8")
    elif field.kind in {FieldKind.BYTES, FieldKind.MESSAGE}:
        raw = bytes(value)
    else:  # pragma: no cover - guarded by the supported FieldKind set
        raise TypeError(f"unsupported field kind: {field.kind}")
    return encode_varint(len(raw)) + raw


def _decode_scalar(field: ProtoField, data: memoryview, offset: int) -> tuple[Any, int]:
    if field.wire_type == 0:
        value, offset = decode_varint(data, offset)
        if field.kind is FieldKind.INT32 and value & (1 << 31):
            value -= 1 << 64 if value > 0xFFFFFFFF else 1 << 32
        elif field.kind is FieldKind.INT64 and value & (1 << 63):
            value -= 1 << 64
        elif field.kind is FieldKind.BOOL:
            value = bool(value)
        return value, offset

    length, offset = decode_varint(data, offset)
    end = offset + length
    if end > len(data):
        raise ProtobufDecodeError("truncated length-delimited protobuf field")
    raw = bytes(data[offset:end])
    if field.kind is FieldKind.STRING:
        try:
            return raw.decode("utf-8"), end
        except UnicodeDecodeError as exc:
            raise ProtobufDecodeError("invalid UTF-8 protobuf string") from exc
    return raw, end


def _skip_unknown(wire_type: int, data: memoryview, offset: int) -> int:
    if wire_type == 0:
        _, offset = decode_varint(data, offset)
        return offset
    if wire_type == 1:
        end = offset + 8
    elif wire_type == 2:
        length, offset = decode_varint(data, offset)
        end = offset + length
    elif wire_type == 5:
        end = offset + 4
    else:
        raise ProtobufDecodeError(f"unsupported protobuf wire type: {wire_type}")
    if end > len(data):
        raise ProtobufDecodeError("truncated unknown protobuf field")
    return end


class ProtoSchema:
    """Encode and decode dictionary values for one recovered message schema."""

    def __init__(self, name: str, fields: tuple[ProtoField, ...]) -> None:
        self.name = name
        self.fields = fields
        self._by_number = {field.number: field for field in fields}
        self._by_name = {field.name: field for field in fields}
        if len(self._by_number) != len(fields) or len(self._by_name) != len(fields):
            raise ValueError(f"duplicate protobuf field in {name}")

    def encode(self, values: Mapping[str, Any]) -> bytes:
        """Serialize known values in stable field-number order."""
        unknown = set(values) - self._by_name.keys()
        if unknown:
            raise KeyError(f"unknown {self.name} fields: {sorted(unknown)}")
        output = bytearray()
        for field in sorted(self.fields, key=lambda item: item.number):
            if field.name not in values or values[field.name] is None:
                continue
            raw_values = values[field.name] if field.repeated else (values[field.name],)
            if field.repeated and isinstance(raw_values, (str, bytes, bytearray)):
                raise TypeError(f"repeated field {field.name} requires an iterable of values")
            for value in raw_values:
                output += encode_varint((field.number << 3) | field.wire_type)
                output += _encode_scalar(field, value)
        return bytes(output)

    def decode(self, data: bytes) -> dict[str, Any]:
        """Decode known fields and safely skip protobuf-compatible unknown fields."""
        view = memoryview(data)
        result: dict[str, Any] = {}
        offset = 0
        while offset < len(view):
            key, offset = decode_varint(view, offset)
            number, wire_type = key >> 3, key & 0x07
            if number == 0:
                raise ProtobufDecodeError("protobuf field number zero is invalid")
            field = self._by_number.get(number)
            if field is None:
                offset = _skip_unknown(wire_type, view, offset)
                continue
            if wire_type != field.wire_type:
                raise ProtobufDecodeError(
                    f"{self.name}.{field.name} expected wire {field.wire_type}, got {wire_type}"
                )
            value, offset = _decode_scalar(field, view, offset)
            if field.repeated:
                result.setdefault(field.name, []).append(value)
            else:
                result[field.name] = value
        return result

