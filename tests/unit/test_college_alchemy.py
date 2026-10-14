"""Production lifecycle, offline recovery and atomic inventory on isolated saves."""
import asyncio
import random
import pytest
from x2server.player.college_upgrade import _catalog

from tests.unit.test_battle import packet
from tests.unit.test_college_upgrade import game, quantity, send as upgrade
from x2server.messages.core import CORE_SCHEMAS
from x2server.messages.lobby import ELEMENT, PRODUCTION_BAR
from x2server.messages.college import ALCHEMY_RECIPE_BAR_DATA
from x2server.player.college import CollegeService, CollegeStateRepository
from x2server.player.economy import EconomyService
from x2server.player.store import PlayerStore


def send(game, flow, seq=1, **fields):
    result = asyncio.run(game[3].dispatch(game[4], packet(fields, seq, 'C2L_' + flow)))
    for message in (*result.before_response, result, *result.pushes):
        CORE_SCHEMAS[message.message_name].encode(message.values)
    return result


def seed_elements(game, number=10):
    repo = game[2]
    repo.growth_base(1)
    state = repo.load(1)
    for row in state['alchemy']['elements']:
        row['num'] = number
    repo.save(1, state)


@pytest.mark.parametrize('recipe', _catalog()['recipes'], ids=lambda r: str(r['RecipeID']))
def test_every_recipe_accepts_exact_materials_and_debits_once(game, recipe):
    store, _, repo, service, _ = game
    seed_elements(game, 0)
    state = repo.load(1)
    state['alchemy']['recipe_exp'] = [{'Key': recipe['RecipeID'], 'Value': 0}]
    elements = {row['elementId']: row for row in state['alchemy']['elements']}
    with store.db:
        for item, count in zip(recipe['ItemGroup'], recipe['ItemNum'], strict=True):
            if item in service.alchemy.element_items:
                elements[service.alchemy.element_items[item]]['num'] = count
            else:
                store.db.execute('INSERT OR REPLACE INTO inventory VALUES (?,?,?)', (1, item, count))
        result = service.alchemy._make(1, state, {'posIndex': 0, 'recipeId': recipe['RecipeID']})
        assert result['code'] == 10
        for item in recipe['ItemGroup']:
            if item in service.alchemy.element_items:
                assert elements[service.alchemy.element_items[item]]['num'] == 0
            else:
                assert quantity(store, item) == 0
        assert service.alchemy._make(1, state, {'posIndex': 0, 'recipeId': recipe['RecipeID']})['code'] == 206
        assert service.alchemy._make(1, state, {'posIndex': 1, 'recipeId': recipe['RecipeID']})['code'] == 22


@pytest.mark.parametrize('energy,expected', [(300, 10), (67, 10), (66, 22)])
def test_energy_acceleration_matches_native_67_point_price(game, energy, expected):
    _, clock, repo, _, _ = game
    seed_elements(game)
    assert send(game, 'MakeItem', posIndex=0, recipeId=36011).values['code'] == 10
    state = repo.load(1)
    state['star_energy'] = energy
    repo.catalog.state_row(state, 702)['buildingLevel'] = 3
    state['alchemy']['production_bars'][0]['endTime'] = clock.value + 8040
    repo.save(1, state)
    result = send(game, 'MakIngSpeed', seq=2, posIndex=0, type=1)
    assert result.values['code'] == expected
    assert repo.load(1)['star_energy'] == energy - (67 if expected == 10 else 0)
    assert send(game, 'MakIngSpeed', seq=2, posIndex=0, type=1).values == result.values
    if expected == 10:
        assert send(game, 'AlchemyCollect', seq=3, posIndex=0).values['code'] == 10


