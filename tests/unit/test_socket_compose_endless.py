import asyncio
from tests.unit.test_economy import env
from tests.unit.test_battle import packet, request
from x2server.player.bag_items import BagItemService
from x2server.player.battle import BattleService
from x2server.player.economy import EconomyService
from x2server.messages.battle import FIGHT_PROFILE, CHECKOUT


def test_equipped_compose_costs_sync_replay_and_failure(env):
    store, economy, ctx = env
    player = store.get(1)
    hero = player['snapshot']['heroes'][0]
    hero['god_equip'] = {'id': 1503, 'star': 1, 'level': 0, 'jewels': {'0': 1250011}}
    player['snapshot']['gold'] = 20000
    store.save_snapshot(1, player['snapshot'], player['revision'])
    with store.db:
        store.db.execute('INSERT INTO inventory VALUES (1,1250011,2)')
    service = BagItemService(store, economy)
    p = packet({'HeroID': 1003, 'HoleIsID': 0, 'RecipeID': 29000}, name='C2L_GodEqupJewelCompose')
    first = asyncio.run(service.compose_equipped(ctx, p))
    assert first.values == {'result': 10, 'ID': 1250012}
    assert first.before_response[0].message_name == 'L2C_HeroUpdate'
    assert asyncio.run(service.compose_equipped(ctx, p)).values == first.values
    snapshot = store.get(1)['snapshot']
    assert snapshot['gold'] == 10000 and snapshot['heroes'][0]['god_equip']['jewels']['0'] == 1250012
    assert store.db.execute('SELECT quantity FROM inventory WHERE item_id=1250011').fetchone()[0] == 0
    assert not store.db.execute('SELECT 1 FROM inventory WHERE item_id=1250012').fetchone()
    bad = packet({'HeroID': 1003, 'HoleIsID': 0, 'RecipeID': 29000}, name='C2L_GodEqupJewelCompose', request_id=2)
    assert asyncio.run(service.compose_equipped(ctx, bad)).values['result'] == 13
    assert store.get(1)['snapshot'] == snapshot


def test_temporal_gate_entry_profile_resume_and_settle(env):
    store, economy, ctx = env
    query = packet({'profileType': 2}, name='C2L_CheckFightProfile')
    assert asyncio.run(economy.endless.check_profile(ctx, query)).values['weeklyId'] == 2060101
    battle = BattleService(store, economy)
    values = request()
    values.update(missionId=2110291, chapter=2060101, sceneId=2210191)
    entered = asyncio.run(battle.enter(ctx, packet(values)))
    assert entered.values['result'] == 10
    power = store.get(1)['snapshot']['mobility']['power']
    drop = packet({'missionId': 2110291, 'chapterId': 2060101, 'sceneId': 2210191,
                   'layer': 3, 'fightTime': 25, 'randomSeed': 101}, name='C2L_FightDropData', request_id=2)
    assert asyncio.run(battle.drop_data(ctx, drop)).values['result'] == 10
    assert asyncio.run(battle.drop_data(ctx, drop)).values['result'] == 10
    assert economy.endless.task_values(1,2060101)['taskList']
    info = asyncio.run(economy.endless.check_profile(ctx, query)).values
    assert info['isProfileExist'] and info['layer'] == 3
    EconomyService(store)  # State survives reconstruction.
    values['isFromProfile'] = True
    resumed = asyncio.run(battle.enter(ctx, packet(values, request_id=3)))
    assert resumed.values['uuid'] == entered.values['uuid']
    assert FIGHT_PROFILE.decode(resumed.values['fightDataProfile'])['layer'] == 3
    assert store.get(1)['snapshot']['mobility']['power'] == power
    checkout = packet({'checkout': CHECKOUT.encode({'sectionId':2110291,'chapterId':2060101,
        'success': True,'fightTime':120})}, name='C2L_CheckoutMainMissionSign', request_id=4)
    result = asyncio.run(battle.checkout(ctx, checkout))
    assert result.values['result'] == 10
    assert asyncio.run(battle.checkout(ctx, checkout)).values == result.values
    assert not asyncio.run(economy.endless.check_profile(ctx, query)).values['isProfileExist']


def test_temporal_gate_task_rewards_retries_and_observation_dedupe(env):
    store, economy, _ = env
    service = economy.endless
    with economy.transaction():
        service.observe(1, 'fixture', 1, 3023, 500)
        service.observe(1, 'fixture', 1, 3023, 500)
    assert store.db.execute('SELECT progress FROM endless_tasks WHERE task_id=100001').fetchone()[0] == 500
    first = service.claim(1, 100001, 'request1')
    assert first['code'] == 10
    assert service.claim(1, 100001, 'request1') == first
    assert store.db.execute('SELECT claimed FROM endless_tasks WHERE task_id=100001').fetchone()[0] == 1
    assert service.claim(1, 100001, 'request2')['code'] == 10
