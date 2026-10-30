import asyncio
import json
import sqlite3
import threading
import time

import pytest

from tests.unit.test_save_manager import make_env, build_full_schema
from x2server.player.diagnostic_retention import (
    DiagnosticRetention, KEEP_SECONDS, TABLES, prune_account,
)
from x2server.player.save_manager import SaveManager

NOW = 1800000000


@pytest.fixture
def data(tmp_path):
    store, accounts, manager = make_env(tmp_path)
    build_full_schema(store)
    store.login('retention-one', 1, NOW)
    store.login('retention-two', 2, NOW)
    yield store, accounts, manager
    manager.close()
    accounts.close()
    store.close()


def report(store, key, stamp, settled=1, pid=1, orphan=False):
    db = store.db
    if not orphan:
        db.execute("INSERT INTO economy_runs(uuid,player_id,session_id,section_id,settled) VALUES (?,?,?,2110801,?)",
                   (key, pid, 'test', settled))
        db.execute("INSERT INTO battle_entries(player_id,request_key,uuid,created_at,response) VALUES (?,?,?,?,?)",
                   (pid, key, key, stamp, b'entry'))
        db.execute('INSERT INTO economy_checkouts VALUES (?,?,?)', (pid, key, key))
    rid = db.execute('INSERT INTO fight_drop_observations VALUES (NULL,?,?,?,?,?,?,?,?,?)',
        (pid, key, 'test', 1, key, stamp, b'raw-body', '{"large":"diagnostic"}', '{"scene":1}')).lastrowid
    db.execute('INSERT INTO fight_drop_items VALUES (?,0,1,2,0,0)', (rid,))
    db.execute('INSERT INTO fight_drop_claims VALUES (?,"currency",0,?)', (rid, '{"value":2}'))
    return rid


def seed(store):
    with store.db:
        ids = {key: report(store, key, stamp, status, pid, orphan) for key, stamp, status, pid, orphan in (
            ('old', NOW-KEEP_SECONDS-1, 1, 1, False),
            ('boundary', NOW-KEEP_SECONDS, 1, 1, False),
            ('recent', NOW-10, 1, 1, False),
            ('active', NOW-KEEP_SECONDS-10, 0, 1, False),
            ('unknown-time', 0, 1, 1, False),
            ('orphan', NOW-KEEP_SECONDS-10, 1, 1, True),
            ('foreign', NOW-KEEP_SECONDS-10, 1, 2, False))}
        for table, values in (
            ('battle_shop_pickups', (1, 10, 1, 9999, NOW-KEEP_SECONDS-1)),
            ('battle_shop_pickups', (1, 11, 1, 2110801, NOW-KEEP_SECONDS-1)),
            ('battle_shop_pickups', (1, 12, 1, 9999, NOW)),
            ('battle_shop_purchases', (1, 1, 1, 10, 1, 100, 1, 9999, NOW-KEEP_SECONDS-1))):
            store.db.execute('INSERT INTO '+table+' VALUES ('+','.join('?'*len(values))+')', values)
        store.db.execute('INSERT INTO battle_unresolved_rewards VALUES ("old",1,2110801,1,"preserve")')
        store.db.execute('INSERT INTO inventory VALUES (1,1237914,50)')
    return ids


def cleanup(store, player=1):
    with store.db:
        return prune_account(store.db, player, NOW-KEEP_SECONDS)


def test_exact_cutoff_owner_and_protected_game_data(data):
    store, _, manager = data
    ids = seed(store)
    before = manager.canonical_state(1)
    cleanup(store)
    after = manager.canonical_state(1)
    for table in before['tables']:
        if table not in TABLES:
            assert after['tables'][table] == before['tables'][table], table
    assert after['snapshot'] == before['snapshot']
    rows = {r['uuid']: r for r in store.db.execute('SELECT * FROM fight_drop_observations')}
    assert rows['old']['decoded'] == rows['old']['context'] == '{}'
    for key in ('boundary','recent','active','unknown-time','orphan','foreign'):
        assert rows[key]['decoded'] == '{"large":"diagnostic"}', key
    assert all(r['body'] == b'raw-body' for r in rows.values())
    assert store.db.execute('SELECT count(*) FROM fight_drop_items WHERE report_id=?',(ids['old'],)).fetchone()[0] == 0
    assert store.db.execute('SELECT count(*) FROM fight_drop_claims WHERE report_id=?',(ids['old'],)).fetchone()[0] == 0
    assert [r[0] for r in store.db.execute('SELECT item_id FROM battle_shop_pickups ORDER BY item_id')] == [11,12]
    assert store.db.execute('SELECT count(*) FROM battle_unresolved_rewards').fetchone()[0] == 1
    assert not any(cleanup(store).values())


