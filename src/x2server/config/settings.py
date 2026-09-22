"""Safe environment-based settings; deployment secrets never belong here."""

from __future__ import annotations

import os
from dataclasses import dataclass

# TEMPORARY_COMPAT: defensive local limit, not a recovered original constant.
DEFAULT_MAX_PACKET_SIZE = 16 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class Settings:
    """Non-secret process settings used by later service milestones."""

    max_packet_size: int = DEFAULT_MAX_PACKET_SIZE
    log_level: str = "INFO"
    tcp_host: str = "127.0.0.1"
    tcp_port: int = 0
    read_timeout: float = 30.0
    write_timeout: float = 10.0
    idle_timeout: float = 120.0
    max_connections: int = 128
    read_chunk_size: int = 64 * 1024
    bootstrap_host: str = "127.0.0.1"
    bootstrap_port: int = 0
    bootstrap_path: str = "/webgameconfig"
    game_server_host: str = "127.0.0.1"
    game_server_port: int = 0
    environment: str = "local-development"
    client_version: str = "2.4"

    @classmethod
    def from_environment(cls) -> Settings:
        """Read non-secret overrides from explicit X2-prefixed variables."""
        max_packet_size = int(os.getenv("X2_MAX_PACKET_SIZE", str(DEFAULT_MAX_PACKET_SIZE)))
        if max_packet_size <= 0:
            raise ValueError("X2_MAX_PACKET_SIZE must be positive")
        tcp_port = int(os.getenv("X2_TCP_PORT", "0"))
        if not 0 <= tcp_port <= 65535:
            raise ValueError("X2_TCP_PORT must be between 0 and 65535")
        max_connections = int(os.getenv("X2_MAX_CONNECTIONS", "128"))
        if max_connections <= 0:
            raise ValueError("X2_MAX_CONNECTIONS must be positive")
        bootstrap_port = int(os.getenv("X2_BOOTSTRAP_PORT", "0"))
        game_server_port = int(os.getenv("X2_GAME_SERVER_PORT", str(tcp_port)))
        for name, port in (
            ("X2_BOOTSTRAP_PORT", bootstrap_port),
            ("X2_GAME_SERVER_PORT", game_server_port),
        ):
            if not 0 <= port <= 65535:
                raise ValueError(f"{name} must be between 0 and 65535")
        bootstrap_path = os.getenv("X2_BOOTSTRAP_PATH", "/webgameconfig")
        if not bootstrap_path.startswith("/"):
            raise ValueError("X2_BOOTSTRAP_PATH must start with /")
        return cls(
            max_packet_size=max_packet_size,
            log_level=os.getenv("X2_LOG_LEVEL", "INFO"),
            tcp_host=os.getenv("X2_TCP_HOST", "127.0.0.1"),
            tcp_port=tcp_port,
            read_timeout=float(os.getenv("X2_READ_TIMEOUT", "30")),
            write_timeout=float(os.getenv("X2_WRITE_TIMEOUT", "10")),
            idle_timeout=float(os.getenv("X2_IDLE_TIMEOUT", "120")),
            max_connections=max_connections,
            read_chunk_size=int(os.getenv("X2_READ_CHUNK_SIZE", str(64 * 1024))),
            bootstrap_host=os.getenv("X2_BOOTSTRAP_HOST", "127.0.0.1"),
            bootstrap_port=bootstrap_port,
            bootstrap_path=bootstrap_path,
            game_server_host=os.getenv(
                "X2_GAME_SERVER_HOST", os.getenv("X2_TCP_HOST", "127.0.0.1")
            ),
            game_server_port=game_server_port,
            environment=os.getenv("X2_ENVIRONMENT", "local-development"),
            client_version=os.getenv("X2_CLIENT_VERSION", "2.4"),
        )


