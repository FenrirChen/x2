import asyncio

from tests.unit.test_battle import packet
from tests.unit.test_economy import env, rewards
from x2server.messages.lobby import MISSION_PAIR
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY

CHIP = 1201039           # 斩念源氏碎片: ItemType 12, client Return [927, 5]
RESTORED_CHIP = 1201041  # 只在 reward_items.json 里, Return 由 item_return_catalog 恢复
FRAGMENT_MONEY = 1237927  # 神笺


def exchange(pairs, request_id=91):
    return packet({"items": [MISSION_PAIR.encode({"Key": item, "Value": count})
                             for item, count in pairs]},
                  request_id=request_id, name="C2L_ItemExchangeCurrency")


def quantity(store, item_id):
    row = store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?",
                           (item_id,)).fetchone()
    return row[0] if row else 0


def test_the_frame_is_registered_and_served_with_the_client_rate(env):
    store, economy, ctx = env
    assert CORE_MESSAGE_REGISTRY.name_for(982) == "C2L_ItemExchangeCurrency"
    assert CORE_MESSAGE_REGISTRY.id_for("L2C_ItemExchangeCurrency") == 983
    assert "C2L_ItemExchangeCurrency" in economy.handlers()
    assert economy.items[CHIP]["Return"] == [927, 5]

    with store.db:
        store.db.execute("INSERT INTO inventory VALUES (?,?,?)", (1, CHIP, 128))
    request = exchange([(CHIP, 128)])
    first = asyncio.run(economy.handle(ctx, request))
    assert first.values["code"] == 10
    assert rewards(first.values["rewardData"]) == {FRAGMENT_MONEY: 640}
    assert quantity(store, CHIP) == 0
    assert quantity(store, FRAGMENT_MONEY) == 640

    # The client re-sends while it has no reply, so the same frame must not pay twice.
    replay = asyncio.run(economy.handle(ctx, request))
    assert replay.values == first.values
    assert quantity(store, FRAGMENT_MONEY) == 640


def test_a_stack_that_is_short_rolls_the_whole_order_back(env):
    store, economy, ctx = env
    with store.db:
        store.db.execute("INSERT INTO inventory VALUES (?,?,?)", (1, CHIP, 3))
    result = asyncio.run(economy.handle(ctx, exchange([(CHIP, 4)])))
    assert result.values["code"] == 13
    assert quantity(store, CHIP) == 3
    assert quantity(store, FRAGMENT_MONEY) == 0


def test_only_type_12_chips_with_a_known_rate_are_served(env):
    store, economy, ctx = env
    with store.db:
        # 1201000 万能神格碎片: ItemType 12 but no Return.
        store.db.execute("INSERT INTO inventory VALUES (?,?,?)", (1, 1201000, 5))
        # 1101014: has a Return column but is not a chip (ItemType 25).
        store.db.execute("INSERT INTO inventory VALUES (?,?,?)", (1, 1101014, 5))
    for pairs, request_id in ((None, 1), ([], 2), ([(1201000, 1)], 3), ([(1101014, 1)], 4),
                              ([(999999, 1)], 5), ([(CHIP, 0)], 6), ([(CHIP, 1000)], 7)):
        request = packet({"items": []}, request_id=request_id, name="C2L_ItemExchangeCurrency") \
            if pairs is None else exchange(pairs, request_id=request_id)
        assert asyncio.run(economy.handle(ctx, request)).values["code"] == 13
    assert quantity(store, 1201000) == 5
    assert quantity(store, 1101014) == 5
    assert quantity(store, FRAGMENT_MONEY) == 0


def test_the_rate_restored_from_the_client_table_serves_the_chip_reward_items_only_has(env):
    store, economy, ctx = env
    assert economy.items[RESTORED_CHIP]["Return"] == [927, 5]
    with store.db:
        store.db.execute("INSERT INTO inventory VALUES (?,?,?)", (1, RESTORED_CHIP, 2))
    result = asyncio.run(economy.handle(ctx, exchange([(RESTORED_CHIP, 2)], request_id=92)))
    assert result.values["code"] == 10
    assert rewards(result.values["rewardData"]) == {FRAGMENT_MONEY: 10}
    assert quantity(store, RESTORED_CHIP) == 0
