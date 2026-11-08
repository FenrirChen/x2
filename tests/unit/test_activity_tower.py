import asyncio

import pytest

from tests.activity_calendar_helpers import activity_start, next_activity_cycle
from tests.unit.test_activity_runtime import runtime, env
from tests.unit.test_battle import packet
from x2server.messages.activity import ACTIVITY_SCHEMAS
from x2server.messages.battle import CHECKOUT, PROFILE_HERO
from x2server.player.battle import BattleService


def send(rt, ctx, op, request=None, rid=1):
    response = asyncio.run(rt.handle(ctx, packet(request or {}, rid, 'C2L_' + op)))
    ACTIVITY_SCHEMAS['L2C_' + op].encode(response.values)
    return response


def open_tower(runtime):
    store, economy, ctx, rt, now = runtime
    now[0] = activity_start(3) + 3600
    economy.activity = rt.a
    return store, economy, ctx, rt, now


def test_unlocked_towers_upgrade_and_reset_from_current_row_cost(runtime):
    store, economy, ctx, rt, _ = open_tower(runtime)
    response = send(rt, ctx, 'QueryActivityTower')
    assert [ACTIVITY_SCHEMAS['ActivityTowerInfo'].decode(v).get('id', 0)
            for v in response.values['towerInfo']] == [0]
    with economy.transaction():
        rt.r.put(1, rt.r.at(), 'tower', 'owned', [1, 5, 9])
        economy._grant(1, 'test:tower-points', {1290193: 24})
    for rid, expected_id, balance in [(100, 2, 22), (101, 3, 16), (102, 4, 0)]:
        reply = send(rt, ctx, 'ActivityTowerLevelUp', {'type': 1, 'opt': 0}, rid)
        assert reply.values['code'] == 10
        assert ACTIVITY_SCHEMAS['ActivityTowerInfo'].decode(reply.values['towerInfo'])['id'] == expected_id
        assert reply.values['towerPoint'] == balance
    assert send(rt, ctx, 'ActivityTowerLevelUp', {'type': 1, 'opt': 0}, 103).values['code'] == 13
    reset = send(rt, ctx, 'ActivityTowerLevelUp', {'type': 1, 'opt': 1}, 104)
    assert reset.values['towerPoint'] == 24
    assert send(rt, ctx, 'ActivityTowerLevelUp', {'type': 1, 'opt': 1}, 104).values == reset.values
    assert rt.tower.balance(1) == 24
    assert send(rt, ctx, 'ActivityTowerLevelUp', {'type': 1, 'opt': 1}, 105).values['code'] == 13


def test_exact_balance_upgrade_then_relogin_and_period_reset(runtime):
    _, economy, ctx, rt, now = open_tower(runtime)
    with economy.transaction():
        rt.r.put(1, rt.r.at(), 'tower', 'owned', [5])
        economy._grant(1, 'test:exact-tower-points', {1290193: 2})
    request = {'type': 2, 'opt': 0}
    reply = send(rt, ctx, 'ActivityTowerLevelUp', request, 200)
    assert reply.values['code'] == 10 and reply.values['towerPoint'] == 0
    assert send(rt, ctx, 'ActivityTowerLevelUp', request, 200).values == reply.values
    assert rt.tower.owned(1, rt.r.at())[2] == 6
    assert send(rt, ctx, 'ActivityTowerLevelUp', request, 201).values['code'] == 13
    now[0] = next_activity_cycle(now[0])
    assert rt.tower.owned(1, rt.r.at()) == {}


@pytest.mark.parametrize('op', ['QueryActivityTower', 'ActivityTowerLevelUp', 'QueryTowerReward', 'ReceiveTowerReward'])
def test_tower_routes_reject_foreign_theme_and_answer_instead_of_hanging(runtime, op):
    _, _, ctx, rt, _ = runtime
    assert send(rt, ctx, op).values['code'] == 13


def test_old_auto_paid_clear_is_not_paid_twice(runtime):
    _, _, ctx, rt, _ = open_tower(runtime)
    period = rt.r.at()
    with rt.e.transaction():
        rt.r.put(1, period, 'clear', 2160621, 1)
    assert 2160621 in send(rt, ctx, 'QueryTowerReward').values['received']
    assert send(rt, ctx, 'ReceiveTowerReward', {'sectionId': 2160621}, 300).values['code'] == 13


