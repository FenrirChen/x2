"""End-to-end account registration flow against the client's real HTTP contract.

Covers the recovered client chain (analysis/account_registration/current_auth_flow.md):
POST /register form {account,password} -> {"success": bool};
POST /loginwithpw -> TokenCtx; POST /apply/httpLogin -> LoginCtx with a
per-account playerID; then the TCP login restores the same player row.
"""
import asyncio
import json
from urllib.request import Request, urlopen
from urllib.parse import urlencode

from x2server.bootstrap.http_server import BootstrapHTTPServer
from x2server.bootstrap.local_identity import LocalIdentityService
from x2server.bootstrap.models import RecoveredBootstrapContract
from x2server.config.settings import Settings
from x2server.messages.core import CORE_SCHEMAS
from x2server.network.dispatcher import Dispatcher
from x2server.network.server import X2TCPServer
from x2server.player.accounts import AccountStore
from x2server.player.login import LoginService
from x2server.player.store import PlayerStore


class AccountFlow:
    def __init__(self, tmp_path, *, seed=None):
        self.store = PlayerStore(tmp_path / "player.db")
        self.accounts = AccountStore(self.store)
        seed_kwargs = dict(account=seed[0], password=seed[1]) if seed else {}
        self.identity = LocalIdentityService(
            RecoveredBootstrapContract.local(Settings(), game_server_port=29000),
            accounts=self.accounts, players=self.store, **seed_kwargs)

    def post(self, path, fields):
        body = self.identity.respond("POST", path, urlencode(fields).encode()).body
        return json.loads(body)

    def register(self, account, password):
        return self.post("/register", {"account": account, "password": password})

    def game_session(self, account, password):
        token_ctx = self.post("/loginwithpw", {"account": account, "password": password})
        assert token_ctx["code"] == "ok"
        login_ctx = self.post("/apply/httpLogin",
            {"accountid": account, "token": token_ctx["token"], "logintype": "GAME"})
        assert login_ctx["code"] == 1
        return token_ctx, login_ctx


def test_register_then_login_allocates_a_persistent_player(tmp_path):
    flow = AccountFlow(tmp_path)
    assert flow.register("nova", "pw1") == {"success": True}
    assert flow.register("nova", "other") == {"success": False}
    assert flow.accounts.get_by_name("nova")["player_id"] == 1
    assert flow.store.get(1)["snapshot"]["level"] == 1

    token_ctx, login_ctx = flow.game_session("nova", "pw1")
    assert token_ctx["id"] == 1  # first account id
    assert isinstance(login_ctx["entryPort"], str)
    player_id = login_ctx["playerID"]
    assert flow.identity.validates_game_identity(player_id, login_ctx["token"])
    assert not flow.identity.validates_game_identity(player_id, token_ctx["token"])
    assert flow.identity.account_for_player(player_id) == "nova"

    # Second login of the same account must restore the same player row.
    _, again = flow.game_session("nova", "pw1")
    assert again["playerID"] == player_id
    assert flow.store.get(player_id)["snapshot"]["nickname"] == "Revival"


def test_two_accounts_get_isolated_players(tmp_path):
    flow = AccountFlow(tmp_path)
    flow.register("nova", "pw1")
    flow.register("orbit", "pw2")
    _, first = flow.game_session("nova", "pw1")
    _, second = flow.game_session("orbit", "pw2")
    assert first["playerID"] != second["playerID"]
    assert flow.identity.account_for_player(first["playerID"]) == "nova"
    assert flow.identity.account_for_player(second["playerID"]) == "orbit"
    assert flow.store.db.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 2


def test_wrong_password_and_unknown_account_rules(tmp_path):
    flow = AccountFlow(tmp_path)
    flow.register("nova", "pw1")
    assert flow.post("/loginwithpw", {"account": "nova", "password": "bad"})["code"] == "invalid"
    assert flow.post("/loginwithpw", {"account": "unknown", "password": "visitor"})["code"] == "invalid"
    assert flow.accounts.get_by_name("unknown") is None
    # But an existing account never auto-accepts a different password.
    assert flow.post("/loginwithpw", {"account": "nova", "password": "pw1"})["code"] == "ok"


