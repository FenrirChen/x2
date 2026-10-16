"""XP regression: bound combat team, receipts, training curve and costs."""
import asyncio
import json
import pytest

from tests.unit.test_economy import env, checkout
from tests.unit.test_battle import packet, request
from tests.unit.test_college_upgrade import game
from tests.unit.test_college_jobs import funded
from tests.unit.test_college_alchemy import send
from x2server.messages.battle import PROFILE_HERO
from x2server.messages.core import HERO_DATA
from x2server.player.battle import BattleService
from x2server.player.progression import ProgressionService
from x2server.player.hero_experience import add_hero_exp
from x2server.player.store import PlayerStore


def test_battle_xp_and_favor_reply_push_replay_and_restart(env):
    store, e, ctx = env
    battle = BattleService(store, e)
    assert asyncio.run(battle.enter(ctx, packet(request()))).values['result'] == 10
    result = asyncio.run(battle.checkout(ctx, checkout()))
    assert result.values['result'] == 10
    assert result.values['heroLevel'] == [2]
    assert result.values['heroExp'] == [0]
    assert result.values['heroUpLevelNum'] == [1]
    assert result.values['heroAddFavorExp'] == [1]
    assert store.get(1)['snapshot']['hero_exp'] == 120  # Shared reward still exists.
    hero = store.get(1)['snapshot']['heroes'][0]
    assert (hero['level'], hero.get('exp', 0)) == (2, 0)
    pushed = next(p for p in result.before_response if p.message_name == 'L2C_HeroUpdate')
    assert HERO_DATA.decode(pushed.values['heros'][0])['level'] == 2
    assert asyncio.run(battle.checkout(ctx, checkout())).values == result.values
    assert store.get(1)['snapshot']['heroes'][0] == hero
    reopened = PlayerStore(store.path)
    try:
        assert reopened.get(1)['snapshot']['heroes'][0] == hero
    finally:
        reopened.close()


def test_only_bound_owned_heroes_receive_xp(env):
    store, e, ctx = env
    with e.transaction():
        snap = store.get(1)['snapshot']
        snap['heroes'].extend([
            {'id': 1004, 'state': 2, 'level': 1, 'star': 1},
            {'id': 1005, 'state': 2, 'level': 1, 'star': 1}])
        e.save_snapshot(1, snap)
    battle = BattleService(store, e)
    req = request()
    req['heros'].append(PROFILE_HERO.encode({'heroId': 1004}))
    assert asyncio.run(battle.enter(ctx, packet(req))).values['result'] == 10
    assert asyncio.run(battle.checkout(ctx, checkout())).values['result'] == 10
    heroes = {h['id']: h for h in store.get(1)['snapshot']['heroes']}
    assert heroes[1003]['level'] == heroes[1004]['level'] == 2
    assert heroes[1005]['level'] == 1 and heroes[1005].get('exp', 0) == 0


def test_defeat_does_not_award_hero_xp(env):
    store, e, ctx = env
    battle = BattleService(store, e)
    asyncio.run(battle.enter(ctx, packet(request())))
    assert asyncio.run(battle.checkout(ctx, checkout(False))).values['result'] == 10
    assert store.get(1)['snapshot']['heroes'][0]['level'] == 1
    assert store.get(1)['snapshot']['heroes'][0].get('exp', 0) == 0


def test_hero_xp_rollback_with_settlement_failure(env, monkeypatch):
    store, e, ctx = env
    battle = BattleService(store, e)
    asyncio.run(battle.enter(ctx, packet(request())))
    before = store.get(1)
    def fail(*args):
        raise RuntimeError('after hero XP')
    monkeypatch.setattr(battle.favor_service, 'battle', fail)
    with pytest.raises(RuntimeError, match='after hero XP'):
        asyncio.run(battle.checkout(ctx, checkout()))
    assert store.get(1) == before
    assert store.db.execute('SELECT count(*) FROM battle_receipts').fetchone()[0] == 0
    assert store.db.execute('SELECT settled FROM economy_runs').fetchone()[0] == 0


def test_trial_and_free_no_reward_modes_do_not_farm_xp(env):
    store, e, _ = env
    xp = BattleService(store, e).hero_experience
    for section, team in [(2110607, [1303]), (2110607, [1003])]:
        with e.transaction():
            run = str(section) + str(team)
            store.db.execute('INSERT INTO battle_entries(player_id,request_key,uuid,created_at,response,team_json) VALUES (1,?,?,0,?,?)',
                             (run, run, b'', json.dumps(team)))
            assert xp.battle(1, run, section) == {}


def test_paid_stamina_fallback_uses_authoritative_cost_only(env):
    store, e, _ = env
    xp = BattleService(store, e).hero_experience
    section = next(s for s, c in e.entry_catalog.sections.items() if not c.get('VReward') and c['Type'] != 5)
    with e.transaction():
        store.db.execute('INSERT INTO battle_costs(uuid,player_id,amount) VALUES (?,1,7)', ('paid-xp',))
        assert xp.gain_for(1, 'paid-xp', section) == 140
        assert xp.gain_for(2, 'paid-xp', section) == 0
        store.db.execute('UPDATE battle_costs SET refunded=1 WHERE uuid=?', ('paid-xp',))
        assert xp.gain_for(1, 'paid-xp', section) == 0


