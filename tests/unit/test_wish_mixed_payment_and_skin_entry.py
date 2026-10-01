import asyncio
import logging

import pytest

from tests.unit.test_battle import packet, request
from tests.unit.test_economy import env  # noqa: F401
from x2server.messages.battle import FIGHT_DATA, FIGHT_HERO
from x2server.messages.core import BASE_INFO
from x2server.messages.economy import ITEM, REWARD
from x2server.player.appearance import AppearanceService
from x2server.player.battle import BattleService
from x2server.player.economy import EconomyService
from x2server.player.store import PlayerStore
from x2server.player.server_clock import ServerClock
from x2server.player.wish import WishService


def funds(store, tickets, light, crystal):
    with store.db:
        store.db.executemany('INSERT INTO inventory VALUES (1,?,?)',
            [(1237914, tickets), (1237913, light)])
    p = store.get(1)
    store.save_snapshot(1, dict(p['snapshot'], crystal=crystal), p['revision'])


def draw(wish, ctx):
    return asyncio.run(wish.draw(ctx, packet({'drawnId': 22203, 'drawType': 1}, name='C2L_LuckDraw')))


@pytest.mark.parametrize('tickets,light,crystal,left', [
    (5, 1500, 999, (0, 0, 999)),
    (4, 1200, 360, (0, 0, 0)),
    (3, 1250, 600, (0, 50, 60)),
    (12, 3000, 1800, (2, 3000, 1800)),
    (0, 3000, 0, (0, 0, 0)),
])
def test_mixed_draw_spends_in_client_order_and_replay_syncs_without_spending(env, monkeypatch,
        tickets, light, crystal, left):
    store, economy, ctx = env
    wish = WishService(store, economy, clock=ServerClock(lambda: WishService.ANCHOR + 1))
    funds(store, tickets, light, crystal)
    monkeypatch.setattr(wish, '_pick', lambda *a: {'item_id': 1201006, 'quantity': 1})
    answer = draw(wish, ctx)
    assert answer.values['code'] == 10
    assert len(REWARD.decode(answer.values['rewardData'])['rewardItem']) == 10
    quantities = dict(store.db.execute('SELECT item_id,quantity FROM inventory WHERE player_id=1'))
    assert (quantities[1237914], quantities[1237913], store.get(1)['snapshot']['crystal']) == left
    assert BASE_INFO.decode(answer.pushes[0].values['BaseInfo'])['VowOfCoin'] == left[0]
    assert BASE_INFO.decode(answer.pushes[0].values['BaseInfo'])['PowerOfLight'] == left[1]
    replay = draw(wish, ctx)
    assert replay.values == answer.values
    assert [p.message_name for p in replay.pushes] == ['PlayerDataProto', 'L2C_ItemAll']
    assert store.db.execute('SELECT quantity FROM inventory WHERE item_id=1201006').fetchone()[0] == 10
    assert dict(store.db.execute('SELECT item_id,quantity FROM inventory WHERE player_id=1')) == quantities
    assert store.db.execute('SELECT COUNT(*) FROM wish_receipts').fetchone()[0] == 1


def test_insufficient_mixed_funds_do_not_partially_spend_and_refresh_client(env, caplog):
    store, economy, ctx = env
    wish = WishService(store, economy, clock=ServerClock(lambda: WishService.ANCHOR + 1))
    funds(store, 4, 1499, 180)
    before = '\n'.join(store.db.iterdump())
    with caplog.at_level(logging.INFO, logger='x2.wish'):
        answer = draw(wish, ctx)
    assert answer.values['code'] == 13
    assert 'reason=insufficient_resources' in caplog.text and 'missing_draws' in caplog.text
    assert '\n'.join(store.db.iterdump()) == before
    assert [p.message_name for p in answer.pushes] == ['PlayerDataProto', 'L2C_ItemAll', 'L2C_CardPool']
    balance = BASE_INFO.decode(answer.pushes[0].values['BaseInfo'])
    assert (balance['VowOfCoin'], balance['PowerOfLight'], balance['Crystal']) == (4, 1499, 180)
    items = {ITEM.decode(raw)['id']: ITEM.decode(raw)['num'] for raw in answer.pushes[1].values['items']}
    assert items[1237914] == 4 and items[1237913] == 1499


def test_query_resyncs_resources_before_card_pool_ui(env):
    store, economy, ctx = env
    wish = WishService(store, economy)
    funds(store, 0, 0, 0)
    answer = asyncio.run(wish.query(ctx, packet({'drawPos': 1}, name='C2L_CardPool')))
    assert [p.message_name for p in answer.before_response] == ['PlayerDataProto', 'L2C_ItemAll']
    balance = BASE_INFO.decode(answer.before_response[0].values['BaseInfo'])
    assert balance['VowOfCoin'] == balance['PowerOfLight'] == balance['Crystal'] == 0


def test_worn_battle_skin_survives_restart_and_is_serialized_into_entry(env, caplog, monkeypatch):
    store, economy, ctx = env
    appearance = AppearanceService(store, economy)
    with store.db:
        store.db.execute('INSERT INTO inventory VALUES (1,1220303,1)')
    with caplog.at_level(logging.INFO):
        answer = asyncio.run(appearance.handle(ctx, packet(
            {'heroId': 1003, 'skinId': 1220303, 'type': 1}, name='C2L_HeroWearSkin')))
    assert answer.values['code'] == 10
    assert 'skin wear saved player=1 hero=1003 skin=1220303 type=1' in caplog.text
    # Outer skin is independently chosen and must not replace the battle skin.
    asyncio.run(appearance.handle(ctx, packet(
        {'heroId': 1003, 'skinId': 1220301, 'type': 2}, name='C2L_HeroWearSkin')))
    path = store.path
    store.close()
    reopened = PlayerStore(path)
    try:
        economy = EconomyService(reopened)
        monkeypatch.setenv('X2_PUBLIC_HOST', 'fenrirchen.com')
        with caplog.at_level(logging.INFO):
            entry = asyncio.run(BattleService(reopened, economy).enter(ctx, packet(request())))
        hero = FIGHT_HERO.decode(FIGHT_DATA.decode(entry.values['data'])['fightHeros'][0])
        assert hero['battleSkinId'] == 1220303
        assert 'battleSkinId=1220303' in caplog.text
        assert str(path.resolve()) in caplog.text
    finally:
        reopened.close()
