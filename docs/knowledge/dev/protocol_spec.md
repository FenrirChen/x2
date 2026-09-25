---
Document-Type: Current Knowledge
Domain: Dev
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - (none; still authoritative)
---

# Confirmed protocol specification (M1)

Status labels in this document are normative.

## Transport

**CONFIRMED:** core game traffic uses a long-lived TCP connection. TCP is a byte stream; a receive operation is not a packet boundary.

## Frame

**CONFIRMED:**

```text
PackInt(totalLen)
PackInt(headLen)
protobuf header
PackInt(messageId)
protobuf body
```

`totalLen` excludes the byte count of its own PackInt prefix and includes every field after it. `headLen` is the exact serialized header byte count.

## PackInt

**CONFIRMED:** signed int32 is zigzag transformed with `(value << 1) ^ (value >> 31)`. The resulting unsigned value uses a big-endian, prefix-length representation:

- 0xxxxxxx: 7 payload bits / 1 byte
- 10xxxxxx + 1 byte: 14 bits / 2 bytes
- 110xxxxx + 2 bytes: 21 bits / 3 bytes
- 1110xxxx + 3 bytes: 28 bits / 4 bytes
- 11110000 + 4 bytes: 32 bits / 5 bytes

This is not protobuf varint. Decoder APIs return the offset immediately after the value.

## Headers and checksum

**CONFIRMED request header:** requestId, sessionid, ackDataVersion, sign, unitId.

**CONFIRMED response header:** requestId, sessionid, dataVersion, errno, errinfo.

**CONFIRMED:** request-header `sign` is unsigned CRC32 of the serialized body. It is unrelated to fight `sign`.

## Message body

**CONFIRMED:** headers and messages use SilentOrbit ProtocolBuffers-compatible protobuf wire format. There is no confirmed network compression or encryption.

The confirmed IDs are maintained in `src/x2server/protocol/registry.py`. No `L2C_CheckoutMainMissionSign` exists.

## Limits

The implementation default `MAX_PACKET_SIZE` is 16 MiB. This is **TEMPORARY_COMPAT**, a defensive local default rather than a recovered original-client constant, and may be adjusted using configuration after controlled compatibility tests.