@pytest.mark.parametrize('building_level,expected', [(1, 500), (2, 800), (10, 4000), (30, 12000)])
def test_training_uses_building_experience_and_legacy_job_fix(game, building_level, expected):
    hid = funded(game)
    store, clock, repo, _, _ = game
    state = repo.load(1)
    next(b for b in state['buildings'] if b['buildingId'] == 704)['buildingLevel'] = building_level
    repo.save(1, state)
    start = send(game, 'StartTrain', trainId=0, heroId=hid)
    assert start.values['code'] == 10
    state = repo.load(1)
    assert state['training'][0]['gain_exp'] == expected
    # Existing jobs still carry the old 25% number; buildID is their start row.
    state['training'][0]['gain_exp'] = 30
    next(b for b in state['buildings'] if b['buildingId'] == 704)['buildingLevel'] = 30
    repo.save(1, state)
    clock.value = start.values['trainEndTime']
    result = send(game, 'FinishTrain', seq=2, trainId=0)
    assert result.values['code'] == 10 and result.values['gainExp'] == expected
    assert send(game, 'FinishTrain', seq=2, trainId=0).values == result.values
    assert send(game, 'FinishTrain', seq=3, trainId=0).values['code'] == 13


def test_training_caps_at_account_level_and_preserves_existing_xp(game):
    hid = funded(game)
    store, clock, repo, _, _ = game
    snap = store.get(1)['snapshot']
    snap['level'] = 2
    snap['heroes'][0]['exp'] = 110
    game[3].jobs.economy.save_snapshot(1, snap)
    start = send(game, 'StartTrain', trainId=0, heroId=hid)
    assert start.values['code'] == 10
    clock.value = start.values['trainEndTime']
    done = send(game, 'FinishTrain', seq=2, trainId=0)
    assert done.values['gainExp'] == 10
    assert done.values['heroLevel'] == 2 and done.values['heroExp'] == 0


def test_shared_xp_curve_multilevel_and_cap():
    hero = {'level': 1, 'exp': 110}
    assert add_hero_exp(hero, 500, 4) == 310
    assert hero == {'level': 4, 'exp': 0}
    assert add_hero_exp(hero, 9999, 4) == 0
    legacy = {'level': 4, 'exp': 22}
    assert add_hero_exp(legacy, 9999, 4) == 0 and legacy['exp'] == 22


def test_manual_level_up_only_pays_missing_xp(env):
    store, e, ctx = env
    with e.transaction():
        snap = store.get(1)['snapshot']
        snap['heroes'][0]['exp'] = 110
        snap['hero_exp'] = 10
        e.save_snapshot(1, snap)
    service = ProgressionService(store, e)
    req = packet({'id': 1003, 'opt': 1}, 51, 'C2L_HeroOpt')
    result = asyncio.run(service.handle(ctx, req))
    assert result.values['code'] == 10
    hero = store.get(1)['snapshot']['heroes'][0]
    assert hero['level'] == 2 and hero['exp'] == 0
    assert store.get(1)['snapshot']['hero_exp'] == 0
    assert asyncio.run(service.handle(ctx, req)).values == result.values
    assert store.get(1)['snapshot']['heroes'][0] == hero


def test_max_level_hero_receives_no_new_xp_but_other_hero_levels(env):
    store, e, ctx = env
    with e.transaction():
        snap = store.get(1)['snapshot']
        snap['heroes'][0].update(level=60, exp=22)
        snap['heroes'].append({'id': 1004, 'state': 2, 'level': 1, 'star': 1})
        e.save_snapshot(1, snap)
    battle = BattleService(store, e)
    req = request()
    req['heros'].append(PROFILE_HERO.encode({'heroId': 1004}))
    assert asyncio.run(battle.enter(ctx, packet(req))).values['result'] == 10
    done = asyncio.run(battle.checkout(ctx, checkout()))
    assert done.values['heroLevel'] == [60, 2]
    assert done.values['heroExp'] == [22, 0]
    assert done.values['heroFullLevel'] == [True, False]


def test_manual_level_keeps_legacy_surplus_instead_of_charging_twice(env):
    store, e, ctx = env
    with e.transaction():
        snap = store.get(1)['snapshot']
        snap['heroes'][0]['exp'] = 150
        snap['hero_exp'] = 0
        e.save_snapshot(1, snap)
    done = asyncio.run(ProgressionService(store, e).handle(
        ctx, packet({'id': 1003, 'opt': 1}, 91, 'C2L_HeroOpt')))
    assert done.values['code'] == 10
    assert store.get(1)['snapshot']['hero_exp'] == 0
    assert store.get(1)['snapshot']['heroes'][0]['exp'] == 30