def test_httplogin_rejects_mismatched_credentials(tmp_path):
    flow = AccountFlow(tmp_path)
    flow.register("nova", "pw1")
    token_ctx = flow.post("/loginwithpw", {"account": "nova", "password": "pw1"})
    base = {"accountid": "nova", "token": token_ctx["token"], "logintype": "GAME"}
    assert flow.post("/apply/httpLogin", dict(base, token="forged"))["code"] == 0
    assert flow.post("/apply/httpLogin", dict(base, accountid="orbit"))["code"] == 0
    assert flow.post("/apply/httpLogin", dict(base, logintype="SDK"))["code"] == 0
    # The client may echo the token id instead of the name.
    assert flow.post("/apply/httpLogin", dict(base, accountid=str(token_ctx["id"])))["code"] == 1


def test_seeded_development_account_still_works(tmp_path):
    flow = AccountFlow(tmp_path, seed=("revival", "revival-local"))
    assert flow.post("/loginwithpw", {"account": "revival", "password": "revival-local"})["code"] == "ok"
    # A fresh database binds the seed account to its own new player.
    _, login_ctx = flow.game_session("revival", "revival-local")
    assert flow.store.get(login_ctx["playerID"])["account"] == "revival"


def test_registration_to_tcp_login_roundtrip(tmp_path):
    flow = AccountFlow(tmp_path)
    flow.register("nova", "pw1")
    _, login_ctx = flow.game_session("nova", "pw1")
    player_id, token = login_ctx["playerID"], login_ctx["token"]

    async def scenario():
        service = LoginService(flow.identity, flow.store)
        server = X2TCPServer(Settings(tcp_port=0), Dispatcher(
            {"C2L_Login": service.login, "C2L_ReConnect": service.reconnect}))
        await server.start()
        try:
            reader, writer = await asyncio.open_connection(server.bound_host, server.bound_port)
            from x2server.protocol.codec import ProtocolCodec
            from x2server.protocol.headers import RequestHeader, ResponseHeader
            from x2server.protocol.framing import PacketStreamDecoder
            writer.write(ProtocolCodec().encode(
                "C2L_Login", {"id": player_id, "token": token}, RequestHeader(request_id=1)))
            decoder = PacketStreamDecoder(ResponseHeader)
            packets = []
            while len(packets) < 2:
                data = await asyncio.wait_for(reader.read(4096), 2)
                assert data
                packets.extend(decoder.feed(data))
            login, push = packets
            values = CORE_SCHEMAS["L2C_Login"].decode(login.body)
            assert values["code"] == 10 and values["id"] == player_id
            assert values["isCreateRole"] is True  # first login of the new player
            writer.close()
            await writer.wait_closed()
        finally:
            await server.stop()
    asyncio.run(scenario())
    assert flow.store.get(player_id)["login_count"] == 1


def test_actual_http_wire_and_relogin_preserve_snapshot(tmp_path):
    flow = AccountFlow(tmp_path)

    async def scenario():
        http = BootstrapHTTPServer("127.0.0.1", 0, flow.identity)
        await http.start()
        try:
            def post(path, values):
                req = Request(f"http://127.0.0.1:{http.bound_port}{path}",
                    urlencode(values).encode("utf-8"), method="POST")
                with urlopen(req, timeout=3) as response:
                    assert response.status == 200
                    return json.load(response)
            assert await asyncio.to_thread(post, "/register", {"account": "fresh", "password": "pw"}) == {"success": True}
            assert await asyncio.to_thread(post, "/register", {"account": "fresh", "password": "pw"}) == {"success": False}
            token = await asyncio.to_thread(post, "/loginwithpw", {"account": "fresh", "password": "pw"})
            assert token["code"] == "ok"
            first = await asyncio.to_thread(post, "/apply/httpLogin", {
                "accountid": "fresh", "token": token["token"], "logintype": "GAME"})
            assert first["code"] == 1
            player_id = first["playerID"]
            player = flow.store.get(player_id)
            player["snapshot"]["gold"] = 37
            flow.store.save_snapshot(player_id, player["snapshot"], player["revision"])
        finally:
            await http.stop()
        return player_id
    player_id = asyncio.run(scenario())
    flow.accounts.close()
    flow.store.close()
    reopened = AccountFlow(tmp_path)
    _, second = reopened.game_session("fresh", "pw")
    assert second["playerID"] == player_id
    assert reopened.store.get(player_id)["snapshot"]["gold"] == 37
    assert reopened.store.db.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 1
