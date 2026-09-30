"""Real HTTP account login, PBS mail reads, and TCP attachment claim."""

import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request

from tests.integration.test_local_registration import AccountFlow
from x2server.bootstrap.http_server import BootstrapHTTPServer
from x2server.config.settings import Settings
from x2server.messages.mail import MAIL_SCHEMAS
from x2server.network.dispatcher import Dispatcher
from x2server.network.server import X2TCPServer
from x2server.player.economy import EconomyService
from x2server.player.login import LoginService
from x2server.player.mail import MailService
from x2server.protocol.codec import ProtocolCodec
from x2server.protocol.framing import PacketStreamDecoder
from x2server.protocol.headers import RequestHeader, ResponseHeader
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY


def post(base, path, values, token=None):
    headers = {}
    if path.startswith("/MailService."):
        body = json.dumps(values).encode()
        headers["Content-Type"] = "application/json"
        if token is not None:
            headers["Authorization"] = "Bearer " + token
    else:
        body = urllib.parse.urlencode(values).encode()
    request = urllib.request.Request(base + path, body, headers, method="POST")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=3) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as response:
        return response.code, json.load(response)


def test_account_token_reads_only_own_mail_and_tcp_claim_survives_relogin(tmp_path):
    flow = AccountFlow(tmp_path)
    assert flow.register("nova", "pw") == {"success": True}
    assert flow.register("orbit", "pw") == {"success": True}
    economy = EconomyService(flow.store)
    mail = MailService(flow.store, economy)
    login = LoginService(flow.identity, flow.store, economy=economy, mail=mail)

    async def scenario():
        http = BootstrapHTTPServer("127.0.0.1", 0, flow.identity)
        tcp = X2TCPServer(Settings(tcp_port=0), Dispatcher(
            {"C2L_Login": login.login, **mail.handlers()}))
        await http.start()
        await tcp.start()
        try:
            base = f"http://127.0.0.1:{http.bound_port}"
            async def http_post(path, values, token=None):
                return await asyncio.to_thread(post, base, path, values, token)

            status, account = await http_post("/loginwithpw", {"account": "nova", "password": "pw"})
            assert status == 200 and account["code"] == "ok"
            _, game = await http_post("/apply/httpLogin", {"accountid": "nova",
                "token": account["token"], "logintype": "GAME"})
            _, other_account = await http_post("/loginwithpw", {"account": "orbit", "password": "pw"})
            player_id = game["playerID"]
            other_id = flow.accounts.get_by_name("orbit")["player_id"]

            reader, writer = await asyncio.open_connection(tcp.bound_host, tcp.bound_port)
            decoder = PacketStreamDecoder(ResponseHeader)
            codec = ProtocolCodec()
            pending = []

            async def send(name, values, request_id, response):
                writer.write(codec.encode(name, values, RequestHeader(request_id=request_id)))
                await writer.drain()
                while True:
                    while pending:
                        packet = pending.pop(0)
                        if CORE_MESSAGE_REGISTRY.name_for(packet.message_id) == response:
                            return packet
                    data = await asyncio.wait_for(reader.read(65536), 3)
                    assert data, f"connection closed before {response}"
                    pending.extend(decoder.feed(data))

            await send("C2L_Login", {"id": player_id, "token": game["token"]}, 1, "L2C_Login")
            args = {"appid": flow.identity.contract.web_config.service_app_id,
                    "userid": str(player_id), "page": 1, "page_num": 20, "state": -1}
            status, page = await http_post("/MailService.GetMailPage", args, account["token"])
            assert status == 200 and page["data"]["total"] == 2
            assert any(row["body"] == "" and row["state"] == 0 for row in page["data"]["mails"])
            welcome = next(row for row in page["data"]["mails"] if row["body"] == "")
            assert (await http_post("/MailService.GetMailPage", args, game["token"]))[0] == 200
            assert (await http_post("/MailService.GetMailPage", args))[0] == 401
            assert (await http_post("/MailService.GetMailPage", args, "abc"))[0] == 401
            assert (await http_post("/MailService.GetMailPage", args,
                                    other_account["token"]))[0] == 403
            assert (await http_post("/MailService.GetMailPage", dict(args, userid=str(other_id)),
                                    account["token"]))[0] == 403
            assert (await http_post("/MailService.GetMail", {"appid": args["appid"],
                "userid": args["userid"], "id": welcome["id"]}, account["token"]))[1]["data"]["mail"]["id"] == welcome["id"]

            claimed = await send("C2L_ReceiveAttachment", {"mailid": int(welcome["id"])},
                                 2, "L2C_ReceiveAttachment")
            assert MAIL_SCHEMAS["L2C_ReceiveAttachment"].decode(claimed.body)["code"] == 10
            crystal = flow.store.get(player_id)["snapshot"]["crystal"]
            assert crystal == 3600
            duplicate = await send("C2L_ReceiveAttachment", {"mailid": int(welcome["id"])},
                                   3, "L2C_ReceiveAttachment")
            assert MAIL_SCHEMAS["L2C_ReceiveAttachment"].decode(duplicate.body)["code"] == 13
            assert flow.store.get(player_id)["snapshot"]["crystal"] == crystal
            assert flow.store.get(other_id)["snapshot"]["crystal"] == 0
            writer.close()
            await writer.wait_closed()

            _, again = await http_post("/loginwithpw", {"account": "nova", "password": "pw"})
            status, page = await http_post("/MailService.GetMailPage", args, again["token"])
            assert status == 200
            assert next(row for row in page["data"]["mails"] if row["id"] == welcome["id"])["state"] == 2
            assert flow.store.get(player_id)["snapshot"]["crystal"] == crystal
            flow.identity._account_tokens[again["token"]].expire = 0
            assert (await http_post("/MailService.GetMailPage", args, again["token"]))[0] == 401
            with flow.accounts.db:
                flow.accounts.db.execute("UPDATE accounts SET status='disabled' WHERE player_id=?",
                                         (player_id,))
            assert (await http_post("/MailService.GetMailPage", args, account["token"]))[0] == 401
            assert (await http_post("/MailService.GetMailPage", args, game["token"]))[0] == 401
        finally:
            await tcp.stop()
            await http.stop()
            flow.accounts.close()
            flow.store.close()

    asyncio.run(scenario())
