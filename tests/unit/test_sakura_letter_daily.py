import json
from datetime import datetime, timedelta, timezone
import pytest

from tests.unit.test_economy import env
from x2server.player.daily_pickups import limits
from x2server.player.economy import UnresolvedEconomy


@pytest.fixture
def letters(env, monkeypatch):
    store, economy, ctx = env
    from x2server.player.battle import BattleService
    BattleService(store, economy)
    now = [int(datetime(2026, 10, 19, 23, 59, 59, tzinfo=timezone(timedelta(hours=8))).timestamp())]
    economy.clock = lambda: now[0]
    monkeypatch.setattr('x2server.player.economy.time.time', lambda: now[0])
    return store, economy, now


def grant(e, source, values):
    with e.transaction():
        return e._grant(1, source, values)


def quantity(store, item):
    r = store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?', (item,)).fetchone()
    return r[0] if r else 0


@pytest.mark.parametrize('item', [1104008, 1104027])
def test_letter_cap_is_cumulative_and_retry_safe(letters, item):
    store, e, now = letters
    assert limits()[item] == 10
    assert grant(e, 'battle:one', {item: 7}) == {item: 7}
    assert grant(e, 'battle:two', {item: 8}) == {item: 3}
    assert grant(e, 'battle:two', {item: 8}) == {item: 3}
    assert grant(e, 'sweep:three', {item: 100, 1237901: 20}) == {1237901: 20}
    assert quantity(store, item) == 10
    # Opening/spending letters cannot restore the daily pickup quota.
    with store.db:
        store.db.execute('UPDATE inventory SET quantity=0 WHERE player_id=1 AND item_id=?', (item,))
    assert grant(e, 'battle:four', {item: 1}) == {}
    now[0] += 1  # Beijing midnight.
    assert grant(e, 'battle:tomorrow', {item: 100}) == {item: 10}
    assert quantity(store, item) == 10
    assert store.db.execute("SELECT count(*) FROM activity_state WHERE namespace='daily-pickups'").fetchone()[0] == 1


@pytest.mark.parametrize('old_count,expected', [(8, 2), (40, 0)])
def test_upgrade_counts_already_opened_letters(letters, old_count, expected):
    store, e, now = letters
    with store.db:
        store.db.execute('INSERT INTO economy_grants VALUES (1,?,?,?)',
                         ('battle:legacy', json.dumps({'1104008': old_count}), now[0] - 60))
        # Yesterday and mail grants must not consume today's pickup quota.
        store.db.execute('INSERT INTO economy_grants VALUES (1,?,?,?)',
                         ('battle:yesterday', '{"1104008":100}', now[0] - 86400))
        store.db.execute('INSERT INTO economy_grants VALUES (1,?,?,?)',
                         ('mail:today', '{"1104008":100}', now[0]))
    result = grant(e, 'battle:after-upgrade', {1104008: 20})
    assert result == ({1104008: expected} if expected else {})
    assert quantity(store, 1104008) == expected


def test_letter_counters_rollback_and_survive_service_recreation(letters):
    store, e, now = letters
    with pytest.raises(UnresolvedEconomy):
        grant(e, 'battle:invalid', {1104008: 8, -1: 1})
    assert quantity(store, 1104008) == 0
    assert grant(e, 'battle:valid', {1104008: 8, 1104027: 9}) == {1104008: 8, 1104027: 9}
    from x2server.player.economy import EconomyService
    recreated = EconomyService(store, clock=lambda: now[0])
    assert grant(recreated, 'battle:restart', {1104008: 8, 1104027: 8}) == {1104008: 2, 1104027: 1}
    assert grant(recreated, 'mail:admin', {1104008: 2}) == {1104008: 2}


def test_sakura_real_checkout_caps_rewards_and_still_settles(letters):
    import asyncio
    from tests.unit.test_battle import packet
    from tests.unit.test_economy import rewards as decode_rewards
    from x2server.messages.battle import CHECKOUT, PROFILE_HERO, OUTSIDE_ITEM
    from x2server.player.activity import ActivityService
    from x2server.player.activity_runtime import ActivityRuntime
    from x2server.player.battle import BattleService
    from x2server.player.mail import MailService
    store, e, now = letters
    from x2server.network.dispatcher import DispatchContext
    from x2server.network.session import SessionState
    ctx = DispatchContext('sakura-test', 'local', SessionState('test', 'session', player_id=1))
    e.activity = ActivityService(e)
    ActivityRuntime(e.activity, MailService(store, e, e.clock))
    battle = BattleService(store, e)
    row = battle.catalog.sections[2161021]
    for sequence, expected in enumerate((7, 3, 0), 1):
        entry = asyncio.run(battle.enter(ctx, packet({'missionId': row['SectionID'],
            'chapter': row['ChapterID'], 'sceneId': row['Maps'][0],
            'heros': [PROFILE_HERO.encode({'heroId': 1003, 'leader': 1})]}, sequence * 10)))
        assert entry.values['result'] == 10
        request = packet({'checkout': CHECKOUT.encode({'chapterId': row['ChapterID'],
            'sectionId': row['SectionID'], 'success': True, 'fightTime': 200,
            'outsideItems': [OUTSIDE_ITEM.encode({'id': 1104027, 'num': 7})]})},
            sequence * 10 + 1, name='C2L_CheckoutMainMissionSign')
        result = asyncio.run(battle.checkout(ctx, request))
        assert result.values['result'] == 10
        assert decode_rewards(result.values['rewardData']).get(1104027, 0) == expected
        assert asyncio.run(battle.checkout(ctx, request)).values == result.values
    assert quantity(store, 1104027) == 10
