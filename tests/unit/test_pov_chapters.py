"""POV chapters (SectionType 4) settle and keep progress outside the weekly calendar.

The generated activity catalog filters every PointOfView row out, so
POVChapterInfo arrives through data/activity_rotation_extra.json. Permanent
chapters have no UnlockActiviyID and therefore no period of their own; their
progress lives in ActivityService.STATE_PERIOD instead of a rotating one.
"""
import json
from importlib.resources import files

import pytest

from tests.unit.test_economy import env
from x2server.messages.lobby import MISSION_PAIR, MISSION_TYPE
from x2server.player.activity import ActivityPeriod, ActivityService, STATE_PERIOD
from x2server.player.activity_rotation import ActivityRotation


PERMANENT = 2021001       # stages 2121001-2121005, ClearReward 734000
ACTIVITY = 2021023        # stages 2121021-2121024, UnlockActiviyID 70010
PERMANENT_REWARD = {1201010: 10, 1204035: 2}
ACTIVITY_REWARD = {1203010: 3, 1290191: 1, 1237989: 2000}


@pytest.fixture
def activity(env):
    store, economy, ctx = env
    now = [ActivityRotation.ANCHOR]
    economy.clock = lambda: now[0]
    return store, economy, ActivityService(economy), now


def chapter(service, chapter_id):
    return next(c for c in service.tables['POVChapterInfo'] if c['ChapterID'] == chapter_id)


def test_supplement_restores_the_generated_catalog_pov_table(activity):
    _, _, service, _ = activity
    shipped = json.loads(files('x2server').joinpath(
        'data/activity_rotation_catalog.json').read_text(encoding='utf-8'))
    # The exporter only keeps chapters that an activity can open.
    assert sorted(c['ChapterID'] for c in shipped['tables']['POVChapterInfo']) == [
        ACTIVITY, 2021511, 2022711, 2022811]
    chapters = {c['ChapterID']: c for c in service.tables['POVChapterInfo']}
    assert len(chapters) == 21
    assert sorted(chapters) == [
        2021001, 2021002, 2021003, 2021023, 2021501, 2021511, 2021800,
        2021901, 2022001, 2022101, 2022201, 2022701, 2022711, 2022801,
        2022811, 2023001, 2023101, 2023102, 2023201, 2023401, 2023501]
    assert [cid for cid, c in chapters.items() if c.get('UnlockActiviyID')] == [
        ACTIVITY, 2021511, 2022711, 2022811]
    assert all(c['StageID'] and c['ClearReward'] for c in chapters.values())
    # The supplement must not disturb the seven generated themes or their slots.
    assert len(service.rotation.themes) == 7
    assert service.rotation.state_cycle_size == 8


def test_permanent_chapter_settles_before_the_calendar_starts(activity):
    _, economy, service, now = activity
    now[0] = ActivityRotation.ANCHOR - 1
    assert service.rotation.at() is None
    row = chapter(service, PERMANENT)
    with economy.transaction():
        for stage in row['StageID'][:-1]:
            assert service.pov_chapter_rewards(1, stage) == {}
        assert service.pov_chapter_rewards(1, row['StageID'][-1]) == PERMANENT_REWARD
        # The whole-chapter gift is once per chapter, not once per clear.
        assert service.pov_chapter_rewards(1, row['StageID'][-1]) == {}


def test_permanent_chapter_progress_survives_the_next_period(activity):
    _, economy, service, now = activity
    row = chapter(service, PERMANENT)
    sentinel = ActivityPeriod(STATE_PERIOD, 0, 0, {})
    with economy.transaction():
        for stage in row['StageID'][:2]:
            assert service.pov_chapter_rewards(1, stage) == {}
    now[0] = service.rotation.bounds(3)[0]
    period = service.rotation.at()
    assert period.index == 1_000_004
    assert all(service.rotation.get(1, sentinel, 'pov-clear', stage, False)
               for stage in row['StageID'][:2])
    assert not any(service.rotation.get(1, period, 'pov-clear', stage, False)
                   for stage in row['StageID'][:2])
    with economy.transaction():
        for stage in row['StageID'][2:]:
            rewards = service.pov_chapter_rewards(1, stage)
    assert rewards == PERMANENT_REWARD
    now[0] = service.rotation.bounds(9)[0]
    assert service.pov_chapter_rewards(1, row['StageID'][0]) == {}


def test_activity_chapter_only_settles_while_its_activity_runs(activity):
    _, economy, service, now = activity
    row = chapter(service, ACTIVITY)
    sentinel = ActivityPeriod(STATE_PERIOD, 0, 0, {})
    now[0] = service.rotation.bounds(3)[0]
    assert service.rotation.activity(70010) is None
    with economy.transaction():
        for stage in row['StageID']:
            assert service.pov_chapter_rewards(1, stage) == {}
    period = service.rotation.at()
    assert not any(service.rotation.get(1, period, 'pov-clear', stage, False)
                   for stage in row['StageID'])
    assert not any(service.rotation.get(1, sentinel, 'pov-clear', stage, False)
                   for stage in row['StageID'])

    now[0] = service.rotation.bounds(2)[0]
    assert service.rotation.activity(70010) is not None
    assert service.rotation.at().index == 1_000_007
    with economy.transaction():
        for stage in row['StageID'][:-1]:
            assert service.pov_chapter_rewards(1, stage) == {}
        assert service.pov_chapter_rewards(1, row['StageID'][-1]) == ACTIVITY_REWARD
        assert service.pov_chapter_rewards(1, row['StageID'][-1]) == {}


def test_dev_unlock_clears_do_not_pay_the_chapter_reward(activity):
    store, economy, service, _ = activity
    row = chapter(service, PERMANENT)
    with economy.transaction():
        for stage in row['StageID']:
            store.db.execute('INSERT OR IGNORE INTO economy_clears VALUES (?,?,?)',
                             (1, stage, 'unlock'))
    assert store.db.execute("SELECT COUNT(*) FROM economy_clears WHERE player_id=1 "
                            "AND first_uuid='unlock'").fetchone()[0] == len(row['StageID'])
    # whole-chapter ClearReward only follows pov-clear, never an unlocked entry.
    with economy.transaction():
        assert service.pov_chapter_rewards(1, row['StageID'][-1]) == {}
    assert service.rotation.get(1, ActivityPeriod(STATE_PERIOD, 0, 0, {}),
                                'pov-clear', row['StageID'][0], False) is False


def test_pov_clear_is_reported_as_a_type_four_frontier(activity):
    store, economy, _, _ = activity
    with economy.transaction():
        economy.mark_section_cleared(1, 2121001, 'pov-run', 4)
    progress = [MISSION_TYPE.decode(raw) for raw in economy.mission_values(1)['OtherChapter']]
    pov = next(entry for entry in progress if entry['type'] == 4)
    assert MISSION_PAIR.decode(pov['missionData'][0]) == {
        'Key': PERMANENT, 'Value': 2121001}
    # mission_values reads the clear ledger only; no run or settlement is invented.
    assert store.db.execute('SELECT COUNT(*) FROM economy_runs').fetchone()[0] == 0
