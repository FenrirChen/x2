from __future__ import annotations

import json
from pathlib import Path

import pytest

from x2server.bootstrap.models import (
    BootstrapConfigError,
    RecoveredBootstrapContract,
    RecoveredControlInfo,
    RecoveredServerAddressConfig,
    RecoveredWebGameConfig,
    ServerAddressEntry,
)
from x2server.bootstrap.service import RecoveredBootstrapService

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "bootstrap"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def recovered_contract() -> RecoveredBootstrapContract:
    return RecoveredBootstrapContract(
        RecoveredWebGameConfig.from_json_bytes(
            fixture("recovered_minimal_webgameconfig.json")
        ),
        RecoveredServerAddressConfig.from_json_bytes(
            fixture("recovered_minimal_server_address.json")
        ),
    )


def test_recovered_webgameconfig_round_trip_has_confirmed_required_fields() -> None:
    config = recovered_contract().web_config

    decoded = RecoveredWebGameConfig.from_json_bytes(config.to_json_bytes())

    assert decoded == config
    assert set(decoded.to_dict()["result"]) == {
        "serviceAppId",
        "pbsServer",
        "loginServer",
        "accountServer",
        "eswebServer",
        "lbPbsServer",
        "lbLoginServer",
        "lbEswebServer",
        "areaId",
    }


def test_recovered_endpoint_maps_ip_and_port_without_transformation() -> None:
    config = recovered_contract().server_addresses

    decoded = RecoveredServerAddressConfig.from_json_bytes(config.to_json_bytes())

    assert decoded.endpoints[0].host == "127.0.0.1"
    assert decoded.endpoints[0].port == 29000
    assert decoded.to_dict()["result"]["data"][0]["ip"] == "127.0.0.1"
    assert decoded.to_dict()["result"]["data"][0]["port"] == 29000


def test_control_info_minimal_response_round_trip() -> None:
    config = RecoveredControlInfo()

    decoded = RecoveredControlInfo.from_json_bytes(config.to_json_bytes())

    assert decoded == config
    assert decoded.to_dict() == {"giftCode": "", "update": ""}


def test_unknown_fields_remain_optional() -> None:
    raw = json.loads(fixture("recovered_minimal_webgameconfig.json"))
    raw["unrelatedEnvelopeField"] = {"future": True}
    raw["result"]["unknownOperatorFlag"] = 7
    raw["result"]["lbPbsServer"] = []

    decoded = RecoveredWebGameConfig.from_json_bytes(json.dumps(raw).encode())

    assert decoded.area_id == "local"
    assert decoded.lb_pbs_server == ()


@pytest.mark.parametrize(
    "field",
    [
        "serviceAppId",
        "pbsServer",
        "loginServer",
        "accountServer",
        "eswebServer",
        "lbPbsServer",
        "lbLoginServer",
        "lbEswebServer",
        "areaId",
    ],
)
def test_confirmed_webgameconfig_fields_are_required(field: str) -> None:
    raw = json.loads(fixture("recovered_minimal_webgameconfig.json"))
    del raw["result"][field]

    with pytest.raises(BootstrapConfigError):
        RecoveredWebGameConfig.from_json_bytes(json.dumps(raw).encode())


def test_address_contract_rejects_empty_endpoint_list() -> None:
    with pytest.raises(BootstrapConfigError):
        RecoveredServerAddressConfig.from_json_bytes(b'{"result":{"data":[]}}')


def test_recovered_service_routes_confirmed_posts() -> None:
    service = RecoveredBootstrapService(recovered_contract())

    connect_info = service.respond("POST", "/apply/connectInfo")
    address = service.respond("POST", "/apply/address?ignored=query")
    control_info = service.respond("POST", "/apply/controlInfo")

    assert connect_info.status == 200
    assert address.status == 200
    assert control_info.status == 200
    assert RecoveredWebGameConfig.from_json_bytes(connect_info.body).area_id == "local"
    assert RecoveredServerAddressConfig.from_json_bytes(address.body).endpoints[0] == (
        ServerAddressEntry("127.0.0.1", 29000, description="local compatibility endpoint")
    )
    assert RecoveredControlInfo.from_json_bytes(control_info.body) == RecoveredControlInfo()


def test_recovered_service_rejects_unconfirmed_route_and_method() -> None:
    service = RecoveredBootstrapService(recovered_contract())

    assert service.respond("GET", "/apply/connectInfo").status == 405
    assert service.respond("POST", "/unknown").status == 404
