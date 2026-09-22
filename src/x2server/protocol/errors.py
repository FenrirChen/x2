"""Explicit protocol failures; callers must not silently discard them."""


class ProtocolError(Exception):
    """Base class for recovered X2 protocol failures."""


class MalformedPacketError(ProtocolError):
    """A packet or scalar violates the confirmed wire format."""


class IncompletePacketError(ProtocolError):
    """More bytes are required before decoding can continue."""


class UnknownMessageError(ProtocolError):
    """A message name or numeric ID is not registered."""


class ChecksumMismatchError(ProtocolError):
    """The request-header CRC32 does not match the message body."""


class ProtobufDecodeError(ProtocolError):
    """A protobuf value is truncated or incompatible with its schema."""

