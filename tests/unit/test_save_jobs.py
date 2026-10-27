import asyncio
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time

import pytest

from tests.unit.test_save_manager import env
from x2server.bootstrap.save_manager_api import SaveManagerAPI
from x2server.player.db_guard import CheckpointGuard
from x2server.player.save_jobs import SaveJobRunner
from x2server.player.save_limits import SaveCooldownError, SaveLimits
from x2server.player.save_manager import AccountOnlineError, SaveManager


def auth(api, name='alpha', password='pw-alpha'):
    result = api.respond('POST', '/save-manager/auth', f'account={name}&password={password}'.encode(), '')
    return 'Bearer ' + json.loads(result[2])['token']


def test_isolated_worker_preserves_complete_rich_archive_and_backup(env):
    store, accounts, manager, alpha, beta = env
    manager.prepare_indexes()
    runner = SaveJobRunner(store, manager.backup_root)
    before = manager.canonical_state(alpha)
    archive = runner.run('export', alpha)
    assert set(manager.parse_save(archive).rows) == set(before['tables'])
    old = store.get(alpha)
    store.save_snapshot(alpha, {**old['snapshot'], 'gold': 123456}, old['revision'])
    backup_state = manager.canonical_state(alpha)
    result = runner.run('import', alpha, archive, offline_check=lambda: True)
    assert manager.canonical_state(alpha) == before
    backup = Path(result['backup'])
    assert backup.is_file() and len(list(backup.parent.glob('*.x2save'))) == 1
    manager.import_save(beta, backup.read_bytes())
    assert manager.canonical_state(beta) == backup_state
    assert not store.importing.is_set()


def test_isolated_online_recheck_and_bad_zip_never_change_state(env):
    store, accounts, manager, alpha, beta = env
    runner = SaveJobRunner(store, manager.backup_root)
    archive = manager.export_save(alpha)
    before = manager.canonical_state(alpha)
    with pytest.raises(AccountOnlineError):
        runner.run('import', alpha, archive, offline_check=lambda: False)
    with pytest.raises(ValueError):
        runner.run('import', alpha, b'broken archive')
    assert not store.importing.is_set()
    assert manager.canonical_state(alpha) == before


def test_cooldowns_persist_across_api_restart_and_archive_restore(env):
    store, accounts, manager, alpha, beta = env
    archive = manager.export_save(alpha)
    limits = SaveLimits(600, 60, 60)
    api = SaveManagerAPI(manager, accounts, lambda: set(), isolated_jobs=True, limits=limits)
    token = auth(api)
    first = api.respond('POST', '/save-manager/export', b'', token)
    assert first[0] == 200
    second = api.respond('POST', '/save-manager/export', b'', token)
    assert second[0] == 429 and json.loads(second[2])['retry_after'] > 0
    # Export must not prevent immediately importing that exported archive.
    assert api.respond('POST', '/save-manager/import', archive, token)[0] == 200
    api = SaveManagerAPI(manager, accounts, lambda: set(), isolated_jobs=True, limits=limits)
    blocked = api.respond('POST', '/save-manager/import', archive, auth(api))
    assert blocked[0] == 429 and json.loads(blocked[2])['retry_after'] >= 590
    assert api.respond('POST', '/save-manager/import', archive, auth(api, 'beta', 'pw-beta'))[0] == 429
    assert 'server_settings' not in manager.parse_save(manager.export_save(alpha)).rows
    # Even an administrator restore cannot roll back server-owned cooldowns.
    manager.import_save(alpha, archive)
    assert api.respond('POST', '/save-manager/import', archive, auth(api))[0] == 429


def test_invalid_and_online_imports_do_not_consume_cooldown(env):
    store, accounts, manager, alpha, beta = env
    api = SaveManagerAPI(manager, accounts, lambda: set(), isolated_jobs=True, limits=SaveLimits())
    token = auth(api)
    assert api.respond('POST', '/save-manager/import', b'bad', token)[0] == 400
    assert not manager.db.execute("SELECT * FROM server_settings WHERE key LIKE 'save-limit:%'").fetchall()
    api.online_player_ids = lambda: {alpha}
    assert api.respond('POST', '/save-manager/import', manager.export_save(alpha), token)[0] == 409
    assert not manager.db.execute("SELECT * FROM server_settings WHERE key LIKE 'save-limit:%'").fetchall()


