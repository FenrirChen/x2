"""Minimal connection metadata for later M2 networking."""

from __future__ import annotations

from dataclasses import dataclass
from x2server.protocol.errors import ProtocolError


@dataclass(slots=True)
class SessionState:
    """Non-business state associated with one future TCP connection."""

    connection_id: str
    session_id: str = ""
    last_request_id: int = 0
    player_id: int | None = None

    def record_request(self, request_id: int, session_id: str) -> None:
        """Record envelope correlation state without authenticating a player."""
        self.last_request_id = request_id
        if self.player_id is None:
            self.session_id = session_id
        elif session_id and session_id != self.session_id:
            raise ProtocolError("authenticated session mismatch")
        # The client can queue requests with an empty session before consuming the
        # login push. Authentication belongs to this TCP connection, not that field.

    def log_context(self, message_id: int, message_name: str) -> dict[str, str | int]:
        """Return safe structured log context; authentication payloads are excluded."""
        return {
            "connection_id": self.connection_id,
            "message_id": message_id,
            "message_name": message_name,
            "request_id": self.last_request_id,
        }

