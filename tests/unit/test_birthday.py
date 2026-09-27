"""The main-story birthday prompt receives a reply and survives relogin."""

import asyncio
from pathlib import Path

import pytest

from tests.unit.test_battle import packet
from tests.unit.test_economy import env  # noqa: F401
from x2server.messages.core import BASE_INFO, PLAYER_DATA, C2L_FILL_BIRTHDAY, L2C_FILL_BIRTHDAY
from x2server.player.birthday import BirthdayService
from x2server.player.store import PlayerStore
from x2server.protocol.errors import ProtocolError


def test_fill_birthday_reply_and_persistence(env):
    store, _, context = env
    service = BirthdayService(store)
    request = packet({"month": 2, "day": 29}, name="C2L_FillBirthday")
    assert C2L_FILL_BIRTHDAY.decode(request.body) == {"month": 2, "day": 29}
    reply = asyncio.run(service.fill(context, request))
    assert reply.values == {"code": 10}
    assert L2C_FILL_BIRTHDAY.decode(L2C_FILL_BIRTHDAY.encode(reply.values)) == {"code": 10}
    pushed = PLAYER_DATA.decode(PLAYER_DATA.encode(reply.before_response[0].values))
    assert BASE_INFO.decode(pushed["BaseInfo"])["Birthday"] == 229
    assert store.get(1)["snapshot"]["birthday"] == 229
    revision = store.get(1)["revision"]
    assert asyncio.run(service.fill(context, request)).values["code"] == 10
    assert store.get(1)["revision"] == revision
    path = store.db.execute("PRAGMA database_list").fetchone()[2]
    reopened = PlayerStore(Path(path))
    try:
        assert reopened.get(1)["snapshot"]["birthday"] == 229
    finally:
        reopened.close()


def test_invalid_or_unauthenticated_birthday_does_not_change_player(env):
    store, _, context = env
    service = BirthdayService(store)
    before = store.get(1)
    for month, day in ((0, 1), (13, 1), (2, 30), (4, 31)):
        reply = asyncio.run(service.fill(context, packet({"month": month, "day": day},
            name="C2L_FillBirthday")))
        assert reply.values == {"code": 13}
    assert store.get(1) == before
    context.session.player_id = None
    with pytest.raises(ProtocolError):
        asyncio.run(service.fill(context, packet({"month": 1, "day": 1},
            name="C2L_FillBirthday")))
