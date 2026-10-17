import pytest
from x2server.player.store import PlayerStore
from x2server.player.economy import EconomyService, UnresolvedEconomy
from x2server.messages.season import SEASON_SCHEMAS, encode


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv('X2_ORIGIN_SEASON_ENABLED', '1')
    store = PlayerStore(tmp_path / 'season.sqlite3')
    p = store.login('season-test', 1, 0)
    store.save_snapshot(1, dict(p['snapshot'], level=60, crystal=100000, mobility={'power': 149},
        heroes=[{'id': 1003, 'state': 2, 'level': 1, 'star': 1}]), p['revision'])
    economy = EconomyService(store)
    yield store, economy, economy.season
    store.close()


def test_sign_and_all_free_tiers_claim_once(env):
    store, e, s = env
    with e.transaction():
        s.operate(1, 'SignBattlePass', {}, 'sign')
    assert s.state(1)['exp'] == 680
    with pytest.raises(UnresolvedEconomy), e.transaction():
        s.operate(1, 'SignBattlePass', {}, 'sign-again')
    with e.transaction():
        s.operate(1, 'BuyBattlePassLevel', {'buyCount': 5}, 'buy')
        s.operate(1, 'ReceiveBattlePass', {'configIds': []}, 'claim')
    state = s.state(1)
    assert state['exp'] == 5680
    assert state['points'] == 5
    assert len(state['levels_claimed']) == 5
    assert all(v == 3 for v in state['levels_claimed'].values())
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1202901').fetchone()[0] >= 1
    with pytest.raises(UnresolvedEconomy), e.transaction():
        s.operate(1, 'ReceiveBattlePass', {'configIds': []}, 'claim-again')


def test_managed_grants_are_idempotent_and_week_cap_applies(env):
    _, e, s = env
    with e.transaction():
        e._grant(1, f'season:{s.instance}:task:one', {1291001: 15000})
        e._grant(1, f'season:{s.instance}:task:one', {1291001: 15000})
        e._grant(1, f'season:{s.instance}:task:two', {1291001: 15000})
    assert s.state(1)['exp'] == 12000
    assert s.state(1)['week_exp'] == 12000


def test_talent_allocation_rolls_back_and_reset_refunds(env):
    store, e, s = env
    tid = min(s.talents)
    with e.transaction():
        e._grant(1, 'points', {1291002: 3})
        s.operate(1, 'BattlePassTalentLevel', {'info': [encode('TalentLevel', {'id': tid, 'level': 2})]}, 'talent')
    assert s.state(1)['points'] == 1
    assert s.attributes(1)
    before = store.get(1)
    with pytest.raises(UnresolvedEconomy), e.transaction():
        s.operate(1, 'BattlePassTalentLevel', {'info': [encode('TalentLevel', {'id': tid, 'level': 999})]}, 'bad')
    assert store.get(1) == before
    with e.transaction():
        s.operate(1, 'BattlePassTalentReset', {'id': tid}, 'reset')
    assert s.state(1)['points'] == 3
    assert not any(s.attributes(1).values())


def test_wire_mission_reserved_field_and_instance_isolation(env):
    _, e, s = env
    raw = encode('L2C_BattlePassMissionInfo', s.mission_values(1))
    decoded = SEASON_SCHEMAS['L2C_BattlePassMissionInfo'].decode(raw)
    assert decoded['maxSeasonId'] == 2090001
    from x2server.player.season import SeasonService
    other = SeasonService(e, enabled=True, instance='second-review')
    assert other.state(1)['exp'] == 0
    assert len(s.task_values(1)['taskList']) == 11


def test_battle_entry_settlement_unlocks_next_layer_once(env):
    import asyncio
    from x2server.player.battle import BattleService
    from x2server.messages.battle import CHECKOUT
    from x2server.network.dispatcher import DispatchContext
    from x2server.network.session import SessionState
    from tests.unit.test_battle import packet, request
    store, e, s = env
    with e.transaction():
        e._grant(1, 'tickets', {1202901: 3})
    ctx = DispatchContext('test', 'local', SessionState('test', 'season-battle', player_id=1))
    battle = BattleService(store, economy=e)
    row = s.configs[2090001]
    sid = row['SectionGroup'][0]
    section = s.sections[sid]
    values = request()
    values.update(missionId=sid, chapter=section['ChapterID'], sceneId=section['Maps'][0])
    entry = asyncio.run(battle.enter(ctx, packet(values)))
    assert entry.values['result'] == 10
    finish = packet({'checkout': CHECKOUT.encode({'chapterId': section['ChapterID'],
        'sectionId': sid, 'success': True, 'fightTime': 180})}, 2, 'C2L_CheckoutMainMissionSign')
    result = asyncio.run(battle.checkout(ctx, finish))
    assert result.values['result'] == 10
    assert s.state(1)['max_layer'] == 1
    assert s.state(1)['stats']['passes'] == 1
    assert any(x.message_name == 'L2C_BattlePassMissionInfo' for x in result.before_response)
    again = asyncio.run(battle.checkout(ctx, finish))
    assert again.values == result.values
    assert s.state(1)['stats']['passes'] == 1
    assert s.mission_values(1)['maxSeasonId'] == 2090004


