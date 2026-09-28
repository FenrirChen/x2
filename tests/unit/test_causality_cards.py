import asyncio

from tests.unit.test_battle import packet
from tests.unit.test_economy import env
from x2server.messages.economy import ECONOMY_SCHEMAS
from x2server.protocol.codec import ProtocolCodec
from x2server.protocol.headers import RequestHeader, ResponseHeader


def test_all_causality_cards_consume_once_and_restore_power(env):
    store, economy, ctx = env
    for item_id, amount in economy.CAUSALITY_CARDS.items():
        with store.db:
            store.db.execute("INSERT INTO inventory VALUES (?,?,?)", (1, item_id, 2))
        before = store.get(1)["snapshot"]["mobility"]["power"]
        request = packet({"id": item_id, "opt": 0, "count": 1}, request_id=item_id, name="C2L_ItemOpt")
        first = asyncio.run(economy.handle(ctx, request))
        assert first.values["code"] == 10
        assert store.get(1)["snapshot"]["mobility"]["power"] == before + amount
        assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?",
                                (item_id,)).fetchone()[0] == 1
        replay = asyncio.run(economy.handle(ctx, request))
        assert replay.values == first.values
        assert store.get(1)["snapshot"]["mobility"]["power"] == before + amount
        wire = ProtocolCodec().encode("L2C_ItemOpt", first.values, ResponseHeader(request_id=1))
        assert ProtocolCodec().decode(wire, ResponseHeader).values["code"] == 10
    assert asyncio.run(economy.handle(ctx, packet({"id": 1202014, "opt": 0, "count": 2},
        name="C2L_ItemOpt"))).values["code"] == 13