def test_worker_timeout_rolls_back_before_releasing_barrier(env, monkeypatch):
    store, accounts, manager, alpha, beta = env
    before = manager.canonical_state(alpha)
    actual = subprocess.Popen
    code = """import json,sys,sqlite3,time
from pathlib import Path
r=json.loads(sys.stdin.readline())
print(json.dumps({'event':'write_begin'}),flush=True)
assert json.loads(sys.stdin.readline())['allow']
db=sqlite3.connect(r['database']);db.execute('BEGIN IMMEDIATE')
db.execute('DELETE FROM inventory WHERE player_id=?',(r['player'],))
Path(r['backup_root']).mkdir(parents=True,exist_ok=True)
Path(r['backup_root'],'writer-entered').write_text('yes')
time.sleep(20)
"""
    def launch(args, **kwargs):
        return actual([getattr(sys,'_base_executable',sys.executable), '-B', '-c', code], **kwargs)
    monkeypatch.setattr(subprocess, 'Popen', launch)
    runner = SaveJobRunner(store, manager.backup_root, timeout=1)
    with pytest.raises(RuntimeError):
        runner.run('import', alpha, b'input', offline_check=lambda: True)
    assert (manager.backup_root / 'writer-entered').is_file()
    assert not store.importing.is_set()
    assert manager.canonical_state(alpha) == before
    with closing(sqlite3.connect(store.path, timeout=.05)) as db:
        db.execute('BEGIN IMMEDIATE'); db.rollback()


def test_background_checkpoint_keeps_loop_running_and_drains_on_cancel(env, monkeypatch):
    store, accounts, manager, alpha, beta = env
    entered, release = threading.Event(), threading.Event()
    actual = store._run_checkpoint
    def slow(db):
        entered.set()
        assert release.wait(4)
        return actual(db)
    monkeypatch.setattr(store, '_run_checkpoint', slow)
    async def scenario():
        watcher = asyncio.create_task(store.checkpoint_watch(.001))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            started = time.monotonic()
            for _ in range(20):
                await asyncio.sleep(.002)
                row = store.get(beta)
                store.save_snapshot(beta, row['snapshot'], row['revision'])
            assert time.monotonic() - started < 1
            watcher.cancel()
            await asyncio.sleep(.02)
            assert not watcher.done()  # Cannot close the lock under its worker.
            guard = CheckpointGuard(store.path)
            try:
                assert not guard.acquire(blocking=False)
            finally:
                guard.close()
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await watcher
    # The external-file-lock check is separate, to avoid re-entering a held lock.
    asyncio.run(scenario())


def test_large_bulk_roundtrip_and_failed_batch_rollback(env):
    store, accounts, manager, alpha, beta = env
    with store.db:
        store.db.executemany('INSERT INTO inventory VALUES (?,?,?)',
                             ((alpha, 1900000+i, i+1) for i in range(600)))
    manager.prepare_indexes()
    archive = manager.export_save(alpha)
    before = manager.canonical_state(alpha)
    runner = SaveJobRunner(store, manager.backup_root)
    runner.run('import', beta, archive, offline_check=lambda: True)
    assert manager.canonical_state(beta) == before
    plan = manager.parse_save(archive)
    rows = [{'player_id':beta,'item_id':2000000+i,'quantity':i} for i in range(600)]
    rows[-1]['item_id'] = rows[0]['item_id']
    manager.db.execute('BEGIN IMMEDIATE')
    try:
        with pytest.raises(sqlite3.IntegrityError):
            manager._insert_many(manager.db, 'inventory', rows, plan)
    finally:
        manager.db.rollback()
    assert manager.canonical_state(beta) == before


