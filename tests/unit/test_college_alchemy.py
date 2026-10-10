"""炼金 (AlchemyService) 生产/交易/元素生命周期, 在隔离存档上跑真实现。

新的炼金实现在 ``x2server.player.alchemy``: 元素池落在 ``alchemy_state`` 表,
产槽落在 ``alchemy_production``, 顾客落在 ``alchemy_customers``。本文件针对它做
端到端断言 (经 Dispatcher 发原生 C2L 字节), 不再依赖被删除的旧 college_alchemy。
"""
import pytest

from tests.unit.test_college_upgrade import game, quantity, seed_elements, send
from x2server.messages.lobby import (CUSTOMER_INFO, ELEMENT, MISSION_PAIR,
                                     PRODUCTION_BAR)
from x2server.player.alchemy import advice_energy
from x2server.player.alchemy import catalog as alchemy_catalog


def test_alchemy_main_data_shape_and_customer_slots_are_distinct(game):
    """590 全量快照: 60 条配方 (未解锁 -1)、8 产槽、6 元素、5 位不重复的顾客。"""
    result = send(game, 'AlchemyMainData')
    assert result.values['code'] == 10
    assert len(result.values['recipeIdExp']) == 60
    assert len(result.values['productionBars']) == 8
    assert len(result.values['elements']) == 6
    assert len(result.values['customeres']) == 5
    assert result.values['buffType'] == 0 and result.values['buffCount'] == 0

    elements = [ELEMENT.decode(raw) for raw in result.values['elements']]
    assert [row['elementId'] for row in elements] == [991, 992, 993, 994, 995, 996]
    assert all(row['num'] == 100 for row in elements)  # 初始元素池即上限

    recipes = [MISSION_PAIR.decode(raw) for raw in result.values['recipeIdExp']]
    unlocked = [row for row in recipes if row['Value'] >= 0]
    assert len(unlocked) == 6  # 每元素仅起始 (level==1) 配方解锁, 取 0
    assert {row['Value'] for row in unlocked} == {0}

    customers = [CUSTOMER_INFO.decode(raw) for raw in result.values['customeres']]
    assert all(row['type'] == 2 and row['questId'] > 0 and row['itemId'] for row in customers)
    # 同一玩家 5 个顾客槽不重复 (param 即神格身份)。
    assert len({row['param'] for row in customers}) == 5


def test_make_item_pay_collect_marks_busy_and_replay(game):
    """594/602: 制作扣金币 + 元素 (pay + 材料), 占用返回 55, 未到时间拒收 13。"""
    store, clock, repo, service, _ = game
    seed_elements(game, 10)
    alchemy = service.alchemy_service
    gold_before = store.get(1)['snapshot']['gold']

    result = send(game, 'MakeItem', posIndex=2, recipeId=36011)
    assert result.values['code'] == 10
    bar = PRODUCTION_BAR.decode(result.values['productionBar'])
    assert bar['recipeId'] == 36011 and bar['endTime'] == clock.value + 4000
    assert bar.get('buffId', []) == []  # 无增益时空 repeated 不下发
    # 基础金币 2400 (Table) + 元素 991: pay 5, 材料 1237991×4 -> 共扣 9。
    assert store.get(1)['snapshot']['gold'] == gold_before - 2400
    assert alchemy.repo.peek(1)['element_num']['991'] == 1

    # 同一槽位再次制作 -> 55, 且不二次扣费。
    assert send(game, 'MakeItem', posIndex=2, recipeId=36011).values['code'] == 55
    assert alchemy.repo.peek(1)['element_num']['991'] == 1
    assert store.get(1)['snapshot']['gold'] == gold_before - 2400
    # 未到时间收 -> 13。
    assert send(game, 'AlchemyCollect', seq=3, posIndex=2).values['code'] == 13
    # 未知槽位 -> 13。
    assert send(game, 'AlchemyCollect', seq=3, posIndex=8).values['code'] == 13

    clock.value += 4000
    collected = send(game, 'AlchemyCollect', seq=4, posIndex=2)
    assert collected.values['code'] == 10
    assert collected.values['exp'] == 1
    assert quantity(store, 1280011) == 1
    assert alchemy.repo.production_rows(1).get(2) is None
    # 已收取的槽位 (产槽已删) 再收 -> 13, 不二次发奖。
    assert send(game, 'AlchemyCollect', seq=4, posIndex=2).values['code'] == 13
    assert quantity(store, 1280011) == 1


