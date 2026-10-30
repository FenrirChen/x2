import asyncio
from contextlib import closing
import io
import json
import sqlite3
import threading
import time
import tracemalloc
import zipfile

import pytest

from tests.unit.test_save_manager import env
from tests.integration._network import connect, close_client, guide_packet, read_response, start_server
from x2server.messages.core import CORE_SCHEMAS
from x2server.network.dispatcher import Dispatcher, OutboundMessage
from x2server.player.save_manager import SaveManager, AccountOnlineError
from x2server.player.store import PlayerStore
from x2server.bootstrap.save_manager_api import SaveManagerAPI


def test_export_snapshot_does_not_block_another_players_commit(env, monkeypatch):
    store, accounts, manager, alpha, beta = env
    manager.prepare_indexes()
    reading = threading.Event()
    release = threading.Event()
    errors, results = [], []
    original = manager._iter_export_table
    def paused(db, table, player_id, blobs, cutoff):
        if table == 'inventory':
            reading.set()
            assert release.wait(3)
        yield from original(db, table, player_id, blobs, cutoff)
    monkeypatch.setattr(manager, '_iter_export_table', paused)
    def export():
        try:
            results.append(manager.export_save(alpha))
        except BaseException as exc:
            errors.append(exc)
    worker = threading.Thread(target=export)
    before = store.get(alpha)['snapshot']['gold']
    worker.start()
    try:
        assert reading.wait(3)
        # The export read transaction remains open while game writes commit.
        row = store.get(alpha)
        store.save_snapshot(alpha, dict(row['snapshot'], gold=before + 1), row['revision'])
        assert accounts.verify('beta', 'pw-beta', 200)
        assert worker.is_alive()
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive() and not errors
    plan = manager.parse_save(results[0])
    assert plan.snapshot['gold'] == before
    assert store.get(alpha)['snapshot']['gold'] == before + 1
    assert store.db.execute('PRAGMA synchronous').fetchone()[0] == 2


def test_import_writer_waits_asynchronously_and_keeps_tcp_alive(env, monkeypatch):
    store, accounts, manager, alpha, beta = env
    manager.prepare_indexes()
    archive = manager.export_save(alpha)
    writing = threading.Event()
    release = threading.Event()
    original = manager._delete_target_state
    def paused(db, player_id, preserve_tables=None):
        writing.set()
        assert release.wait(5)
        return original(db, player_id, preserve_tables)
    monkeypatch.setattr(manager, '_delete_target_state', paused)
    async def scenario():
        calls = []
        async def handler(context, packet):
            row = store.get(beta)
            store.save_snapshot(beta, dict(row['snapshot'], gold=row['snapshot']['gold'] + 1), row['revision'])
            calls.append(packet.header.request_id)
            return OutboundMessage('L2C_GuideStep', {'code': 10})
        server = await start_server(Dispatcher({'C2L_GuideStep': handler}, wait_for_database=store.wait_for_import))
        reader, writer = await connect(server)
        imported = asyncio.create_task(asyncio.to_thread(manager.import_save, alpha, archive))
        try:
            assert await asyncio.to_thread(writing.wait, 4)
            writer.write(guide_packet(1)); await writer.drain()
            ticks = 0
            for _ in range(10):
                await asyncio.sleep(.01)
                ticks += 1
            assert ticks == 10 and calls == []
            assert server.active_connection_count == 1
            release.set()
            await asyncio.wait_for(imported, 5)
            response = await read_response(reader)
            assert CORE_SCHEMAS['L2C_GuideStep'].decode(response.body)['code'] == 10
            writer.write(guide_packet(2)); await writer.drain()
            assert (await read_response(reader)).header.request_id == 2
            assert calls == [1, 2]
        finally:
            release.set()
            await imported
            await close_client(writer)
            await server.stop()
    asyncio.run(scenario())
    assert not store.importing.is_set()


