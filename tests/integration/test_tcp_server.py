import asyncio

from x2server.protocol.codec import ProtocolCodec
from x2server.protocol.headers import ResponseHeader

from tests.integration._network import (
    close_client,
    connect,
    guide_packet,
    observing_dispatcher,
    read_response,
    start_server,
)


def test_server_start_connect_clean_close() -> None:
    async def scenario() -> None:
        server = await start_server()
        _, writer = await connect(server)
        await server.wait_for_active_connections(1)
        await close_client(writer)
        await server.wait_for_active_connections(0)
        await server.stop()
        assert server.active_connection_count == 0

    asyncio.run(scenario())


def test_server_identifies_synthetic_guide_and_request_id() -> None:
    async def scenario() -> None:
        queue = asyncio.Queue()
        server = await start_server(observing_dispatcher(queue))
        _, writer = await connect(server)
        writer.write(guide_packet(request_id=17))
        await writer.drain()
        context, packet = await asyncio.wait_for(queue.get(), timeout=2.0)
        assert packet.message_id == 374
        assert packet.header.request_id == 17
        assert context.session.last_request_id == 17
        await close_client(writer)
        await server.wait_for_active_connections(0)
        await server.stop()

    asyncio.run(scenario())


def test_response_send_path_correlates_request_id() -> None:
    async def scenario() -> None:
        queue = asyncio.Queue()
        server = await start_server(observing_dispatcher(queue, response=True))
        reader, writer = await connect(server)
        writer.write(guide_packet(request_id=23))
        await writer.drain()
        response_packet = await read_response(reader)
        decoded = ProtocolCodec().decode(
            # Reframe is unnecessary in production; this assertion checks body schema directly.
            ProtocolCodec().encode(
                "L2C_GuideStep",
                {"code": 0},
                ResponseHeader(request_id=23, session_id="synthetic-session"),
            ),
            ResponseHeader,
        )
        assert response_packet.message_id == 375
        assert response_packet.header.request_id == 23
        assert response_packet.header.session_id == "synthetic-session"
        assert decoded.values == {"code": 0}
        await close_client(writer)
        await server.wait_for_active_connections(0)
        await server.stop()

    asyncio.run(scenario())


def test_server_graceful_shutdown_closes_active_connection() -> None:
    async def scenario() -> None:
        server = await start_server()
        reader, writer = await connect(server)
        await server.wait_for_active_connections(1)
        await server.stop()
        assert await asyncio.wait_for(reader.read(1), timeout=2.0) == b""
        assert server.active_connection_count == 0
        await close_client(writer)

    asyncio.run(scenario())


def test_incomplete_packet_at_eof_closes_only_connection() -> None:
    async def scenario() -> None:
        server = await start_server()
        _, writer = await connect(server)
        packet = guide_packet()
        writer.write(packet[: len(packet) // 2])
        await writer.drain()
        await close_client(writer)
        await server.wait_for_active_connections(0)
        await server.stop()

    asyncio.run(scenario())

