"""Real timed jobs, restart, occupancy and atomic claims on isolated saves."""
import pytest
import asyncio
from tests.unit.test_college_upgrade import game, send, seed_elements
from x2server.messages.lobby import TRAINING_DATA, EXPLORE_DATA
from x2server.player.alchemy import catalog as alchemy_catalog
from x2server.player.college import CollegeStateRepository
from x2server.player.college_power import hero_power
from x2server.player.store import PlayerStore
from x2server.protocol.headers import RequestHeader
from x2server.protocol.types import DecodedPacket
from x2server.messages.core import CORE_SCHEMAS


def funded(game):
    repo, store = game[2], game[0]
    repo.growth_base(1)
    state = repo.load(1)
    state['star_energy'] = 200
    repo.save(1, state)
    player = store.get(1)
    if not player['snapshot'].get('heroes'):
        store.save_snapshot(1, dict(player['snapshot'], heroes=[
            {'id': 1003, 'state': 2, 'level': 1, 'star': 1, 'exp': 0}]), player['revision'])
    return next(h['id'] for h in store.get(1)['snapshot']['heroes'] if h['state'] == 2)


def test_native_training_wire_start_cancel_finish_and_completion_push(game):
    funded(game)
    # Independent bytes from C2L_StartTrain.Serialize 0x3b8e9a4:
    # tag 08=trainId; tag 20=heroId (1003), not declaration-order tag 10.
    raw = bytes.fromhex('080020eb07')
    request = DecodedPacket(0, 0, RequestHeader(request_id=101), 259, raw)
    result = asyncio.run(game[3].dispatch(game[4], request))
    assert result.values['code'] == 10 and result.values['heroId'] == 1003
    assert result.before_response[0].message_name == 'L2C_QueryGrowthBase'
    wire = result.before_response[0].values['trainingList'][0]
    assert TRAINING_DATA.decode(wire)['trainingStatus'] == 2
    assert send(game, 'CancelTrain', seq=102, trainId=0).values['code'] == 10
    request = DecodedPacket(0, 0, RequestHeader(request_id=103), 259, raw)
    assert asyncio.run(game[3].dispatch(game[4], request)).values['code'] == 10
    game[1].value += 7200
    messages = game[3].upgrades.complete_due(1)
    assert [m.message_name for m in messages] == ['L2C_QueryGrowthBase', 'L2C_TrainingUpdate']
    for message in messages:
        CORE_SCHEMAS[message.message_name].encode(message.values)
    assert TRAINING_DATA.decode(messages[1].values['trainList'][0])['trainingStatus'] == 3
    assert game[3].upgrades.complete_due(1) == ()
    assert send(game, 'FinishTrain', seq=104, trainId=0).values['code'] == 10
    assert TRAINING_DATA.decode(game[2].growth_base(1)['trainingList'][0])['trainingStatus'] == 1


def test_native_explore_wire_party_and_restart_claim(game):
    funded(game)
    # C2L_StartExplore native tags 1/2/3(repeated)/4; hero1003, ruin34001.
    raw = bytes.fromhex('0800100018eb0720d18902')
    request = DecodedPacket(0, 0, RequestHeader(request_id=201), 242, raw)
    result = asyncio.run(game[3].dispatch(game[4], request))
    assert result.values['code'] == 10
    job = EXPLORE_DATA.decode(result.before_response[0].values['exploreList'][0])
    assert job['exploreStatus'] == 2 and job['ruinId'] == 34001 and job['heroList'] == [1003]
    game[1].value += 10800
    restored = PlayerStore(game[0].path)
    repo = CollegeStateRepository(restored, game[1])
    from x2server.player.college import CollegeService
    from x2server.player.economy import EconomyService
    service = CollegeService(repo, economy=EconomyService(restored, game[1].now))
    reopened = (restored, game[1], repo, service, game[4])
    assert send(reopened, 'FinishExplore', seq=202, exploreId=0).values['code'] == 10
    assert EXPLORE_DATA.decode(repo.growth_base(1)['exploreList'][0])['exploreStatus'] == 1
    assert restored.get(1)['snapshot']['heroes'][0]['college_status'] == 0
    restored.close()


