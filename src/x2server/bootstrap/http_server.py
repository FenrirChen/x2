"""Standard-library localhost HTTP transport for the fixed bootstrap service."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from x2server.player.transactions import is_database_busy

from .service import BootstrapService, HTTPResponse, RecoveredBootstrapService

LOGGER = logging.getLogger("x2.bootstrap.http")
MAX_REQUEST_BODY = 64 * 1024
# /save-manager/import uploads whole .x2save containers; the cap matches the
# save-manager validation limit instead of the bootstrap JSON body limit.
MAX_SAVE_MANAGER_BODY = 96 * 1024 * 1024 + 64 * 1024


def _handler_for(
    service: BootstrapService | RecoveredBootstrapService,
) -> type[BaseHTTPRequestHandler]:
    save_upload_slot = threading.BoundedSemaphore(1)

    class Handler(BaseHTTPRequestHandler):
        server_version = "X2Bootstrap/0.1"
        sys_version = ""

        def _send(self, response: HTTPResponse) -> None:
            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            self.send_header("Content-Length", str(len(response.body)))
            self.send_header("Cache-Control", "no-store")
            for name, value in response.headers:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(response.body)

        def _consume_request_body(self, *, discard=False) -> HTTPResponse | None:
            """Drain a small POST body without parsing or logging its contents.

            Leaving inbound bytes unread can make Windows close the socket with a reset,
            causing the client to lose an otherwise valid response.
            """
            route = self.path.split("?", 1)[0]
            max_body = (MAX_SAVE_MANAGER_BODY if route.startswith("/save-manager/")
                        else MAX_REQUEST_BODY)
            raw_length = self.headers.get("Content-Length", "0")
            try:
                length = int(raw_length)
            except ValueError:
                return HTTPResponse(
                    400, "application/json; charset=utf-8", b'{"error":"bad_content_length"}\n'
                )
            if length < 0:
                return HTTPResponse(
                    400, "application/json; charset=utf-8", b'{"error":"bad_content_length"}\n'
                )
            if length > max_body:
                return HTTPResponse(
                    413, "application/json; charset=utf-8", b'{"error":"request_too_large"}\n'
                )
            if discard:
                remaining = length
                while remaining:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                self.request_body = b''
                complete = remaining == 0
            else:
                self.request_body = self.rfile.read(length) if length else b""
                complete = len(self.request_body) == length
            if not complete:
                return HTTPResponse(
                    400, "application/json; charset=utf-8", b'{"error":"truncated_request"}\n'
                )
            return None

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            heavy = self.path.split('?', 1)[0] in ('/save-manager/import', '/save-manager/export')
            if heavy:
                self.connection.settimeout(30)  # Idle upload clients cannot retain the admission slot forever.
            if heavy and not save_upload_slot.acquire(blocking=False):
                # Drain without retaining another 96MB archive. Reading the body
                # preserves the busy response on clients sensitive to TCP resets.
                error = self._consume_request_body(discard=True)
                self._send(error or HTTPResponse(503, 'application/json; charset=utf-8',
                    b'{"error":"save_manager_busy"}', (('Retry-After', '1'),)))
                return
            try:
                self._do_POST()
            finally:
                if heavy:
                    save_upload_slot.release()

        def _do_POST(self):
            if error := self._consume_request_body():
                self._send(error)
                return
            if self.path.split("?", 1)[0].startswith("/MailService."):
                try:
                    payload = json.loads(self.request_body)
                    fields = sorted(payload) if isinstance(payload, dict) else [type(payload).__name__]
                    mail_page = payload.get("page") if isinstance(payload, dict) else None
                    mail_state = payload.get("state") if isinstance(payload, dict) else None
                except (ValueError, UnicodeDecodeError):
                    fields = ["non_json"]
                    mail_page = mail_state = None
                authorization = self.headers.get("Authorization", "")
                LOGGER.info("mail HTTP request shape route=%s fields=%s page=%s state=%s headers=%s auth_scheme=%s auth_size=%s",
                            self.path.split("?", 1)[0], fields, mail_page, mail_state,
                            sorted(key.lower() for key in self.headers if key.lower() not in
                                   {"host", "user-agent", "accept", "connection", "content-length"}),
                            authorization.split(" ", 1)[0] if authorization else "absent",
                            len(authorization))
            try:
                response = service.respond("POST", self.path, self.request_body,
                                           authorization=self.headers.get("Authorization", ""))
            except Exception as exc:
                if not is_database_busy(exc):
                    raise
                LOGGER.warning('HTTP database busy route=%s', self.path.split('?', 1)[0])
                response = HTTPResponse(503, 'application/json; charset=utf-8',
                                        b'{"error":"database_busy"}', (('Retry-After', '1'),))
            if self.path.split("?", 1)[0].startswith("/MailService."):
                LOGGER.info("mail HTTP response route=%s status=%s",
                            self.path.split("?", 1)[0], response.status)
            self._send(response)

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            self._send(service.respond("GET", self.path))

        def log_message(self, format: str, *args: object) -> None:
            # BaseHTTPRequestHandler's default request line includes query strings.
            # Log only the route; credentials and tokens must never enter this log.
            LOGGER.info("bootstrap request from %s: %s %s", self.client_address[0],
                        self.command, self.path.split("?", 1)[0])

    return Handler


class BootstrapHTTPServer:
    """Start and stop a fixed-route ThreadingHTTPServer without blocking asyncio."""

    def __init__(
        self,
        host: str,
        port: int,
        service: BootstrapService | RecoveredBootstrapService,
    ) -> None:
        self.host = host
        self.port = port
        self.service = service
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def bound_host(self) -> str:
        if self._server is None:
            raise RuntimeError("bootstrap server is not started")
        return str(self._server.server_address[0])

    @property
    def bound_port(self) -> int:
        if self._server is None:
            raise RuntimeError("bootstrap server is not started")
        return int(self._server.server_address[1])

    async def start(self) -> None:
        """Bind the configured localhost endpoint and start its owned thread."""
        if self._server is not None:
            raise RuntimeError("bootstrap server already started")
        server = ThreadingHTTPServer((self.host, self.port), _handler_for(self.service))
        server.daemon_threads = True
        thread = threading.Thread(
            target=server.serve_forever,
            name="x2-bootstrap-http",
            daemon=True,
        )
        self._server = server
        self._thread = thread
        thread.start()

    async def stop(self) -> None:
        """Stop request handling, close the socket and join the owned thread."""
        server, self._server = self._server, None
        thread, self._thread = self._thread, None
        if server is None:
            return
        await asyncio.to_thread(server.shutdown)
        server.server_close()
        if thread is not None:
            await asyncio.to_thread(thread.join, 2.0)
            if thread.is_alive():
                raise RuntimeError("bootstrap HTTP thread failed to stop")