def test_tower_first_clear_manual_claim_and_replay_complete_chain(runtime):
    _, economy, ctx, rt, _ = open_tower(runtime)
    battle = BattleService(rt.a.store, economy)
    assert send(rt, ctx, 'ReceiveTowerReward', {'sectionId': 2160621}, 399).values['code'] == 13
    entry = asyncio.run(battle.enter(ctx, packet({'missionId': 2160621, 'chapter': 2060501, 'sceneId': 2260561,
        'heros': [PROFILE_HERO.encode({'heroId': 1336, 'leader': 1})]}, 400)))
    assert entry.values['result'] == 10
    assert entry.values['towerPlayerPassiveList'] == [242421]
    assert entry.values['towerMonsterPassiveList'] == [242439]
    done = packet({'checkout': CHECKOUT.encode({'chapterId': 2060501, 'sectionId': 2160621,
                    'success': True, 'fightTime': 180})}, 401, 'C2L_CheckoutMainMissionSign')
    result = asyncio.run(battle.checkout(ctx, done))
    assert result.values['result'] == 10
    assert rt.r.get(1, rt.r.at(), 'clear', 2160621, 0) == 1
    assert rt.tower.balance(1) == 0
    query = send(rt, ctx, 'QueryTowerReward', rid=402)
    assert 2160621 not in query.values['received']
    claim = send(rt, ctx, 'ReceiveTowerReward', {'sectionId': 2160621}, 403)
    assert claim.values['code'] == 10 and 2160621 in claim.values['received']
    assert rt.tower.balance(1) == 2
    assert rt.tower.owned(1, rt.r.at()) == {1: 1, 2: 5, 3: 9}
    assert 'L2C_QueryActivityTower' in [m.message_name for m in claim.before_response]
    assert send(rt, ctx, 'ReceiveTowerReward', {'sectionId': 2160621}, 403).values == claim.values
    assert send(rt, ctx, 'ReceiveTowerReward', {'sectionId': 2160621}, 404).values['code'] == 13
    assert rt.tower.balance(1) == 2
    assert asyncio.run(battle.checkout(ctx, done)).values['result'] == 10
    assert rt.tower.balance(1) == 2


def test_legacy_parked_tower_is_repaired_without_regranting_paid_currency(runtime):
    store, economy, ctx, rt, _ = open_tower(runtime)
    period = rt.r.at()
    with economy.transaction():
        rt.r.put(1, period, 'clear', 2160621, 1)
        store.db.execute('INSERT INTO activity_runs VALUES (?,1,?,2160621,?,1)',
                         ('legacy-tower', period.index, int(economy.clock())))
        store.db.execute('INSERT INTO pending_rewards VALUES (1,?,?,1,?)',
                         ('battle:legacy-tower', 1105010, 'old unresolved tower'))
        economy._grant(1, 'old-paid-points', {1290193: 2})
    assert 2160621 not in send(rt, ctx, 'QueryTowerReward', rid=501).values['received']
    assert send(rt, ctx, 'ReceiveTowerReward', {'sectionId': 2160621}, 502).values['code'] == 10
    assert rt.tower.balance(1) == 2
    assert rt.tower.owned(1, period) == {1: 1}
    assert not store.db.execute('SELECT 1 FROM pending_rewards WHERE source=?', ('battle:legacy-tower',)).fetchone()
    assert send(rt, ctx, 'ReceiveTowerReward', {'sectionId': 2160621}, 503).values['code'] == 13


def test_every_tower_first_clear_bundle_has_only_supported_destinations(runtime):
    from collections import Counter
    _, economy, _, rt, _ = open_tower(runtime)
    valid = {row['TowerItem'] for row in rt.tower.rows.values()}
    for section in rt.tower.ranks:
        deferred = Counter()
        rewards = economy.gifts(rt.a.sections[section]['FirVReward'], deferred=deferred)
        assert not (set(deferred) - valid)
        assert rewards or deferred


def test_battle_tower_loadout_uses_current_levels_and_the_same_period_passives(runtime):
    store, economy, ctx, rt, _ = open_tower(runtime)
    with economy.transaction():
        rt.r.put(1, rt.r.at(), 'tower', 'owned', [4, 6, 9])
        entry = rt.tower.entry(1, 2160623, [1, 5])
    assert entry['selectedTowerList'] == [4, 6]
    from x2server.messages.battle import BATTLE_SCHEMAS
    assert BATTLE_SCHEMAS['C2L_FightData'].decode(
        BATTLE_SCHEMAS['C2L_FightData'].encode({'selectedTowerList': [1, 5]}))['selectedTowerList'] == [1, 5]
    assert BATTLE_SCHEMAS['L2C_FightData'].decode(
        BATTLE_SCHEMAS['L2C_FightData'].encode(entry)) == entry
    assert rt.tower.entry(1, 2160623, [4, 6]) == entry
    assert rt.tower.entry(1, 2160621, [4, 6])['selectedTowerList'] == []
    with economy.transaction():
        for sid in (2160621, 2160622):
            rt.r.put(1, rt.r.at(), 'clear', sid, 1)
    battle = BattleService(store, economy)
    response = asyncio.run(battle.enter(ctx, packet({'missionId': 2160623,
        'chapter': 2060501, 'sceneId': 2260563, 'selectedTowerList': [1, 5],
        'heros': [PROFILE_HERO.encode({'heroId': 1003, 'leader': 1})]}, 600)))
    assert response.values['result'] == 10
    assert all(response.values[key] == value for key, value in entry.items())


@pytest.mark.parametrize('requested', [[], [1, 2], [13], [999999], [1, 5, 9, 13, 17]])
def test_locked_duplicate_or_oversize_battle_tower_loadout_is_rejected(runtime, requested):
    from x2server.player.economy import UnresolvedEconomy
    _, economy, _, rt, _ = open_tower(runtime)
    with economy.transaction():
        rt.r.put(1, rt.r.at(), 'tower', 'owned', [1, 5, 9])
    with pytest.raises(UnresolvedEconomy):
        with economy.transaction():
            rt.tower.entry(1, 2160623, requested)
