"""Save-manager HTTP surface over the real bootstrap 18080 framework.

Covers the client contract: /save-manager/auth (account+password -> short-lived
purpose-limited token), status, export and import — including the online-player
rejection and token invalidation after a successful import. Passwords and
tokens must never appear in responses they do not belong to, nor in logs.
"""
import asyncio
import json
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlencode

import pytest

from tests.unit.test_save_manager import build_full_schema, populate_rich_state, apply_snapshot, rich_snapshot
from x2server.bootstrap.http_server import BootstrapHTTPServer
from x2server.bootstrap.local_identity import LocalIdentityService
from x2server.bootstrap.models import RecoveredBootstrapContract
from x2server.bootstrap.save_manager_api import SaveManagerAPI
from x2server.config.settings import Settings
from x2server.player.accounts import AccountStore
from x2server.player.save_manager import SaveManager
from x2server.player.store import PlayerStore


class OnlineRegistry:
    def __init__(self) -> None:
        self.players: set[int] = set()


@pytest.fixture()
def service(tmp_path):
    store = PlayerStore(tmp_path / "player.db")
    build_full_schema(store)
    accounts = AccountStore(store)
    manager = SaveManager(store, backup_root=tmp_path / "backups")
    online = OnlineRegistry()
    api = SaveManagerAPI(manager, accounts, online_player_ids=lambda: online.players)
    service = LocalIdentityService(
        RecoveredBootstrapContract.local(Settings(), game_server_port=29000),
        accounts=accounts, players=store, save_manager_api=api)
    assert accounts.create("alpha", "pw-alpha", 100) == "created"
    yield service, accounts, manager, online, store
    manager.close()
    store.close()


def test_auth_status_export_import_flow(service):
    identity, accounts, manager, online, store = service
    response = identity.respond("POST", "/save-manager/auth",
                                urlencode({"account": "alpha", "password": "pw-alpha"}).encode())
    assert response.status == 200
    payload = json.loads(response.body)
    assert payload["code"] == "ok"
    token = payload["token"]

    # wrong password / empty credentials
    bad = json.loads(identity.respond(
        "POST", "/save-manager/auth",
        urlencode({"account": "alpha", "password": "wrong"}).encode()).body)
    assert bad["code"] == "invalid"
    empty = json.loads(identity.respond(
        "POST", "/save-manager/auth",
        urlencode({"account": "", "password": ""}).encode()).body)
    assert empty["code"] == "empty"

    # status
    status = json.loads(identity.respond(
        "POST", "/save-manager/status", b"",
        authorization=f"Bearer {token}").body)
    assert status == {"code": "ok", "account": "alpha", "online": False}

    # export
    export = identity.respond("POST", "/save-manager/export", b"",
                              authorization=f"Bearer {token}")
    assert export.status == 200
    assert export.content_type == "application/octet-stream"
    assert export.body[:2] == b"PK"

    # import while offline succeeds
    account = accounts.get_by_name("alpha")
    result = json.loads(identity.respond(
        "POST", "/save-manager/import", export.body,
        authorization=f"Bearer {token}").body)
    assert result["code"] == "ok"
    assert Path(result["backup"]).exists()

    # a successful import invalidates the save token
    after = identity.respond("POST", "/save-manager/status", b"",
                             authorization=f"Bearer {token}")
    assert after.status == 401


def test_import_rejects_online_account(service):
    identity, accounts, manager, online, store = service
    token = json.loads(identity.respond(
        "POST", "/save-manager/auth",
        urlencode({"account": "alpha", "password": "pw-alpha"}).encode()).body)["token"]
    export = identity.respond("POST", "/save-manager/export", b"",
                              authorization=f"Bearer {token}")
    player_id = accounts.get_by_name("alpha")["player_id"]
    online.players.add(player_id)
    rejected = identity.respond("POST", "/save-manager/import", export.body,
                                authorization=f"Bearer {token}")
    assert rejected.status == 409
    payload = json.loads(rejected.body)
    assert payload["error"] == "account_online"
    assert "在线" in payload["message"]
    online.players.discard(player_id)
    ok = identity.respond("POST", "/save-manager/import", export.body,
                          authorization=f"Bearer {token}")
    assert json.loads(ok.body)["code"] == "ok"


