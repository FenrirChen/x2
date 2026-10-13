import pytest
from tests.unit.test_economy import env
from tests.unit.test_world_boss import admit_fixture


def test_bound_boss_rejected_team_change_has_no_side_effect(env):
    store, e, ctx = env
    bid = admit_fixture(e, 2140101)
    with e.transaction():
        store.db.execute("UPDATE world_boss_members SET run_id='existing-run' WHERE boss_id=?", (bid,))
    before = dict(store.db.execute('SELECT * FROM world_boss_members WHERE boss_id=?', (bid,)).fetchone())
    with pytest.raises(ValueError):
        e.world_boss.battle_admission(1, 2140101, [1004])
    after = dict(store.db.execute('SELECT * FROM world_boss_members WHERE boss_id=?', (bid,)).fetchone())
    assert after == before


def test_boss_admission_validates_without_writing_team(env):
    store, e, ctx = env
    bid = admit_fixture(e, 2140101)
    with e.transaction():
        store.db.execute('UPDATE world_boss_runs SET state=1 WHERE boss_id=?', (bid,))
    assert e.world_boss.battle_admission(1, 2140101, [1004]) == bid
    assert store.db.execute('SELECT team FROM world_boss_members WHERE boss_id=?', (bid,)).fetchone()[0] == '[1003]'
    assert e.world_boss.get_boss(bid)['state'] == 1


def test_boss_entry_adopts_selected_team_only_on_success(env):
    from tests.unit.test_battle import packet, request
    from x2server.player.battle import BattleService
    from x2server.messages.battle import PROFILE_HERO
    store, e, ctx = env
    p = store.get(1)
    heroes = list(p['snapshot']['heroes']) + [{'id': 1004, 'state': 2, 'level': 1, 'star': 1}]
    store.save_snapshot(1, dict(p['snapshot'], heroes=heroes), p['revision'])
    bid = admit_fixture(e, 2140101)
    with e.transaction():
        store.db.execute('UPDATE world_boss_runs SET state=1 WHERE boss_id=?', (bid,))
    battle = BattleService(store, e)
    row = battle.catalog.sections[2140101]
    values = request()
    values.update(missionId=2140101, chapter=row['ChapterID'], sceneId=row['Maps'][0],
        heros=[PROFILE_HERO.encode({'heroId':1004, 'leader':1})])
    coro = battle.enter(ctx, packet(values))
    try:
        coro.send(None)
    except StopIteration as done:
        answer = done.value
    finally:
        coro.close()
    assert answer.values['result'] == 10
    member = store.db.execute('SELECT team,run_id FROM world_boss_members WHERE boss_id=?', (bid,)).fetchone()
    assert member['team'] == '[1004]' and member['run_id'] == answer.values['uuid']
    assert e.world_boss.get_boss(bid)['state'] == 2


def test_boss_avatar_id_uses_picture_catalog():
    from x2server.player.world_boss import head_icon_of
    assert head_icon_of(1003) == 1270301