def test_busy_write_returns_failure_but_next_request_uses_same_connection(tmp_path):
    store = PlayerStore(tmp_path / 'busy.sqlite3')
    store.login('game', 1, 0)
    with closing(sqlite3.connect(store.path)) as blocker:
        blocker.execute('PRAGMA wal_autocheckpoint=0')
        blocker.execute('BEGIN IMMEDIATE')
        async def scenario():
            async def handler(context, packet):
                with store.db:
                    store.db.execute('UPDATE players SET login_count=login_count+1 WHERE id=1')
                return OutboundMessage('L2C_GuideStep', {'code': 10})
            server = await start_server(Dispatcher({'C2L_GuideStep': handler}))
            reader, writer = await connect(server)
            try:
                writer.write(guide_packet(1)); await writer.drain()
                response = await read_response(reader)
                assert CORE_SCHEMAS['L2C_GuideStep'].decode(response.body)['code'] == 13
                assert not store.db.in_transaction
                blocker.rollback()
                writer.write(guide_packet(2)); await writer.drain()
                response = await read_response(reader)
                assert CORE_SCHEMAS['L2C_GuideStep'].decode(response.body)['code'] == 10
                assert server.active_connection_count == 1
            finally:
                await close_client(writer)
                await server.stop()
        asyncio.run(scenario())
    store.close()


def test_indexes_cover_every_owner_query_and_migration_is_repeatable(env):
    store, accounts, manager, alpha, beta = env
    manager.prepare_indexes()
    before = [tuple(r) for r in store.db.execute("SELECT name,sql FROM sqlite_schema WHERE type='index' ORDER BY name")]
    manager.prepare_indexes()
    assert before == [tuple(r) for r in store.db.execute("SELECT name,sql FROM sqlite_schema WHERE type='index' ORDER BY name")]
    for table in manager._missing.copy():
        manager.exists(table)
    from x2server.player.save_manager import PLAYER_TABLES, JOIN_OWNERS
    for table in PLAYER_TABLES:
        if not manager.exists(table) or table in JOIN_OWNERS:
            continue
        plan = [r[3] for r in store.db.execute(f'EXPLAIN QUERY PLAN SELECT * FROM {table} WHERE player_id=? ORDER BY rowid', (alpha,))]
        assert not any(step.startswith('SCAN ') or 'TEMP B-TREE' in step for step in plan), (table, plan)


def test_large_export_peak_is_below_uncompressed_table_size(tmp_path):
    store = PlayerStore(tmp_path / 'large.sqlite3')
    store.login('large', 1, 0)
    with store.db:
        store.db.execute('CREATE TABLE economy_runs(uuid TEXT PRIMARY KEY, player_id INTEGER, payload TEXT)')
        value = 'abc12345' * 1024
        store.db.executemany('INSERT INTO economy_runs VALUES (?,1,?)', ((str(i), value) for i in range(4096)))
    manager = SaveManager(store)
    manager.prepare_indexes()
    try:
        tracemalloc.start()
        archive = manager.export_save(1)
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        assert peak < 32 * 1024 * 1024, peak
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            assert zipped.getinfo('save.json').file_size > 32 * 1024 * 1024
        assert len(manager.parse_save(archive).rows['economy_runs']) == 4096
    finally:
        tracemalloc.stop()
        manager.close(); store.close()


def test_import_parses_uploaded_archive_only_once_and_clears_barrier_on_failure(env, monkeypatch):
    store, accounts, manager, alpha, beta = env
    archive = manager.export_save(alpha)
    parsed = []
    original = manager.parse_save
    def counting(data):
        parsed.append(len(data))
        return original(data)
    monkeypatch.setattr(manager, 'parse_save', counting)
    manager.import_save(alpha, archive)
    assert len(parsed) == 1
    before = manager.canonical_state(alpha)
    with pytest.raises(AccountOnlineError):
        manager.import_save(alpha, archive, offline_check=lambda: False)
    assert not store.importing.is_set()
    assert manager.canonical_state(alpha) == before


