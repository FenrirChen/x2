"""Opt-in local identity bridge for the client's existing Account login mode.

TEMPORARY_COMPAT: one configured development account, ephemeral tokens, no
official/channel credentials and no player snapshot. Never enable on a public listener.
Response field names/success codes come from LoginManager's two HTTP coroutines.
"""

from __future__ import annotations

import json
import secrets
import time
from collections.abc import Callable
from urllib.parse import parse_qs, urlsplit

from .models import RecoveredBootstrapContract, RecoveredControlInfo
from .service import HTTPResponse, RecoveredBootstrapService


class LocalIdentityService(RecoveredBootstrapService):
    def __init__(
        self, contract: RecoveredBootstrapContract, *, account: str, password: str,
        clock: Callable[[], float] = time.time,
    ) -> None:
        super().__init__(contract, RecoveredControlInfo(update="LEBIAN"))
        if not account or not password:
            raise ValueError("local account and password must be nonempty")
        self.account = account
        self._password = password
        self._clock = clock
        self._account_token = secrets.token_urlsafe(32)
        self._game_token = secrets.token_urlsafe(32)
        self._start = int(clock())
        self._expire = self._start + 3600

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
        if path not in ("/login", "/loginwithpw", "/apply/httpLogin"):
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
        if self._clock() >= self._expire:
            return self._json({"code": "expired"} if path != "/apply/httpLogin" else
                              {"code": 0, "logicCode": 0})
        if path in ("/login", "/loginwithpw"):
            valid = (values.get("account") == self.account and secrets.compare_digest(
                values.get("password", "").encode(), self._password.encode()))
            if not valid:
                return self._json({"code": "invalid"})
            return self._json({"code": "ok", "token": self._account_token, "id": 1,
                               "start": self._start, "expire": self._expire})
        valid = (values.get("accountid") in (self.account, "1") and
                 values.get("logintype") == "GAME" and secrets.compare_digest(
                     values.get("token", "").encode(), self._account_token.encode()))
        if not valid:
            return self._json({"code": 0, "logicCode": 0})
        endpoint = self.contract.server_addresses.endpoints[0]
        return self._json({"code": 1, "logicCode": 0, "token": self._game_token,
                           "playerID": 1, "entryIP": endpoint.host,
                           "entryPort": str(endpoint.port), "serverID": "1"})

    def validates_game_identity(self, player_id: int, token: str) -> bool:
        return (player_id == 1 and self._clock() < self._expire and
                secrets.compare_digest(token.encode(), self._game_token.encode()))
