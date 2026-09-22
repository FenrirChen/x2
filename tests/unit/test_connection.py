import asyncio

from x2server.network.dispatcher import OutboundMessage
from x2server.network.session import SessionState
from x2server.protocol.headers import ResponseHeader


def test_session_identity_is_distinct_from_connection_identity() -> None:
    session = SessionState(connection_id="connection-1", session_id="network-session")
    assert session.connection_id != session.session_id


def test_outbound_message_is_business_neutral_value_container() -> None:
    response = OutboundMessage("L2C_GuideStep", {"code": 0})
    assert response.message_name == "L2C_GuideStep"
    assert response.values == {"code": 0}
    assert asyncio.iscoroutinefunction(asyncio.StreamWriter.drain)
    assert ResponseHeader(request_id=7).request_id == 7

