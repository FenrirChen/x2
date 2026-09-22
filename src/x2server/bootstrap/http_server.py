"""Standard-library localhost HTTP transport for the fixed bootstrap service."""

from __future__ import annotations

import asyncio
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .service import BootstrapService, HTTPResponse

LOGGER = logging.getLogger("x2.bootstrap.http")


def _handler_for(service: BootstrapService) -> type[BaseHTTPRequestHandler]:
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

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            self._send(service.respond("POST", self.path))

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            self._send(service.respond("GET", self.path))

        def log_message(self, format: str, *args: object) -> None:
            # Never include request bodies or authentication data.
            LOGGER.info("bootstrap request from %s: %s", self.client_address[0], format % args)

    return Handler


class BootstrapHTTPServer:
    """Start and stop a fixed-route ThreadingHTTPServer without blocking asyncio."""

    def __init__(self, host: str, port: int, service: BootstrapService) -> None:
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

