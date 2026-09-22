"""Contract and rejection cases for the opt-in Account compatibility bridge."""
import json
from urllib.parse import urlencode

from x2server.bootstrap.local_identity import LocalIdentityService
from x2server.bootstrap.models import RecoveredBootstrapContract
from x2server.config.settings import Settings


def test_identity_exchange_and_expiry():
    now = [1000.0]
    service = LocalIdentityService(RecoveredBootstrapContract.local(Settings(), game_server_port=29000),
                                   account="lab", password="local", clock=lambda: now[0])

    def post(path, fields):
        return json.loads(service.respond("POST", path, urlencode(fields).encode()).body)

    assert post("/loginwithpw", {"account": "lab", "password": "wrong"})["code"] == "invalid"
    login = post("/loginwithpw", {"account": "lab", "password": "local"})
    assert login["code"] == "ok"
    fields = {"accountid": "lab", "logintype": "GAME", "token": login["token"]}
    game = post("/apply/httpLogin", fields)
    assert game["code"] == 1
    assert isinstance(game["entryPort"], str)
    assert game["token"] != login["token"]
    assert service.validates_game_identity(game["playerID"], game["token"])
    assert not service.validates_game_identity(2, game["token"])
    assert not service.validates_game_identity(1, login["token"])
    assert post("/apply/httpLogin", dict(fields, token="invalid"))["code"] == 0
    assert post("/apply/httpLogin", dict(fields, accountid="other"))["code"] == 0
    assert post("/apply/httpLogin", dict(fields, logintype="SDK"))["code"] == 0
    assert service.respond("GET", "/login").status == 405
    assert service.respond("POST", "/login", b"account=a&account=b").status == 400
    assert service.respond("POST", "/login", b"\xff").status == 400
    now[0] = 4600
    assert post("/apply/httpLogin", fields)["code"] == 0
    assert not service.validates_game_identity(1, game["token"])
