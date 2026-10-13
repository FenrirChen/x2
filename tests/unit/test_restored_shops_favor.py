import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from tests.unit.test_economy import env, checkout
from tests.unit.test_battle import packet, request
from tests.unit.test_activity_runtime import runtime
from x2server.messages.economy import GOODS, REWARD, REWARD_ITEM
from x2server.player.shop import ShopService
from x2server.player.battle import BattleService
from x2server.player.system_mail import deliver_player_gift, insert_system_mail
from x2server.player.activity_rotation import ActivityRotation
from tests.activity_calendar_helpers import activity_start


def listing(service, ctx, sid):
    result = asyncio.run(service.handle(ctx, packet({'shopId': sid}, name='C2L_ShopGoods')))
    assert result.values['code'] == 10
    return [GOODS.decode(b) for b in result.values['goods']]


def buy(service, ctx, sid, gid, quantity=1, rid=100):
    return asyncio.run(service.handle(ctx, packet({'shopId': sid, 'goodsId': gid,
        'buyNum': quantity}, rid, 'C2L_BuyGoods')))


def fund(store, item, amount=10000):
    with store.db:
        store.db.execute('INSERT INTO inventory VALUES (1,?,?) ON CONFLICT(player_id,item_id) DO UPDATE SET quantity=excluded.quantity', (item, amount))


def test_ticket_daily_hero_weekly_shared_quota_and_monday_midnight(env):
    store, e, ctx = env
    now = [int(datetime(2026, 10, 18, 23, 59, tzinfo=timezone(timedelta(hours=8))).timestamp())]
    e.clock = lambda: now[0]
    service = ShopService(store, e)
    fund(store, 1237915)
    first = listing(service, ctx, 805)
    hero = next(x for x in first if x['goodsId'] == 1905101)
    assert hero['itemId'] not in {1211024, 1211039, 1211040}
    paid = buy(service, ctx, 805, 1905101)
    assert paid.values['code'] == 10
    hid = hero['itemId'] - 1210000
    assert next(h for h in store.get(1)['snapshot']['heroes'] if h['id'] == hid)['star'] == 5
    assert buy(service, ctx, 805, 1905101).values == paid.values
    assert buy(service, ctx, 805, 1905101, rid=101).values['code'] == 13
    now[0] += 120  # Monday 00:01 resets quota.
    second = next(x for x in listing(service, ctx, 805) if x['goodsId'] == 1905101)
    assert second['itemId'] != hero['itemId'] and second['hasBuyTimes'] == 0
    assert buy(service, ctx, 805, 1905101, rid=102).values['code'] == 10
    now[0] += 86400
    assert next(x for x in listing(service, ctx, 805) if x['goodsId'] == 1905101)['hasBuyTimes'] == 1
    assert buy(service, ctx, 805, 1905101, rid=103).values['code'] == 13
    assert buy(service, ctx, 805, 1905201, rid=104).values['code'] == 10


def test_ticket_five_rounds_exact_batch_cost_hidden_future_and_replay(env):
    store, e, ctx = env
    service = ShopService(store, e)
    fund(store, 1237915, 258)
    assert buy(service, ctx, 805, 1905305).values['code'] == 13
    for index, (num, cost) in enumerate([(1, 10), (2, 18), (5, 40), (10, 70), (20, 120)]):
        gid = 1905301 + index
        rounds = [x for x in listing(service, ctx, 805) if 1905301 <= x['goodsId'] <= 1905305]
        assert [(x['goodsId'], x['num'], x['price']) for x in rounds] == [(gid, num, cost)]
        assert buy(service, ctx, 805, gid, quantity=2, rid=200 + index).values['code'] == 13
        result = buy(service, ctx, 805, gid, rid=300 + index)
        assert result.values['code'] == 10 and result.values['itemNum'] == num
        assert buy(service, ctx, 805, gid, rid=300 + index).values == result.values
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237915').fetchone()[0] == 0
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237914').fetchone()[0] == 38
    assert not [x for x in listing(service, ctx, 805) if 1905301 <= x['goodsId'] <= 1905305]


@pytest.mark.parametrize('sid,currency,size', [(803, 1237918, 12), (806, 1237905, 17)])
def test_catalog_debit_delivery_limit_and_rejection_rollback(env, sid, currency, size):
    store, e, ctx = env
    service = ShopService(store, e)
    fund(store, currency, 1000000)
    fund(store, 1237904, 1000000)
    goods = listing(service, ctx, sid)
    assert len(goods) == size
    for index, good in enumerate(goods):
        limit = good['canBuyTimes']
        result = buy(service, ctx, sid, good['goodsId'], quantity=limit, rid=400 + index)
        assert result.values['code'] == 10, (good, result.values)
        assert result.values['itemNum'] == limit * good['num']
        before = store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?', (result.values['changeItemID'],)).fetchone()[0]
        assert buy(service, ctx, sid, good['goodsId'], rid=500 + index).values['code'] == 13
        assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?', (result.values['changeItemID'],)).fetchone()[0] == before


