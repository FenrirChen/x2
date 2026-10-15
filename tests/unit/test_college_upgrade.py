"""Building progression against isolated saves and an advancing server clock."""
import asyncio
import pytest

from tests.unit.test_battle import packet
from x2server.messages.core import CORE_SCHEMAS
from x2server.messages.lobby import BUILDING_BASE_INFO, BUILD_QUEUE, TRAINING_DATA
from x2server.network.dispatcher import DispatchContext
from x2server.network.session import SessionState
from x2server.player.college import CollegeService, CollegeStateRepository
from x2server.player.economy import EconomyService
from x2server.player.lobby import LobbyService
from x2server.player.store import PlayerStore


class Clock:
    value = 1_800_000_000

    def now(self):
        return self.value


@pytest.fixture
def game(tmp_path):
    store = PlayerStore(tmp_path / 'buildings.db')
    store.login('upgrade', 1, 0)
    snapshot = store.get(1)
    store.save_snapshot(1, dict(snapshot['snapshot'], level=60, gold=500000), snapshot['revision'])
    clock = Clock()
    economy = EconomyService(store, clock.now)
    repo = CollegeStateRepository(store, clock)
    service = CollegeService(repo, economy=economy)
    with store.db:
        for item in (1237801, 1237802, 1237832):
            store.db.execute('INSERT INTO inventory VALUES (?,?,?)', (1, item, 100))
    context = DispatchContext('upgrades', 'local', SessionState('upgrades', 'unique-session', player_id=1))
    yield store, clock, repo, service, context
    store.close()


def send(game, flow, bid=701, kind=1, seq=1, **fields):
    service, context = game[3:]
    result = asyncio.run(service.dispatch(context, packet(
        {'buildingId': bid, 'type': kind, **fields}, seq, 'C2L_' + flow)))
    # Every emitted message is encodable with the actual registered wire schema.
    for message in (*result.before_response, result, *result.pushes):
        CORE_SCHEMAS[message.message_name].encode(message.values)
    return result


def quantity(store, item):
    return store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?', (item,)).fetchone()[0]


def test_timed_upgrade_payment_replay_and_restart(game):
    store, clock, repo, service, _ = game
    result = send(game, 'BuildingUpgrade')
    assert result.values == {'code': 10, 'buildingId': 701, 'type': 1,
                             'buildTime': 600, 'endTime': clock.value + 600}
    assert result.before_response[0].message_name == 'L2C_QueryGrowthBase'
    assert store.get(1)['snapshot']['gold'] == 490000
    assert quantity(store, 1237801) == 97
    assert send(game, 'BuildingUpgrade').values == result.values
    assert quantity(store, 1237801) == 97
    assert send(game, 'BuildingUpgrade', bid=702, seq=2).values['code'] == 55
    restored = PlayerStore(store.path)
    restored_repo = CollegeStateRepository(restored, clock)
    assert BUILD_QUEUE.decode(restored_repo.growth_base(1)['buildQueue'])['upgradeEndTime'] == clock.value + 600
    clock.value += 599
    assert service.upgrades.complete_due(1) == ()
    clock.value += 1
    pushes = service.upgrades.complete_due(1)
    assert [p.message_name for p in pushes] == ['L2C_QueryGrowthBase', 'L2C_UpLevelBuildingId']
    assert BUILDING_BASE_INFO.decode(pushes[0].values['buildingList'][0])['buildingLevel'] == 2
    assert service.upgrades.complete_due(1) == ()
    assert restored_repo.load(1)['buildings'][0]['buildingLevel'] == 2
    restored.close()


def test_errors_never_charge_and_type_is_authoritative(game):
    store, _, repo, _, _ = game
    before = store.get(1)['snapshot']
    assert send(game, 'BuildingUpgrade', kind=2).values['code'] == 13
    assert send(game, 'BuildingUpgrade', bid=999).values['code'] == 13
    assert send(game, 'BuildingUpgrade', bid=703).values['code'] == 13  # needs hall level 2
    assert send(game, 'BuildStarUP').values['code'] == 56
    assert store.get(1)['snapshot'] == before
    assert quantity(store, 1237801) == 100
    with store.db:
        store.db.execute('UPDATE inventory SET quantity=0 WHERE item_id=1237801')
    assert send(game, 'BuildingUpgrade').values['code'] == 22
    assert store.get(1)['snapshot'] == before
    snapshot = store.get(1)
    store.save_snapshot(1, dict(snapshot['snapshot'], gold=0), snapshot['revision'])
    assert send(game, 'BuildingUpgrade').values['code'] == 35
    assert not repo.load(1).get('build_queue')