def test_cleanup_rollback_and_missing_schema_fail_closed(data):
    store, _, manager = data
    seed(store)
    before = manager.canonical_state(1)
    store.db.execute('BEGIN')
    prune_account(store.db, 1, NOW-KEEP_SECONDS)
    store.db.rollback()
    assert manager.canonical_state(1) == before
    db = sqlite3.connect(':memory:')
    try:
        assert prune_account(db, 1, NOW) == {}
        db.execute('CREATE TABLE battle_shop_pickups(player_id,created_at)')
        db.execute('INSERT INTO battle_shop_pickups VALUES (1,1)')
        assert prune_account(db, 1, NOW)['battle_shop_pickups'] == 0
    finally:
        db.close()


def test_export_is_readonly_and_old_archives_cannot_restore_expired_diagnostics(data, monkeypatch):
    store, _, manager = data
    ids = seed(store)
    # Produce a valid old-format archive while the synthetic rows are recent.
    monkeypatch.setattr('x2server.player.save_manager.time.time', lambda: NOW-KEEP_SECONDS)
    legacy = manager.export_save(1)
    assert any(r['report_id'] == ids['old'] for r in manager.parse_save(legacy).rows['fight_drop_items'])
    monkeypatch.setattr('x2server.player.save_manager.time.time', lambda: NOW)
    before = manager.canonical_state(1)
    archive = manager.export_save(1)
    assert manager.canonical_state(1) == before  # virtual export filtering only
    parsed = manager.parse_save(archive)
    assert not any(r['report_id'] == ids['old'] for r in parsed.rows['fight_drop_items'])
    assert next(r for r in parsed.rows['fight_drop_observations'] if r['uuid']=='old')['decoded'] == '{}'
    manager.import_save(1, legacy)
    assert store.db.execute('SELECT decoded,body FROM fight_drop_observations WHERE uuid="old"').fetchone()[0] == '{}'
    assert store.db.execute('SELECT count(*) FROM fight_drop_items WHERE report_id=?',(ids['old'],)).fetchone()[0] == 0
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1').fetchone()[0] == 50
    assert len(list(manager.backup_root.glob('player_1/latest.x2save'))) == 1
    # A failed import after cleanup must restore all old rows and balances.
    before = manager.canonical_state(1)
    monkeypatch.setattr(manager, '_bump_sequences', lambda db: (_ for _ in ()).throw(RuntimeError('after cleanup')))
    with pytest.raises(RuntimeError, match='after cleanup'):
        manager.import_save(1, legacy)
    assert manager.canonical_state(1) == before


def test_background_keyset_sweep_and_restart_are_idempotent(data):
    store, _, _ = data
    seed(store)
    worker = DiagnosticRetention(store, lambda: NOW, batch_size=2)
    for table in TABLES:
        while True:
            changed, done = worker.step(table)
            if done:
                break
    assert not any(cleanup(store).values())
    assert not store.importing.is_set()
    assert store.db.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
    with pytest.raises(ValueError):
        worker.step('inventory')


def test_cancel_drains_background_writer(data):
    store, _, _ = data
    entered, release = threading.Event(), threading.Event()
    worker = DiagnosticRetention(store)
    def step(table):
        with store.import_write():
            entered.set()
            release.wait(5)
        return 0, True
    worker.step = step
    async def scenario():
        task = asyncio.create_task(worker.watch())
        await asyncio.to_thread(entered.wait, 5)
        task.cancel()
        await asyncio.sleep(.02)
        assert not task.done() and store.importing.is_set()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not store.importing.is_set()
    asyncio.run(scenario())


from tests.unit.test_economy import env