def test_element_energy_purchase_limit_day_and_replay(game):
    repo, clock, service = game[2], game[1], game[3]
    seed_elements(game, 0)
    for index in range(3):
        state = repo.load(1)
        state['star_energy'] = 200
        state['alchemy']['elements'][5]['num'] = 0
        repo.save(1, state)
        result = send(game, 'AlchemyBuy', seq=index + 1, type=1, typeId=996)
        assert result.values['code'] == 10
        assert [m.message_name for m in result.before_response[:2]] == [
            'L2C_QueryGrowthBase', 'L2C_AlchemyMainData']
        assert repo.load(1)['star_energy'] == 100
        assert repo.load(1)['alchemy']['elements'][5]['num'] == 100
        assert repo.load(1)['alchemy']['elements'][5]['buyTimesDay'] == index + 1
        assert send(game, 'AlchemyBuy', seq=index + 1, type=1, typeId=996).values == result.values
        assert repo.load(1)['star_energy'] == 100
    assert send(game, 'AlchemyBuy', seq=4, type=1, typeId=996).values['code'] == 13
    clock.value += 86400
    assert send(game, 'AlchemyBuy', seq=5, type=1, typeId=996).values['code'] == 10
    assert repo.load(1)['alchemy']['elements'][5]['num'] == 120
    assert repo.load(1)['alchemy']['elements'][5]['buyTimesDay'] == 1


def test_element_crystal_fill_rounding_cap_and_failure(game):
    store, _, repo, _, _ = game
    seed_elements(game, 114)
    player = store.get(1)
    store.save_snapshot(1, dict(player['snapshot'], crystal=1), player['revision'])
    assert send(game, 'AlchemyBuy', type=2, typeId=996).values['code'] == 36
    assert repo.load(1)['alchemy']['elements'][5]['num'] == 114
    player = store.get(1)
    store.save_snapshot(1, dict(player['snapshot'], crystal=10), player['revision'])
    result = send(game, 'AlchemyBuy', seq=2, type=2, typeId=996)
    assert result.values['code'] == 10
    assert store.get(1)['snapshot']['crystal'] == 8
    assert repo.load(1)['alchemy']['elements'][5]['num'] == 120
    assert repo.load(1)['alchemy']['elements'][5]['buyTimesDay'] == 0
    assert send(game, 'AlchemyBuy', seq=2, type=2, typeId=996).values == result.values
    assert store.get(1)['snapshot']['crystal'] == 8
    assert send(game, 'AlchemyBuy', seq=3, type=2, typeId=996).values['code'] == 14
    assert send(game, 'AlchemyBuy', seq=4, type=2, typeId=997).values['code'] == 13


def test_element_purchase_atomic_rollback(game, monkeypatch):
    store, _, repo, _, _ = game
    seed_elements(game, 0)
    player = store.get(1)
    store.save_snapshot(1, dict(player['snapshot'], crystal=100), player['revision'])
    monkeypatch.setattr(repo, 'save', lambda *args: (_ for _ in ()).throw(RuntimeError('disk')))
    with pytest.raises(RuntimeError):
        send(game, 'AlchemyBuy', type=2, typeId=996)
    assert store.get(1)['snapshot']['crystal'] == 100
    assert repo.load(1)['alchemy']['elements'][5]['num'] == 0
    assert store.db.execute('SELECT count(*) FROM college_alchemy_receipts').fetchone()[0] == 0


def test_customer_handoff_real_payment_replay_and_restart(game):
    store, clock, repo, service, context = game
    customer = service._customer_for(1, 1)
    item, count = customer['itemId'][0], customer['itemNum'][0]
    recipe = next(r for r in service.alchemy.recipes.values() if r['ProductID'] == item)
    before = store.get(1)['snapshot']['gold']
    assert send(game, 'AlchemyFinish', type=1, posIndex=1).values['code'] == 22
    with store.db:
        store.db.execute('INSERT INTO inventory VALUES (?,?,?)', (1, item, count * 2))
    result = send(game, 'AlchemyFinish', seq=2, type=1, posIndex=1)
    assert result.values['code'] == 10 and result.values['alchemyType'] == 2
    assert result.values['type'] == 1 and result.values['posIndex'] == 1
    assert store.get(1)['snapshot']['gold'] == before + recipe['Gold']
    assert quantity(store, item) == count
    assert send(game, 'AlchemyFinish', seq=2, type=1, posIndex=1).values == result.values
    assert store.get(1)['snapshot']['gold'] == before + recipe['Gold']
    assert quantity(store, item) == count
    # Receipt survives a new service/connection sharing the original session.
    restored = PlayerStore(store.path)
    restored_repo = CollegeStateRepository(restored, clock)
    restored_service = CollegeService(restored_repo, economy=EconomyService(restored, clock.now))
    restored_game = (restored, clock, restored_repo, restored_service, context)
    assert send(restored_game, 'AlchemyFinish', seq=2, type=1, posIndex=1).values == result.values
    assert quantity(restored, item) == count
    restored.close()


