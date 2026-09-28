"""Network settings for the local launcher and the Linux service."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DeploymentEndpoints:
    bind_host: str
    public_host: str
    http_port: int
    game_port: int
    chat_port: int

    @classmethod
    def from_environment(cls) -> "DeploymentEndpoints":
        bind_host = os.getenv("X2_BIND_HOST", "127.0.0.1")
        public_host = os.getenv("X2_PUBLIC_HOST", "10.0.2.2")
        if not bind_host or not public_host or any(c in public_host for c in "/:@ \t\r\n"):
            raise ValueError("invalid X2 bind or public host")

        def port(name: str, default: int) -> int:
            value = int(os.getenv(name, str(default)))
            if not 1 <= value <= 65535:
                raise ValueError(f"{name} must be between 1 and 65535")
            return value

        result = cls(bind_host, public_host, port("X2_HTTP_PORT", 18080),
                     port("X2_GAME_PORT", 29000), port("X2_CHAT_PORT", 29001))
        if len({result.http_port, result.game_port, result.chat_port}) != 3:
            raise ValueError("X2 listener ports must be distinct")
        return result
