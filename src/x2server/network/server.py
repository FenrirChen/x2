"""Asyncio listener and explicit ownership of connection tasks."""

from __future__ import annotations

import asyncio
import itertools
import logging

from x2server.config.settings import Settings

from .connection import X2Connection
from .dispatcher import Dispatcher

LOGGER = logging.getLogger("x2.network.server")


class X2TCPServer:
    """Bind, accept and gracefully stop X2 development TCP connections."""

    def __init__(self, settings: Settings, dispatcher: Dispatcher | None = None) -> None:
        self.settings = settings
        self.dispatcher = dispatcher or Dispatcher()
        self._server: asyncio.Server | None = None
        self._connections: dict[str, X2Connection] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._ids = itertools.count(1)
        self._connection_changed = asyncio.Condition()

    @property
    def bound_host(self) -> str:
        if self._server is None or not self._server.sockets:
            raise RuntimeError("server is not started")
        return str(self._server.sockets[0].getsockname()[0])

    @property
    def bound_port(self) -> int:
        if self._server is None or not self._server.sockets:
            raise RuntimeError("server is not started")
        return int(self._server.sockets[0].getsockname()[1])

    @property
    def active_connection_count(self) -> int:
        return len(self._connections)

    async def start(self) -> None:
        """Bind the configured localhost listener without serving business logic."""
        if self._server is not None:
            raise RuntimeError("server already started")
        self._server = await asyncio.start_server(
            self._accept,
            self.settings.tcp_host,
            self.settings.tcp_port,
        )

    async def serve_forever(self) -> None:
        """Serve until cancelled or stop closes the listener."""
        if self._server is None:
            raise RuntimeError("server is not started")
        async with self._server:
            await self._server.serve_forever()

    async def _accept(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        if len(self._connections) >= self.settings.max_connections:
            writer.close()
            await writer.wait_closed()
            LOGGER.warning("connection limit reached")
            return
        connection_id = f"connection-{next(self._ids)}"
        connection = X2Connection(
            connection_id,
            reader,
            writer,
            self.dispatcher,
            self.settings,
            self._connection_closed,
        )
        self._connections[connection_id] = connection
        task = asyncio.create_task(connection.run(), name=f"x2-{connection_id}")
        self._tasks[connection_id] = task
        task.add_done_callback(
            lambda completed, cid=connection_id: self._task_completed(cid, completed)
        )
        await self._notify_connection_change()

    def _connection_closed(self, connection_id: str) -> None:
        self._connections.pop(connection_id, None)
        loop = asyncio.get_running_loop()
        loop.create_task(self._notify_connection_change())

    def _task_completed(self, connection_id: str, task: asyncio.Task[None]) -> None:
        self._tasks.pop(connection_id, None)
        if not task.cancelled() and (error := task.exception()) is not None:
            LOGGER.error("connection task failed: %s", error)

    async def _notify_connection_change(self) -> None:
        async with self._connection_changed:
            self._connection_changed.notify_all()

    async def wait_for_active_connections(self, count: int, timeout: float = 2.0) -> None:
        """Wait deterministically for lifecycle state; useful for shutdown coordination/tests."""
        async def wait() -> None:
            async with self._connection_changed:
                await self._connection_changed.wait_for(
                    lambda: len(self._connections) == count
                )

        if len(self._connections) == count:
            return
        async with asyncio.timeout(timeout):
            await wait()

    async def stop(self) -> None:
        """Stop accepts, close active connections and await every owned task."""
        server, self._server = self._server, None
        if server is not None:
            server.close()
            await server.wait_closed()
        connections = list(self._connections.values())
        if connections:
            await asyncio.gather(*(connection.close() for connection in connections))
        tasks = list(self._tasks.values())
        if tasks:
            done, pending = await asyncio.wait(tasks, timeout=self.settings.write_timeout)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                if not task.cancelled():
                    task.exception()
        self._connections.clear()
        self._tasks.clear()

