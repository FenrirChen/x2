from pathlib import Path

import pytest

from x2server.bootstrap.models import (
    SCHEMA_STATUS,
    BootstrapConfig,
    BootstrapConfigError,
    GameEndpoint,
)
from x2server.bootstrap.service import BootstrapService
from x2server.config.settings import Settings


def fixture_body() -> bytes:
    path = Path(__file__).resolve().parents[1] / "fixtures" / "bootstrap" / "synthetic_webgameconfig.json"
    return path.read_bytes()


def test_synthetic_fixture_is_nonempty_and_round_trips() -> None:
    config = BootstrapConfig.from_json_bytes(fixture_body())
    assert config.game_server == GameEndpoint("127.0.0.1", 29000)
    assert config.client_version == "2.4"
    assert SCHEMA_STATUS.encode() in config.to_json_bytes()


def test_game_endpoint_is_configurable() -> None:
    settings = Settings(game_server_host="localhost", game_server_port=31000)
    config = BootstrapConfig.from_settings(settings)
    assert config.game_server == GameEndpoint("localhost", 31000)


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"not-json",
        b"{}",
        b'{"_fixture":{"synthetic":false}}',
        b'{"_fixture":{"synthetic":true,"schemaStatus":"wrong"},"gameServer":{}}',
    ],
)
def test_malformed_config_fails_explicitly(body: bytes) -> None:
    with pytest.raises(BootstrapConfigError):
        BootstrapConfig.from_json_bytes(body)


def test_service_requires_post_and_fixed_path() -> None:
    service = BootstrapService(BootstrapConfig.from_json_bytes(fixture_body()))
    assert service.respond("POST", "/webgameconfig").status == 200
    assert service.respond("GET", "/webgameconfig").status == 405
    assert service.respond("POST", "/unknown").status == 404

