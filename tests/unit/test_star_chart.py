import asyncio
from pathlib import Path

import pytest

from tests.unit.test_economy import env
from tests.unit.test_battle import packet, request
from x2server.messages.core import PLAYER_DATA, BASE_INFO
from x2server.messages.star_chart import STAR_MAP, STAR_PAIR, STAR_DAILY
from x2server.messages.battle import CHECKOUT, FIGHT_DATA, DROP_DATA, OUTSIDE_ITEM
from x2server.player.star_chart import StarChartService, catalog, state, unlocked
from x2server.player.login import LoginService
from x2server.player.battle import BattleService
from x2server.player.store import PlayerStore
from x2server.player.economy import EconomyService


def seed(store, economy, abilities=(39000,), gold=100000, points=100):
    p = store.get(1)
    economy.save_snapshot(1, {**p['snapshot'], 'gold': gold})
    for row in catalog()['abilities']:
        if row['ID'] in abilities:
            store.db.execute('INSERT OR IGNORE INTO economy_clears VALUES (1,?,?)',
                             (row['unlock_section'], 'test'))
    for item in (1237916, 1237922):
        store.db.execute('INSERT OR REPLACE INTO inventory VALUES (1,?,?)', (item, points))
    store.db.commit()


def send(service, ctx, name, values=None, rid=1):
    return asyncio.run(service.handle(ctx, packet(values or {}, rid, name)))


def test_locked_new_account_and_explicit_wire_defaults(env):
    store, economy, ctx = env
    service = StarChartService(store, economy)
    push = LoginService.snapshot_push(store.get(1), store)
    wire = PLAYER_DATA.decode(PLAYER_DATA.encode(push.values))
    assert STAR_MAP.decode(wire['StarMap']) == {'AIPoint': 0}
    assert STAR_DAILY.decode(wire['Daily']) == {'AddAIPointCount': 0}
    assert BASE_INFO.decode(wire['BaseInfo'])['AIPointAutoAdd'] == 0
    assert send(service, ctx, 'C2L_StarSkillUp', {'skillID': 390001, 'targetLevel': 1}).values['code'] == 13
    assert send(service, ctx, 'C2L_AddAIPoint').values['code'] == 13
    assert send(service, ctx, 'C2L_AutoAddAIPoint', {'open': True}).values['code'] == 13


def test_upgrade_atomic_cost_replay_push_order_and_relogin(env):
    store, economy, ctx = env
    seed(store, economy)
    service = StarChartService(store, economy)
    values = {'skillID': 390001, 'targetLevel': 1}
    result = send(service, ctx, 'C2L_StarSkillUp', values)
    assert result.values == {'code': 10, **values}
    assert result.before_response[0].message_name == 'PlayerDataProto'
    skills = {r['Key']: r['Value'] for r in map(STAR_PAIR.decode,
        STAR_MAP.decode(result.before_response[0].values['StarMap'])['StarSkill'])}
    assert skills[390001] == 1
    assert store.get(1)['snapshot']['gold'] == 99000
    assert store.db.execute('SELECT quantity FROM inventory WHERE item_id=1237916').fetchone()[0] == 99
    assert send(service, ctx, 'C2L_StarSkillUp', values).values == result.values
    assert send(service, ctx, 'C2L_StarSkillUp', values, rid=2).values['code'] == 13
    assert store.get(1)['snapshot']['gold'] == 99000
    other = PlayerStore(Path(store.path))
    try:
        assert other.get(1)['snapshot']['star_chart']['skills']['390001'] == 1
        assert unlocked(other, 1) == {39000}
    finally:
        other.close()


@pytest.mark.parametrize('skill,target', [(390001, 2), (390001, -1), (390001, 99),
    (392001, 1), (392004, 1), (391001, 1), (999, 1)])
def test_invalid_skill_target_and_orphans_never_spend(env, skill, target):
    store, economy, ctx = env
    seed(store, economy)
    service = StarChartService(store, economy)
    assert send(service, ctx, 'C2L_StarSkillUp', {'skillID': skill, 'targetLevel': target}).values['code'] == 13
    assert store.get(1)['snapshot']['gold'] == 100000
    assert store.db.execute('SELECT quantity FROM inventory WHERE item_id=1237916').fetchone()[0] == 100


