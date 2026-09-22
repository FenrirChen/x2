"""Strongly typed synthetic and statically recovered bootstrap models."""

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


def _load_json_object(body: bytes, description: str) -> dict[str, Any]:
    try:
        raw = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BootstrapConfigError(f"malformed {description}") from exc
    if not isinstance(raw, dict):
        raise BootstrapConfigError(f"{description} must be a JSON object")
    return raw


def _required_string(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise BootstrapConfigError(f"{key} must be a non-empty string")
    return value


def _required_string_list(mapping: dict[str, Any], key: str) -> tuple[str, ...]:
    value = mapping.get(key)
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise BootstrapConfigError(f"{key} must be a string list")
    return tuple(value)


@dataclass(frozen=True, slots=True)
class RecoveredWebGameConfig:
    """Confirmed subset parsed by ``AppMainImpl.LoadWebGameConfig``.

    The field names and ``result`` envelope are CONFIRMED by static evidence.
    Values supplied here are local compatibility values, not recovered official
    production values.
    """

    service_app_id: str
    pbs_server: str
    login_server: str
    account_server: str
    esweb_server: str
    lb_pbs_server: tuple[str, ...]
    lb_login_server: tuple[str, ...]
    lb_esweb_server: tuple[str, ...]
    area_id: str

    def __post_init__(self) -> None:
        scalar_values = (
            self.service_app_id,
            self.pbs_server,
            self.login_server,
            self.account_server,
            self.esweb_server,
            self.area_id,
        )
        if any(not value or any(char in value for char in "\r\n\x00") for value in scalar_values):
            raise BootstrapConfigError("recovered WebGameConfig strings must be non-empty")
        for values in (self.lb_pbs_server, self.lb_login_server, self.lb_esweb_server):
            if any(
                not value or any(char in value for char in "\r\n\x00") for value in values
            ):
                raise BootstrapConfigError("recovered WebGameConfig lists contain invalid values")

    def to_dict(self) -> dict[str, Any]:
        """Return the confirmed JSON envelope and field names."""
        return {
            "result": {
                "serviceAppId": self.service_app_id,
                "pbsServer": self.pbs_server,
                "loginServer": self.login_server,
                "accountServer": self.account_server,
                "eswebServer": self.esweb_server,
                "lbPbsServer": list(self.lb_pbs_server),
                "lbLoginServer": list(self.lb_login_server),
                "lbEswebServer": list(self.lb_esweb_server),
                "areaId": self.area_id,
            }
        }

    def to_json_bytes(self) -> bytes:
        """Serialize a deterministic UTF-8 compatibility response."""
        return (json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True) + "\n").encode(
            "utf-8"
        )

    @classmethod
    def from_json_bytes(cls, body: bytes) -> RecoveredWebGameConfig:
        """Parse the confirmed subset while tolerating unrelated extra fields."""
        raw = _load_json_object(body, "recovered WebGameConfig")
        result = raw.get("result")
        if not isinstance(result, dict):
            raise BootstrapConfigError("result must be a JSON object")
        return cls(
            service_app_id=_required_string(result, "serviceAppId"),
            pbs_server=_required_string(result, "pbsServer"),
            login_server=_required_string(result, "loginServer"),
            account_server=_required_string(result, "accountServer"),
            esweb_server=_required_string(result, "eswebServer"),
            lb_pbs_server=_required_string_list(result, "lbPbsServer"),
            lb_login_server=_required_string_list(result, "lbLoginServer"),
            lb_esweb_server=_required_string_list(result, "lbEswebServer"),
            area_id=_required_string(result, "areaId"),
        )


@dataclass(frozen=True, slots=True)
class ServerAddressEntry:
    """One endpoint parsed by ``ServerIPModule._getServerIP``."""

    host: str
    port: int
    weight: int = 0
    zone_id: int = 1
    description: str = ""

    def __post_init__(self) -> None:
        if not self.host or any(char in self.host for char in "\r\n\x00"):
            raise BootstrapConfigError("server address host must be non-empty and single-line")
        if not 1 <= self.port <= 65535:
            raise BootstrapConfigError("server address port must be between 1 and 65535")

    def to_dict(self) -> dict[str, Any]:
        """Return field names consumed by the recovered client parser."""
        return {
            "ip": self.host,
            "port": self.port,
            "weight": self.weight,
            "zid": self.zone_id,
            "des": self.description,
        }


