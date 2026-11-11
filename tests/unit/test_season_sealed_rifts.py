import asyncio

import pytest

from tests.unit.test_season_tower_skip import env, setup, enter
from tests.unit.test_battle import packet
from x2server.messages.battle import CHECKOUT
from x2server.messages.core import INT_PAIR
from x2server.player.season import SeasonService


def checkout(battle, ctx, section, row, reports, rid=2, success=True):
    request = packet({'checkout': CHECKOUT.encode({
        'sectionId': section, 'chapterId': row['ChapterID'], 'success': success,
        'fightTime': 300, 'npcEventOnNumber': [INT_PAIR.encode({'Key': k, 'Value': v})
                                             for k, v in reports]})},
        rid, 'C2L_CheckoutMainMissionSign')
    return asyncio.run(battle.checkout(ctx, request)), request


def test_real_checkout_counts_each_rift_and_replay_never_adds_again(env):
    store, economy, season, battle, ctx = setup(env)
    response, sid, row = enter(season, battle, ctx, 10, 1)
    assert response.values['result'] == 10
    response, request = checkout(battle, ctx, sid, row, [
        (68912, 5), (68712, 1), (68901, 10), (68921, 6), (68911, 6), (60001, 7),
        (68912, 5), (68912, -1), (68712, 1001)])
    assert response.values['result'] == 10
    assert season.state(1)['stats']['passes'] == 1
    assert season.state(1)['stats']['sealed_rifts'] == 6
    assert asyncio.run(battle.checkout(ctx, request)).values == response.values
    assert season.state(1)['stats']['sealed_rifts'] == 6
    achievement = next(r for r in season.achievement_values(1) if r['achvId'] == 6007112)
    assert achievement['achvProgress'] == 6
    restored = SeasonService(economy)
    assert restored.state(1)['stats']['sealed_rifts'] == 6


@pytest.mark.parametrize('success,reports', [(False, [(68912, 5)]), (True, [])])
def test_missing_reports_or_failed_battle_do_not_invent_rift_progress(env, success, reports):
    _, _, season, battle, ctx = setup(env)
    entered, sid, row = enter(season, battle, ctx, 10, 1)
    assert entered.values['result'] == 10
    response, _ = checkout(battle, ctx, sid, row, reports, success=success)
    assert response.values['result'] == 10
    assert season.state(1)['stats'].get('sealed_rifts', 0) == 0


def test_existing_progress_is_preserved_without_adding_one_per_new_clear(env):
    _, economy, season, battle, ctx = setup(env)
    with economy.transaction():
        state = season.state(1)
        state['stats']['passes'] = 7
        state['stats'].pop('sealed_rifts', None)
        season.write(1, state)
    entered, sid, row = enter(season, battle, ctx, 10, 1)
    assert entered.values['result'] == 10
    response, _ = checkout(battle, ctx, sid, row, [(68912, 4)])
    assert response.values['result'] == 10
    assert season.state(1)['stats']['sealed_rifts'] == 11
    assert season.state(1)['stats']['passes'] == 8


def test_all_sealing_achievements_use_rifts_and_keep_original_thresholds(env):
    _, _, season = env
    rows = [r for r in season.achievements.values() if '封印裂隙' in r['description']]
    assert len(rows) == 10
    assert {r['rule']['kind'] for r in rows} == {'sealed_rifts'}
    assert sorted(r['rule']['target'] for r in rows) == [1, 50, 100, 150, 200, 250, 300, 350, 400, 450]