@pytest.mark.parametrize('award_index', range(11))
def test_explore_all_official_reward_destinations(game, monkeypatch, award_index):
    hid = funded(game)
    store, clock, repo, service, _ = game
    gift = service.jobs.economy.gift_contents['761001']
    draw = sum(gift['weights'][:award_index])
    monkeypatch.setattr('secrets.randbelow', lambda upper: draw if upper == sum(gift['weights']) else 0)
    assert send(game, 'StartExplore', seq=1, exploreId=0, ruinId=34001, heroIds=[hid]).values['code'] == 10
    clock.value += 10800
    assert send(game, 'FinishExplore', seq=2, exploreId=0).values['code'] == 10
    assert not repo.load(1)['explore']
    assert store.get(1)['snapshot']['heroes'][0]['college_status'] == 0
    if gift['items'][award_index][0] in (1237991, 1237992):
        # 元素奖励落在新的元素池 (alchemy_state 表), 不是学院快照的旧 alchemy.elements。
        eid = gift['items'][award_index][0] - 1237000
        element_num = service.alchemy_service.repo.peek(1)['element_num']
        assert element_num[str(eid)] >= 50
        assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?',
                                (gift['items'][award_index][0],)).fetchone() is None


def test_explore_speed_price_replay_and_separate_claim(game):
    hid = funded(game)
    store, clock, repo, _, _ = game
    assert send(game, 'StartExplore', seq=1, exploreId=0, ruinId=34001, heroIds=[hid]).values['code'] == 10
    clock.value += 10800 - 721
    end = repo.load(1)['explore'][0]['exploreEndTime']
    player = store.get(1)
    store.save_snapshot(1, dict(player['snapshot'], crystal=1), player['revision'])
    assert send(game, 'ExploreSpeed', seq=2, exploreId=0).values['code'] == 36
    assert repo.load(1)['explore'][0]['exploreEndTime'] == end
    player = store.get(1)
    store.save_snapshot(1, dict(player['snapshot'], crystal=10), player['revision'])
    result = send(game, 'ExploreSpeed', seq=2, exploreId=0)
    assert result.values == {'code': 10, 'exploreId': 0, 'exploreEndTime': clock.value}
    CORE_SCHEMAS[result.message_name].encode(result.values)
    assert store.get(1)['snapshot']['crystal'] == 8
    assert store.get(1)['snapshot']['heroes'][0]['college_status'] == 2
    assert repo.load(1)['explore'][0]['exploreEndTime'] == clock.value
    assert send(game, 'ExploreSpeed', seq=2, exploreId=0).values == result.values
    assert store.get(1)['snapshot']['crystal'] == 8
    assert send(game, 'ExploreSpeed', seq=3, exploreId=0).values['code'] == 205
    assert send(game, 'CancelExplore', seq=4, exploreId=0).values['code'] == 205
    claim = send(game, 'FinishExplore', seq=5, exploreId=0)
    assert claim.values['code'] == 10
    assert send(game, 'FinishExplore', seq=5, exploreId=0).values == claim.values
    assert not repo.load(1)['explore']
    assert store.get(1)['snapshot']['heroes'][0]['college_status'] == 0


def test_explore_speed_write_failure_rolls_back(game, monkeypatch):
    hid = funded(game)
    store, _, repo, _, _ = game
    player = store.get(1)
    store.save_snapshot(1, dict(player['snapshot'], crystal=100), player['revision'])
    assert send(game, 'StartExplore', seq=1, exploreId=0, ruinId=34001, heroIds=[hid]).values['code'] == 10
    original = repo.load(1)
    monkeypatch.setattr(repo, 'save', lambda *a: (_ for _ in ()).throw(RuntimeError('disk')))
    with pytest.raises(RuntimeError):
        send(game, 'ExploreSpeed', seq=2, exploreId=0)
    assert store.get(1)['snapshot']['crystal'] == 100
    assert repo.load(1) == original
    assert store.db.execute('SELECT count(*) FROM college_job_receipts').fetchone()[0] == 1


def test_energy_recovery_and_legacy_anchor(game):
    _, clock, repo, _, _ = game
    # -1 是"未初始化": 首次结算直接补满 96, 下次恢复时刻锚定在 now。
    wire = repo.growth_base(1)
    assert wire['starEnergy'] == 96 and wire['starGainTime'] == clock.value
    # 掉到 10 后按每小时 2 点恢复; 不满一整刻不恢复。
    state = repo.load(1)
    state.update(star_energy=10, star_energy_at=clock.value)
    repo.save(1, state)
    clock.value += 1799
    assert repo.growth_base(1)['starEnergy'] == 10
    clock.value += 1
    assert repo.growth_base(1)['starEnergy'] == 11
    clock.value += 3600 * 100
    assert repo.growth_base(1)['starEnergy'] == 96
    # 满值后 star_gain_time 推到现在。
    assert repo.growth_base(1)['starGainTime'] == clock.value
    # star_gain_time 是派生字段: 结算按 star_energy_at 重算, 脏值被覆盖。
    state = repo.load(1)
    state.update(star_energy=10, star_energy_at=clock.value,
                 star_gain_time=clock.value + 9999)
    repo.save(1, state)
    assert repo.growth_base(1)['starEnergy'] == 10
    assert repo.growth_base(1)['starGainTime'] == clock.value + 1800


