"""PR integration: native fields, transaction rollback and durable resumption."""
import asyncio
from datetime import datetime, timedelta, timezone

from tests.unit.test_economy import env, rewards
from tests.unit.test_battle import packet, request
from tests.unit.test_restored_shops_favor import listing, buy, fund
from x2server.messages.core import HERO_DATA, INT_PAIR
from x2server.messages.battle import FIGHT_PROFILE
from x2server.messages.economy import REWARD
from x2server.messages.equipment import HERO_EQUIP
from x2server.player.appearance import AppearanceService
from x2server.player.hero import encode_hero_data
from x2server.player.battle import BattleService
from x2server.player.economy import EconomyService
from x2server.player.gift_packages import GiftPackageService
from x2server.player.shop import ShopService
from tests.unit.test_gift_package_free_daily import cell


def test_favorite_owned_hero_roundtrip_and_rejection(env):
    store, e, ctx = env
    service = AppearanceService(store, e)
    for opt, enjoy in [(5, 1), (5, 1), (6, 0)]:
        response = asyncio.run(service.handle(ctx, packet(
            {'opt': opt, 'values': [1003]}, 100 + opt, 'C2L_Account')))
        assert response.values == {'result': 10, 'opt': opt}
        assert response.before_response[0].message_name == 'L2C_HeroUpdate'
        assert HERO_DATA.decode(response.before_response[0].values['heros'][0])['Enjoy'] == enjoy
        snapshot = store.get(1)['snapshot']
        assert HERO_DATA.decode(encode_hero_data(snapshot['heroes'][0]))['Enjoy'] == enjoy
        for values in [[], [9999], [1003, 1004]]:
            bad = asyncio.run(service.handle(ctx, packet(
                {'opt': opt, 'values': values}, 200, 'C2L_Account')))
            assert bad.values['result'] == 13 and not bad.before_response
            assert store.get(1)['snapshot'] == snapshot
    p = store.get(1)
    p['snapshot']['heroes'].append({'id': 1004, 'state': 1, 'level': 1, 'star': 1})
    store.save_snapshot(1, p['snapshot'], p['revision'])
    bad = asyncio.run(service.handle(ctx, packet(
        {'opt': 5, 'values': [1004]}, 300, 'C2L_Account')))
    assert bad.values['result'] == 13


def test_element_profile_persists_across_save_resume_without_doubling(env):
    store, e, ctx = env
    battle = BattleService(store, e)
    values = request()
    values.update(missionId=2110291, chapter=2060101, sceneId=2210191)
    entered = asyncio.run(battle.enter(ctx, packet(values)))
    assert entered.values['result'] == 10
    compose = packet({'elementID': 420501, 'count': 1}, 10, 'C2L_ElementCompose')
    assert asyncio.run(e.element_compose.compose(ctx, compose)).values['code'] == 10
    assert asyncio.run(e.element_compose.compose(ctx, compose)).values['code'] == 10
    drop = packet({'missionId': 2110291, 'chapterId': 2060101, 'sceneId': 2210191,
                   'layer': 3, 'fightTime': 25}, 11, 'C2L_FightDropData')
    assert asyncio.run(battle.drop_data(ctx, drop)).values['result'] == 10
    raw = store.db.execute('SELECT profile FROM endless_profiles WHERE player_id=1').fetchone()[0]
    profile = FIGHT_PROFILE.decode(raw)
    assert profile['elementExp'] == 30
    assert [INT_PAIR.decode(r) for r in profile['formulaCompose']] == [{'Key': 420501, 'Value': 1}]
    rebuilt = EconomyService(store)
    resumed_battle = BattleService(store, rebuilt)
    values['isFromProfile'] = True
    response = asyncio.run(resumed_battle.enter(ctx, packet(values, 12)))
    assert response.values['result'] == 10 and response.values['uuid'] == entered.values['uuid']
    resumed = FIGHT_PROFILE.decode(response.values['fightDataProfile'])
    assert resumed['elementExp'] == 30 and resumed['formulaCompose'] == profile['formulaCompose']
    assert asyncio.run(resumed_battle.drop_data(ctx, drop)).values['result'] == 10
    saved = FIGHT_PROFILE.decode(store.db.execute('SELECT profile FROM endless_profiles WHERE player_id=1').fetchone()[0])
    assert saved['elementExp'] == 30 and saved['formulaCompose'] == profile['formulaCompose']


