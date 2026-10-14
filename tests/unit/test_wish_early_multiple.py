import asyncio
from tests.unit.test_economy import env
from tests.unit.test_battle import packet
from x2server.player.wish import WishService
from x2server.player.server_clock import ServerClock
from x2server.messages.economy import REWARD, REWARD_ITEM


def test_early_multiple_top_heroes_remain_individual_slots(env, monkeypatch):
    store, e, context = env
    player = store.get(1)
    store.save_snapshot(1, dict(player['snapshot'], crystal=1800), player['revision'])
    s = WishService(store, e, clock=ServerClock(lambda: s.ANCHOR + 1))
    store.db.execute("INSERT INTO wish_pity VALUES (1,'standard',0,0,0)")
    prizes = iter([1211012, 1211012] + [1201006] * 8)
    groups = []
    def pick(pool, group='common'):
        groups.append(group)
        return {'item_id': next(prizes), 'quantity': 1}
    monkeypatch.setattr(s, '_pick', pick)
    req = packet({'drawnId': 22203, 'drawType': 1}, 1, 'C2L_LuckDraw')
    result = asyncio.run(s.draw(context, req))
    assert result.values['code'] == 10
    rows = [REWARD_ITEM.decode(x) for x in REWARD.decode(result.values['rewardData'])['rewardItem']]
    assert len(rows) == 10 and [r['itemId'] for r in rows[:2]] == [1211012, 1211012]
    assert [r['transform'] for r in rows[:2]] == [False, True]
    assert groups == ['common'] * 10
    assert s.state(1, 22203)[4] == 8
    assert asyncio.run(s.draw(context, req)).values == result.values
