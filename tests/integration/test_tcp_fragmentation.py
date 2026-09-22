import asyncio

from tests.integration._network import (
    close_client,
    connect,
    guide_packet,
    observing_dispatcher,
    start_server,
)


def test_packet_split_across_three_tcp_writes() -> None:
    async def scenario() -> None:
        queue = asyncio.Queue()
        server = await start_server(observing_dispatcher(queue))
        _, writer = await connect(server)
        packet = guide_packet()
        first, second = len(packet) // 3, (len(packet) * 2) // 3
        for chunk in (packet[:first], packet[first:second], packet[second:]):
            writer.write(chunk)
            await writer.drain()
        _, observed = await asyncio.wait_for(queue.get(), timeout=2.0)
        assert observed.message_id == 374
        await close_client(writer)
        await server.wait_for_active_connections(0)
        assert queue.empty()
        await server.stop()

    asyncio.run(scenario())


def test_complete_packet_then_partial_packet_waits_for_remainder() -> None:
    async def scenario() -> None:
        queue = asyncio.Queue()
        server = await start_server(observing_dispatcher(queue))
        _, writer = await connect(server)
        first = guide_packet(request_id=1, step_id=21011)
        second = guide_packet(request_id=2, step_id=21012)
        split = len(second) // 2
        writer.write(first + second[:split])
        await writer.drain()
        _, first_observed = await asyncio.wait_for(queue.get(), timeout=2.0)
        assert first_observed.header.request_id == 1
        assert queue.empty()
        writer.write(second[split:])
        await writer.drain()
        _, second_observed = await asyncio.wait_for(queue.get(), timeout=2.0)
        assert second_observed.header.request_id == 2
        await close_client(writer)
        await server.wait_for_active_connections(0)
        await server.stop()

    asyncio.run(scenario())

