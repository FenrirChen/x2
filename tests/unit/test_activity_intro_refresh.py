from tests.activity_calendar_helpers import activity_start, next_activity_cycle
"""The native preview gate must stay closed after a completed single intro."""
import asyncio
import pytest

from tests.unit.test_activity_runtime import runtime
from tests.unit.test_economy import env
from tests.unit.test_battle import packet
from x2server.player.activity_rotation import ActivityRotation
from x2server.player.activity import ActivityService
from x2server.player.activity_runtime import ActivityRuntime
from x2server.player.mail import MailService
from x2server.messages.activity import ACTIVITY_SCHEMAS


def native_refresh_after(timestamp):
    # Independent arithmetic from ARM64 ServerTime.GetRefreshTime 0x3e5227c:
    # return timestamp + 86400 - ((timestamp - 18000) % 86400).
    return timestamp + 86400 - ((timestamp - 18000) % 86400)


@pytest.mark.parametrize('theme_index', range(7))
def test_all_theme_intros_survive_native_refresh_query_replay_and_restart(runtime, theme_index):
    store, economy, context, rt, now = runtime
    now[0] = activity_start(theme_index) + 8 * 3600
    family = 2 if rt.r.at().theme['group'] == 7 else 1 if rt.r.at().theme['group'] == 99 else 3
    query = packet({'activityType': family}, 1301, 'C2L_ActivityPreNoticInfo')
    assert asyncio.run(rt.handle(context, query)).values['lastPreNoticSec'] == 0
    claim = packet({'activityType': family}, 1302, 'C2L_ActivityPreNotic')
    first = asyncio.run(rt.handle(context, claim))
    assert first.values['code'] == 10 and first.values.get('rewardData')
    grants = store.db.execute('SELECT COUNT(*) FROM economy_grants').fetchone()[0]
    old = first.values['lastPreNoticSec']
    now[0] = native_refresh_after(old)
    assert now[0] >= native_refresh_after(old)  # old response re-enables native intro
    result = asyncio.run(rt.handle(context, query))  # same cached query, previously zero
    assert now[0] < native_refresh_after(result.values['lastPreNoticSec'])
    replay = asyncio.run(rt.handle(context, claim))
    assert now[0] < native_refresh_after(replay.values['lastPreNoticSec'])
    assert replay.values.get('rewardData') == first.values.get('rewardData')
    assert store.db.execute('SELECT COUNT(*) FROM economy_grants').fetchone()[0] == grants
    restored = ActivityRuntime(ActivityService(economy), MailService(store, economy, economy.clock))
    fresh = packet({'activityType': family}, 1303, 'C2L_ActivityPreNotic')
    response = asyncio.run(restored.handle(context, fresh))
    assert response.values['code'] == 10 and not response.values.get('rewardData')
    assert now[0] < native_refresh_after(response.values['lastPreNoticSec'])
    assert store.db.execute('SELECT COUNT(*) FROM economy_grants').fetchone()[0] == grants
    now[0] = next_activity_cycle(now[0])
    assert restored.a.pre_notice(1, family)['lastPreNoticSec'] == 0
    second_period = restored.r.at()
    # A receipt from the old period may neither mark this intro complete nor
    # pay another reward; a new request/session can claim the new period once.
    assert asyncio.run(restored.handle(context, claim)).values['code'] == 13
    fresh_claim = packet({'activityType': family}, 1312, 'C2L_ActivityPreNotic')
    second = asyncio.run(restored.handle(context, fresh_claim))
    assert second.values['code'] == 10
    assert second.values.get('rewardData') == first.values.get('rewardData')
    second_grants = store.db.execute('SELECT COUNT(*) FROM economy_grants').fetchone()[0]
    assert second_grants > grants
    assert asyncio.run(restored.handle(context, fresh_claim)).values == second.values
    assert store.db.execute('SELECT COUNT(*) FROM economy_grants').fetchone()[0] == second_grants
    now[0] = native_refresh_after(second.values['lastPreNoticSec'])
    if now[0] >= second_period.end:
        now[0] = second_period.end - 1
    acknowledgement = restored.a.pre_notice(1, family, claim=True)
    assert acknowledgement['code'] == 10 and not acknowledgement.get('rewardData')
    assert now[0] < native_refresh_after(acknowledgement['lastPreNoticSec'])
    now[0] = second_period.start + 49 * 86400 + 8 * 3600
    assert restored.a.pre_notice(1, family)['lastPreNoticSec'] == 0
    third = asyncio.run(restored.handle(context, packet({'activityType': family}, 1322,
                                                      'C2L_ActivityPreNotic')))
    assert third.values['code'] == 10 and third.values.get('rewardData')


def test_cached_calendar_query_and_completion_follow_moved_review_start(runtime):
    _, _, context, rt, now = runtime
    query = packet({}, 1401, 'C2L_QueryActivity')
    first = asyncio.run(rt.handle(context, query))
    rows = [ACTIVITY_SCHEMAS['ActivityData'].decode(raw) for raw in first.values['activityData']]
    start = rows[0]['startTime']
    rt.r.anchor += 1800
    now[0] += 1800
    latest = asyncio.run(rt.handle(context, query))
    rows = [ACTIVITY_SCHEMAS['ActivityData'].decode(raw) for raw in latest.values['activityData']]
    assert rows[0]['startTime'] == start + 1800


def test_yuexi_dialogue_replay_does_not_restore_old_refresh_timestamp(runtime):
    store, economy, context, rt, now = runtime
    now[0] = activity_start(6) + 8 * 3600
    query = packet({}, 1501, 'C2L_ActivityDialogReciveInfo')
    assert asyncio.run(rt.handle(context, query)).values['lastReciveTimeSec'] == 0
    claim = packet({}, 1502, 'C2L_ActivityDialogue')
    result = asyncio.run(rt.handle(context, claim))
    grants = store.db.execute('SELECT COUNT(*) FROM economy_grants').fetchone()[0]
    now[0] = native_refresh_after(result.values['lastReciveTimeSec'])
    for request in (query, claim, packet({}, 1503, 'C2L_ActivityDialogue')):
        response = asyncio.run(rt.handle(context, request))
        assert response.values['code'] == 10
        assert now[0] < native_refresh_after(response.values['lastReciveTimeSec'])
    assert store.db.execute('SELECT COUNT(*) FROM economy_grants').fetchone()[0] == grants
