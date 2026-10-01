import asyncio
import sqlite3
import pytest

from x2server.messages.achievements import ACHV
from x2server.player.economy import EconomyService
from x2server.player.store import PlayerStore
from x2server.network.dispatcher import DispatchContext
from x2server.network.session import SessionState
from tests.unit.test_battle import packet


@pytest.fixture
def env(tmp_path):
    store = PlayerStore(tmp_path / 'achievements.sqlite3')
    player = store.login('achievement-test', 1, 0)
    store.save_snapshot(1, dict(player['snapshot'], level=60,
        heroes=[{'id': 1003, 'state': 2, 'star': 4, 'level': 30},
                {'id': 1004, 'state': 2, 'star': 4, 'level': 30},
                {'id': 1005, 'state': 2, 'star': 4, 'level': 30}]), player['revision'])
    economy = EconomyService(store)
    ctx = DispatchContext('test', 'local', SessionState('test', 'session', player_id=1))
    yield store, economy, ctx
    store.close()


def call(env, name, data, request_id=1):
    _, economy, ctx = env
    return asyncio.run(economy.achievements.handle(ctx, packet(data, name=name, request_id=request_id)))


def test_favor_bindings_use_account_heroes_and_zhuque_alias(env):
    store, economy, _ = env
    service = economy.achievements
    player = store.get(1)
    heroes = [{'id': hero_id, 'level': 1, 'star': 1, 'state': 2}
              for hero_id in service.initial_favor]
    next(h for h in heroes if h['id'] == 1028)['favor'] = {'level': 4, 'exp': 850}
    store.save_snapshot(1, dict(player['snapshot'], heroes=heroes), player['revision'])
    states = service.states(1)
    for achv_id, row in service.rows.items():
        rule = row['rule']
        if rule['kind'] != 'hero_favor':
            continue
        assert rule['hero'] in service.initial_favor
        expected = 4 if rule['hero'] == 1028 else service.initial_favor[rule['hero']]
        assert states[achv_id][0] == min(expected, row['targets'][-1])
    # Canonical UnitBase hero 1034 is named 陵光; achievement calls her 朱雀.
    assert service.rows[660650]['rule'] == {'kind': 'hero_favor', 'hero': 1034}


def test_overview_native_point_status_array_and_paginated_lists(env):
    answer = call(env, 'C2L_AchvOverView', {}).values
    assert answer['code'] == 10 and len(answer['achvOverViewData']) == 4
    assert len(answer['achvPointRewardList']) == 15
    assert answer['achvPointRewardList'][0] == 1
    ids = []
    for start in range(0, 400, 30):
        values = call(env, 'C2L_AchvDetialData', {'achvType': 1, 'startIndex': start, 'endIndex': start+30}).values
        assert values['code'] == (10 if values['achvDataList'] else 97) and len(values['achvDataList']) <= 30
        ids.extend(ACHV.decode(v)['achvId'] for v in values['achvDataList'])
    assert len(ids) == len(set(ids)) and 661000 in ids
    for data in ({'achvType': 0}, {'achvType': 1, 'startIndex': -1, 'endIndex': 30},
                 {'achvType': 1, 'startIndex': 0, 'endIndex': 100000}):
        assert call(env, 'C2L_AchvDetialData', data).values['code'] == 13


def test_stage_claim_retry_does_not_claim_next_stage_and_survives_reopen(env):
    store, economy, ctx = env
    req = {'achvId': 661000}
    first = call(env, 'C2L_AchvReward', req).values
    assert first['code'] == 10
    after = store.get(1)['snapshot']
    assert call(env, 'C2L_AchvReward', req).values == first
    assert store.get(1)['snapshot'] == after
    assert economy.achievements.states(1)[661000] == (60, 1)
    assert call(env, 'C2L_AchvReward', req, 2).values['code'] == 10
    assert economy.achievements.states(1)[661000] == (60, 2)
    with sqlite3.connect(store.path) as reader:
        assert reader.execute("SELECT COUNT(*) FROM economy_grants WHERE source LIKE 'achievement:661000:%'").fetchone()[0] == 2
    path = store.path
    store.close()
    reopened = PlayerStore(path)
    try:
        restored = EconomyService(reopened)
        assert restored.achievements.states(1)[661000] == (60, 2)
        assert not reopened.db.in_transaction
    finally:
        reopened.close()


