import pytest

from x2server.protocol.codec import ProtocolCodec
from x2server.protocol.errors import UnknownMessageError
from x2server.protocol.framing import encode_packet
from x2server.protocol.headers import RequestHeader, ResponseHeader


@pytest.fixture
def codec() -> ProtocolCodec:
    return ProtocolCodec()


def test_c2l_guide_step_packet_round_trip(codec: ProtocolCodec) -> None:
    values = {"stepId": 21011, "stepState": 2}
    header = RequestHeader(request_id=11, session_id="synthetic", ack_data_version=7, unit_id=100)
    decoded = codec.decode(codec.encode("C2L_GuideStep", values, header), RequestHeader)
    assert decoded.message_name == "C2L_GuideStep"
    assert decoded.values == values
    assert decoded.packet.header.request_id == 11


def test_l2c_guide_step_packet_round_trip(codec: ProtocolCodec) -> None:
    values = {"code": 0}
    header = ResponseHeader(request_id=11, session_id="synthetic", data_version=8)
    decoded = codec.decode(codec.encode("L2C_GuideStep", values, header), ResponseHeader)
    assert decoded.message_name == "L2C_GuideStep"
    assert decoded.values == values


def test_login_schemas_round_trip_without_login_business(codec: ProtocolCodec) -> None:
    request_values = {
        "id": 123,
        "token": "synthetic-not-a-real-token",
        "deviceid": "synthetic-device",
        "connectType": 1,
        "submitInfo": b"\x08\x01",
    }
    request = RequestHeader(request_id=1, unit_id=123)
    decoded_request = codec.decode(codec.encode("C2L_Login", request_values, request), RequestHeader)
    assert decoded_request.values == request_values

    response_values = {
        "code": 0,
        "id": 123,
        "loginCount": 1,
        "startDataVersion": 1,
        "serverTime": 1000,
        "isCreateRole": True,
        "heroAll": b"\x0a\x00",
        "sgroupId": "synthetic-group",
    }
    response = ResponseHeader(request_id=1, session_id="synthetic")
    decoded_response = codec.decode(codec.encode("L2C_Login", response_values, response), ResponseHeader)
    assert decoded_response.values == response_values


def test_prepare_mission_schemas_round_trip(codec: ProtocolCodec) -> None:
    request = codec.encode(
        "C2L_PrepareMainMission",
        {"chapter": 2010000, "level": 2110001},
        RequestHeader(request_id=2),
    )
    assert codec.decode(request, RequestHeader).values == {"chapter": 2010000, "level": 2110001}
    response = codec.encode(
        "L2C_PrepareMainMission", {"result": 0}, ResponseHeader(request_id=2)
    )
    assert codec.decode(response, ResponseHeader).values == {"result": 0}


def test_unknown_message_id_is_rejected(codec: ProtocolCodec) -> None:
    packet = encode_packet(RequestHeader(request_id=1), 999_999, b"")
    with pytest.raises(UnknownMessageError, match="unknown message ID"):
        codec.decode(packet, RequestHeader)


def test_direction_mismatch_is_rejected(codec: ProtocolCodec) -> None:
    with pytest.raises(TypeError, match="RequestHeader"):
        codec.encode("C2L_GuideStep", {"stepId": 1, "stepState": 1}, ResponseHeader())

