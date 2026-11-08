"""Native achievement rows index GiftGroup with stage, independently of status."""
import pytest

from tests.unit.test_origin_season import env
from tests.unit.test_season_progress_rewards import call
from x2server.messages.season import SEASON_SCHEMAS
from x2server.player.season import SeasonService


def page(service, group, start=0):
    reply = call(service, 'SeasonAchvDetialData',
                 {'achvType': group, 'startIndex': start, 'endIndex': start + 30}, 800 + start + group)
    if reply.values['code'] == 97:
        return []  # Native GetDetailData skips the list on the terminal reply.
    assert reply.values['code'] == 10
    return [SEASON_SCHEMAS['SeasonAchvData'].decode(raw)
            for raw in reply.values.get('achvDataList', [])]


def check_native_reward_index(service, rows):
    for row in rows:
        # BattlePassAchievement.InitAchievement at 0x1808554..0x1808574.
        groups = service.achievements[row['achvId']]['GiftGroup']
        assert 0 <= row.get('stage', 0) < len(groups), row
        assert groups[row.get('stage', 0)]


def test_claimed_achievement_reload_has_valid_reward_index_and_cannot_pay_twice(env):
    _, e, s = env
    aid = 6007123
    with e.transaction():
        state = s.state(1)
        state['achievement_floors'][str(aid)] = 50
        s.write(1, state)
    group = s.achievements[aid]['AchievementGroup']['value']
    check_native_reward_index(s, page(s, group))
    assert call(s, 'SeasonAchvReward', {'achvId': aid}, 900).values['code'] == 10
    s = SeasonService(e, enabled=True)
    rows = page(s, group)
    check_native_reward_index(s, rows)
    target = next(r for r in rows if r['achvId'] == aid)
    assert target['status'] == 2 and target.get('stage', 0) == 0
    assert call(s, 'SeasonAchvReward', {'achvId': aid}, 901).values['code'] == 13


@pytest.mark.parametrize('group', [1, 2, 3])
def test_every_claimed_achievement_page_keeps_native_gift_index_in_range(env, group):
    _, e, s = env
    with e.transaction():
        state = s.state(1)
        state['achievements_claimed'] = list(s.achievements)
        s.write(1, state)
    expected = {aid for aid, row in s.achievements.items()
                if row['AchievementGroup']['value'] == group}
    seen = []
    for start in range(0, len(expected) + 30, 30):
        rows = page(s, group, start)
        check_native_reward_index(s, rows)
        assert all(r['status'] == 2 for r in rows)
        seen.extend(r['achvId'] for r in rows)
    assert len(seen) == len(set(seen)) and set(seen) == expected
