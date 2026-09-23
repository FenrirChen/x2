import asyncio
import json
from urllib.parse import urlencode

from x2server.bootstrap.local_identity import LocalIdentityService
from x2server.bootstrap.models import RecoveredBootstrapContract
from x2server.config.settings import Settings
from x2server.messages.core import CORE_SCHEMAS, BASE_INFO, PLAYER_DATA, MOBILITY, HERO_ALL, HERO_DATA, STRING_PAIR
from x2server.network.dispatcher import Dispatcher
from x2server.network.server import X2TCPServer
from x2server.player.login import LoginService
from x2server.player.hero import HeroService
from x2server.player.lobby import LobbyService
from x2server.messages.lobby import LOBBY_IDS
from x2server.player.store import PlayerStore
from x2server.protocol.codec import ProtocolCodec
from x2server.protocol.framing import PacketStreamDecoder
from x2server.protocol.headers import RequestHeader, ResponseHeader


def identity_and_token():
    identity = LocalIdentityService(RecoveredBootstrapContract.local(Settings(), game_server_port=29000),
                                    account="lab", password="local")
    def post(path, values):
        return json.loads(identity.respond("POST", path, urlencode(values).encode()).body)
    account = post("/loginwithpw", {"account": "lab", "password": "local"})
    game = post("/apply/httpLogin", {"accountid": "lab", "token": account["token"], "logintype": "GAME"})
    return identity, game["token"]


def test_login_push_heartbeat_reconnect_and_authentication(tmp_path):
    async def scenario():
        identity, token = identity_and_token()
        store = PlayerStore(tmp_path / "player.db")
        service = LoginService(identity, store)
        server = X2TCPServer(Settings(tcp_port=0), Dispatcher({**LobbyService().handlers(),
            "C2L_HeroAll": HeroService(store).query_all, "C2L_Login": service.login,
            "C2L_ReConnect": service.reconnect, "C2L_ServerTableConfig": service.server_config}))
        await server.start()
        writers = []

        async def connect():
            reader, writer = await asyncio.open_connection(server.bound_host, server.bound_port)
            writers.append(writer)
            return reader, writer

        async def read(reader, count):
            decoder = PacketStreamDecoder(ResponseHeader)
            packets = []
            while len(packets) < count:
                data = await asyncio.wait_for(reader.read(4096), 2)
                assert data
                packets.extend(decoder.feed(data))
            assert len(packets) == count
            return packets

        def send(writer, name, values, request_id=1, session=""):
            writer.write(ProtocolCodec().encode(name, values, RequestHeader(request_id=request_id, session_id=session)))

        try:
            reader, writer = await connect()
            send(writer, "C2L_SystemInfo", {})
            assert await asyncio.wait_for(reader.read(1), 2) == b""
            reader, writer = await connect()
            send(writer, "C2L_Login", {"id": 1, "token": "wrong"})
            assert await asyncio.wait_for(reader.read(1), 2) == b""
            assert store.db.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 0

            reader, writer = await connect()
            send(writer, "C2L_Login", {"id": 1, "token": token}, request_id=7)
            login, push = await read(reader, 2)
            values = CORE_SCHEMAS["L2C_Login"].decode(login.body)
            assert values["code"] == 10 and values["isCreateRole"] is True
            assert login.header.request_id == 7 and login.header.session_id
            assert push.message_id == 1000 and push.header.request_id == 0
            assert push.header.data_version == 1
            base = BASE_INFO.decode(PLAYER_DATA.decode(push.body)["BaseInfo"])
            assert base["Id"] == 1 and base["NickName"] == store.get(1)["snapshot"]["nickname"]
            session = login.header.session_id
            writer.write(b"\0\0")
            send(writer, "C2L_ServerTableConfig", {}, 8, "")
            config, = await read(reader, 1)
            assert config.message_id == 946 and config.header.request_id == 8
            assert config.header.session_id == session
            config_values = CORE_SCHEMAS["L2C_ServerTableConfig"].decode(config.body)
            assert STRING_PAIR.decode(config_values["keyVal"][0]) == {"key": "PowerBuyNum", "val": "120"}
            before_queries = store.get(1)
            for index, (name, _, response_id) in enumerate(LOBBY_IDS, 100):
                request = {"type": 3, "chapterId": 1} if name == "GameTask" else {}
                if name == "ReceiveGiftRew":
                    request = {"type": 2}
                if name == "AccountBuffData":
                    request = {"buffId": [1, 2]}
                send(writer, "C2L_" + name, request, index, session)
                reply, = await read(reader, 1)
                assert reply.message_id == response_id and reply.header.request_id == index
                decoded = CORE_SCHEMAS["L2C_" + name].decode(reply.body)
                if name == "GameTask":
                    assert decoded["type"] == 3 and decoded["chapterId"] == 1
                if name == "ReceiveGiftRew":
                    assert decoded["code"] == 13 and "rewardData" not in decoded
                if name == "AccountBuffData":
                    assert decoded["buffId"] == [1, 2]
            assert store.get(1) == before_queries  # Queries/denied gifts cannot grant anything.
            writer.close()
            await writer.wait_closed()

            reader, writer = await connect()
            send(writer, "C2L_ReConnect", {"id": 1, "token": token}, 9, session)
            reconnect, = await read(reader, 1)
            assert CORE_SCHEMAS["L2C_ReConnect"].decode(reconnect.body)["code"] == 10
            assert store.get(1)["login_count"] == 1
            send(writer, "C2L_ServerTableConfig", {}, 10, "spoofed")
            assert await asyncio.wait_for(reader.read(1), 2) == b""

            current = store.get(1)
            saved = dict(current["snapshot"], level=60, main_chapter=2010000,
                main_section=2110001, heroes=[{"id": 1003, "state": 2, "level": 1, "star": 1}],
                mobility={"power": 149})
            store.save_snapshot(1, saved, current["revision"])
            reader, writer = await connect()
            send(writer, "C2L_Login", {"id": 1, "token": token}, 11)
            login, push = await read(reader, 2)
            login_values = CORE_SCHEMAS["L2C_Login"].decode(login.body)
            hero = HERO_DATA.decode(HERO_ALL.decode(login_values["heroAll"])["heros"][0])
            assert hero["id"] == 1003 and hero["state"] == 2
            assert hero["godEquip"] == b""  # Client requires a present no-equipment object.
            player_data = PLAYER_DATA.decode(push.body)
            assert MOBILITY.decode(player_data["Mobility"])["Power"] == 149
            base = BASE_INFO.decode(player_data["BaseInfo"])
            assert (base["Level"], base["MainChapter"], base["MainSection"]) == (60, 2010000, 2110001)
            send(writer, "C2L_HeroAll", {}, 12, login.header.session_id)
            reply, = await read(reader, 1)
            assert reply.message_id == 547 and reply.header.request_id == 12
            assert HERO_ALL.decode(reply.body) == HERO_ALL.decode(login_values["heroAll"])
            writer.close()
            await writer.wait_closed()
            assert store.get(1)["snapshot"] == saved

            # Recreating identity invalidates old tokens; player data remains durable.
            replacement, _ = identity_and_token()
            assert not replacement.validates_game_identity(1, token)
        finally:
            for writer in writers:
                writer.close()
                await writer.wait_closed()
            await server.stop()
            store.close()
    asyncio.run(scenario())
