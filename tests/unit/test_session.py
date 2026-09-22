from x2server.network.session import SessionState


def test_session_tracks_envelope_state_only() -> None:
    session = SessionState("connection-1")
    session.record_request(7, "synthetic-session")
    assert session.last_request_id == 7
    assert session.session_id == "synthetic-session"


def test_log_context_contains_no_authentication_payload() -> None:
    context = SessionState("connection-1", last_request_id=7).log_context(374, "C2L_GuideStep")
    assert context == {
        "connection_id": "connection-1",
        "message_id": 374,
        "message_name": "C2L_GuideStep",
        "request_id": 7,
    }