def test_make_item_insufficient_locked_recipe_and_out_of_range_slot(game):
    """594 校验顺序: 元素不足 22, 未解锁配方 13, 越界 13, 未知配方 29。"""
    store, _, repo, service, _ = game
    alchemy = service.alchemy_service
    before = store.get(1)['snapshot']

    seed_elements(game, 0)
    assert send(game, 'MakeItem', posIndex=0, recipeId=36011).values['code'] == 22
    seed_elements(game, 10)
    assert send(game, 'MakeItem', seq=2, posIndex=0, recipeId=36012).values['code'] == 13
    assert send(game, 'MakeItem', seq=3, posIndex=8, recipeId=36011).values['code'] == 13
    assert send(game, 'MakeItem', seq=4, posIndex=0, recipeId=99999).values['code'] == 29
    assert store.get(1)['snapshot'] == before
    assert alchemy.repo.production_rows(1) == {}
    assert alchemy.repo.peek(1)['element_num']['991'] == 10


def test_alchemy_buy_daily_limit_tier_and_cross_day_reset(game):
    """604: typeId 挡位扣金币, 日限 10, 跨天 (00:00 日界) 重置。"""
    store, clock, repo, service, _ = game
    alchemy = service.alchemy_service
    seed_elements(game, 0)
    gold_before = store.get(1)['snapshot']['gold']

    for index in range(10):
        assert send(game, 'AlchemyBuy', seq=index + 1, type=991, typeId=1).values['code'] == 10
    assert send(game, 'AlchemyBuy', seq=11, type=991, typeId=1).values['code'] == 13
    assert store.get(1)['snapshot']['gold'] == gold_before - 10 * 2000
    assert alchemy.repo.peek(1)['element_num']['991'] == 50
    assert alchemy.repo.peek(1)['element_buy_count']['991'] == 10

    # 跨天: 购买次数清零; 元素同时按 1800s/次 恢复到上限, 再买 5 仍封顶 100。
    clock.value += 86400
    assert send(game, 'AlchemyBuy', seq=12, type=991, typeId=1).values['code'] == 10
    assert alchemy.repo.peek(1)['element_buy_count']['991'] == 1
    assert alchemy.repo.peek(1)['element_num']['991'] == 100
    # 未知挡位 -> 13。
    assert send(game, 'AlchemyBuy', seq=13, type=991, typeId=9).values['code'] == 13


def test_alchemy_finish_delivery_reward_and_refusal_rotation(game):
    """598: 完成委托交付产物换奖励; 拒绝换人; 重复结算不二次发奖。"""
    store, clock, repo, service, _ = game
    main = send(game, 'AlchemyMainData')
    customer = CUSTOMER_INFO.decode(main.values['customeres'][0])
    item, count = customer['itemId'][0], customer['itemNum'][0]

    # 未持有交付物 -> 22, 且不发奖。
    assert send(game, 'AlchemyFinish', type=1, posIndex=0).values['code'] == 22

    with store.db:
        store.db.execute('INSERT OR REPLACE INTO inventory VALUES (?,?,?)', (1, item, count))
    result = send(game, 'AlchemyFinish', seq=2, type=1, posIndex=0)
    assert result.values['code'] == 10
    assert result.values['alchemyType'] == 2 and result.values['rewardData'] != b''
    assert quantity(store, item) == 0

    # 重复点「完成」: 该槽已结算, 换人后回成功但不重复发奖/扣物。
    with store.db:
        store.db.execute('INSERT OR REPLACE INTO inventory VALUES (?,?,?)', (1, item, count))
    replay = send(game, 'AlchemyFinish', seq=2, type=1, posIndex=0)
    assert replay.values['code'] == 10 and replay.values['rewardData'] == b''
    assert quantity(store, item) == count

    # 拒绝委托 (type=2): 不发奖, 顾客离场, 下次读取换一位。
    before = CUSTOMER_INFO.decode(send(game, 'AlchemyMainData', seq=3).values['customeres'][1])
    refusal = send(game, 'AlchemyFinish', seq=4, type=2, posIndex=1)
    assert refusal.values['code'] == 10 and refusal.values['type'] == 2
    assert refusal.values['rewardData'] == b''
    after = CUSTOMER_INFO.decode(send(game, 'AlchemyMainData', seq=5).values['customeres'][1])
    assert after['param'] != before['param']
    # 空槽位 (无顾客) -> 13。
    assert send(game, 'AlchemyFinish', seq=6, type=1, posIndex=5).values['code'] == 13