def test_club_native_prices_quota_revision_and_exact_debit(env):
    store, e, ctx = env
    service = ShopService(store, e)
    week = service._period(2)
    with store.db:
        for gid in [1915101, 1915401]:
            store.db.execute('INSERT INTO shop_compat_counts VALUES (1,807,?,?,?)',
                             (gid, week + ':club-items-20261016', 10))
    goods = {g['goodsId']: g for g in listing(service, ctx, 807)}
    assert (goods[1915101]['itemId'], goods[1915101]['price']) == (1203001, 50)
    assert (goods[1915401]['itemId'], goods[1915401]['price']) == (1203023, 1200)
    assert all(goods[g]['hasBuyTimes'] == 0 for g in [1915101, 1915401])
    fund(store, 1237924, 2450)
    for gid, quantity, cost, item in [(1915101, 1, 50, 1203001), (1915401, 2, 2400, 1203023)]:
        response = buy(service, ctx, 807, gid, quantity, gid)
        assert response.values['code'] == 10
        assert response.values['itemNum'] == quantity
        if item == 1203023:
            # 6★随机兽主 is an E_AutoUsed receipt (client Item: FunctionEff 7, no Used),
            # so the purchase must open it on the spot: one 6★ instance per copy and no
            # dead receipt left in the bag. Parking the receipt is the bug this fixes.
            assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?',
                                    (item,)).fetchone() is None
            equips = REWARD.decode(response.values['rewardData'])['rewardEquip']
            assert len(equips) == quantity
            assert all(HERO_EQUIP.decode(raw)['star'] == 6 for raw in equips)
        else:
            assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?', (item,)).fetchone()[0] == quantity
        assert buy(service, ctx, 807, gid, quantity, gid).values == response.values
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237924').fetchone()[0] == 0
    assert buy(service, ctx, 807, 1915401, 1, 301).values['code'] == 13
    fund(store, 1237924, 49)
    assert buy(service, ctx, 807, 1915101, 1, 302).values['code'] == 13
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237924').fetchone()[0] == 49
    goods = {g['goodsId']: g for g in listing(ShopService(store, e), ctx, 807)}
    assert goods[1915101]['hasBuyTimes'] == 1 and goods[1915401]['hasBuyTimes'] == 2


def test_daily_midnight_old_claims_missing_days_replay_and_failure_rollback(env, monkeypatch):
    store, e, ctx = env
    zone = timezone(timedelta(hours=8))
    now = [int(datetime(2026, 10, 17, 23, 59, 59, tzinfo=zone).timestamp())]
    e.clock = lambda: now[0]
    service = GiftPackageService(store, e)
    with store.db:
        for day in range(1, 6):
            store.db.execute('INSERT INTO gift_package_claims VALUES (1,2700000,?,?)',
                             (f'2026-10-{day:02}', now[0] - (17-day)*86400))
    assert cell(service)['PurchaseTime'] == 5 and cell(service)['state'] == 0
    claim = packet({'giftPackageID': 2700000, 'num': 1}, 700, 'C2L_BuyGiftPackage')
    response = asyncio.run(service.buy(ctx, claim))
    assert response.values['code'] == 10
    assert 1237925 not in rewards(response.values['rewardData'])
    snapshot = store.get(1)['snapshot']
    assert asyncio.run(service.buy(ctx, claim)).values == response.values
    assert store.get(1)['snapshot'] == snapshot
    now[0] += 1
    service = GiftPackageService(store, e)
    assert cell(service)['PurchaseTime'] == 6 and cell(service)['state'] == 0
    # A missing seventh-day gift must not consume today's claim or advance progress.
    monkeypatch.delitem(service.gifts, 781005)
    claim = packet({'giftPackageID': 2700000, 'num': 1}, 701, 'C2L_BuyGiftPackage')
    assert asyncio.run(service.buy(ctx, claim)).values['code'] == 13
    assert cell(service)['PurchaseTime'] == 6 and cell(service)['state'] == 0
    assert store.get(1)['snapshot'] == snapshot
    service = GiftPackageService(store, e)
    response = asyncio.run(service.buy(ctx, claim))
    assert response.values['code'] == 10
    assert rewards(response.values['rewardData']) == {1237925: 1}
    assert cell(service)['PurchaseTime'] == 7 and cell(service)['state'] == 1
