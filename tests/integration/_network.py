from __future__ import annotations

import asyncio

from x2server.config.settings import Settings
from x2server.network.dispatcher import DispatchContext, Dispatcher, OutboundMessage
from x2server.network.server import X2TCPServer
from x2server.protocol.codec import ProtocolCodec
from x2server.protocol.headers import RequestHeader, ResponseHeader
from x2server.protocol.types import DecodedPacket


def guide_packet(request_id: int = 1, step_id: int = 21011) -> bytes:
    return ProtocolCodec().encode(
        "C2L_GuideStep",
        {"stepId": step_id, "stepState": 2},
        RequestHeader(
            request_id=request_id,
            session_id="synthetic-session",
            ack_data_version=1,
            unit_id=100,
        ),
    )


def observing_dispatcher(
    queue: asyncio.Queue[tuple[DispatchContext, DecodedPacket]],
    *,
    response: bool = False,
) -> Dispatcher:
    async def handler(
        context: DispatchContext, packet: DecodedPacket
    ) -> OutboundMessage | None:
        queue.put_nowait((context, packet))
        return OutboundMessage("L2C_GuideStep", {"code": 0}) if response else None

    return Dispatcher({"C2L_GuideStep": handler})


async def start_server(
    dispatcher: Dispatcher | None = None,
    *,
    max_packet_size: int = 16 * 1024 * 1024,
) -> X2TCPServer:
    settings = Settings(
        tcp_host="127.0.0.1",
        tcp_port=0,
        read_timeout=2.0,
        write_timeout=2.0,
        idle_timeout=2.0,
        max_packet_size=max_packet_size,
    )
    server = X2TCPServer(settings, dispatcher)
    await server.start()
    return server


async def connect(server: X2TCPServer) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    return await asyncio.open_connection(server.bound_host, server.bound_port)


async def close_client(writer: asyncio.StreamWriter) -> None:
    writer.close()
    await writer.wait_closed()


async def read_response(reader: asyncio.StreamReader) -> DecodedPacket:
    from x2server.protocol.framing import PacketStreamDecoder

    decoder = PacketStreamDecoder(ResponseHeader)
    while True:
        data = await asyncio.wait_for(reader.read(4096), timeout=2.0)
        if not data:
            raise AssertionError("connection closed before response")
        packets = decoder.feed(data)
        if packets:
            assert len(packets) == 1
            return packets[0]

