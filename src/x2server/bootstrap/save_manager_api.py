"""Save-manager HTTP API on the existing bootstrap 18080 service.

Routes (all POST unless noted; JSON in/out unless noted):
  POST /save-manager/auth    form {account,password} -> {code:"ok",token,...}
  POST /save-manager/status  Bearer <save-token> -> {code, account, online}
  POST /save-manager/export  Bearer <save-token> -> application/octet-stream .x2save
  POST /save-manager/import  Bearer <save-token>, body = .x2save bytes -> {code,...}

Authentication reuses AccountStore.verify (PBKDF2). Save tokens are separate,
short-lived and single-purpose: they cannot be used as game tokens and game
tokens are not accepted here. Passwords and tokens never enter logs.
"""
from __future__ import annotations

import json
import logging
import secrets
import threading
import time
from collections.abc import Callable
from urllib.parse import parse_qs

from ..player.save_manager import MAX_UPLOAD_BYTES, SaveManager

LOGGER = logging.getLogger("x2.bootstrap.save_manager")

TOKEN_TTL = 600.0
MAX_BODY = MAX_UPLOAD_BYTES + 64 * 1024
ROUTE_PREFIX = "/save-manager/"


class SaveManagerAPI:
    """Dispatches /save-manager/* for the bootstrap HTTP service."""

    def __init__(self, save_manager: SaveManager, accounts,
                 online_player_ids: Callable[[], set[int]],
                 clock: Callable[[], float] = time.time) -> None:
        self.save_manager = save_manager
        self.accounts = accounts
        self.online_player_ids = online_player_ids
        self._clock = clock
        self._tokens: dict[str, _SaveToken] = {}
        self._lock = threading.Lock()

    @property
    def max_body_bytes(self) -> int:
        return MAX_BODY

    def respond(self, method: str, path: str, body: bytes,
                authorization: str) -> tuple[int, str, bytes]:
        """Return (status, content_type, payload) for a /save-manager/ route."""
        try:
            return self._respond(method, path, body, authorization)
        except PermissionError:
            return self._json(401, {"error": "unauthorized"})
        except LookupError:
            return self._json(404, {"error": "unknown_account"})
        except ValueError as exc:
            return self._json(400, {"error": "invalid_save", "message": str(exc)})
        except OSError as exc:
            LOGGER.error("save-manager I/O failure route=%s error=%s", path, type(exc).__name__)
            return self._json(500, {"error": "internal_error"})
        except RuntimeError:
            LOGGER.exception("save-manager online status unavailable")
            return self._json(503, {"error": "online_status_unavailable"})

    def _respond(self, method: str, path: str, body: bytes,
                 authorization: str) -> tuple[int, str, bytes]:
        if method.upper() != "POST":
            return self._json(405, {"error": "method_not_allowed"})
        if len(body) > MAX_BODY:
            return self._json(413, {"error": "request_too_large"})
        route = path[len(ROUTE_PREFIX):]
        if route == "auth":
            return self._auth(body)
        token = self._require_token(authorization)
        if route == "status":
            return self._status(token)
        if route == "export":
            return self._export(token)
        if route == "import":
            return self._import(token, body)
        return self._json(404, {"error": "unknown_route"})

    # -- auth ----------------------------------------------------------------

    def _auth(self, body: bytes) -> tuple[int, str, bytes]:
        try:
            fields = parse_qs(body.decode("utf-8"), keep_blank_values=True,
                              strict_parsing=True, max_num_fields=8)
            values = {key: item[0] for key, item in fields.items() if len(item) == 1}
            account_name = values.get("account", "")
            password = values.get("password", "")
        except (ValueError, UnicodeDecodeError):
            return self._json(400, {"error": "invalid_form"})
        if not account_name or not password:
            return self._json(200, {"code": "empty"})
        row = self.accounts.verify(account_name, password, int(self._clock()))
        if row is None:
            LOGGER.info("save-manager auth failed account_size=%d", len(account_name))
            return self._json(200, {"code": "invalid"})
        token = secrets.token_urlsafe(32)
        expire = self._clock() + TOKEN_TTL
        with self._lock:
            self._tokens[token] = _SaveToken(row["account_id"], row["username"],
                                             row["player_id"], expire)
        LOGGER.info("save-manager auth ok account_id=%s", row["account_id"])
        return self._json(200, {"code": "ok", "token": token,
                                "expires_in": int(TOKEN_TTL)})

    def _require_token(self, authorization: str) -> _SaveToken:
        if not authorization.startswith("Bearer "):
            raise PermissionError("missing bearer token")
        token = authorization[7:].strip()
        with self._lock:
            entry = self._tokens.get(token)
        if entry is None or self._clock() >= entry.expire:
            raise PermissionError("invalid or expired save token")
        return entry

    def _purge_expired(self) -> None:
        now = self._clock()
        with self._lock:
            for token in [t for t, v in self._tokens.items() if now >= v.expire]:
                del self._tokens[token]

    # -- routes ----------------------------------------------------------------

    def _status(self, token: _SaveToken) -> tuple[int, str, bytes]:
        self._purge_expired()
        online = self._safe_online_ids()
        return self._json(200, {"code": "ok", "account": token.username,
                                "online": token.player_id in online})

    def _export(self, token: _SaveToken) -> tuple[int, str, bytes]:
        payload = self.save_manager.export_save(token.player_id)
        LOGGER.info("save-manager export account_id=%s bytes=%d",
                    token.account_id, len(payload))
        return (200, "application/octet-stream", payload)

    def _import(self, token: _SaveToken, body: bytes) -> tuple[int, str, bytes]:
        if not body:
            return self._json(400, {"error": "empty_body"})
        online = self._safe_online_ids()
        if token.player_id in online:
            LOGGER.info("save-manager import rejected (online) account_id=%s", token.account_id)
            return self._json(409, {"error": "account_online",
                                    "message": "账号当前在线，请先退出游戏后再导入存档。"})
        result = self.save_manager.import_save(token.player_id, body,
                                               actor=f"save-manager:{token.username}")
        LOGGER.info("save-manager import ok account_id=%s", token.account_id)
        with self._lock:
            for stale in [t for t, v in self._tokens.items() if v.account_id == token.account_id]:
                del self._tokens[stale]
        return self._json(200, {"code": "ok", "backup": result["backup"]})

    def _safe_online_ids(self) -> set[int]:
        try:
            return set(self.online_player_ids())
        except Exception as exc:  # an unavailable checker must not permit a live overwrite
            raise RuntimeError("online player check failed") from exc

    @staticmethod
    def _json(status: int, payload: dict) -> tuple[int, str, bytes]:
        return (status, "application/json; charset=utf-8",
                (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))


class _SaveToken:
    __slots__ = ("account_id", "username", "player_id", "expire")

    def __init__(self, account_id: int, username: str, player_id: int, expire: float) -> None:
        self.account_id = account_id
        self.username = username
        self.player_id = player_id
        self.expire = expire