def test_star_level_gate_and_real_unlock_effects(game):
    _, _, repo, service, _ = game
    state = repo.load(1)
    for row in state['buildings']:
        row['buildingLevel'] = 3
    repo.save(1, state)
    assert send(game, 'BuildingUpgrade').values['code'] == 57
    assert send(game, 'BuildStarUP', seq=2).values['star'] == 2
    alchemy = service._alchemy_main(1).values
    assert len(alchemy['customeres']) == 5
    assert len(alchemy['productionBars']) == 4  # hall star 2
    assert send(game, 'BuildStarUP', bid=707, seq=3).values['code'] == 10
    from x2server.messages.lobby import MISSION_PAIR
    recipes = [MISSION_PAIR.decode(raw) for raw in service._alchemy_main(1).values['recipeIdExp']]
    # A furnace star upgrade does not bypass recipe experience prerequisites.
    # Locked (-1) rows must stay out of the wire or the client exposes them as
    # craftable products with negative manufacture counts.
    assert {row['Key'] for row in recipes} == {36011, 36021, 36031, 36041, 36051, 36061}
    assert all(row['Value'] == 0 for row in recipes)
    assert send(game, 'BuildStarUP', bid=704, seq=4).values['code'] == 10
    slots = [TRAINING_DATA.decode(v) for v in repo.growth_base(1)['trainingList']]
    # The client always draws TRAIN_MAX_NUM rows; hall star 2 unlocks slot 1.
    assert [r['trainingId'] for r in slots] == list(range(6))
    assert [r['trainingStatus'] for r in slots] == [1, 1, 0, 0, 0, 0]
    assert send(game, 'BuildStarUP', bid=704, seq=4).values['code'] == 10
    assert repo.load(1)['buildings'][3]['buildingStar'] == 2


def test_speed_item_and_offline_completion(game):
    store, clock, repo, _, _ = game
    send(game, 'BuildingUpgrade')
    assert send(game, 'BuildSpeedUP', seq=2, itemId=1237801, itemNum=1).values['code'] == 13
    assert send(game, 'BuildSpeedUP', seq=3, itemId=1237832, itemNum=2).values['code'] == 13
    result = send(game, 'BuildSpeedUP', seq=4, itemId=1237832, itemNum=1)
    assert result.values['code'] == 10 and result.values['buildStatus'] == 1
    assert quantity(store, 1237832) == 99
    assert repo.load(1)['buildings'][0]['buildingLevel'] == 2
    send(game, 'BuildingUpgrade', seq=5)
    clock.value += 900
    assert BUILDING_BASE_INFO.decode(repo.growth_base(1)['buildingList'][0])['buildingLevel'] == 3
    assert BUILD_QUEUE.decode(repo.growth_base(1)['buildQueue']) == {}


def test_failed_save_rolls_back_currency_material_and_receipt(game, monkeypatch):
    store, _, repo, _, _ = game
    def fail(*args):
        raise RuntimeError('disk failure')
    monkeypatch.setattr(repo, 'save', fail)
    with pytest.raises(RuntimeError):
        send(game, 'BuildingUpgrade')
    assert store.get(1)['snapshot']['gold'] == 500000
    assert quantity(store, 1237801) == 100
    assert store.db.execute('SELECT count(*) FROM college_upgrade_receipts').fetchone()[0] == 0


def test_world_boss_entry_regression(game):
    result = asyncio.run(LobbyService().query(game[4], packet({}, 1, 'C2L_QueryWorldBossOpenTime')))
    assert result.values == {'code': 10}


def test_level_effect_vectors_and_account_requirement(game):
    store, clock, repo, _, _ = game
    assert repo.catalog.effect(repo.load(1), 702, 5) == [240]
    assert send(game, 'BuildingUpgrade', bid=702).values['code'] == 10
    clock.value += 300
    repo.growth_base(1)
    assert repo.catalog.effect(repo.load(1), 702, 5) == [270]
    assert repo.catalog.effect(repo.load(1), 702, 6) == [105]
    snapshot = store.get(1)
    store.save_snapshot(1, dict(snapshot['snapshot'], level=3), snapshot['revision'])
    assert send(game, 'BuildingUpgrade', seq=2).values['code'] == 37
    assert quantity(store, 1237801) == 97


def test_repository_never_commits_an_outer_transaction(game):
    store, _, repo, _, _ = game
    with pytest.raises(RuntimeError):
        with game[3].upgrades.economy.transaction():
            store.db.execute('UPDATE inventory SET quantity=quantity-1 WHERE item_id=1237801')
            state = repo.load(1)
            state['star_energy'] = 9
            repo.save(1, state)
            raise RuntimeError('outer transaction aborted')
    assert quantity(store, 1237801) == 100
    assert repo.load(1)['star_energy'] == 0
