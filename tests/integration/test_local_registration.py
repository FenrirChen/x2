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
from x2server.player.economy import EconomyService
from x2server.player.mail import MailService
from x2server.network.dispatcher import DispatchContext
from x2server.network.session import SessionState
from tests.unit.test_battle import packet


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
    assert flow.store.get(player_id)["snapshot"]["nickname"] == ""
    assert [h["id"] for h in flow.store.get(player_id)["snapshot"]["heroes"]] == [1003]


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


def test_tcp_login_creates_daily_mail_once_after_registration(tmp_path):
    flow = AccountFlow(tmp_path)
    assert flow.register("nova", "pw") == {"success": True}
    _, login_ctx = flow.game_session("nova", "pw")
    economy = EconomyService(flow.store)
    mail = MailService(flow.store, economy)
    service = LoginService(flow.identity, flow.store, economy=economy, mail=mail)
    request = packet({"id": login_ctx["playerID"], "token": login_ctx["token"]}, name="C2L_Login")
    for _ in range(2):
        context = DispatchContext("test", "local", SessionState("test"))
        response = asyncio.run(service.login(context, request))
        assert response.values["code"] == 10
        assert next(push for push in response.pushes if push.message_name == "L2C_MailData").values["total"] == 2
    assert flow.store.db.execute("SELECT count(*) FROM player_mail").fetchone()[0] == 2


def test_reconnect_creates_and_pushes_daily_mail_once(tmp_path):
    flow = AccountFlow(tmp_path)
    assert flow.register("nova", "pw") == {"success": True}
    _, login_ctx = flow.game_session("nova", "pw")
    economy = EconomyService(flow.store)
    mail = MailService(flow.store, economy)
    service = LoginService(flow.identity, flow.store, economy=economy, mail=mail)
    request = packet({"id": login_ctx["playerID"], "token": login_ctx["token"]},
                     name="C2L_ReConnect")
    context = DispatchContext("test", "local", SessionState("test"))
    first = asyncio.run(service.reconnect(context, request))
    assert first.values["code"] == 10
    assert next(push for push in first.pushes if push.message_name == "L2C_MailData").values["total"] == 2
    second = asyncio.run(service.reconnect(context, request))
    assert second.values["code"] == 10
    assert not any(push.message_name == "L2C_MailData" for push in second.pushes)
    assert flow.store.db.execute("SELECT count(*) FROM player_mail").fetchone()[0] == 2


def test_http_mail_page_uses_game_token_and_isolates_accounts(tmp_path):
    flow = AccountFlow(tmp_path)
    assert flow.register("nova", "pw") == {"success": True}
    assert flow.register("orbit", "pw") == {"success": True}
    _, first = flow.game_session("nova", "pw")
    _, second = flow.game_session("orbit", "pw")
    assert flow.accounts.ensure_daily_login_mail(first["playerID"], 1_800_000_000)
    args = {"appid": flow.identity.contract.web_config.service_app_id,
            "userid": str(first["playerID"]), "page": 1, "page_num": 20, "state": -1}
    def query(token):
        response = flow.identity.respond("POST", "/MailService.GetMailPage",
            json.dumps(args).encode(), authorization="Bearer " + token)
        return response.status, json.loads(response.body)
    status, result = query(first["token"])
    assert status == 200 and result["data"]["total"] == 2
    assert len(result["data"]["mails"]) == 2
    assert json.loads(result["data"]["mails"][0]["attachment"])["attachment"]
    assert query(second["token"])[0] == 403
    assert query("invalid")[0] == 401


def test_real_client_bare_bearer_mail_requires_local_single_online_player(tmp_path):
    flow = AccountFlow(tmp_path)
    flow.register("nova", "pw")
    flow.register("orbit", "pw")
    _, first = flow.game_session("nova", "pw")
    flow.game_session("orbit", "pw")
    player_id = first["playerID"]
    flow.identity.allow_local_mail_without_token = True
    flow.identity.active_mail_players = lambda: {player_id}
    args = {"appid": flow.identity.contract.web_config.service_app_id,
            "userid": str(player_id), "page": 1, "page_num": 20, "state": -1}
    def query(values):
        return flow.identity.respond("POST", "/MailService.GetMailPage",
            json.dumps(values).encode(), authorization="Bearer")
    response = query(args)
    assert response.status == 200
    data = json.loads(response.body)
    assert data["code"] == 0 and data["data"]["total"] == 1
    assert len(data["data"]["mails"]) == 1
    assert query(dict(args, userid="2")).status == 401
    flow.identity.active_mail_players = lambda: {1, 2}
    assert query(args).status == 401
    flow.identity.allow_local_mail_without_token = False
    flow.identity.active_mail_players = lambda: {player_id}
    assert query(args).status == 401


def test_bare_bearer_mail_over_http_after_authenticated_tcp_login(tmp_path):
    flow = AccountFlow(tmp_path)
    flow.register("fresh", "pw")
    _, login_ctx = flow.game_session("fresh", "pw")
    player_id = login_ctx["playerID"]

    async def scenario():
        service = LoginService(flow.identity, flow.store)
        tcp = X2TCPServer(Settings(tcp_port=0), Dispatcher({"C2L_Login": service.login}))
        flow.identity.allow_local_mail_without_token = True
        flow.identity.active_mail_players = tcp.authenticated_player_ids
        http = BootstrapHTTPServer("127.0.0.1", 0, flow.identity)
        await tcp.start()
        await http.start()
        try:
            reader, writer = await asyncio.open_connection(tcp.bound_host, tcp.bound_port)
            from x2server.protocol.codec import ProtocolCodec
            from x2server.protocol.headers import RequestHeader
            writer.write(ProtocolCodec().encode("C2L_Login", {"id": player_id,
                "token": login_ctx["token"]}, RequestHeader(request_id=1)))
            await writer.drain()
            assert await asyncio.wait_for(reader.read(4096), 2)
            args = {"appid": flow.identity.contract.web_config.service_app_id,
                    "userid": str(player_id), "page": 1, "page_num": 20, "state": -1}
            def request():
                req = Request(f"http://127.0.0.1:{http.bound_port}/MailService.GetMailPage",
                    json.dumps(args).encode(), {"Authorization": "Bearer", "Content-Type": "application/json"},
                    method="POST")
                with urlopen(req, timeout=3) as response:
                    return response.status, json.load(response)
            status, body = await asyncio.to_thread(request)
            assert status == 200 and body["data"]["total"] == 1
            assert len(body["data"]["mails"]) == 1
            writer.close()
            await writer.wait_closed()
        finally:
            await http.stop()
            await tcp.stop()
    asyncio.run(scenario())