@dataclass(frozen=True, slots=True)
class RecoveredServerAddressConfig:
    """Confirmed ``result.data`` endpoint-list response."""

    endpoints: tuple[ServerAddressEntry, ...]

    def __post_init__(self) -> None:
        if not self.endpoints:
            raise BootstrapConfigError("at least one server endpoint is required")

    def to_dict(self) -> dict[str, Any]:
        """Return the confirmed endpoint-list envelope."""
        return {"result": {"data": [entry.to_dict() for entry in self.endpoints]}}

    def to_json_bytes(self) -> bytes:
        """Serialize a deterministic UTF-8 compatibility response."""
        return (json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True) + "\n").encode(
            "utf-8"
        )

    @classmethod
    def from_json_bytes(cls, body: bytes) -> RecoveredServerAddressConfig:
        """Parse the endpoint subset needed to reach ``MarsNetManager.SetIP``."""
        raw = _load_json_object(body, "recovered server-address config")
        result = raw.get("result")
        data = result.get("data") if isinstance(result, dict) else None
        if not isinstance(data, list) or not data:
            raise BootstrapConfigError("result.data must be a non-empty list")
        endpoints: list[ServerAddressEntry] = []
        try:
            for item in data:
                if not isinstance(item, dict):
                    raise BootstrapConfigError("result.data entries must be objects")
                endpoints.append(
                    ServerAddressEntry(
                        host=_required_string(item, "ip"),
                        port=int(item["port"]),
                        weight=int(item.get("weight", 0)),
                        zone_id=int(item.get("zid", 1)),
                        description=str(item.get("des", "")),
                    )
                )
        except (KeyError, TypeError, ValueError) as exc:
            raise BootstrapConfigError("invalid server-address entry") from exc
        return cls(tuple(endpoints))


@dataclass(frozen=True, slots=True)
class RecoveredControlInfo:
    """Minimal root object consumed by ``AppMainImpl._controlInfo``."""

    gift_code: str = ""
    update: str = ""

    def __post_init__(self) -> None:
        if any(char in value for value in (self.gift_code, self.update) for char in "\r\n\x00"):
            raise BootstrapConfigError("control-info strings must be single-line")

    def to_dict(self) -> dict[str, str]:
        return {"giftCode": self.gift_code, "update": self.update}

    def to_json_bytes(self) -> bytes:
        return (json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True) + "\n").encode(
            "utf-8"
        )

    @classmethod
    def from_json_bytes(cls, body: bytes) -> RecoveredControlInfo:
        raw = _load_json_object(body, "recovered control-info response")
        gift_code = raw.get("giftCode")
        update = raw.get("update")
        if not isinstance(gift_code, str) or not isinstance(update, str):
            raise BootstrapConfigError("giftCode and update must be strings")
        return cls(gift_code, update)


@dataclass(frozen=True, slots=True)
class RecoveredBootstrapContract:
    """The two confirmed HTTP responses required before game TCP connection."""

    web_config: RecoveredWebGameConfig
    server_addresses: RecoveredServerAddressConfig

    @classmethod
    def local(
        cls,
        settings: Settings,
        *,
        game_server_port: int | None = None,
    ) -> RecoveredBootstrapContract:
        """Build local-only compatibility values from safe runtime settings."""
        port = settings.game_server_port if game_server_port is None else game_server_port
        local_http = f"http://{settings.bootstrap_host}:{settings.bootstrap_port}"
        web = RecoveredWebGameConfig(
            service_app_id="x2-local-compat",
            pbs_server=local_http,
            login_server=local_http,
            account_server=local_http,
            esweb_server=local_http,
            lb_pbs_server=(local_http,),
            lb_login_server=(local_http,),
            lb_esweb_server=(local_http,),
            area_id="local",
        )
        addresses = RecoveredServerAddressConfig(
            (ServerAddressEntry(settings.game_server_host, port),)
        )
        return cls(web, addresses)
