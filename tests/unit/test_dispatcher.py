import asyncio

from x2server.network.dispatcher import (
    DispatchContext,
    Dispatcher,
    DispatchStatus,
)
from x2server.network.session import SessionState
from x2server.protocol.headers import RequestHeader
from x2server.protocol.types import DecodedPacket


def packet(message_id: int) -> DecodedPacket:
    return DecodedPacket(1, 0, RequestHeader(request_id=9), message_id, b"")


def test_known_message_without_handler_is_explicitly_unimplemented() -> None:
    async def scenario() -> None:
        context = DispatchContext("connection-1", "127.0.0.1:1", SessionState("connection-1"))
        outcome = await Dispatcher().dispatch(context, packet(54))
        assert outcome.status is DispatchStatus.UNIMPLEMENTED
        assert outcome.message_name == "C2L_Login"
        assert outcome.response is None

    asyncio.run(scenario())


def test_unknown_message_is_nonfatal_and_explicit() -> None:
    async def scenario() -> None:
        context = DispatchContext("connection-1", "127.0.0.1:1", SessionState("connection-1"))
        outcome = await Dispatcher().dispatch(context, packet(999_999))
        assert outcome.status is DispatchStatus.UNKNOWN
        assert outcome.message_name is None

    asyncio.run(scenario())