def test_heavy_save_requests_are_rejected_without_queuing_more_big_archives(env, monkeypatch):
    store, accounts, manager, alpha, beta = env
    api = SaveManagerAPI(manager, accounts, lambda: set())
    body = json.loads(api.respond('POST', '/save-manager/auth', b'account=alpha&password=pw-alpha', '')[2])
    auth = 'Bearer ' + body['token']
    entered, release = threading.Event(), threading.Event()
    original = manager.export_save
    def paused(player):
        entered.set(); assert release.wait(3)
        return original(player)
    monkeypatch.setattr(manager, 'export_save', paused)
    results = []
    worker = threading.Thread(target=lambda: results.append(api.respond('POST', '/save-manager/export', b'', auth)))
    worker.start()
    try:
        assert entered.wait(2)
        busy = api.respond('POST', '/save-manager/export', b'', auth)
        assert busy[0] == 503 and json.loads(busy[2])['error'] == 'save_manager_busy'
    finally:
        release.set(); worker.join(5)
    assert results[0][0] == 200
    assert api.respond('POST', '/save-manager/status', b'', auth)[0] == 200


def test_only_coordinated_checkpoint_runs_and_loop_does_not_block(env, monkeypatch):
    store, accounts, manager, alpha, beta = env
    for db in (store.db, accounts.db, manager.db):
        assert db.execute('PRAGMA wal_autocheckpoint').fetchone()[0] == 0
        assert db.execute('PRAGMA synchronous').fetchone()[0] == 2
    locked, release = threading.Event(), threading.Event()
    def hold_writer_guard():
        with store.checkpoint_guard:
            locked.set()
            assert release.wait(3)
    worker = threading.Thread(target=hold_writer_guard)
    calls = []
    original_checkpoint = store._run_checkpoint
    def observe(db):
        calls.append(threading.get_ident())
        return original_checkpoint(db)
    monkeypatch.setattr(store, '_run_checkpoint', observe)
    async def scenario():
        watcher = asyncio.create_task(store.checkpoint_watch(interval=.01))
        try:
            worker.start()
            assert await asyncio.to_thread(locked.wait, 2)
            for _ in range(5):
                await asyncio.sleep(.01)
            assert not calls
            release.set()
            await asyncio.to_thread(worker.join, 2)
            await asyncio.sleep(.03)
            assert calls
        finally:
            release.set()
            watcher.cancel()
            try:
                await watcher
            except asyncio.CancelledError:
                pass
    asyncio.run(scenario())
    assert all(t != threading.get_ident() for t in calls)


def test_export_limits_and_backup_validation_are_preserved(env, monkeypatch):
    store, accounts, manager, alpha, beta = env
    import x2server.player.save_manager as module
    old = manager.export_save(alpha)
    first = manager.import_save(alpha, old)
    backup = module.Path(first['backup'])
    before = backup.read_bytes()
    monkeypatch.setattr(module, 'MAX_ENTRY_UNCOMPRESSED', 20)
    with pytest.raises(ValueError, match='limit'):
        manager.export_save(alpha)
    assert not manager.db.in_transaction
    assert backup.read_bytes() == before


def test_checkpoint_guard_excludes_external_admin_process(tmp_path):
    import subprocess, sys, os
    from x2server.player.db_guard import CheckpointGuard
    guard = CheckpointGuard(tmp_path / 'shared.sqlite3')
    process_env = dict(os.environ, PYTHONPATH=str(__import__('pathlib').Path(__file__).resolve().parents[2] / 'src'))
    code = 'from x2server.player.db_guard import CheckpointGuard; import sys; g=CheckpointGuard(sys.argv[1]); print(g.acquire(blocking=False))'
    try:
        with guard:
            result = subprocess.run([sys.executable, '-B', '-c', code, str(tmp_path / 'shared.sqlite3')], capture_output=True, text=True, timeout=5, env=process_env)
            assert result.returncode == 0, result.stderr
            assert result.stdout.strip() == 'False'
        result = subprocess.run([sys.executable, '-B', '-c', code, str(tmp_path / 'shared.sqlite3')], capture_output=True, text=True, timeout=5, env=process_env)
        assert result.returncode == 0 and result.stdout.strip() == 'True', result.stderr
    finally:
        guard.close()