def test_http_busy_upload_is_drained_without_entering_save_api():
    import urllib.request
    import urllib.error
    from x2server.bootstrap.http_server import BootstrapHTTPServer
    from x2server.bootstrap.service import HTTPResponse
    entered, release = threading.Event(), threading.Event()
    class Service:
        calls = 0
        def respond(self, *args, **kwargs):
            self.calls += 1
            entered.set()
            assert release.wait(5)
            return HTTPResponse(200,'application/json',b'{"code":"ok"}')
    def post(url, body):
        request = urllib.request.Request(url,data=body)
        try:
            response = urllib.request.urlopen(request,timeout=5)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status,json.loads(response.read())
    async def scenario():
        service = Service(); server = BootstrapHTTPServer('127.0.0.1',0,service)
        await server.start()
        url = f'http://127.0.0.1:{server.bound_port}/save-manager/import'
        first = asyncio.create_task(asyncio.to_thread(post,url,b'first'))
        try:
            assert await asyncio.to_thread(entered.wait,2)
            rejected = await asyncio.to_thread(post,url,b'x'*(2*1024*1024))
            assert rejected == (503,{'error':'save_manager_busy'})
            assert service.calls == 1
        finally:
            release.set(); await first; await server.stop()
    asyncio.run(scenario())


def test_dispatch_burst_yields_between_sync_handlers():
    from x2server.network.dispatcher import Dispatcher, DispatchContext, OutboundMessage
    from x2server.network.session import SessionState
    from tests.unit.test_battle import packet
    async def scenario():
        async def handler(context, request):
            time.sleep(.005)  # stand in for a synchronous durable SQLite commit
            return OutboundMessage('L2C_GuideStep',{'code':10})
        dispatcher = Dispatcher({'C2L_GuideStep':handler})
        ctx = DispatchContext('test','local',SessionState('test','test'))
        gaps = [];done = False
        async def heartbeat():
            while not done:
                start = time.perf_counter(); await asyncio.sleep(.001)
                gaps.append(time.perf_counter()-start)
        watch = asyncio.create_task(heartbeat())
        try:
            replies = await asyncio.gather(*(dispatcher.dispatch(ctx,packet({'stepId':1,'stepState':2},i+1,'C2L_GuideStep')) for i in range(50)))
            assert all(r.response.values['code']==10 for r in replies)
            assert len(gaps)>5 and max(gaps)<.1
        finally:
            done = True; await watch
    asyncio.run(scenario())


def test_dispatch_rechecks_import_after_waiting_its_turn(env):
    from x2server.network.dispatcher import Dispatcher, DispatchContext, OutboundMessage
    from x2server.network.session import SessionState
    from tests.unit.test_battle import packet
    store, accounts, manager, alpha, beta = env
    async def scenario():
        calls = []
        async def handler(context, request):
            calls.append(1)
            return OutboundMessage('L2C_GuideStep',{'code':10})
        dispatcher = Dispatcher({'C2L_GuideStep':handler},wait_for_database=store.wait_for_import)
        ctx = DispatchContext('test','local',SessionState('test','test'))
        await dispatcher._dispatch_turn.acquire()
        task = asyncio.create_task(dispatcher.dispatch(ctx,packet({'stepId':1,'stepState':2},1,'C2L_GuideStep')))
        await asyncio.sleep(.01)
        store.importing.set()
        dispatcher._dispatch_turn.release()
        try:
            await asyncio.sleep(.03)
            assert calls == []
        finally:
            store.importing.clear()
        assert (await task).response.values['code']==10
    asyncio.run(scenario())