def test_customer_refusal_rotation_replay_query_and_restart(game):
    store, clock, repo, service, context = game
    repo.growth_base(1)
    original = service._customer_for(1, 1)
    neighbor = service._customer_for(1, 0)
    wallet = store.get(1)['snapshot']
    inventory = list(store.db.execute('SELECT * FROM inventory'))
    # The client sends price toggles even when refusing; they cost nothing.
    result = send(game, 'AlchemyFinish', seq=20, type=2, posIndex=1, plusPrice=True)
    assert result.values['code'] == 10 and result.values['type'] == 2
    assert result.values['posIndex'] == 1 and result.values['rewardData'] == b''
    replacement = service._customer_for(1, 1)
    assert replacement['questId'] != original['questId']
    assert service._customer_for(1, 0) == neighbor
    assert send(game, 'AlchemyFinish', seq=20, type=2, posIndex=1, plusPrice=True).values == result.values
    assert service._customer_for(1, 1) == replacement
    from x2server.messages.lobby import CUSTOMER_INFO
    queried = send(game, 'SingleCustomerInfo', seq=21, posIndex=1)
    assert CUSTOMER_INFO.decode(queried.values['customere']) == replacement
    assert store.get(1)['snapshot'] == wallet
    assert list(store.db.execute('SELECT * FROM inventory')) == inventory
    restored = PlayerStore(store.path)
    rebuilt = CollegeService(CollegeStateRepository(restored, clock), economy=EconomyService(restored, clock.now))
    assert rebuilt._customer_for(1, 1) == replacement
    restored.close()


def test_customer_refusal_write_failure_rolls_back_rotation(game, monkeypatch):
    game[2].growth_base(1)
    original = game[3]._customer_for(1, 1)
    with monkeypatch.context() as failure:
        failure.setattr(game[2], 'save', lambda *a: (_ for _ in ()).throw(RuntimeError('disk')))
        with pytest.raises(RuntimeError):
            send(game, 'AlchemyFinish', type=2, posIndex=1)
    assert game[3]._customer_for(1, 1) == original
    assert game[0].db.execute('SELECT count(*) FROM college_alchemy_receipts').fetchone()[0] == 0


@pytest.mark.parametrize('fields', [dict(type=3, posIndex=1), dict(type=2, posIndex=5), dict(type=1, posIndex=5),
    dict(type=1, posIndex=-1), dict(type=1, posIndex=1, plusPrice=True, discountPrice=True)])
def test_customer_invalid_handoff_never_charges(game, fields):
    before = game[0].get(1)['snapshot']
    assert send(game, 'AlchemyFinish', **fields).values['code'] == 13
    assert game[0].get(1)['snapshot'] == before
    assert game[0].db.execute('SELECT count(*) FROM college_alchemy_receipts').fetchone()[0] == 0


def test_customer_write_failure_rolls_back_goods_gold_and_receipt(game, monkeypatch):
    store, _, repo, service, _ = game
    customer = service._customer_for(1, 0)
    item, count = customer['itemId'][0], customer['itemNum'][0]
    with store.db:
        store.db.execute('INSERT INTO inventory VALUES (?,?,?)', (1, item, count))
    before = store.get(1)['snapshot']
    monkeypatch.setattr(repo, 'save', lambda *args: (_ for _ in ()).throw(RuntimeError('disk')))
    with pytest.raises(RuntimeError):
        send(game, 'AlchemyFinish', type=1, posIndex=0)
    assert quantity(store, item) == count
    assert store.get(1)['snapshot'] == before
    assert store.db.execute('SELECT count(*) FROM college_alchemy_receipts').fetchone()[0] == 0