def test_insufficient_cost_rolls_back_and_max_level(env):
    store, economy, ctx = env
    seed(store, economy, gold=999)
    service = StarChartService(store, economy)
    assert send(service, ctx, 'C2L_StarSkillUp', {'skillID': 390001, 'targetLevel': 1}).values['code'] == 13
    assert store.db.execute('SELECT quantity FROM inventory WHERE item_id=1237916').fetchone()[0] == 100
    seed(store, economy)
    for level in range(1, 6):
        assert send(service, ctx, 'C2L_StarSkillUp', {'skillID': 390001, 'targetLevel': level}, rid=level).values['code'] == 10
    assert send(service, ctx, 'C2L_StarSkillUp', {'skillID': 390001, 'targetLevel': 6}, rid=6).values['code'] == 13
    assert store.get(1)['snapshot']['gold'] == 85000


def test_ai_charge_capacity_cost_daily_reset_and_feature(env):
    store, economy, ctx = env
    seed(store, economy, (39400,))
    service = StarChartService(store, economy)
    now = [1790812800]
    economy.clock = lambda: now[0]
    result = send(service, ctx, 'C2L_AddAIPoint')
    assert result.values == {'code': 10, 'AIPoint': 100, 'AddAIPointCount': 1}
    assert send(service, ctx, 'C2L_AddAIPoint').values == result.values
    assert send(service, ctx, 'C2L_AddAIPoint', rid=2).values['AIPoint'] == 150
    assert send(service, ctx, 'C2L_AddAIPoint', rid=3).values['code'] == 13
    assert store.db.execute('SELECT quantity FROM inventory WHERE item_id=1237922').fetchone()[0] == 70
    assert send(service, ctx, 'C2L_AutoAddAIPoint', {'open': True}).values['code'] == 13
    assert send(service, ctx, 'C2L_StarSkillUp', {'skillID': 394005, 'targetLevel': 1}).values['code'] == 10
    assert send(service, ctx, 'C2L_AutoAddAIPoint', {'open': True}, rid=2).values['code'] == 10
    now[0] += 86400
    snapshot = store.get(1)['snapshot']
    assert state(snapshot, now[0])['charge_count'] == 0
    assert state(snapshot, now[0])['points'] == 150
    push = economy.pushes(1)[0]
    assert STAR_DAILY.decode(push.values['Daily'])['AddAIPointCount'] == 0
    assert BASE_INFO.decode(push.values['BaseInfo'])['AIPointAutoAdd'] == 1


def test_training_gate_budget_checkout_and_no_rewards(env):
    store, economy, ctx = env
    battle = BattleService(store, economy)
    values = request()
    values.update(missionId=2119900, chapter=2019900, sceneId=2219900)
    assert asyncio.run(battle.enter(ctx, packet(values))).values['result'] == 13
    seed(store, economy, (39100,))
    entered = asyncio.run(battle.enter(ctx, packet(values)))
    assert entered.values['result'] == 10
    drop = DROP_DATA.decode(FIGHT_DATA.decode(entered.values['data'])['dropData'])
    assert not any(drop['dropValues'])
    before = store.get(1)['snapshot']
    checkout = packet({'checkout': CHECKOUT.encode({'chapterId': 2019900, 'sectionId': 2119900,
        'success': True, 'fightTime': 1, 'outsideItems': [OUTSIDE_ITEM.encode({'id': 1237901, 'num': 10000})],
        'mazeItems': [OUTSIDE_ITEM.encode({'id': 1004943, 'num': 1})]})}, name='C2L_CheckoutMainMissionSign')
    result = asyncio.run(battle.checkout(ctx, checkout))
    assert result.values['result'] == 10
    assert asyncio.run(battle.checkout(ctx, checkout)).values == result.values
    assert store.get(1)['snapshot']['gold'] == before['gold']
    assert not store.db.execute('SELECT 1 FROM inventory WHERE item_id=1004943').fetchone()
    assert not store.db.execute('SELECT 1 FROM economy_clears WHERE section_id=2119900').fetchone()
    values.update(missionId=2119903, sceneId=2219903)
    assert asyncio.run(battle.enter(ctx, packet(values, 2))).values['result'] == 13