def test_routes_reject_missing_or_garbage_tokens(service):
    identity, accounts, *_ = service
    assert identity.respond("POST", "/save-manager/export", b"").status == 401
    assert identity.respond("POST", "/save-manager/export", b"",
                            authorization="Bearer nonsense").status == 401
    assert identity.respond("GET", "/save-manager/export").status == 405
    token = json.loads(identity.respond(
        "POST", "/save-manager/auth",
        urlencode({"account": "alpha", "password": "pw-alpha"}).encode()).body)["token"]
    # auth happens before routing; an authenticated unknown route is a 404
    assert identity.respond("POST", "/save-manager/unknown", b"",
                            authorization=f"Bearer {token}").status == 404


def test_game_tokens_are_not_accepted_as_save_tokens(service):
    """A save-management token must never be a game token and vice versa."""
    identity, accounts, *_ = service
    save = json.loads(identity.respond(
        "POST", "/save-manager/auth",
        urlencode({"account": "alpha", "password": "pw-alpha"}).encode()).body)["token"]
    game = identity.respond("POST", "/loginwithpw",
                            urlencode({"account": "alpha", "password": "pw-alpha"}).encode())
    game_token = json.loads(game.body)["token"]
    # game token must not open save-manager routes
    assert identity.respond("POST", "/save-manager/status", b"",
                            authorization=f"Bearer {game_token}").status == 401
    # save token must not pass the game identity validation
    assert not identity.validates_game_identity(1, save)


def test_import_fails_closed_when_online_checker_fails(service):
    identity, accounts, manager, online, store = service
    token = json.loads(identity.respond(
        "POST", "/save-manager/auth",
        urlencode({"account": "alpha", "password": "pw-alpha"}).encode()).body)["token"]
    pid = accounts.get_by_name("alpha")["player_id"]
    archive = manager.export_save(pid)
    before = manager.canonical_state(pid)
    def unavailable():
        raise TimeoutError("test checker unavailable")
    identity._save_manager_api.online_player_ids = unavailable
    result = identity.respond("POST", "/save-manager/import", archive,
                              authorization=f"Bearer {token}")
    assert result.status == 503
    assert manager.canonical_state(pid) == before


def test_export_reimports_more_than_128_battle_blobs(service):
    identity, accounts, manager, online, store = service
    pid = accounts.get_by_name("alpha")["player_id"]
    with store.db:
        for index in range(150):
            store.db.execute('''INSERT INTO battle_entries
                VALUES (?,?,?,1000,?,0,'MainMission',0,'[]',0)''',
                (pid, str(index), f'large-{index}', bytes([index])))
    before = manager.canonical_state(pid)
    archive = manager.export_save(pid)
    assert len(manager.parse_save(archive).blobs) == 150
    manager.import_save(pid, archive)
    assert manager.canonical_state(pid) == before


def test_end_to_end_http_socket(service):
    """The bootstrap HTTP server forwards large save bodies to the API."""
    async def scenario() -> None:
        identity, accounts, manager, online, store = service
        pid = accounts.get_by_name('alpha')['player_id']
        apply_snapshot(store, pid, rich_snapshot(40))
        with store.db:
            populate_rich_state(store.db, pid)
        before = manager.canonical_state(pid)
        # Same bind used on Linux deployments; client connects by host address.
        server = BootstrapHTTPServer("0.0.0.0", 0, identity)
        await server.start()
        try:
            base = f"http://127.0.0.1:{server.bound_port}"
            auth_response = await asyncio.to_thread(
                post, f"{base}/save-manager/auth",
                urlencode({"account": "alpha", "password": "pw-alpha"}).encode())
            auth = auth_response["token"]
            export = await asyncio.to_thread(post, f"{base}/save-manager/export", b"", auth=auth, raw=True)
            assert export[:2] == b"PK"
            from x2server.player.save_manager import PLAYER_TABLES
            plan = manager.parse_save(export)
            assert set(plan.rows) == set(PLAYER_TABLES)
            assert all(plan.rows[table] for table in PLAYER_TABLES)
            result = await asyncio.to_thread(post, f"{base}/save-manager/import", export, auth=auth)
            assert result["code"] == "ok"
            assert manager.canonical_state(pid) == before
        finally:
            await server.stop()
    asyncio.run(scenario())


def post(url: str, body: bytes, auth: str | None = None, raw: bool = False) -> bytes | dict:
    req = urllib.request.Request(url, data=body, method="POST")
    if auth:
        req.add_header("Authorization", f"Bearer {auth}")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=5.0) as response:
            payload = response.read()
    except urllib.error.HTTPError as error:
        payload = error.read()
    if raw:
        return payload
    return json.loads(payload)
