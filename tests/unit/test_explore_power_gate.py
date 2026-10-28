"""Native exploration admission: the client owns the 50% line, not the server."""
from copy import deepcopy

from tests.unit.test_college_upgrade import game
from tests.unit.test_college_jobs import funded
from tests.unit.test_college_alchemy import send
from x2server.messages.lobby import EXPLORE_DATA


def test_every_ruin_and_difficulty_starts_below_native_half_power(game, monkeypatch):
    hid = funded(game)
    store, _, repo, service, _ = game
    state = repo.load(1)
    state['ruins'] = [{'ruinId': rid, 'exp': row['Exp'][-1], 'queueCount': 0}
                     for rid, row in service.jobs.explores.items()]
    state['star_energy'] = 240
    repo.save(1, state)
    power = [0]
    monkeypatch.setattr('x2server.player.college_power.hero_power', lambda *args: power[0])
    seq = 10000
    for rid, row in service.jobs.explores.items():
        for difficulty, target in enumerate(row['Conditon']):
            req = dict(exploreId=0, ruinId=rid, heroIds=[hid], diffdifficulty=difficulty)
            before = repo.load(1)
            # 门槛由客户端按属性203自算, 服务端估算偏低时也必须放行,
            # 否则界面已经 99%/100% 的队伍仍会被回 186 弹「神力不足50%」。
            power[0] = 0
            accepted = send(game, 'StartExplore', seq=seq, **req)
            assert accepted.values['code'] == 10, (rid, difficulty, accepted.values)
            job = repo.load(1)['explore'][0]
            assert job['fightCapacity'] == 0 and job['difficulty'] == difficulty
            assert repo.load(1)['star_energy'] == before['star_energy'] - row['PowerConsume']
            assert send(game, 'StartExplore', seq=seq, **req).values == accepted.values
            assert repo.load(1)['star_energy'] == before['star_energy'] - row['PowerConsume']
            assert send(game, 'CancelExplore', seq=seq+1, exploreId=0).values['code'] == 10
            # 达到或超过 50% 线的队伍行为不变。
            power[0] = (target + 1) // 2
            assert send(game, 'StartExplore', seq=seq+2, **req).values['code'] == 10
            assert send(game, 'CancelExplore', seq=seq+3, exploreId=0).values['code'] == 10
            assert repo.load(1)['star_energy'] == before['star_energy']
            seq += 4


