import asyncio

from x2server.protocol.packint import encode_packint

from tests.integration._network import (
    close_client,
    connect,
    guide_packet,
    observing_dispatcher,
    start_server,
)


def test_bad_crc_closes_current_connection_but_server_survives() -> None:
    async def scenario() -> None:
        queue = asyncio.Queue()
        server = await start_server(observing_dispatcher(queue))
        reader, writer = await connect(server)
        damaged = bytearray(guide_packet())
        damaged[-1] ^= 1
        writer.write(damaged)
        await writer.drain()
        assert await asyncio.wait_for(reader.read(1), timeout=2.0) == b""
        await server.wait_for_active_connections(0)
        await close_client(writer)

        _, valid_writer = await connect(server)
        valid_writer.write(guide_packet(request_id=2))
        await valid_writer.drain()
        _, observed = await asyncio.wait_for(queue.get(), timeout=2.0)
        assert observed.header.request_id == 2
        await close_client(valid_writer)
        await server.wait_for_active_connections(0)
        await server.stop()

    asyncio.run(scenario())


def test_oversized_length_safely_disconnects_client() -> None:
    async def scenario() -> None:
        server = await start_server(max_packet_size=100)
        reader, writer = await connect(server)
        writer.write(encode_packint(101))
        await writer.drain()
        assert await asyncio.wait_for(reader.read(1), timeout=2.0) == b""
        await server.wait_for_active_connections(0)
        await close_client(writer)
        await server.stop()

    asyncio.run(scenario())


def test_malformed_packint_safely_disconnects_client() -> None:
    async def scenario() -> None:
        server = await start_server()
        reader, writer = await connect(server)
        writer.write(b"\xf1\x00\x00\x00\x00")
        await writer.drain()
        assert await asyncio.wait_for(reader.read(1), timeout=2.0) == b""
        await server.wait_for_active_connections(0)
        await close_client(writer)
        await server.stop()

    asyncio.run(scenario())

