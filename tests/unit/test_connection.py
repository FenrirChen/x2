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


def test_refresh_response_does_not_share_delivery_turn_with_following_reply() -> None:
    from x2server.network.connection import X2Connection
    from x2server.network.dispatcher import Dispatcher
    from x2server.config.settings import Settings

    async def scenario():
        writes = []
        class Writer:
            def get_extra_info(self, name):
                return None
            def write(self, data):
                writes.append(data)
            async def drain(self):
                pass
        connection = X2Connection('test', asyncio.StreamReader(), Writer(),
                                  Dispatcher(), Settings(), lambda _: None)
        async def deliver():
            await connection.send_response(OutboundMessage('L2C_QueryMission', {}, dispatch_gap=0.05), 1)
            await connection.send_response(OutboundMessage('L2C_GameTask', {'code': 10, 'type': 1}), 2)
        delivery = asyncio.create_task(deliver())
        await asyncio.sleep(0)
        assert len(writes) == 1  # A refresh callback can run before the next reply arrives.
        await delivery
        assert len(writes) == 2
    asyncio.run(scenario())