def test_training_timed_claim_and_replay(game):
    hid = funded(game)
    store, clock, repo, _, _ = game
    result = send(game, 'StartTrain', trainId=0, heroId=hid)
    assert result.values['code'] == 10
    assert result.values['trainTime'] == 7200
    assert result.values['buildId'] == 24401
    assert repo.load(1)['star_energy'] == 195
    assert send(game, 'StartTrain', trainId=0, heroId=hid).values == result.values
    assert send(game, 'FinishTrain', seq=2, trainId=0).values['code'] == 205
    restored = PlayerStore(store.path)
    restored_repo = CollegeStateRepository(restored, clock)
    assert TRAINING_DATA.decode(restored_repo.growth_base(1)['trainingList'][0])['heroId'] == hid
    clock.value += 7200
    assert TRAINING_DATA.decode(repo.growth_base(1)['trainingList'][0])['trainingStatus'] == 3
    result = send(game, 'FinishTrain', seq=3, trainId=0)
    assert result.values['code'] == 10 and result.values['gainExp'] == 30
    hero = next(h for h in store.get(1)['snapshot']['heroes'] if h['id'] == hid)
    assert hero['exp'] == 30 and hero['college_status'] == 0 and hero['state'] == 2
    assert send(game, 'FinishTrain', seq=3, trainId=0).values == result.values
    assert send(game, 'FinishTrain', seq=4, trainId=0).values['code'] == 13
    assert not restored_repo.load(1)['training']
    restored.close()


def test_queue_wire_uses_native_unlocked_and_occupied_states(game):
    repo, clock = game[2], game[1]
    wire = repo.growth_base(1)
    assert TRAINING_DATA.decode(wire['trainingList'][0])['trainingStatus'] == 1
    assert TRAINING_DATA.decode(wire['trainingList'][0])['buildID'] == 24401
    assert EXPLORE_DATA.decode(wire['exploreList'][0])['exploreStatus'] == 1
    hid = funded(game)
    send(game, 'StartTrain', trainId=0, heroId=hid)
    assert TRAINING_DATA.decode(repo.growth_base(1)['trainingList'][0])['trainingStatus'] == 2
    send(game, 'CancelTrain', seq=2, trainId=0)
    assert TRAINING_DATA.decode(repo.growth_base(1)['trainingList'][0])['trainingStatus'] == 1
    send(game, 'StartExplore', seq=3, exploreId=0, ruinId=34001, heroIds=[hid])
    clock.value += 10800
    occupied = EXPLORE_DATA.decode(repo.growth_base(1)['exploreList'][0])
    assert occupied['exploreStatus'] == 2 and occupied['heroList'] == [hid]
    assert send(game, 'FinishExplore', seq=4, exploreId=0).values['code'] == 10
    assert EXPLORE_DATA.decode(repo.growth_base(1)['exploreList'][0])['exploreStatus'] == 1


def test_training_cancel_and_occupancy_no_rewards(game):
    hid = funded(game)
    assert send(game, 'StartTrain', trainId=0, heroId=hid).values['code'] == 10
    result = send(game, 'StartExplore', seq=2, exploreId=0, ruinId=34001, heroIds=[hid])
    assert result.values['code'] == 64
    assert send(game, 'CancelTrain', seq=3, trainId=0).values['code'] == 10
    assert game[2].load(1)['star_energy'] == 195
    assert not game[2].load(1)['training']
    assert send(game, 'CancelTrain', seq=4, trainId=0).values['code'] == 13
    hero = next(h for h in game[0].get(1)['snapshot']['heroes'] if h['id'] == hid)
    assert hero.get('exp', 0) == 0 and hero['college_status'] == 0