def test_card_window_gate_and_consumption(game):
    assert send(game, 'HelpPowerSpeedValid', type=1).values == {'code': 13, 'type': 1}
    upgrade(game, 'BuildingUpgrade')
    assert send(game, 'HelpPowerSpeedValid', seq=2, type=1).values == {'code': 10, 'type': 1}
    assert send(game, 'HelpPowerSpeedValid', seq=3, type=2).values['code'] == 13
    assert upgrade(game, 'BuildSpeedUP', seq=4, itemId=1237832, itemNum=1).values['code'] == 10
    assert quantity(game[0], 1237832) == 99
    assert send(game, 'HelpPowerSpeedValid', seq=5, type=1).values['code'] == 13


@pytest.mark.parametrize('item,seconds', [(1237831, 600), (1237832, 3600),
    (1237833, 7200), (1237834, 14400), (1237835, 28800)])
def test_all_five_official_speed_cards(game, item, seconds):
    store, _, repo, service, _ = game
    with store.db:
        store.db.execute('INSERT OR REPLACE INTO inventory VALUES (?,?,?)', (1, item, 2))
    assert service.upgrades.speed_cards[item]['EffData'] == [seconds]
    upgrade(game, 'BuildingUpgrade')
    result = upgrade(game, 'BuildSpeedUP', seq=2, itemId=item, itemNum=1)
    assert result.values['code'] == 10 and result.values['buildStatus'] == 1
    assert quantity(store, item) == 1
    assert repo.load(1)['buildings'][0]['buildingLevel'] == 2


def test_element_timestamp_period_cap_and_legacy_migration(game):
    _, clock, repo, service, _ = game
    snapshot = service._alchemy_main(1).values
    elements = [ELEMENT.decode(wire) for wire in snapshot['elements']]
    assert all(row['num'] == 0 and row['lastRecoverTime'] == clock.value for row in elements)
    clock.value += 1799
    repo.growth_base(1)
    assert repo.load(1)['alchemy']['elements'][0]['num'] == 0
    clock.value += 1
    repo.growth_base(1)
    assert [row['num'] for row in repo.load(1)['alchemy']['elements']] == [1, 1, 1, 1, 0, 0]
    clock.value += 10 * 365 * 86400
    elements = [ELEMENT.decode(wire) for wire in service._alchemy_main(1).values['elements']]
    assert [row['num'] for row in elements] == [120, 120, 120, 120, 0, 0]
    assert elements[0]['lastRecoverTime'] == clock.value
    state = repo.load(1)
    state['alchemy']['elements'][0].update(num=2**31 - 1, lastRecoverTime=0)
    state['alchemy']['elements'][1].update(num=0, lastRecoverTime=clock.value + 86400)
    repo.save(1, state)
    elements = [ELEMENT.decode(wire) for wire in service._alchemy_main(1).values['elements']]
    assert elements[0]['num'] == 120
    assert elements[1]['num'] == 0 and elements[1]['lastRecoverTime'] == clock.value


def test_make_collect_replay_and_restart(game):
    store, clock, repo, _, _ = game
    seed_elements(game)
    before_gold = store.get(1)['snapshot']['gold']
    result = send(game, 'MakeItem', posIndex=2, recipeId=36011)
    assert result.values['code'] == 10
    bar = PRODUCTION_BAR.decode(result.values['productionBar'])
    assert bar == {'recipeId': 36011, 'endTime': clock.value + 4000, 'buffId': [0]}
    assert repo.load(1)['alchemy']['elements'][0]['num'] == 6
    assert store.get(1)['snapshot']['gold'] == before_gold  # Gold is SELL price
    assert send(game, 'MakeItem', posIndex=2, recipeId=36011).values == result.values
    assert repo.load(1)['alchemy']['elements'][0]['num'] == 6
    assert send(game, 'MakeItem', seq=2, posIndex=2, recipeId=36011).values['code'] == 206
    assert send(game, 'AlchemyCollect', seq=3, posIndex=2).values['code'] == 205
    restored_store = PlayerStore(store.path)
    restored_repo = CollegeStateRepository(restored_store, clock)
    restored_service = CollegeService(restored_repo, economy=EconomyService(restored_store, clock.now))
    assert PRODUCTION_BAR.decode(restored_service._alchemy_main(1).values['productionBars'][2]) == bar
    restored_store.close()
    clock.value += 4000
    collected = send(game, 'AlchemyCollect', seq=4, posIndex=2)
    assert collected.values['code'] == 10
    assert collected.values['exp'] == 1
    assert quantity(store, 1280011) == 1
    assert repo.load(1)['alchemy']['production_bars'][2] is None
    assert send(game, 'AlchemyCollect', seq=4, posIndex=2).values == collected.values
    assert send(game, 'AlchemyCollect', seq=5, posIndex=2).values['code'] == 204
    assert quantity(store, 1280011) == 1