def test_worker_losing_supervisor_pipe_cannot_leave_partial_save(env, tmp_path):
    import os
    store, accounts, manager, alpha, beta = env
    archive = manager.export_save(alpha)
    original = manager.canonical_state(alpha)
    old = store.get(alpha)
    store.save_snapshot(alpha,{**old['snapshot'],'gold':987654},old['revision'])
    changed = manager.canonical_state(alpha)
    source = tmp_path / 'worker-input.x2save'; source.write_bytes(archive)
    cfg = {'operation':'import','player':alpha,'database':str(store.path.resolve()),
           'backup_root':str(manager.backup_root.resolve()), 'input':str(source),
           'output':str(tmp_path/'unused-output'),'actor':'test','limits':None}
    process_env = dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[2]/'src'))
    options = {'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
    proc = subprocess.Popen([getattr(sys,'_base_executable',sys.executable),'-B','-m','x2server.player.save_worker'],
                            stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,encoding='utf-8',env=process_env,**options)
    try:
        proc.stdin.write(json.dumps(cfg)+'\n');proc.stdin.flush()
        assert json.loads(proc.stdout.readline())['event']=='write_begin'
        with store.import_write():
            proc.stdin.write('{"allow":true}\n');proc.stdin.flush()
            proc.stdin.close()  # Simulate the server process disappearing.
            assert proc.wait(timeout=10) in (0,70)
        after = manager.canonical_state(alpha)
        assert after == original or after == changed
        assert store.db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
        assert not store.importing.is_set()
    finally:
        if proc.poll() is None:
            proc.kill();proc.wait()
        if not proc.stdin.closed:proc.stdin.close()
        proc.stdout.close()


def test_shutdown_kills_and_drains_active_writer_before_database_close(env, monkeypatch):
    store, accounts, manager, alpha, beta = env
    before = manager.canonical_state(alpha)
    manager.backup_root.mkdir(parents=True,exist_ok=True)
    marker = manager.backup_root / 'shutdown-writer-entered'
    actual = subprocess.Popen
    code = """import json,sys,sqlite3,time
from pathlib import Path
r=json.loads(sys.stdin.readline())
print(json.dumps({'event':'write_begin'}),flush=True)
assert json.loads(sys.stdin.readline())['allow']
db=sqlite3.connect(r['database']);db.execute('BEGIN IMMEDIATE')
db.execute('DELETE FROM inventory WHERE player_id=?',(r['player'],))
Path(r['backup_root'],'shutdown-writer-entered').write_text('yes')
time.sleep(20)
"""
    def launch(args, **kwargs):
        return actual([getattr(sys,'_base_executable',sys.executable),'-B','-c',code],**kwargs)
    monkeypatch.setattr(subprocess,'Popen',launch)
    runner = SaveJobRunner(store,manager.backup_root,timeout=30)
    errors = []
    def run():
        try:runner.run('import',alpha,b'input',offline_check=lambda:True)
        except RuntimeError as exc:errors.append(exc)
    worker = threading.Thread(target=run);worker.start()
    try:
        deadline = time.monotonic()+5
        while not marker.exists() and time.monotonic()<deadline:
            time.sleep(.01)
        assert marker.exists() and store.importing.is_set()
        runner.close()
        worker.join(3)
        assert not worker.is_alive() and errors
        assert not store.importing.is_set()
        assert manager.canonical_state(alpha)==before
        assert not runner._processes
        with pytest.raises(RuntimeError):runner.run('export',alpha)
    finally:
        runner.close();worker.join(5)


def test_no_cooldown_allows_consecutive_full_exports_and_imports(env, monkeypatch):
    store, accounts, manager, alpha, beta = env
    # Older environment settings and persisted cooldowns must not reactivate
    # restrictions in the production API's default (limits=None) configuration.
    monkeypatch.setenv('X2_SAVE_IMPORT_COOLDOWN_SECONDS','600')
    monkeypatch.setenv('X2_SAVE_GLOBAL_IMPORT_COOLDOWN_SECONDS','60')
    monkeypatch.setenv('X2_SAVE_EXPORT_COOLDOWN_SECONDS','60')
    keys = (f'save-limit:import:{alpha}','save-limit:import:global',f'save-limit:export:{alpha}')
    for key in keys:
        manager.db.execute('INSERT OR REPLACE INTO server_settings VALUES (?,?)', (key,str(time.time()+86400)))
    before_limits = {r[0]:r[1] for r in manager.db.execute("SELECT key,value FROM server_settings WHERE key LIKE 'save-limit:%'")}
    before = manager.canonical_state(alpha)
    api = SaveManagerAPI(manager,accounts,lambda:set(),isolated_jobs=True)
    assert api.limits is None
    try:
        token = auth(api)
        archives = [api.respond('POST','/save-manager/export',b'',token) for _ in range(2)]
        assert all(r[0]==200 and r[2].startswith(b'PK') for r in archives)
        for response in archives:
            assert manager.parse_save(response[2]).source_player_id == alpha
        for _ in range(2):
            result = api.respond('POST','/save-manager/import',archives[0][2],auth(api))
            assert result[0]==200 and json.loads(result[2])['code']=='ok'
            assert manager.canonical_state(alpha)==before
        assert len(list((manager.backup_root/f'player_{alpha}').glob('*.x2save')))==1
        assert {r[0]:r[1] for r in manager.db.execute("SELECT key,value FROM server_settings WHERE key LIKE 'save-limit:%'")} == before_limits
        assert api.respond('POST','/save-manager/import',b'broken archive',auth(api))[0]==400
    finally:
        api.close()