def test_real_computed_hero_in_half_to_full_band_can_start(game):
    from x2server.player.college_power import hero_power
    hid = funded(game)
    store, clock, repo, service, _ = game
    hero = next(h for h in store.get(1)['snapshot']['heroes'] if h['id'] == hid)
    power = hero_power(store, 1, hero, clock)
    candidate = next((r, d) for r in service.jobs.explores.values()
                     for d, target in enumerate(r['Conditon']) if (target+1)//2 <= power < target)
    row, difficulty = candidate
    state = repo.load(1)
    state['ruins'] = [r for r in state['ruins'] if r['ruinId'] != row['ID']]
    state['ruins'].append({'ruinId': row['ID'], 'exp': row['Exp'][-1], 'queueCount': 0})
    repo.save(1, state)
    result = send(game, 'StartExplore', seq=200, exploreId=0, ruinId=row['ID'], heroIds=[hid], diffdifficulty=difficulty)
    assert result.values['code'] == 10
    job = EXPLORE_DATA.decode(repo.growth_base(1)['exploreList'][0])
    assert job['fightCapacity'] == power


def test_team_power_is_sum_of_owned_heroes_and_cost_charged_once(game, monkeypatch):
    hid = funded(game)
    store, _, repo, service, _ = game
    snapshot = store.get(1)['snapshot']
    snapshot['heroes'].append({'id': 1004, 'level': 1, 'star': 1, 'state': 2})
    service.jobs.economy.save_snapshot(1, snapshot)
    monkeypatch.setattr('x2server.player.college_power.hero_power', lambda *args: 25)
    result = send(game, 'StartExplore', seq=301, exploreId=0, ruinId=34001, heroIds=[hid, 1004])
    assert result.values['code'] == 10
    state = repo.load(1)
    assert state['explore'][0]['fightCapacity'] == 50
    assert state['star_energy'] == 200 - service.jobs.explores[34001]['PowerConsume']
    assert send(game, 'StartExplore', seq=302, exploreId=0, ruinId=34001, heroIds=[hid, 1004]).values['code'] == 55
    assert repo.load(1)['star_energy'] == state['star_energy']


def test_stale_explore_id_starts_in_a_free_queue_row(game, monkeypatch):
    """Stale row selection uses an idle row without unlocking extra queues."""
    hid = funded(game)
    store, _, repo, service, _ = game
    state=repo.load(1)
    next(r for r in state['buildings'] if r['buildingId']==705)['buildingStar']=2
    repo.save(1,state)
    monkeypatch.setattr('x2server.player.college_power.hero_power', lambda *args: 60)
    assert send(game, 'StartExplore', seq=601, exploreId=0, ruinId=34001, heroIds=[hid]).values['code'] == 10
    snapshot = store.get(1)['snapshot']
    snapshot['heroes'].append({'id': 1004, 'level': 1, 'star': 1, 'state': 2})
    service.jobs.economy.save_snapshot(1, snapshot)
    assert send(game, 'StartExplore', seq=602, exploreId=0, ruinId=34001, heroIds=[1004]).values['code'] == 10
    assert sorted(j['exploreId'] for j in repo.load(1)['explore']) == [0, 1]


def test_start_still_checks_ownership_and_unlocked_difficulty(game, monkeypatch):
    hid = funded(game)
    monkeypatch.setattr('x2server.player.college_power.hero_power', lambda *args: 999999)
    assert send(game, 'StartExplore', seq=401, exploreId=0, ruinId=34001, heroIds=[9999]).values['code'] == 13
    assert send(game, 'StartExplore', seq=402, exploreId=0, ruinId=34001, heroIds=[hid, hid]).values['code'] == 13
    # 普通难度要遗迹经验点亮 ExploreEffect 类型 2 的第二档; 经验 0 时只开简单。
    assert send(game, 'StartExplore', seq=403, exploreId=0, ruinId=34001, heroIds=[hid], diffdifficulty=1).values['code'] == 13
    assert not game[2].load(1)['explore']


def test_low_power_estimate_never_blocks_and_atomic_start_failure(game, monkeypatch):
    hid = funded(game)
    store, _, repo, service, _ = game
    row = deepcopy(service.jobs.explores[34001])
    row['Conditon'] = [101, 201, 301]
    monkeypatch.setitem(service.jobs.explores, 34001, row)
    power = [50]
    monkeypatch.setattr('x2server.player.college_power.hero_power', lambda *args: power[0])
    req = dict(exploreId=0, ruinId=34001, heroIds=[hid])
    # 50 < ceil(101/2) 只是估算偏低, 不能挡住出发。
    assert send(game, 'StartExplore', seq=501, **req).values['code'] == 10
    assert repo.load(1)['explore'][0]['fightCapacity'] == 50
    assert send(game, 'CancelExplore', seq=502, exploreId=0).values['code'] == 10
    before = repo.load(1)
    snapshot = store.get(1)
    def receipts():
        return store.db.execute('SELECT count(*) FROM college_job_receipts').fetchone()[0]
    already = receipts()
    def fail(*args):
        raise RuntimeError('injected queue persistence failure')
    monkeypatch.setattr(repo, 'save', fail)
    import pytest
    with pytest.raises(RuntimeError, match='injected queue'):
        send(game, 'StartExplore', seq=503, **req)
    assert repo.load(1) == before
    assert store.get(1) == snapshot
    assert receipts() == already


def test_explore_visible_slots_follow_official_building_star_effects(game):
    funded(game)
    _,_,repo,service,_=game
    state=repo.load(1)
    gate=next(r for r in state['buildings'] if r['buildingId']==705)
    for star in range(1,len(repo.catalog.buildings[705]['StarID'])+1):
        gate['buildingStar']=star
        slots=list(map(EXPLORE_DATA.decode,repo.jobs_wire(state,'explore')))
        capacity=repo.catalog.effect(state,705,1,star=True)[0]
        assert [s['exploreStatus'] for s in slots]==[1]*capacity+[0]*(6-capacity)
