"""Fixed-route bootstrap response service, independent from HTTP transport."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from .models import BootstrapConfig, RecoveredBootstrapContract, RecoveredControlInfo


@dataclass(frozen=True, slots=True)
class HTTPResponse:
    """Small transport-neutral HTTP response value."""

    status: int
    content_type: str
    body: bytes
    headers: tuple[tuple[str, str], ...] = ()


class BootstrapService:
    """Serve one fixed synthetic config; never read arbitrary files or request data."""

    def __init__(self, config: BootstrapConfig, path: str = "/webgameconfig") -> None:
        if not path.startswith("/"):
            raise ValueError("bootstrap path must start with /")
        self.config = config
        self.path = path

    def respond(self, method: str, target: str) -> HTTPResponse:
        """Return explicit 200/404/405 responses without exposing tracebacks."""
        path = urlsplit(target).path
        if path != self.path:
            return HTTPResponse(404, "application/json; charset=utf-8", b'{"error":"not_found"}\n')
        if method.upper() != "POST":
            return HTTPResponse(
                405,
                "application/json; charset=utf-8",
                b'{"error":"method_not_allowed"}\n',
                (("Allow", "POST"),),
            )
        return HTTPResponse(200, "application/json; charset=utf-8", self.config.to_json_bytes())


class RecoveredBootstrapService:
    """Serve the two HTTP responses recovered from static client evidence."""

    CONNECT_INFO_PATH = "/apply/connectInfo"
    SERVER_ADDRESS_PATH = "/apply/address"
    CONTROL_INFO_PATH = "/apply/controlInfo"

    def __init__(
        self,
        contract: RecoveredBootstrapContract,
        control_info: RecoveredControlInfo | None = None,
    ) -> None:
        self.contract = contract
        self.control_info = control_info or RecoveredControlInfo()

    def respond(self, method: str, target: str) -> HTTPResponse:
        """Route only the confirmed POST endpoints."""
        path = urlsplit(target).path
        if path not in (
            self.CONNECT_INFO_PATH,
            self.SERVER_ADDRESS_PATH,
            self.CONTROL_INFO_PATH,
        ):
            return HTTPResponse(404, "application/json; charset=utf-8", b'{"error":"not_found"}\n')
        if method.upper() != "POST":
            return HTTPResponse(
                405,
                "application/json; charset=utf-8",
                b'{"error":"method_not_allowed"}\n',
                (("Allow", "POST"),),
            )
        if path == self.CONNECT_INFO_PATH:
            body = self.contract.web_config.to_json_bytes()
        elif path == self.SERVER_ADDRESS_PATH:
            body = self.contract.server_addresses.to_json_bytes()
        else:
            body = self.control_info.to_json_bytes()
        return HTTPResponse(200, "application/json; charset=utf-8", body)
