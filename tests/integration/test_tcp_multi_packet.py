import asyncio

from tests.integration._network import (
    close_client,
    connect,
    guide_packet,
    observing_dispatcher,
    start_server,
)


def test_two_packets_in_one_tcp_write() -> None:
    async def scenario() -> None:
        queue = asyncio.Queue()
        server = await start_server(observing_dispatcher(queue))
        _, writer = await connect(server)
        writer.write(guide_packet(request_id=1) + guide_packet(request_id=2))
        await writer.drain()
        observed = [
            (await asyncio.wait_for(queue.get(), timeout=2.0))[1],
            (await asyncio.wait_for(queue.get(), timeout=2.0))[1],
        ]
        assert [packet.header.request_id for packet in observed] == [1, 2]
        await close_client(writer)
        await server.wait_for_active_connections(0)
        assert queue.empty()
        await server.stop()

    asyncio.run(scenario())

