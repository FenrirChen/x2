import asyncio

import pytest

from tests.activity_calendar_helpers import activity_start, next_activity_cycle
from tests.unit.test_activity_runtime import runtime
from tests.unit.test_economy import env
from tests.unit.test_battle import packet
from x2server.messages.activity import ACTIVITY_SCHEMAS


@pytest.mark.parametrize('theme', range(7))
def test_activity_catalog_seeds_only_current_unlocked_pools(runtime, theme):
    _, _, context, rt, now = runtime
    now[0] = activity_start(theme) + 3600
    response = asyncio.run(rt.handle(context, packet({}, 2100 + theme, 'C2L_QueryActivity')))
    assert response.values['code'] == 10
    assert response.dispatch_gap > 0
    pools = [m for m in response.pushes if m.message_name == 'L2C_ActivityRewardPoolInfo']
    period = rt.r.at()
    row = rt.r.of_type(26, period)
    assert bool(pools) == bool(row)
    if row:
        assert len(pools) == 1
        values = pools[0].values
        assert values['activityId'] == row['ActivityID']
        ACTIVITY_SCHEMAS['L2C_ActivityRewardPoolInfo'].encode(values)
        ids = [ACTIVITY_SCHEMAS['RewardPoolInfo'].decode(v)['rewardPoolId']
               for v in values['rewardPoolInfos']]
        assert ids == rt.a.unlocked_pools(1, period, row)
        assert ids and ids[0] == row['ActivityParam1'][0]


def test_pool_catalog_is_fresh_next_occurrence(runtime):
    _, _, context, rt, now = runtime
    now[0] = activity_start(2) + 3600
    row = rt.r.of_type(26)
    first = rt.a.boxes[row['ActivityParam1'][0]]
    with rt.e.transaction():
        rt.r.put(1, rt.r.at(), 'pool', first['BoxID'],
                 {str(gid): n for gid, n in zip(first['UnlockGroupID'], first['UnlockGroupTimes'])})
    query = packet({}, 2190, 'C2L_QueryActivity')
    old = asyncio.run(rt.handle(context, query))
    old_pool = next(m for m in old.pushes if m.message_name == 'L2C_ActivityRewardPoolInfo')
    assert len(old_pool.values['rewardPoolInfos']) > 1
    now[0] = next_activity_cycle(now[0])
    new = asyncio.run(rt.handle(context, query))
    new_pool = next(m for m in new.pushes if m.message_name == 'L2C_ActivityRewardPoolInfo')
    assert len(new_pool.values['rewardPoolInfos']) == 1


def test_rotation_watch_seeds_pool_after_activity_directory(runtime, monkeypatch):
    _, _, _, rt, now = runtime
    now[0] = activity_start(2) + 3600
    delivered = []

    class Server:
        def authenticated_player_ids(self):
            return {1}

        async def push_to_player(self, player, message):
            delivered.append(message)

    async def stop(_):
        raise asyncio.CancelledError

    monkeypatch.setattr('x2server.player.activity_runtime.asyncio.sleep', stop)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(rt.watch(Server()))
    names = [m.message_name for m in delivered]
    assert names.index('L2C_QueryActivity') < names.index('L2C_ActivityRewardPoolInfo')
    pool = next(m for m in delivered if m.message_name == 'L2C_ActivityRewardPoolInfo')
    assert pool.values['rewardPoolInfos']


def test_watch_seeds_a_fresh_connection_without_a_period_change(runtime, monkeypatch):
    _, _, _, rt, now = runtime
    now[0] = activity_start(2) + 3600
    delivered = []
    iteration = [0]

    class Server:
        def authenticated_connection_keys(self):
            return {1: ('connection-a' if iteration[0] < 2 else 'connection-b',)}

        async def push_to_player(self, player, message):
            delivered.append((iteration[0], message.message_name))

    async def advance(_):
        iteration[0] += 1
        if iteration[0] == 3:
            raise asyncio.CancelledError

    monkeypatch.setattr('x2server.player.activity_runtime.asyncio.sleep', advance)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(rt.watch(Server()))
    assert [i for i, name in delivered if name == 'L2C_ActivityRewardPoolInfo'] == [0, 2]


def test_connection_keys_ignore_closed_and_unauthenticated_connections():
    from types import SimpleNamespace
    from x2server.network.server import X2TCPServer
    server = object.__new__(X2TCPServer)
    def connection(player, closed=False):
        return SimpleNamespace(session=SimpleNamespace(player_id=player), closed=closed)
    server._connections = {'b': connection(1), 'a': connection(1),
                           'closed': connection(2, True), 'login': connection(None)}
    assert server.authenticated_connection_keys() == {1: ('a', 'b')}