def test_forged_slots_locked_recipes_and_insufficient_material(game):
    store, _, repo, _, _ = game
    before = store.get(1)['snapshot']
    assert send(game, 'MakeItem', posIndex=0, recipeId=36011).values['code'] == 22
    seed_elements(game)
    for pos, recipe in ((-1, 36011), (3, 36011), (0, 36012), (0, 99999)):
        assert send(game, 'MakeItem', posIndex=pos, recipeId=recipe).values['code'] == 13
    assert store.get(1)['snapshot'] == before
    assert repo.load(1)['alchemy']['elements'][0]['num'] == 10


def test_batch_validation_and_no_duplicate_rewards(game):
    store, clock, repo, _, _ = game
    seed_elements(game, 20)
    for pos in (0, 1, 2):
        assert send(game, 'MakeItem', seq=pos + 1, posIndex=pos, recipeId=36011).values['code'] == 10
    clock.value += 4000
    assert send(game, 'AlchemyOnekeyCollect', seq=4, posIndex=[0, 3]).values['code'] == 13
    assert send(game, 'AlchemyOnekeyCollect', seq=5, posIndex=[0, 0]).values['code'] == 13
    assert all(repo.load(1)['alchemy']['production_bars'])
    result = send(game, 'AlchemyOnekeyCollect', seq=6, posIndex=[2, 0, 1])
    assert result.values['code'] == 10
    row = ALCHEMY_RECIPE_BAR_DATA.decode(result.values['barData'][0])
    assert row['recipeId'] == 36011 and row['posIndex'] == [2, 0, 1]
    assert row['expBefore'] == 0 and row['exp'] == 3
    assert quantity(store, 1280011) == 3
    assert send(game, 'AlchemyOnekeyCollect', seq=6, posIndex=[2, 0, 1]).values == result.values
    assert quantity(store, 1280011) == 3


def test_collect_unlocks_next_recipe_independent_of_furnace_star(game):
    _, clock, repo, service, _ = game
    seed_elements(game, 20)
    state = repo.load(1)
    state['alchemy']['recipe_exp'] = [{'Key': 36011, 'Value': 2}]
    repo.catalog.state_row(state, 707)['buildingStar'] = 1
    repo.save(1, state)
    assert send(game, 'MakeItem', posIndex=0, recipeId=36012).values['code'] == 13
    assert send(game, 'MakeItem', seq=2, posIndex=0, recipeId=36011).values['code'] == 10
    clock.value += 4000
    assert send(game, 'AlchemyCollect', seq=3, posIndex=0).values['exp'] == 3
    assert service.alchemy.recipe_exp(repo.load(1))[36012] == 0
    assert send(game, 'MakeItem', seq=4, posIndex=0, recipeId=36012).values['code'] == 10