def test_battle_favor_persisted_from_authoritative_team_replay_does_not_double(env):
    store, e, ctx = env
    service = BattleService(store, e)
    assert asyncio.run(service.enter(ctx, packet(request()))).values['result'] == 10
    result = asyncio.run(service.checkout(ctx, checkout()))
    assert result.values['result'] == 10
    assert result.values['heroFavorExp'] == [1]
    assert result.values['heroAddFavorExp'] == [1]
    assert store.get(1)['snapshot']['heroes'][0]['favor']['exp'] == 1
    assert asyncio.run(service.checkout(ctx, checkout())).values == result.values
    assert store.get(1)['snapshot']['heroes'][0]['favor']['exp'] == 1


def test_failed_battle_has_no_favor(env):
    store, e, ctx = env
    service = BattleService(store, e)
    assert asyncio.run(service.enter(ctx, packet(request()))).values['result'] == 10
    result = asyncio.run(service.checkout(ctx, checkout(False)))
    assert result.values['result'] == 10 and result.values['heroAddFavorExp'] == [0]


def test_favor_failure_rolls_back_entire_battle_settlement(env, monkeypatch):
    store, e, ctx = env
    service = BattleService(store, e)
    assert asyncio.run(service.enter(ctx, packet(request()))).values['result'] == 10
    before = store.get(1)
    def fail(*args):
        raise RuntimeError('injected favor persistence failure')
    monkeypatch.setattr(service.favor_service, 'battle', fail)
    with pytest.raises(RuntimeError, match='injected'):
        asyncio.run(service.checkout(ctx, checkout()))
    assert store.get(1) == before
    assert store.db.execute('SELECT count(*) FROM battle_receipts').fetchone()[0] == 0
    assert store.db.execute('SELECT settled FROM economy_runs').fetchone()[0] == 0
    assert store.db.execute('SELECT count(*) FROM economy_clears').fetchone()[0] == 0


def test_favor_only_bound_owned_team_and_trial_exclusion(env):
    store, e, _ = env
    service = BattleService(store, e).favor_service
    with e.transaction():
        snapshot = store.get(1)['snapshot']
        snapshot['heroes'].append({'id': 1004, 'state': 2, 'level': 1, 'star': 5})
        e.save_snapshot(1, snapshot)
        for key, team in [('regular', [1003, 1199]), ('trial', [1303]), ('normal-ch7', [1003, 1004])]:
            store.db.execute('INSERT INTO battle_entries(player_id,request_key,uuid,created_at,response,team_json) VALUES (1,?,?,0,?,?)',
                             (key, key, b'', json.dumps(team)))
        assert service.battle(1, 'regular', 2110801) == {1003: 1}
        assert service.battle(1, 'trial', 2110607) == {}
        normal = service.battle(1, 'normal-ch7', 2110607)
        assert set(normal) == {1003, 1004} and all(x > 0 for x in normal.values())


@pytest.mark.parametrize('theme', [0, 5])
def test_cafe_upgrade_only_spends_store_exp_all_shop_types(runtime, theme):
    store, e, ctx, rt, now = runtime
    now[0] = activity_start(theme) + 3600
    period = rt.a.period(1)
    food = rt.r.of_type(27, period)
    for kind in food['ActivityParam1']:
        _, _, state = rt.cafe.context(1, kind)
        cost = rt.cafe.levels[kind, 1]['Exp']
        state.update(unlocked=True, exp=cost)
        with e.transaction():
            rt.cafe.save(1, period, kind, state)
        result = asyncio.run(rt.handle(ctx, packet({'storeType': kind}, 600 + kind, 'C2L_CafeStoreLevelUp')))
        assert result.values['code'] == 10 and result.values['level'] == 2 and result.values['exp'] == 0
        assert asyncio.run(rt.handle(ctx, packet({'storeType': kind}, 600 + kind, 'C2L_CafeStoreLevelUp'))).values == result.values
        assert asyncio.run(rt.handle(ctx, packet({'storeType': kind}, 700 + kind, 'C2L_CafeStoreLevelUp'))).values['code'] == 13


def test_new_once_mail_backfill_delete_restart_and_history_blocks_reissue(env):
    store, _, _ = env
    assert deliver_player_gift(store, 1, 'causality_oct13') == (1, [])
    row = store.db.execute("SELECT attachments FROM player_mail WHERE source_key LIKE 'causality_gift_20261013_50:%'").fetchone()
    assert json.loads(row[0]) == {'1202014': 50}
    with store.db:
        store.db.execute("DELETE FROM player_mail WHERE source_key LIKE 'causality_gift_20261013_50:%'")
    assert deliver_player_gift(store, 2, 'causality_oct13') == (0, [])