def test_all_500_levels_rewards_can_be_received(env):
    _, e, s = env
    with e.transaction():
        e._grant(1, 'max-exp', {1291001: 500000})
        answer = s.operate(1, 'ReceiveBattlePass', {}, 'all')
    assert answer['code'] == 10
    assert len(s.state(1)['levels_claimed']) == 500
    assert s.state(1)['points'] == 500


def test_sync_does_not_dispatch_purchase_popup(env):
    _, e, s = env
    messages = s.pushes(1)
    assert [m.message_name for m in messages] == ['L2C_QueryBattlePassInfo', 'L2C_BattlePassTalentUpdate', 'L2C_TaskUpdate', 'L2C_TreasureBoxUpdate']
    assert not s.pushes(1)
    with e.transaction():
        e._grant(1, 'sync-exp', {1291001: 1000})
    assert s.pushes(1)


def test_battle_talent_wire_includes_stat_and_passive(env):
    _, e, s = env
    with e.transaction():
        e._grant(1, 'passive-points', {1291002: 5})
        s.operate(1, 'BattlePassTalentLevel', {'info': [encode('TalentLevel', {'id': 6006001, 'level': 2}),
            encode('TalentLevel', {'id': 6006011, 'level': 1})]}, 'passives')
    values = [SEASON_SCHEMAS['TalentAttr'].decode(raw) for raw in s.battle_talents(1)]
    assert {v['id'] for v in values} == {6006001, 6006011}
    assert next(v for v in values if v['id'] == 6006011)['passiveId'] == 242900


def test_v4_archive_import_keeps_destination_season_claims(env, tmp_path):
    import io, json, zipfile
    from x2server.player.save_manager import SaveManager, SEASON_ADDED_TABLES
    from tests.unit.test_save_manager import build_full_schema
    store, e, s = env
    build_full_schema(store)
    manager = SaveManager(store, backup_root=tmp_path/'backups')
    try:
        with e.transaction():
            e._grant(1, 'legacy-test', {1291001: 5000})
            s.operate(1, 'ReceiveBattlePass', {}, 'legacy-claim')
        before = s.state(1)
        archive = manager.export_save(1)
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            manifest = json.loads(z.read('manifest.json'))
            document = json.loads(z.read('save.json'))
            blobs = [z.read(n) for n in sorted(z.namelist()) if n.startswith('blobs/')]
        manifest['server_save_schema'] = 'x2-revival/4'
        for table in SEASON_ADDED_TABLES:
            del document['tables'][table]
        manager.import_save(1, manager._container_bytes(manifest, document, blobs))
        assert s.state(1) == before
    finally:
        manager.close()


def test_line_task_uses_line_table_and_claims_stages_once(env):
    _, e, s = env
    for i in range(15):
        e.record_event(1, f'strengthen-{i}', 12)
    assert s.state(1)['tasks']['6007005'] == 15
    first = s.claim_task_response(1, 6007005, 'request-one')
    assert first['code'] == 10
    after_first = s.state(1)
    assert after_first['task_stages']['6007005'] == 1
    assert 6007005 not in after_first['task_claimed']
    assert s.claim_task_response(1, 6007005, 'request-one') == first
    assert s.state(1) == after_first
    assert s.claim_task_response(1, 6007005, 'request-two')['code'] == 10
    assert s.claim_task_response(1, 6007005, 'request-three')['code'] == 10
    assert 6007005 in s.state(1)['task_claimed']
    assert s.claim_task_response(1, 6007005, 'request-four')['code'] == 13


def test_all_season_requests_have_encoded_error_or_live_response(env):
    from x2server.messages.season import SEASON_IDS
    from x2server.network.dispatcher import DispatchContext
    from x2server.network.session import SessionState
    from tests.unit.test_battle import packet
    _, e, s = env
    ctx = DispatchContext('test', 'local', SessionState('test', 'route-check', player_id=1))
    for i, (name, _, _) in enumerate(SEASON_IDS):
        coro = s.handle(ctx, packet({}, i+1, 'C2L_'+name))
        try:
            coro.send(None)
        except StopIteration as done:
            answer = done.value
        else:
            raise AssertionError('Handler unexpectedly needs asynchronous I/O')
        finally:
            coro.close()
        assert answer.message_name == 'L2C_'+name
        wire = SEASON_SCHEMAS[answer.message_name].encode(answer.values)
        assert SEASON_SCHEMAS[answer.message_name].decode(wire)['code'] in (10,13,97)