def test_point_reward_exact_tier_and_duplicate_no_payment(env):
    first = call(env, 'C2L_AchvPointReward', {'achvPointId': 0}).values
    assert first['code'] == 10
    assert call(env, 'C2L_AchvPointReward', {'achvPointId': 0}).values == first
    after = env[0].get(1)['snapshot']
    assert call(env, 'C2L_AchvPointReward', {'achvPointId': 0}, 2).values['code'] == 13
    assert env[0].get(1)['snapshot'] == after
    assert call(env, 'C2L_AchvOverView', {}).values['achvPointRewardList'][0] == 2
    for tier in [-1, 14, 15, 1000000]:
        assert call(env, 'C2L_AchvPointReward', {'achvPointId': tier}, tier+100).values['code'] == 13


def test_owned_jewel_in_socket_tombstone_excluded_and_monotonic(env):
    store, economy, _ = env
    with store.db:
        store.db.execute('INSERT INTO inventory VALUES (1,1250011,0)')
    assert economy.achievements.states(1)[661500][0] == 0
    snapshot = store.get(1)['snapshot']
    snapshot['heroes'][0]['god_equip'] = {'id': 1503, 'star': 1, 'level': 0, 'jewels': {'0': 1250011}}
    economy.save_snapshot(1, snapshot)
    assert economy.achievements.states(1)[661500][0] == 1
    assert call(env, 'C2L_AchvReward', {'achvId': 661500}).values['code'] == 10
    snapshot = store.get(1)['snapshot']; snapshot['heroes'][0]['god_equip']['jewels'] = {}
    economy.save_snapshot(1, snapshot)
    assert economy.achievements.states(1)[661500] == (1, 1)


def test_login_days_unique_and_unknown_conditions_cannot_claim(env):
    economy = env[1]
    economy.clock = lambda: 1790817334
    economy.login_event(1); economy.login_event(1)
    assert economy.achievements.states(1)[662000][0] == 1
    economy.clock = lambda: 1790817334 + 86400
    economy.login_event(1)
    assert economy.achievements.states(1)[662000][0] == 2
    assert call(env, 'C2L_AchvReward', {'achvId': 660001}).values['code'] == 13
    assert call(env, 'C2L_AchvReward', {'achvId': 123}).values['code'] == 13


def test_reward_failure_rolls_back_claim_and_receipt(env, monkeypatch):
    from x2server.player.economy import UnresolvedEconomy
    def fail(*args, **kwargs): raise UnresolvedEconomy('test reward failure')
    monkeypatch.setattr(env[1], '_grant', fail)
    assert call(env, 'C2L_AchvReward', {'achvId': 661000}).values['code'] == 13
    assert env[1].achievements.states(1)[661000][1] == 0
    assert env[0].db.execute('SELECT COUNT(*) FROM achievement_receipts').fetchone()[0] == 0


def test_story_final_clear_and_blood_moon_exact_section(env):
    store, economy, _ = env
    with store.db:
        store.db.execute("INSERT INTO economy_clears VALUES (1,2110801,'intermediate')")
        store.db.execute("INSERT INTO economy_clears VALUES (1,2110859,'other-moon')")
    states = economy.achievements.states(1)
    assert states[662050][0] == 0 and states[662900][0] == 0
    with store.db:
        store.db.execute("INSERT INTO economy_clears VALUES (1,2110804,'final')")
        store.db.execute("INSERT INTO economy_clears VALUES (1,2110860,'blood-moon')")
    states = economy.achievements.states(1)
    assert states[662050][0] == 1 and states[662900][0] == 1