def test_settlement_replay_tasks_and_new_battle_after_actual_cleanup(env):
    from tests.unit.test_battle import packet, request
    from tests.unit.test_economy import checkout
    from x2server.player.battle import BattleService
    store, economy, ctx = env
    battle = BattleService(store, economy)
    entry = asyncio.run(battle.enter(ctx, packet(request(), 201)))
    assert entry.values['result'] == 10
    drop = packet({'missionId':2110801,'chapterId':2010100}, 202, 'C2L_FightDropData')
    assert asyncio.run(battle.drop_data(ctx, drop)).values['result'] == 10
    result = asyncio.run(battle.checkout(ctx, checkout()))
    assert result.values['result'] == 10
    before = store.get(1)
    stamp = int(time.time()) - KEEP_SECONDS - 1
    with economy.transaction():
        store.db.execute('UPDATE fight_drop_observations SET recorded_at=?', (stamp,))
        store.db.execute('UPDATE battle_entries SET created_at=?', (stamp,))
        # Valid diagnostic child associated with the real settled report.
        rid=store.db.execute('SELECT id FROM fight_drop_observations').fetchone()[0]
        store.db.execute('INSERT INTO fight_drop_items VALUES (?,0,1,1,0,0)', (rid,))
        raw = store.db.execute('SELECT body FROM fight_drop_observations').fetchone()[0]
        pruned = prune_account(store.db,1,int(time.time())-KEEP_SECONDS)
        assert pruned['fight_drop_items'] == 1
    assert store.db.execute('SELECT body FROM fight_drop_observations').fetchone()[0] == raw
    assert asyncio.run(battle.checkout(ctx, checkout())).values == result.values
    assert store.get(1) == before
    # Current consumers still read intact progress and settlement evidence.
    economy.achievements.refresh(1)
    economy.dp.refresh(1, 2010100)
    economy.task_values(1, 1)
    assert asyncio.run(battle.enter(ctx, packet(request(), 203))).values['result'] == 10


def test_legacy_cross_account_import_retains_only_target_owned_diagnostics(data, monkeypatch):
    store, _, manager = data
    seed(store)
    monkeypatch.setattr('x2server.player.save_manager.time.time',lambda:NOW-KEEP_SECONDS)
    old = manager.export_save(1)
    monkeypatch.setattr('x2server.player.save_manager.time.time',lambda:NOW)
    original = manager.canonical_state(1)
    manager.import_save(2,old)
    assert manager.canonical_state(1) == original
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=2').fetchone()[0] == 50
    rows=store.db.execute('SELECT decoded FROM fight_drop_observations WHERE player_id=2').fetchall()
    assert len(rows)==6
    assert sum(r[0]=='{}' for r in rows)==1
    assert store.db.execute('SELECT count(*) FROM fight_drop_items i JOIN fight_drop_observations o ON o.id=i.report_id WHERE o.player_id=2').fetchone()[0] == 5



def test_large_old_diagnostic_json_does_not_hit_export_entry_limit(data, monkeypatch):
    store, _, manager = data
    payload=json.dumps({'padding':'x'*(8*1024*1024)})
    with store.db:
        for i in range(9):
            rid=report(store,'large-old-'+str(i),NOW-KEEP_SECONDS-1)
            store.db.execute('UPDATE fight_drop_observations SET decoded=?,context=? WHERE id=?',
                             (payload,payload,rid))
    monkeypatch.setattr('x2server.player.save_manager.time.time',lambda:NOW-KEEP_SECONDS)
    with pytest.raises(ValueError,match='export uncompressed limit exceeded'):
        manager.export_save(1)
    monkeypatch.setattr('x2server.player.save_manager.time.time',lambda:NOW)
    archive=manager.export_save(1)
    assert len(archive)<100000
    rows=manager.parse_save(archive).rows['fight_drop_observations']
    assert len(rows)==9 and all(r['decoded']==r['context']=='{}' for r in rows)
    assert all(r['body'] for r in rows)  # raw evidence remains in BLOB entries
    # The read-only export must not silently perform physical cleanup.
    assert store.db.execute('SELECT length(decoded) FROM fight_drop_observations LIMIT 1').fetchone()[0]>8*1024*1024



from tests.unit.test_save_manager import env as rich_env


def test_all_save_tables_preserve_functional_records_during_cleanup(rich_env):
    store, _, manager, player, _ = rich_env
    seed(store)
    before=manager.canonical_state(player)
    with store.db:
        prune_account(store.db,player,NOW-KEEP_SECONDS)
    after=manager.canonical_state(player)
    assert len(before['tables'])==102
    for table in before['tables']:
        if table not in TABLES:
            assert after['tables'][table]==before['tables'][table],table
    assert after['snapshot']==before['snapshot']
    # Raw parent reports and their ownership/digests are never deleted.
    assert store.db.execute('SELECT count(*) FROM fight_drop_observations WHERE player_id=?',(player,)).fetchone()[0]==7