def test_busy_checkpoint_does_not_kill_checkpoint_watch(env):
    store, accounts, manager, alpha, beta = env
    async def scenario():
        cursor = store.db.execute('SELECT id FROM players')
        cursor.fetchone()
        task = asyncio.create_task(store.checkpoint_watch(interval=.01))
        try:
            await asyncio.sleep(.03)
            assert not task.done()
            cursor.close()
            await asyncio.sleep(.03)
            assert not task.done()
        finally:
            cursor.close()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    asyncio.run(scenario())


def test_failed_staged_backup_verification_keeps_previous_backup_and_save(env, monkeypatch):
    store, accounts, manager, alpha, beta = env
    archive = manager.export_save(alpha)
    first = manager.import_save(alpha, archive)
    from pathlib import Path
    backup = Path(first['backup'])
    original_bytes = backup.read_bytes()
    original_state = manager.canonical_state(alpha)
    def fail_verification(path):
        raise ValueError('staged backup checksum failed')
    monkeypatch.setattr(manager, '_verify_export', fail_verification)
    with pytest.raises(ValueError, match='checksum failed'):
        manager.import_save(alpha, archive)
    assert backup.read_bytes() == original_bytes
    assert manager.canonical_state(alpha) == original_state
    assert not store.importing.is_set()
    assert not list(backup.parent.glob('*.tmp'))


def test_schema_migration_refreshes_export_columns(env):
    store, accounts, manager, alpha, beta = env
    assert 'extra_state' not in manager.columns('activity_state')
    store.db.execute("ALTER TABLE activity_state ADD COLUMN extra_state TEXT DEFAULT 'new-value'")
    manager.prepare_indexes()
    plan = manager.parse_save(manager.export_save(alpha))
    assert plan.rows['activity_state']
    assert all(row['extra_state'] == 'new-value' for row in plan.rows['activity_state'])


def test_online_check_is_repeated_inside_import_barrier(env):
    store, accounts, manager, alpha, beta = env
    archive = manager.export_save(alpha)
    before = manager.canonical_state(alpha)
    states = iter((set(), {alpha}))
    api = SaveManagerAPI(manager, accounts, lambda: next(states))
    auth = 'Bearer ' + json.loads(api.respond('POST', '/save-manager/auth', b'account=alpha&password=pw-alpha', '')[2])['token']
    result = api.respond('POST', '/save-manager/import', archive, auth)
    assert result[0] == 409 and json.loads(result[2])['error'] == 'account_online'
    assert not store.importing.is_set()
    assert manager.canonical_state(alpha) == before


def test_http_busy_returns_retryable_response_instead_of_dropping_transport():
    import urllib.request, urllib.error
    from x2server.bootstrap.http_server import BootstrapHTTPServer
    from x2server.bootstrap.service import HTTPResponse
    class Service:
        calls = 0
        def respond(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise sqlite3.OperationalError('database is locked')
            return HTTPResponse(200, 'application/json', b'{"code":"ok"}')
    async def scenario():
        service = Service()
        server = BootstrapHTTPServer('127.0.0.1', 0, service)
        await server.start()
        def call():
            request = urllib.request.Request(f'http://127.0.0.1:{server.bound_port}/loginwithpw', data=b'', method='POST')
            try:
                response = urllib.request.urlopen(request, timeout=2)
            except urllib.error.HTTPError as response:
                return response.code, json.loads(response.read()), response.headers.get('Retry-After')
            with response:
                return response.status, json.loads(response.read()), response.headers.get('Retry-After')
        try:
            assert await asyncio.to_thread(call) == (503, {'error': 'database_busy'}, '1')
            assert (await asyncio.to_thread(call))[:2] == (200, {'code': 'ok'})
            assert service.calls == 2
        finally:
            await server.stop()
    asyncio.run(scenario())