def test_exploration_gates_cancel_and_claim(game, monkeypatch):
    hid = funded(game)
    store, clock, repo, service, _ = game
    # Native first ruin threshold=100; ordinary starting heroes exceed it.
    hero = next(h for h in store.get(1)['snapshot']['heroes'] if h['id'] == hid)
    assert hero_power(store, 1, hero, clock) >= 100
    assert send(game, 'StartExplore', exploreId=0, ruinId=34001, heroIds=[hid], diffdifficulty=1).values['code'] == 13
    assert send(game, 'StartExplore', exploreId=0, ruinId=34001, heroIds=[hid, hid]).values['code'] == 13
    assert send(game, 'StartExplore', exploreId=0, ruinId=34002, heroIds=[hid]).values['code'] == 13
    result = send(game, 'StartExplore', seq=2, exploreId=0, ruinId=34001, heroIds=[hid])
    assert result.values['code'] == 10
    assert repo.load(1)['star_energy'] == 194
    job = EXPLORE_DATA.decode(repo.growth_base(1)['exploreList'][0])
    assert job['exploreEndTime'] == clock.value + 10800
    assert job['heroList'] == [hid]
    assert send(game, 'StartTrain', seq=3, trainId=0, heroId=hid).values['code'] == 63
    assert send(game, 'FinishExplore', seq=4, exploreId=0).values['code'] == 205
    assert send(game, 'CancelExplore', seq=5, exploreId=0).values['code'] == 10
    assert repo.load(1)['star_energy'] == 200
    assert send(game, 'CancelExplore', seq=6, exploreId=0).values['code'] == 13
    assert send(game, 'StartExplore', seq=7, exploreId=0, ruinId=34001, heroIds=[hid]).values['code'] == 10
    # Force an element award to check its special capped storage destination.
    monkeypatch.setattr(service.jobs.economy, 'gifts', lambda *a, **kw: {1237991: 50})
    clock.value += 10800
    # 元素池清零并把恢复锚点钉在当前时刻, 奖励 50 点即落在新元素池 (clamped to cap)。
    seed_elements(game, 0)
    result = send(game, 'FinishExplore', seq=8, exploreId=0)
    assert result.values['code'] == 10 and result.values['exp'] == 1
    assert [r['ruinId'] for r in repo.load(1)['ruins']] == [34001, 34002]
    assert service.alchemy_service.repo.peek(1)['element_num']['991'] == 50
    quantity = store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1281001').fetchone()[0]
    assert 2 <= quantity <= 4
    assert send(game, 'FinishExplore', seq=8, exploreId=0).values == result.values
    assert send(game, 'FinishExplore', seq=9, exploreId=0).values['code'] == 13
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1281001').fetchone()[0] == quantity


def test_job_write_failure_rolls_back_energy_and_hero(game, monkeypatch):
    hid = funded(game)
    original = game[0].get(1)['snapshot']
    monkeypatch.setattr(game[2], 'save', lambda *a: (_ for _ in ()).throw(RuntimeError('disk')))
    with pytest.raises(RuntimeError):
        send(game, 'StartTrain', trainId=0, heroId=hid)
    assert game[0].get(1)['snapshot'] == original
    assert game[2].load(1)['star_energy'] == 200
    assert not game[2].load(1)['training']
    assert game[0].db.execute('SELECT count(*) FROM college_job_receipts').fetchone()[0] == 0


@pytest.mark.parametrize('kind,field,amount', [(1, 'gold', 1000), (2, 'crystal', 50)])
def test_alchemy_energy_and_crystal_speed(game, kind, field, amount):
    funded(game)
    seed_elements(game)
    service = game[3]
    store, clock, repo, _, _ = game
    rid = min(alchemy_catalog()['recipes'], key=int)
    assert send(game, 'MakeItem', posIndex=0, recipeId=rid).values['code'] == 10
    assert service.alchemy_service.repo.production_rows(1)[0]['endAt'] == clock.value + 4000
    # 对应货币不足时加速被拒 (回 35), 产槽不受影响。
    player = store.get(1)
    store.save_snapshot(1, dict(player['snapshot'], gold=0, crystal=0), player['revision'])
    assert send(game, 'MakIngSpeed', seq=2, posIndex=0, type=kind).values['code'] == 35
    assert service.alchemy_service.repo.production_rows(1)[0]['endAt'] == clock.value + 4000
    # 补足货币后加速成功: 扣对应货币, 产槽立刻到时。
    player = store.get(1)
    store.save_snapshot(1, dict(player['snapshot'], gold=500000, crystal=100), player['revision'])
    before = store.get(1)['snapshot'][field]
    result = send(game, 'MakIngSpeed', seq=2, posIndex=0, type=kind)
    assert result.values['code'] == 10
    assert store.get(1)['snapshot'][field] == before - amount
    assert service.alchemy_service.repo.production_rows(1)[0]['endAt'] == clock.value
    # 新实现没有"已到期短路": 重复加速会再扣一次 (旧断言的 205 已废弃)。
    assert send(game, 'MakIngSpeed', seq=3, posIndex=0, type=kind).values['code'] == 10
    assert store.get(1)['snapshot'][field] == before - 2 * amount
    assert send(game, 'AlchemyCollect', seq=4, posIndex=0).values['code'] == 10
