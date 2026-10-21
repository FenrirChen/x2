import asyncio

from tests.unit.test_battle import packet, request
from tests.unit.test_economy import env
from x2server.messages.battle import CHECKOUT
from x2server.player.battle import BattleService


def enter(battle, ctx, rid):
    values = request()
    values.update(missionId=2110291, chapter=2060101, sceneId=2210191)
    result = asyncio.run(battle.enter(ctx, packet(values, rid)))
    assert result.values['result'] == 10
    return result


def compose(e, ctx, rid, fid, count=1):
    return asyncio.run(e.element_compose.compose(ctx, packet(
        {'elementID': fid, 'count': count}, rid, 'C2L_ElementCompose')))


def checkout(battle, ctx, success, rid=20):
    return asyncio.run(battle.checkout(ctx, packet({'checkout': CHECKOUT.encode({
        'sectionId': 2110291, 'chapterId': 2060101,
        'success': success, 'fightTime': 120})}, rid, 'C2L_CheckoutMainMissionSign')))


def inventory(store, player_id=1):
    return {row[0]: row[1] for row in store.db.execute(
        'SELECT item_id,quantity FROM inventory WHERE player_id=?', (player_id,))}


def test_composed_products_are_delivered_on_clear(env):
    """合成产物被客户端标成 source=COMPOSE, outsideItems 里没有它们, 结算补发."""
    store, e, ctx = env
    battle = BattleService(store, e)
    enter(battle, ctx, 1)
    # 420501 -> 1202013 因果收集卡(超大), useScene=1
    assert compose(e, ctx, 10, 420501).values['code'] == 10
    # 420502 -> 1101051 30点光能, E_ReportCurrency 代理 -> 账号光能 1237913 x30
    assert compose(e, ctx, 11, 420502).values['code'] == 10
    # 420508 -> 1002018 攻击药剂, useScene=0 局内专用, 带不出去
    assert compose(e, ctx, 12, 420508).values['code'] == 10
    before = inventory(store)
    result = checkout(battle, ctx, True, 13)
    assert result.values['result'] == 10
    after = inventory(store)
    assert after.get(1202013, 0) - before.get(1202013, 0) == 1
    assert after.get(1237913, 0) - before.get(1237913, 0) >= 30
    assert after.get(1002018, 0) == before.get(1002018, 0)
    replay = checkout(battle, ctx, True, 13)
    assert replay.values == result.values
    assert inventory(store) == after


def test_composed_products_are_not_delivered_on_failure(env):
    store, e, ctx = env
    battle = BattleService(store, e)
    enter(battle, ctx, 1)
    assert compose(e, ctx, 10, 420501).values['code'] == 10
    before = inventory(store)
    result = checkout(battle, ctx, False, 11)
    assert result.values['result'] == 10
    after = inventory(store)
    assert after.get(1202013, 0) == before.get(1202013, 0)
