"""Opt-in local identity bridge for the client's existing Account login mode.

TEMPORARY_COMPAT origins: one configured development account, ephemeral tokens.
The REVIVAL_COMPATIBILITY multi-account mode (``accounts``+``players`` supplied)
persists accounts, implements the client's real ``/register`` contract and
allocates one player row per account during registration. Public deployment
remains blocked pending client validation and security review.
Response field names/success codes come from LoginManager's HTTP coroutines:
TokenCtx, LoginCtx and IsCreate (analysis/account_registration/current_auth_flow.md).
"""

from __future__ import annotations

import json
import sqlite3
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from .models import RecoveredBootstrapContract, RecoveredControlInfo
from .service import HTTPResponse, RecoveredBootstrapService

TOKEN_LIFETIME = 3600


@dataclass
class _AccountToken:
    account_id: int
    username: str
    expire: float


@dataclass
class _GameToken:
    player_id: int
    expire: float


class LocalIdentityService(RecoveredBootstrapService):
    def __init__(
        self, contract: RecoveredBootstrapContract, *, account: str | None = None,
        password: str | None = None, accounts=None, players=None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        super().__init__(contract, RecoveredControlInfo(update="LEBIAN"))
        if accounts is None and (not account or not password):
            raise ValueError("local account and password must be nonempty")
        self.account = account
        self._password = password
        self._accounts = accounts
        self._players = players
        self._clock = clock
        self._account_token = secrets.token_urlsafe(32)
        self._game_token = secrets.token_urlsafe(32)
        self._start = int(clock())
        self._expire = self._start + TOKEN_LIFETIME
        self._account_tokens: dict[str, _AccountToken] = {}
        self._game_tokens: dict[str, _GameToken] = {}
        if accounts is not None and account and password:
            # Seed the configured development account only when the username is free.
            accounts.create(account, password, self._start, allow_legacy=True)

    @staticmethod
    def _json(value: dict[str, object] | list[dict[str, object]], status: int = 200) -> HTTPResponse:
        return HTTPResponse(status, "application/json; charset=utf-8",
                            (json.dumps(value) + "\n").encode("utf-8"))

    def respond(self, method: str, target: str, body: bytes = b"") -> HTTPResponse:
        path = urlsplit(target).path
        if path == "/apply/chatNode" and method.upper() == "POST":
            # ChatModule.GetChatServers parses a list of ChannelInfo, with a
            # second JSON-encoded list in channel; Connect splits entry on ':'.
            return self._json([{"channel": json.dumps([{"channel": 1, "free": 1, "limit": 1}]),
                               "entry": "10.0.2.2:29001", "nodeType": "local", "token": ""}])
        if path not in ("/register", "/login", "/loginwithpw", "/apply/httpLogin"):
            return super().respond(method, target, body)
        if method.upper() != "POST":
            return HTTPResponse(405, "application/json", b'{"error":"method_not_allowed"}',
                                (("Allow", "POST"),))
        try:
            fields = parse_qs(body.decode("utf-8"), keep_blank_values=True,
                              strict_parsing=True, max_num_fields=64)
            if any(len(values) != 1 for values in fields.values()):
                raise ValueError("duplicate form fields")
            values = {key: item[0] for key, item in fields.items()}
        except (ValueError, UnicodeDecodeError):
            return self._json({"error": "invalid_form"}, 400)
        if path == "/register":
            return self._register(values)
        if path in ("/login", "/loginwithpw"):
            return self._password_login(values, path)
        return self._http_login(values)

    # -- Revival compatibility account mode --------------------------------

    def _register(self, values: dict[str, str]) -> HTTPResponse:
        # Client contract: LoginManager.StartCreate posts account/password and
        # parses only IsCreate{success: bool}; the form may also carry blanks.
        if self._accounts is None:
            return self._json({"success": False})
        outcome = "duplicate"
        try:
            outcome = self._accounts.create(values.get("account", ""), values.get("password", ""),
                                            int(self._clock()))
        except ValueError:
            outcome = "duplicate"
        except sqlite3.Error:
            return self._json({"success": False}, 500)
        return self._json({"success": outcome == "created"})

    def _password_login(self, values: dict[str, str], path: str) -> HTTPResponse:
        account_name = values.get("account", "")
        password = values.get("password", "")
        if self._accounts is None:
            if self._clock() >= self._expire:
                return self._json({"code": "expired"})
            valid = (account_name == self.account and secrets.compare_digest(
                password.encode(), self._password.encode()))
            if not valid:
                return self._json({"code": "invalid"})
            return self._json({"code": "ok", "token": self._account_token, "id": 1,
                               "start": self._start, "expire": self._expire})
        now = int(self._clock())
        try:
            row = self._accounts.verify(account_name, password, now)
        except sqlite3.Error:
            return self._json({"code": "error"}, 500)
        if row is None:
            return self._json({"code": "invalid"})
        token = secrets.token_urlsafe(32)
        expire = self._clock() + TOKEN_LIFETIME
        self._account_tokens[token] = _AccountToken(row["account_id"], row["username"], expire)
        return self._json({"code": "ok", "token": token, "id": row["account_id"],
                           "start": int(self._clock()), "expire": int(expire)})

    def _http_login(self, values: dict[str, str]) -> HTTPResponse:
        token = values.get("token", "")
        if self._accounts is None:
            if self._clock() >= self._expire:
                return self._json({"code": 0, "logicCode": 0})
            valid = (values.get("accountid") in (self.account, "1") and
                     values.get("logintype") == "GAME" and secrets.compare_digest(
                         token.encode(), self._account_token.encode()))
            if not valid:
                return self._json({"code": 0, "logicCode": 0})
            endpoint = self.contract.server_addresses.endpoints[0]
            return self._json({"code": 1, "logicCode": 0, "token": self._game_token,
                               "playerID": 1, "entryIP": endpoint.host,
                               "entryPort": str(endpoint.port), "serverID": "1"})
        binding = self._account_tokens.get(token)
        if binding is None or self._clock() >= binding.expire:
            return self._json({"code": 0, "logicCode": 0})
        if values.get("logintype") != "GAME":
            return self._json({"code": 0, "logicCode": 0})
        # The token is the credential; accountid is only cross-checked because
        # the wire form is observed to carry the username or the token id.
        if values.get("accountid") not in (binding.username, str(binding.account_id)):
            return self._json({"code": 0, "logicCode": 0})
        try:
            row = self._accounts.get_by_id(binding.account_id)
        except sqlite3.Error:
            return self._json({"code": 0, "logicCode": 0}, 500)
        if row is None or row["status"] != "active" or row["player_id"] is None:
            return self._json({"code": 0, "logicCode": 0})
        player_id = row["player_id"]
        game_token = secrets.token_urlsafe(32)
        self._game_tokens[game_token] = _GameToken(player_id, self._clock() + TOKEN_LIFETIME)
        endpoint = self.contract.server_addresses.endpoints[0]
        return self._json({"code": 1, "logicCode": 0, "token": game_token,
                           "playerID": player_id, "entryIP": endpoint.host,
                           "entryPort": str(endpoint.port), "serverID": "1"})

    # -- TCP-side validation ------------------------------------------------

    def validates_game_identity(self, player_id: int, token: str) -> bool:
        if self._accounts is None:
            return (player_id == 1 and self._clock() < self._expire and
                    secrets.compare_digest(token.encode(), self._game_token.encode()))
        binding = self._game_tokens.get(token)
        return (binding is not None and binding.player_id == player_id and
                self._clock() < binding.expire)

    def account_for_player(self, player_id: int) -> str:
        """Username owning the player row; legacy mode has exactly one account."""
        if self._accounts is None:
            return self.account
        row = self._accounts.get_by_player(player_id)
        if row is None:
            raise ValueError(f"no account bound to player {player_id}")
        return row["username"]
