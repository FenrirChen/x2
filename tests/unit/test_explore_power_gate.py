"""Chinese native exploration gate uses 50% of CollegeExplore.Conditon."""
from copy import deepcopy

from tests.unit.test_college_upgrade import game
from tests.unit.test_college_jobs import funded
from tests.unit.test_college_alchemy import send
from x2server.messages.lobby import EXPLORE_DATA


def test_every_ruin_and_difficulty_native_half_power_boundary(game, monkeypatch):
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
            minimum = (target + 1) // 2
            req = dict(exploreId=0, ruinId=rid, heroIds=[hid], diffdifficulty=difficulty)
            before = repo.load(1)
            power[0] = minimum - 1
            refused = send(game, 'StartExplore', seq=seq, **req)
            assert refused.values['code'] == 186, (rid, difficulty, refused.values)
            assert repo.load(1)['star_energy'] == before['star_energy']
            assert not repo.load(1)['explore']
            assert next(h for h in store.get(1)['snapshot']['heroes'] if h['id'] == hid).get('college_status', 0) == 0
            power[0] = minimum
            accepted = send(game, 'StartExplore', seq=seq+1, **req)
            assert accepted.values['code'] == 10, (rid, difficulty, accepted.values)
            job = repo.load(1)['explore'][0]
            assert job['fightCapacity'] == minimum and job['difficulty'] == difficulty
            assert repo.load(1)['star_energy'] == before['star_energy'] - row['PowerConsume']
            assert send(game, 'StartExplore', seq=seq+1, **req).values == accepted.values
            assert repo.load(1)['star_energy'] == before['star_energy'] - row['PowerConsume']
            assert send(game, 'CancelExplore', seq=seq+2, exploreId=0).values['code'] == 10
            seq += 3


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
    assert send(game, 'StartExplore', seq=302, exploreId=0, ruinId=34001, heroIds=[hid, 1004]).values['code'] == 13
    assert repo.load(1)['star_energy'] == state['star_energy']


def test_rejected_gate_still_checks_ownership_and_unlocked_difficulty(game, monkeypatch):
    hid = funded(game)
    monkeypatch.setattr('x2server.player.college_power.hero_power', lambda *args: 999999)
    assert send(game, 'StartExplore', seq=401, exploreId=0, ruinId=34001, heroIds=[9999]).values['code'] == 13
    assert send(game, 'StartExplore', seq=402, exploreId=0, ruinId=34001, heroIds=[hid, hid]).values['code'] == 13
    assert send(game, 'StartExplore', seq=403, exploreId=0, ruinId=34001, heroIds=[hid], diffdifficulty=1).values['code'] == 13
    assert not game[2].load(1)['explore']


def test_gate_odd_threshold_rounds_up_and_atomic_start_failure(game, monkeypatch):
    hid = funded(game)
    store, _, repo, service, _ = game
    row = deepcopy(service.jobs.explores[34001])
    row['Conditon'] = [101, 201, 301]
    monkeypatch.setitem(service.jobs.explores, 34001, row)
    power = [50]
    monkeypatch.setattr('x2server.player.college_power.hero_power', lambda *args: power[0])
    req = dict(exploreId=0, ruinId=34001, heroIds=[hid])
    assert send(game, 'StartExplore', seq=501, **req).values['code'] == 186
    before = repo.load(1)
    snapshot = store.get(1)
    power[0] = 51
    def fail(*args):
        raise RuntimeError('injected queue persistence failure')
    monkeypatch.setattr(repo, 'save', fail)
    import pytest
    with pytest.raises(RuntimeError, match='injected queue'):
        send(game, 'StartExplore', seq=502, **req)
    assert repo.load(1) == before
    assert store.get(1) == snapshot
    assert store.db.execute('SELECT count(*) FROM college_job_receipts').fetchone()[0] == 0
