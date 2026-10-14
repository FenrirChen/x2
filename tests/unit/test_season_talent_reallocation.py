import asyncio
import pytest
from tests.unit.test_origin_season import env
from tests.unit.test_season_protocol_tasks import ctx
from tests.unit.test_battle import packet
from x2server.messages.season import encode, SEASON_SCHEMAS
from x2server.player.season import SeasonService


def call(s, op, values, rid):
    return asyncio.run(s.handle(ctx(), packet(values, rid, 'C2L_' + op)))


def allocate(s, changes, rid):
    return call(s, 'BattlePassTalentLevel', {'info': [encode('TalentLevel',
        {'id': tid, 'level': n}) for tid, n in changes]}, rid)


def test_reset_then_increment_save_replay_and_relogin(env):
    store, e, s = env
    tid, other = sorted(s.talents)[:2]
    with e.transaction():
        e._grant(1, 'talent-test-points', {1291002: 10})
    assert allocate(s, [(tid, 3), (other, 2)], 1).values['code'] == 10
    before = store.get(1)['snapshot']['crystal']
    reset = call(s, 'BattlePassTalentReset', {'id': tid}, 2)
    assert reset.values['code'] == 10
    assert reset.values['leftPoint'] == 8
    assert store.get(1)['snapshot']['crystal'] == before - 3 * s.activities[0]['ActivityParam3'][0]
    assert call(s, 'BattlePassTalentReset', {'id': tid}, 2).values == reset.values
    assert s.state(1)['talents'][str(other)] == 2
    assert allocate(s, [(tid, 1)], 3).values['code'] == 10
    # Existing talent receives one additional point, not final level one.
    result = allocate(s, [(tid, 1), (other, 1)], 4)
    assert result.values['code'] == 10
    levels = {r['id']: r['level'] for r in map(SEASON_SCHEMAS['TalentInfo'].decode, result.values['info'])}
    assert levels[tid] == 2 and levels[other] == 3
    assert result.values['leftPoint'] == 5
    assert allocate(s, [(tid, 1), (other, 1)], 4).values == result.values
    new = SeasonService(e, enabled=True, instance=s.instance)
    assert new.talent_values(1) == s.talent_values(1)
    assert new.attributes(1) == s.attributes(1)


@pytest.mark.parametrize('mode', ['negative', 'over-max', 'over-budget', 'duplicate'])
def test_invalid_increment_is_atomic(env, mode):
    store, e, s = env
    tid = min(s.talents)
    with e.transaction():
        e._grant(1, 'talent-test-points', {1291002: 2})
    before = s.state(1)
    changes = {'negative': [(tid, -1)], 'over-max': [(tid, s.talents[tid]['MaxLevel'] + 1)],
        'over-budget': [(tid, 3)], 'duplicate': [(tid, 1), (tid, 1)]}[mode]
    assert allocate(s, changes, 10).values['code'] == 13
    assert s.state(1) == before


def test_undone_pending_points_do_not_block_other_talent(env):
    _, e, s = env
    tid, other = sorted(s.talents)[:2]
    with e.transaction():
        e._grant(1, 'talent-test-points', {1291002: 4})
    assert allocate(s, [(tid, 2)], 1).values['code'] == 10
    assert allocate(s, [(tid, 0), (other, 1)], 2).values['code'] == 10
    assert s.state(1)['talents'][str(tid)] == 2
    assert s.state(1)['points'] == 1
