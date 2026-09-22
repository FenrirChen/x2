"""Confirmed protobuf request and response header models."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .crc import body_crc32
from .protobuf import FieldKind, ProtoField, ProtoSchema

_REQUEST_SCHEMA = ProtoSchema(
    "CC_ClientRequestHead",
    (
        ProtoField(1, "requestId", FieldKind.UINT32),
        ProtoField(2, "sessionid", FieldKind.STRING),
        ProtoField(3, "ackDataVersion", FieldKind.INT32),
        ProtoField(4, "sign", FieldKind.INT64),
        ProtoField(5, "unitId", FieldKind.INT64),
    ),
)

_RESPONSE_SCHEMA = ProtoSchema(
    "CC_ClientResponseHead",
    (
        ProtoField(1, "requestId", FieldKind.UINT32),
        ProtoField(2, "sessionid", FieldKind.STRING),
        ProtoField(3, "dataVersion", FieldKind.INT32),
        ProtoField(4, "errno", FieldKind.INT32),
        ProtoField(5, "errinfo", FieldKind.STRING),
    ),
)


@dataclass(frozen=True, slots=True)
class RequestHeader:
    """Client request envelope header."""

    request_id: int = 0
    session_id: str = ""
    ack_data_version: int = 0
    sign: int = 0
    unit_id: int = 0

    def with_body_checksum(self, body: bytes) -> RequestHeader:
        """Return a copy whose sign is the confirmed body CRC32."""
        return replace(self, sign=body_crc32(body))

    def to_bytes(self) -> bytes:
        """Serialize this header as protobuf."""
        return _REQUEST_SCHEMA.encode(
            {
                "requestId": self.request_id,
                "sessionid": self.session_id,
                "ackDataVersion": self.ack_data_version,
                "sign": self.sign,
                "unitId": self.unit_id,
            }
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> RequestHeader:
        """Deserialize a request header from protobuf bytes."""
        values = _REQUEST_SCHEMA.decode(data)
        return cls(
            request_id=values.get("requestId", 0),
            session_id=values.get("sessionid", ""),
            ack_data_version=values.get("ackDataVersion", 0),
            sign=values.get("sign", 0),
            unit_id=values.get("unitId", 0),
        )


@dataclass(frozen=True, slots=True)
class ResponseHeader:
    """Server response envelope header."""

    request_id: int = 0
    session_id: str = ""
    data_version: int = 0
    errno: int = 0
    errinfo: str = ""

    def to_bytes(self) -> bytes:
        """Serialize this header as protobuf."""
        return _RESPONSE_SCHEMA.encode(
            {
                "requestId": self.request_id,
                "sessionid": self.session_id,
                "dataVersion": self.data_version,
                "errno": self.errno,
                "errinfo": self.errinfo,
            }
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> ResponseHeader:
        """Deserialize a response header from protobuf bytes."""
        values = _RESPONSE_SCHEMA.decode(data)
        return cls(
            request_id=values.get("requestId", 0),
            session_id=values.get("sessionid", ""),
            data_version=values.get("dataVersion", 0),
            errno=values.get("errno", 0),
            errinfo=values.get("errinfo", ""),
        )

