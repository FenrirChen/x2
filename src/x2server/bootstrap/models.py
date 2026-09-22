"""Strongly typed synthetic bootstrap configuration.

The retired service's official JSON field names remain UNKNOWN. This model is a
development compatibility contract and must not be labelled original behavior.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from x2server.config.settings import Settings

SCHEMA_STATUS = "UNKNOWN_OFFICIAL_BODY_SCHEMA"


class BootstrapConfigError(ValueError):
    """A bootstrap fixture is malformed or violates safe local constraints."""


@dataclass(frozen=True, slots=True)
class GameEndpoint:
    """Configured game TCP endpoint advertised by the development service."""

    host: str
    port: int

    def __post_init__(self) -> None:
        if not self.host or any(character in self.host for character in "\r\n\x00"):
            raise BootstrapConfigError("game server host must be non-empty and single-line")
        if not 0 <= self.port <= 65535:
            raise BootstrapConfigError("game server port must be between 0 and 65535")


@dataclass(frozen=True, slots=True)
class BootstrapConfig:
    """Synthetic known-subset model; official field mapping is still unknown."""

    game_server: GameEndpoint
    environment: str
    client_version: str
    unknown_official_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.environment or not self.client_version:
            raise BootstrapConfigError("environment and client_version must be non-empty")

    @classmethod
    def from_settings(
        cls, settings: Settings, *, game_server_port: int | None = None
    ) -> BootstrapConfig:
        """Build a local fixture, optionally advertising an ephemeral bound TCP port."""
        return cls(
            game_server=GameEndpoint(
                settings.game_server_host,
                settings.game_server_port if game_server_port is None else game_server_port,
            ),
            environment=settings.environment,
            client_version=settings.client_version,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the documented synthetic JSON shape."""
        return {
            "_fixture": {
                "synthetic": True,
                "schemaStatus": SCHEMA_STATUS,
                "notOfficialCapture": True,
            },
            "gameServer": {
                "host": self.game_server.host,
                "port": self.game_server.port,
            },
            "environment": self.environment,
            "clientVersion": self.client_version,
            "unknownOfficialFields": list(self.unknown_official_fields),
        }

    def to_json_bytes(self) -> bytes:
        """Serialize a deterministic non-empty UTF-8 JSON fixture."""
        return (json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True) + "\n").encode(
            "utf-8"
        )

    @classmethod
    def from_json_bytes(cls, body: bytes) -> BootstrapConfig:
        """Parse and validate only the synthetic development schema."""
        try:
            raw = json.loads(body.decode("utf-8"))
            fixture = raw["_fixture"]
            endpoint = raw["gameServer"]
            unknown = raw.get("unknownOfficialFields", [])
            if fixture.get("synthetic") is not True or fixture.get("schemaStatus") != SCHEMA_STATUS:
                raise BootstrapConfigError("fixture marker/schema status is invalid")
            if not isinstance(unknown, list) or not all(isinstance(item, str) for item in unknown):
                raise BootstrapConfigError("unknownOfficialFields must be a string list")
            return cls(
                game_server=GameEndpoint(str(endpoint["host"]), int(endpoint["port"])),
                environment=str(raw["environment"]),
                client_version=str(raw["clientVersion"]),
                unknown_official_fields=tuple(unknown),
            )
        except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BootstrapConfigError("malformed synthetic bootstrap config") from exc

