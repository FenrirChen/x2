"""Exercise the separate quiet channel using the actual framed handshake."""
import asyncio
import json

from x2server.bootstrap.local_identity import LocalIdentityService
from x2server.bootstrap.models import RecoveredBootstrapContract
from x2server.config.settings import Settings
from x2server.messages.chat import CHAT_SCHEMAS
from x2server.network.dispatcher import Dispatcher
from x2server.network.server import X2TCPServer
from x2server.player.chat import SilentChatService
from x2server.protocol.codec import ProtocolCodec
from x2server.protocol.framing import PacketStreamDecoder
from x2server.protocol.headers import RequestHeader, ResponseHeader


def test_chat_node_and_fragmented_join_with_heartbeat():
    identity = LocalIdentityService(RecoveredBootstrapContract.local(Settings(), game_server_port=29000),
                                    account="lab", password="local")
    nodes = json.loads(identity.respond("POST", "/apply/chatNode").body)
    assert nodes[0]["entry"] == "10.0.2.2:29001"
    assert json.loads(nodes[0]["channel"]) == [{"channel": 1, "free": 1, "limit": 1}]
    # The client serializer uses tag 0x30 for channelId, not field 4.
    assert CHAT_SCHEMAS["C2L_ChatJoin"].decode(bytes.fromhex("08013001")) == {"PlayerID": 1, "channelId": 1}

    async def scenario():
        server = X2TCPServer(Settings(tcp_port=0), Dispatcher(SilentChatService().handlers()))
        await server.start()
        reader, writer = await asyncio.open_connection(server.bound_host, server.bound_port)
        decoder = PacketStreamDecoder(ResponseHeader)
        async def reply():
            while True:
                data = await asyncio.wait_for(reader.read(4096), 2)
                assert data
                packets = decoder.feed(data)
                if packets:
                    assert len(packets) == 1
                    return packets[0]
        try:
            for request_id, player, code in ((1, 2, 13), (2, 1, 10)):
                packet = ProtocolCodec().encode("C2L_ChatJoin", {"PlayerID": player, "channelId": 1},
                                                RequestHeader(request_id=request_id))
                writer.write(b"\0\0" + packet[:5])
                await writer.drain()
                writer.write(packet[5:])
                response = await reply()
                assert response.message_id == 522 and response.header.request_id == request_id
                assert CHAT_SCHEMAS["L2C_ChatJoin"].decode(response.body)["code"] == code
            writer.write(b"\0\0" + ProtocolCodec().encode("C2L_ChatAway", {}, RequestHeader(request_id=3)))
            assert (await reply()).message_id == 528
        finally:
            writer.close()
            await writer.wait_closed()
            await server.stop()
    asyncio.run(scenario())