def test_busy_or_failed_background_batch_keeps_rows_cursor_and_guard(data):
    store, _, _ = data
    ids=seed(store)
    worker=DiagnosticRetention(store,lambda:NOW,batch_size=2)
    blocker=sqlite3.connect(store.path,timeout=.1,isolation_level=None)
    try:
        blocker.execute('BEGIN IMMEDIATE')
        with pytest.raises(sqlite3.OperationalError):
            worker.step('fight_drop_items')
        assert worker.position['fight_drop_items']==0
        assert not store.importing.is_set()
    finally:
        blocker.rollback()
        blocker.close()
    store.db.execute("CREATE TRIGGER stop_diagnostic_delete AFTER DELETE ON fight_drop_items BEGIN SELECT RAISE(ABORT,'injected cleanup failure'); END")
    with pytest.raises(sqlite3.IntegrityError,match='injected cleanup failure'):
        worker.step('fight_drop_items')
    assert worker.position['fight_drop_items']==0 and not store.importing.is_set()
    assert store.db.execute('SELECT count(*) FROM fight_drop_items WHERE report_id=?',(ids['old'],)).fetchone()[0]==1
    store.db.execute('DROP TRIGGER stop_diagnostic_delete')
    worker.step('fight_drop_items')
    assert store.db.execute('SELECT count(*) FROM fight_drop_items WHERE report_id=?',(ids['old'],)).fetchone()[0]==0
    for value in (0,-1,1025):
        with pytest.raises(ValueError):
            DiagnosticRetention(store,batch_size=value)



def test_first_export_refreshes_schema_after_services_create_tables(data, monkeypatch):
    store, _, manager = data
    seed(store)
    monkeypatch.setattr('x2server.player.save_manager.time.time',lambda:NOW)
    parsed=manager.parse_save(manager.export_save(1))
    assert parsed.rows['battle_shop_purchases']==[]
    assert [r['item_id'] for r in parsed.rows['battle_shop_pickups']]==[11,12]



def test_unknown_nullable_legacy_timestamp_is_retained_in_export_predicate():
    from x2server.player.diagnostic_retention import condition, live_tables
    db=sqlite3.connect(':memory:')
    try:
        db.execute('CREATE TABLE economy_runs(uuid,player_id,section_id,settled)')
        db.execute('CREATE TABLE battle_shop_pickups(player_id,section_id,created_at)')
        db.execute('INSERT INTO battle_shop_pickups VALUES (1,1,NULL)')
        predicate=condition('battle_shop_pickups',live_tables(db))
        assert db.execute('SELECT count(*) FROM battle_shop_pickups t WHERE NOT ('+predicate+')',{'cutoff':NOW}).fetchone()[0]==1
        assert prune_account(db,1,NOW)['battle_shop_pickups']==0
    finally:
        db.close()



def test_import_plan_filter_matches_consistent_export_without_writing_history(data,monkeypatch):
    from x2server.player.diagnostic_retention import prune_plan
    store,_,manager=data
    seed(store)
    monkeypatch.setattr('x2server.player.save_manager.time.time',lambda:NOW-KEEP_SECONDS)
    legacy=manager.export_save(1)
    plan=manager.parse_save(legacy)
    monkeypatch.setattr('x2server.player.save_manager.time.time',lambda:NOW)
    expected=manager.parse_save(manager.export_save(1))
    changed=prune_plan(plan,NOW-KEEP_SECONDS)
    assert changed['fight_drop_items']==changed['fight_drop_claims']==1
    assert plan.rows==expected.rows
    assert plan.snapshot==expected.snapshot and plan.blobs==expected.blobs
    assert store.db.execute('SELECT decoded FROM fight_drop_observations WHERE uuid="old"').fetchone()[0]!='{}'


def test_background_barrier_precedes_worker_start(data):
    store, _, _ = data
    entered, release = threading.Event(), threading.Event()
    worker = DiagnosticRetention(store)
    def step(table):
        # Deliberately stall before import_write can set its own event.
        entered.set()
        assert release.wait(5)
        return 0, True
    worker.step = step
    async def scenario():
        task = asyncio.create_task(worker._step_guarded('fight_drop_items'))
        assert await asyncio.to_thread(entered.wait, 5)
        assert store.maintenance.is_set()
        waiter = asyncio.create_task(store.wait_for_import())
        await asyncio.sleep(.02)
        assert not waiter.done()
        release.set()
        assert await task == (0, True)
        await waiter
        assert not store.maintenance.is_set()
    asyncio.run(scenario())


def test_maintenance_completion_does_not_clear_new_import_barrier(data):
    store, _, _ = data
    worker = DiagnosticRetention(store)
    def step(table):
        # Model a save writer acquiring the import flag after this batch exits
        # its own guard but before the event loop consumes its result.
        store.importing.set()
        return 0, True
    worker.step = step
    async def scenario():
        assert await worker._step_guarded('fight_drop_items') == (0, True)
        assert store.importing.is_set() and not store.maintenance.is_set()
        waiter = asyncio.create_task(store.wait_for_import())
        await asyncio.sleep(.02)
        assert not waiter.done()
        store.importing.clear()
        await waiter
    asyncio.run(scenario())
