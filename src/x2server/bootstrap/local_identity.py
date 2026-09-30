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
import logging
import secrets
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from .models import RecoveredBootstrapContract, RecoveredControlInfo
from .service import HTTPResponse, RecoveredBootstrapService

TOKEN_LIFETIME = 3600
LOGGER = logging.getLogger("x2.bootstrap.identity")


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
        chat_entry: str = "10.0.2.2:29001",
        clock: Callable[[], float] = time.time,
    ) -> None:
        super().__init__(contract, RecoveredControlInfo(update="LEBIAN"))
        if accounts is None and (not account or not password):
            raise ValueError("local account and password must be nonempty")
        self.account = account
        self._password = password
        self._accounts = accounts
        self._players = players
        self._chat_entry = chat_entry
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

    def respond(self, method: str, target: str, body: bytes = b"", *, authorization: str = "") -> HTTPResponse:
        path = urlsplit(target).path
        if path in ("/MailService.GetMailPage", "/MailService.GetMail"):
            return self._mail_http(method, path, body, authorization)
        if path == "/apply/chatNode" and method.upper() == "POST":
            # ChatModule.GetChatServers parses a list of ChannelInfo, with a
            # second JSON-encoded list in channel; Connect splits entry on ':'.
            return self._json([{"channel": json.dumps([{"channel": 1, "free": 1, "limit": 1}]),
                               "entry": self._chat_entry, "nodeType": "local", "token": ""}])
        # These are optional LoginManager telemetry/notice probes.  Some
        # client builds surface a transport error when the endpoint is 404,
        # even though no response data is consumed.  A side-effect-free 200
        # keeps the login flow moving to /apply/httpLogin.
        if path in ("/apply/loginStep", "/apply/noticeUrl") and method.upper() == "POST":
            return self._json({})
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

    def _mail_http(self, method: str, path: str, body: bytes, authorization: str) -> HTTPResponse:
        """Serve PBS mail reads using either authenticated login token."""
        if method.upper() != "POST":
            return self._json({"error": "method_not_allowed"}, 405)
        try:
            args = json.loads(body)
            if not isinstance(args, dict):
                raise ValueError("invalid request")
            requested_player = int(args.get("userid", 0))
            if requested_player <= 0:
                raise ValueError("invalid player")
            if self._accounts is None:
                return self._json({"error": "unauthorized"}, 401)
            if authorization.startswith("Bearer ") and authorization[7:].strip():
                player_id = self._mail_player_for_token(authorization[7:].strip())
                if player_id is None:
                    return self._json({"error": "unauthorized"}, 401)
                if requested_player != player_id:
                    return self._json({"error": "forbidden"}, 403)
                LOGGER.info("mail auth mode=token userid=%s", requested_player)
            elif authorization.strip() == "Bearer":
                account = self._accounts.get_by_player(requested_player)
                if (account is None or account["status"] != "active" or
                        account["player_id"] != requested_player):
                    return self._json({"error": "unauthorized"}, 401)
                LOGGER.info("mail auth mode=revival_bare_bearer userid=%s", requested_player)
            else:
                return self._json({"error": "unauthorized"}, 401)
            if args.get("appid") != self.contract.web_config.service_app_id:
                return self._json({"error": "forbidden"}, 403)
            if path == "/MailService.GetMailPage":
                page, page_size = int(args.get("page", 1)), int(args.get("page_num", 20))
                if not 0 <= page <= 100000 or not 1 <= page_size <= 100:
                    raise ValueError("invalid page")
                state = int(args.get("state", -1))
                if state not in (-1, 0, 1, 2, 3, 4):
                    raise ValueError("invalid state")
            else:
                mail_id = int(args["id"])
                if mail_id <= 0:
                    raise ValueError("invalid id")
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            return self._json({"error": "invalid_request"}, 400)
        with self._accounts._lock:
            db = self._accounts.db
            if path == "/MailService.GetMailPage":
                condition = "player_id=? AND deleted=0"
                params: list[int] = [requested_player]
                if state != -1:
                    condition += " AND state=?"
                    params.append(state)
                total = db.execute(f"SELECT count(*) FROM player_mail WHERE {condition}", params).fetchone()[0]
                rows = db.execute(f"SELECT * FROM player_mail WHERE {condition} "
                                  "ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?",
                                  (*params, page_size, max(page - 1, 0) * page_size)).fetchall()
                data = {"total": total, "mails": [self._pbs_mail(row) for row in rows]}
            else:
                row = db.execute("SELECT * FROM player_mail WHERE player_id=? AND id=? AND deleted=0",
                                 (requested_player, mail_id)).fetchone()
                data = {"mail": self._pbs_mail(row) if row is not None else None}
        return self._json({"error": "" if path.endswith("GetMailPage") or data["mail"] else "not_found",
                           "data": data, "code": 0 if path.endswith("GetMailPage") or data["mail"] else 404})

    def _mail_player_for_token(self, token: str) -> int | None:
        """Resolve account and game credentials through the existing login bindings."""
        if not token or self._accounts is None:
            return None
        now = self._clock()
        game = self._game_tokens.get(token)
        if game is not None and now < game.expire:
            account = self._accounts.get_by_player(game.player_id)
            return game.player_id if account and account["status"] == "active" else None
        login = self._account_tokens.get(token)
        if login is None or now >= login.expire:
            return None
        account = self._accounts.get_by_id(login.account_id)
        if (account is None or account["status"] != "active" or
                account["username"] != login.username or account["player_id"] is None):
            return None
        owner = self._accounts.get_by_player(account["player_id"])
        return account["player_id"] if owner and owner["account_id"] == login.account_id else None

    @staticmethod
    def _pbs_mail(row: sqlite3.Row) -> dict[str, object]:
        rewards = json.loads(row["attachments"])
        attachment = {"attachment": [{"item": int(item), "num": count}
                                      for item, count in rewards.items()], "equip": [], "gift": []}
        return {"id": str(row["id"]), "from": row["sender"], "title": row["title"],
                "body": row["body"], "state": row["state"], "time": str(row["created_at"]),
                "attachment": json.dumps(attachment, separators=(",", ":")), "type": 0,
                "expireAt": "0", "operateId": "", "readTime": "0", "recvTime": "0",
                "delTime": "0"}

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

    def ensure_daily_login_mail(self, player_id: int, now: int) -> bool:
        return self._accounts.ensure_daily_login_mail(player_id, now) if self._accounts is not None else False

    def ensure_welcome_mail(self, player_id: int, now: int) -> bool:
        return self._accounts.ensure_welcome_mail(player_id, now) if self._accounts is not None else False