def test_existing_recipe_experience_recovers_unlocks_and_all_locked_wire_rows(game):
    store, _, repo, service, _ = game
    seed_elements(game, 120)
    with store.db:
        store.db.execute('INSERT INTO inventory VALUES (?,?,?)', (1, 1281001, 5))
    state = repo.load(1)
    state['alchemy']['recipe_exp'] = [{'Key': 36021, 'Value': 5}, {'Key': 36022, 'Value': -1}]
    repo.catalog.state_row(state, 707)['buildingStar'] = 1
    repo.save(1, state)
    fields = service.alchemy.snapshot_fields(repo.load(1))
    from x2server.messages.lobby import MISSION_PAIR
    exp = {r['Key']: r['Value'] for r in map(MISSION_PAIR.decode, fields['recipeIdExp'])}
    assert exp[36021] == 5 and exp[36022] == 0
    assert 36030 not in exp
    assert all(value >= 0 for value in exp.values())
    assert send(game, 'MakeItem', recipeId=36022, posIndex=0).values['code'] == 10


def test_recipe_effects_match_thresholds_and_building_tier(game):
    _, _, repo, service, _ = game
    seed_elements(game, 20)
    state = repo.load(1)
    state['alchemy']['recipe_exp'] = [{'Key': 36011, 'Value': 12}]
    repo.catalog.state_row(state, 707)['buildingStar'] = 2
    repo.save(1, state)
    assert service.alchemy.recipe_exp(state)[36012] == 0
    result = send(game, 'MakeItem', posIndex=0, recipeId=36011)
    assert PRODUCTION_BAR.decode(result.values['productionBar'])['endTime'] == game[1].value + 3000
    assert repo.load(1)['alchemy']['elements'][0]['num'] == 17  # 4 minus 1


def test_fifth_slot_doubles_collected_output_at_full_proficiency(game):
    store, clock, repo, service, _ = game
    seed_elements(game, 20)
    assert send(game, 'MakeItem', posIndex=0, recipeId=36011).values['code'] == 10
    state = repo.load(1)
    state['alchemy']['recipe_exp'] = [{'Key': 36011, 'Value': 18}]
    # The fifth slot carries the doubled-output effect and must stay reachable
    # once every threshold is met.
    assert service.alchemy.effects(service.alchemy.recipes[36011], 18, 5) == [200]
    end = next(t for t in range(1, 1000) if random.Random(
        'college-double:1:0:%s' % t).randrange(1000) < 200)
    state['alchemy']['production_bars'][0]['endTime'] = end
    repo.save(1, state)
    collected = send(game, 'AlchemyCollect', seq=2, posIndex=0)
    assert collected.values['code'] == 10
    assert store.db.execute(
        'SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1280011').fetchone()[0] == 2


def test_save_failure_rolls_back_element_queue_rewards_and_receipts(game, monkeypatch):
    store, clock, repo, _, _ = game
    seed_elements(game)
    def fail(*args):
        raise RuntimeError('disk failure')
    original = repo.save
    monkeypatch.setattr(repo, 'save', fail)
    with pytest.raises(RuntimeError):
        send(game, 'MakeItem', posIndex=0, recipeId=36011)
    assert repo.load(1)['alchemy']['elements'][0]['num'] == 10
    assert not repo.load(1)['alchemy']['production_bars']
    monkeypatch.setattr(repo, 'save', original)
    send(game, 'MakeItem', posIndex=0, recipeId=36011)
    clock.value += 4000
    monkeypatch.setattr(repo, 'save', fail)
    with pytest.raises(RuntimeError):
        send(game, 'AlchemyCollect', seq=2, posIndex=0)
    assert repo.load(1)['alchemy']['production_bars'][0]
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1280011').fetchone() is None
    assert store.db.execute('SELECT count(*) FROM college_alchemy_receipts').fetchone()[0] == 1


def test_element_recovery_uses_old_rate_before_completed_upgrade(game):
    _, clock, repo, _, _ = game
    seed_elements(game, 0)
    state = repo.load(1)
    state['build_queue'] = {'buildingId': 703, 'upgradeStatus': 1,
        'upgradeStartTime': clock.value, 'upgradeEndTime': clock.value + 1800, 'target_level': 2}
    repo.save(1, state)
    clock.value += 3600
    repo.growth_base(1)
    assert [r['num'] for r in repo.load(1)['alchemy']['elements']] == [2, 2, 2, 2, 1, 0]