def test_named_beast_set_requires_six_distinct_slots(env):
    from x2server.player.equipment import EquipmentService
    store, economy, _ = env
    EquipmentService(store, economy)
    parts = economy.achievements.rows[661211]['rule']['parts']
    assert len(parts) == 6
    ids = list(map(int, parts))
    with store.db:
        for i in range(6):
            store.db.execute('INSERT INTO equipment_instances(player_id,type_id,star,param,marker) VALUES (1,?,6,?,?)',
                             (ids[0], '{}', f'duplicate-{i}'))
    states = economy.achievements.states(1)
    assert states[661210][0] == 1 and states[661211][0] == 0
    with store.db:
        for i, item in enumerate(ids[1:]):
            store.db.execute('INSERT INTO equipment_instances(player_id,type_id,star,param,marker) VALUES (1,?,6,?,?)',
                             (item, '{}', f'other-part-{i}'))
    assert economy.achievements.states(1)[661211][0] == 1


def test_timed_clear_only_accepted_settled_successful_receipts(env):
    from x2server.player.battle import BattleService
    from x2server.messages.battle import CHECKOUT, BATTLE_SCHEMAS
    store, economy, _ = env
    BattleService(store, economy)
    def run(key, settled, success, seconds):
        with store.db:
            store.db.execute('INSERT INTO economy_runs(uuid,player_id,session_id,section_id,settled) VALUES (?,1,?,?,?)', (key, 'session', 2110851, settled))
            store.db.execute('INSERT INTO battle_checkout_wire VALUES (?,?,?)',
                (key, CHECKOUT.encode({'sectionId': 2110851, 'success': success}), '[]'))
            store.db.execute('INSERT INTO battle_receipts VALUES (?,?,?,?)', (key, key, 1,
                BATTLE_SCHEMAS['L2C_CheckoutMainMission'].encode({'result': 10, 'fightTimeLength': seconds})))
    run('unsettled', 0, True, 100); run('failure', 1, False, 100); run('slow', 1, True, 361)
    assert economy.achievements.states(1)[662070][0] == 0
    run('accepted', 1, True, 360)
    assert economy.achievements.states(1)[662070][0] == 1


def test_claim_all_stages_at_high_level_and_last_stage_stays_in_bounds(env):
    store, economy, _ = env
    snapshot = store.get(1)['snapshot']; snapshot['level'] = 80
    economy.save_snapshot(1, snapshot)
    for stage in range(15):
        assert call(env, 'C2L_AchvReward', {'achvId': 661000}, stage+100).values['code'] == 10
    state = economy.achievements.states(1)[661000]
    assert economy.achievements.value(661000, state)['stage'] == 14
    assert economy.achievements.value(661000, state)['status'] == 2
    assert call(env, 'C2L_AchvReward', {'achvId': 661000}, 200).values['code'] == 13


def test_legacy_login_evidence_is_adopted_once(env):
    from x2server.player.task_calendar import task_period
    store, economy, _ = env
    now = 1790817334; economy.clock = lambda: now
    day = task_period(1, now)[0]
    with store.db:
        store.db.execute('INSERT INTO economy_events VALUES (1,?)', (f'challenge:loginday:{day}:58',))
    economy.achievements.login(1)
    assert economy.achievements.states(1)[662000][0] == 1


def test_client_recount_is_only_a_refresh_hint(env):
    from x2server.protocol.protobuf import ProtoField, ProtoSchema, FieldKind
    condition = ProtoSchema('ReCountCondition', tuple(ProtoField(i, n, FieldKind.INT32)
        for i, n in enumerate(('conditionId', 'isLineCondition', 'taskOrAchvId'), 1)))
    answer = call(env, 'C2L_ReCountAchv', {'conditions': [condition.encode(
        {'conditionId': 620001, 'isLineCondition': 1, 'taskOrAchvId': 660001})],
        'extras': [99999999], 'extra': 99999999})
    assert answer.values == {'code': 10}
    assert [p.message_name for p in answer.pushes] == ['L2C_AchvUpdate']
    assert env[1].achievements.states(1)[660001] == (0, 0)
    assert env[0].db.execute("SELECT COUNT(*) FROM economy_grants WHERE source LIKE 'achievement:%'").fetchone()[0] == 0
