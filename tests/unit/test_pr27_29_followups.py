"""Customer identity and completion credits must survive refresh and boundaries."""
from datetime import datetime
import pytest

from tests.unit.test_college_upgrade import game
from tests.unit.test_college_alchemy import send
from tests.unit.test_college_jobs import funded
from tests.unit.test_college_pray import setup, send as pray
from x2server.player.college import CollegeService
from x2server.player.task_calendar import BEIJING


def orders(service):
    return [service._customer_for(1, pos) for pos in range(5)]


def progress(economy, task):
    economy.ensure_periods(1)
    return economy.store.db.execute(
        'SELECT progress FROM economy_tasks WHERE player_id=1 AND task_id=?', (task,)).fetchone()[0]


def test_customer_refusals_leave_all_other_positions_and_orders_unchanged(game):
    _, _, repo, service, _ = game
    for sequence in range(1, 46):
        before = orders(service)
        pos = sequence % 5
        assert send(game, 'AlchemyFinish', seq=sequence, type=2, posIndex=pos).values['code'] == 10
        after = orders(service)
        assert all(before[i] == after[i] for i in range(5) if i != pos)
        assert before[pos]['questId'] != after[pos]['questId']
        assert len({r['param'] for r in after}) == 5
        assert orders(CollegeService(repo, economy=service.alchemy.economy)) == after


def test_customer_suggestion_persists_across_main_queries_and_expires_next_day(game):
    _, clock, repo, service, _ = game
    funded(game)
    before = orders(service)
    assert send(game, 'AlchemyButtonClick', seq=1, type=1, posIndex=0).values['code'] == 10
    suggested = orders(service)
    assert suggested[0]['itemId'] == [before[0]['adviseItemId']]
    assert suggested[1:] == before[1:]
    service._alchemy_main(1)
    assert orders(service) == suggested
    state = repo.load(1)
    state['alchemy'].pop('customer_day')
    state['alchemy'].pop('customer_positions')
    repo.save(1, state)
    assert orders(service)[0] == suggested[0]  # legacy suggested order adoption
    clock.value += 86400
    changed = orders(service)
    assert changed != suggested and len({r['param'] for r in changed}) == 5
    assert repo.load(1)['alchemy']['customer_orders'] == {}


@pytest.mark.parametrize('kind', ['train', 'pray'])
def test_completed_jobs_count_only_on_collection_across_day_and_week(game, kind):
    store, clock, _, service, _ = game
    clock.value = int(datetime(2026, 10, 12, 4, 30, tzinfo=BEIJING).timestamp())
    if kind == 'train':
        hero = funded(game)
        start = lambda seq: send(game, 'StartTrain', seq=seq, trainId=0, heroId=hero)
        cancel = lambda seq: send(game, 'CancelTrain', seq=seq, trainId=0)
        finish = lambda seq: send(game, 'FinishTrain', seq=seq, trainId=0)
        daily, weekly = 630008, 630108
    else:
        setup(game)
        start = lambda seq: pray(game, 'BuildStartPrayGod', seq=seq, heroId=1003)
        cancel = lambda seq: pray(game, 'BuildCancelPrayGod', seq=seq)
        finish = lambda seq: pray(game, 'BuildRewardPrayGod', seq=seq)
        daily, weekly = 630006, 630112
    e = service.jobs.economy
    assert start(1).values['code'] == 10
    assert progress(e, daily) == progress(e, weekly) == 0
    assert cancel(2).values['code'] == 10
    assert progress(e, daily) == progress(e, weekly) == 0
    assert start(3).values['code'] == 10
    clock.value += 86400
    assert progress(e, daily) == progress(e, weekly) == 0
    claim = finish(4)
    assert claim.values['code'] == 10
    assert progress(e, daily) == progress(e, weekly) == 1
    assert finish(4).values == claim.values
    assert finish(5).values['code'] == 13
    assert progress(e, daily) == progress(e, weekly) == 1