def test_alchemy_button_click_suggestion_costs_star_energy(game):
    """600: type==1 花星能使顾客改要建议产物; 其它 type -> 13。"""
    store, clock, repo, service, _ = game
    state = repo.load(1)
    state['star_energy'] = 50
    repo.save(1, state)
    main = send(game, 'AlchemyMainData')
    customer = CUSTOMER_INFO.decode(main.values['customeres'][0])
    recommended = customer['adviseItemId']
    recipe = next(r for r in alchemy_catalog()['recipes'].values()
                  if int(r['productId']) == recommended)
    cost = advice_energy(int(recipe['gold']))

    result = send(game, 'AlchemyButtonClick', type=1, posIndex=0)
    assert result.values['code'] == 10
    assert result.values['result'] == customer['itemId'][0]
    assert repo.load(1)['star_energy'] == 50 - cost

    changed = CUSTOMER_INFO.decode(
        send(game, 'SingleCustomerInfo', seq=2, posIndex=0).values['customere'])
    assert changed['itemId'] == [recommended]
    assert changed['adviseItemId'] == customer['itemId'][0]
    assert send(game, 'AlchemyButtonClick', seq=3, type=2, posIndex=0).values['code'] == 13


def test_alchemy_make_cancel_refunds_half(game):
    """824: 取消产槽按 cancel_refund_ratio (0.5) 退还金币/材料/元素。"""
    store, clock, repo, service, _ = game
    alchemy = service.alchemy_service
    seed_elements(game, 10)
    gold_before = store.get(1)['snapshot']['gold']

    assert send(game, 'MakeItem', posIndex=1, recipeId=36011).values['code'] == 10
    assert store.get(1)['snapshot']['gold'] == gold_before - 2400
    assert alchemy.repo.peek(1)['element_num']['991'] == 1

    result = send(game, 'AlchemyMakeCancel', seq=2, posIndex=1)
    assert result.values['code'] == 10
    # 退 50%: 金币 1200; 材料 1237991 -> 2; 元素 991 pay 5*0.5 = 2 -> 3。
    assert store.get(1)['snapshot']['gold'] == gold_before - 1200
    assert quantity(store, 1237991) == 2
    assert alchemy.repo.peek(1)['element_num']['991'] == 3
    assert alchemy.repo.production_rows(1) == {}
    # 空槽取消 -> 13。
    assert send(game, 'AlchemyMakeCancel', seq=3, posIndex=1).values['code'] == 13


def test_element_recovery_after_interval(game):
    """元素按 recoverSec=1800 / recoverNum=3 惰性恢复。"""
    store, clock, repo, service, _ = game
    alchemy = service.alchemy_service
    seed_elements(game, 0)
    send(game, 'AlchemyMainData')
    assert alchemy.repo.peek(1)['element_num']['991'] == 0
    clock.value += 1800
    send(game, 'AlchemyMainData', seq=2)
    assert alchemy.repo.peek(1)['element_num']['991'] == 3


def test_make_item_stage_failure_rolls_back_currency_elements_and_queue(game, monkeypatch):
    """落盘失败 (stage 抛错) 时经济事务回滚, 金币/元素/产槽全部还原。"""
    store, _, repo, service, _ = game
    alchemy = service.alchemy_service
    seed_elements(game, 10)
    gold_before = store.get(1)['snapshot']['gold']

    def fail(*args):
        raise RuntimeError('disk failure')

    monkeypatch.setattr(alchemy.repo, 'stage', fail)
    with pytest.raises(RuntimeError):
        send(game, 'MakeItem', posIndex=0, recipeId=36011)
    assert store.get(1)['snapshot']['gold'] == gold_before
    assert alchemy.repo.peek(1)['element_num']['991'] == 10
    assert alchemy.repo.production_rows(1) == {}