def test_ai_daily_limit_and_discount_use_skill_parameters(env):
    store, economy, ctx = env
    seed(store, economy, (39400,))
    service = StarChartService(store, economy)
    # Drain after each charge to distinguish daily limits from capacity limits.
    for rid in range(1, 4):
        assert send(service, ctx, 'C2L_AddAIPoint', rid=rid).values['code'] == 10
        snapshot = store.get(1)['snapshot']
        snapshot['star_chart']['points'] = 0
        economy.save_snapshot(1, snapshot)
        store.db.commit()
    assert send(service, ctx, 'C2L_AddAIPoint', rid=4).values['code'] == 13
    assert store.db.execute('SELECT quantity FROM inventory WHERE item_id=1237922').fetchone()[0] == 40
    assert send(service, ctx, 'C2L_StarSkillUp', {'skillID': 394001, 'targetLevel': 1}, rid=5).values['code'] == 10
    assert send(service, ctx, 'C2L_StarSkillUp', {'skillID': 394002, 'targetLevel': 1}, rid=6).values['code'] == 10
    assert send(service, ctx, 'C2L_AddAIPoint', rid=7).values['code'] == 10
    assert store.db.execute('SELECT quantity FROM inventory WHERE item_id=1237922').fetchone()[0] == 12


def test_ai_battle_consumption_and_receipt_replay(env):
    store, economy, ctx = env
    seed(store, economy, (39400,))
    service = StarChartService(store, economy)
    assert send(service, ctx, 'C2L_AddAIPoint').values['code'] == 10
    store.db.execute('INSERT INTO economy_clears VALUES (1,2110851,?)', ('test',))
    store.db.commit()
    battle = BattleService(store, economy)
    values = request(useAIPoint=True)
    values.update(missionId=2110851, sceneId=2210851, expertMode=True)
    entered = asyncio.run(battle.enter(ctx, packet(values)))
    assert entered.values['result'] == 10
    assert store.get(1)['snapshot']['star_chart']['points'] == 85
    assert asyncio.run(battle.enter(ctx, packet(values))).values == entered.values
    assert store.get(1)['snapshot']['star_chart']['points'] == 85
    checkout = packet({'checkout': CHECKOUT.encode({'chapterId': 2010100, 'sectionId': 2110851,
        'success': False, 'useAIPoint': True, 'fightTime': 1})}, name='C2L_CheckoutMainMissionSign')
    assert asyncio.run(battle.checkout(ctx, checkout)).values['result'] == 10
    assert asyncio.run(battle.checkout(ctx, checkout)).values['result'] == 10
    assert store.get(1)['snapshot']['star_chart']['points'] == 85


def test_ai_insufficient_entry_rolls_back_stamina_and_run(env):
    store, economy, ctx = env
    seed(store, economy, (39400,))
    store.db.execute('INSERT INTO economy_clears VALUES (1,2110851,?)', ('test',))
    store.db.commit()
    battle = BattleService(store, economy)
    values = request(useAIPoint=True)
    values.update(missionId=2110851, sceneId=2210851)
    assert asyncio.run(battle.enter(ctx, packet(values))).values['result'] == 13
    assert store.get(1)['snapshot']['mobility']['power'] == 149
    assert not store.db.execute('SELECT 1 FROM economy_runs').fetchone()


def test_chapter_clear_unlock_arrives_before_checkout_callback(env):
    store, economy, ctx = env
    battle = BattleService(store, economy)
    values = request()
    values.update(missionId=2110804, sceneId=2210804)
    assert asyncio.run(battle.enter(ctx, packet(values))).values['result'] == 10
    assert 39000 not in unlocked(store, 1)
    checkout = packet({'checkout': CHECKOUT.encode({'chapterId': 2010100, 'sectionId': 2110804,
        'success': True, 'fightTime': 120})}, name='C2L_CheckoutMainMissionSign')
    result = asyncio.run(battle.checkout(ctx, checkout))
    assert result.values['result'] == 10
    chart = STAR_MAP.decode(result.before_response[0].values['StarMap'])
    assert 39000 in [STAR_PAIR.decode(r)['Key'] for r in chart['StarAbility']]
