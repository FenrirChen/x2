import pytest

from x2server.protocol.errors import UnknownMessageError
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY


@pytest.mark.parametrize(
    ("name", "message_id"),
    [
        ("C2L_Login", 54),
        ("L2C_Login", 79),
        ("C2L_FightData", 126),
        ("L2C_FightData", 130),
        ("C2L_CheckoutMainMission", 150),
        ("C2L_PrepareMainMission", 151),
        ("L2C_CheckoutMainMission", 152),
        ("L2C_PrepareMainMission", 153),
        ("C2L_FightDropData", 264),
        ("L2C_FightDropData", 266),
        ("C2L_GuideStep", 374),
        ("L2C_GuideStep", 375),
        ("L2C_ItemUpdate", 553),
        ("L2C_ItemAll", 555),
        ("C2L_ItemAll", 556),
        ("C2L_CheckoutMainMissionSign", 887),
    ],
)
def test_registry_bidirectional_lookup(name: str, message_id: int) -> None:
    assert CORE_MESSAGE_REGISTRY.id_for(name) == message_id
    assert CORE_MESSAGE_REGISTRY.name_for(message_id) == name


def test_unknown_name_and_id_are_explicit() -> None:
    with pytest.raises(UnknownMessageError):
        CORE_MESSAGE_REGISTRY.id_for("L2C_CheckoutMainMissionSign")
    with pytest.raises(UnknownMessageError):
        CORE_MESSAGE_REGISTRY.name_for(999_999)

