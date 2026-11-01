"""Regressions for database maintenance readiness, using real SQLite guards."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from tests.unit.test_diagnostic_retention import data
from x2server.player.db_guard import CheckpointGuard
from x2server.player.diagnostic_retention import DiagnosticRetention


@pytest.mark.parametrize('separate_guard', [False, True])
def test_busy_checkpoint_does_not_pause_game_or_advance_cursor(data, separate_guard):
    store, _, _ = data
    worker = DiagnosticRetention(store)
    worker.position['fight_drop_items'] = 11
    entered, release = threading.Event(), threading.Event()
    errors = []
    def blocker():
        guard = CheckpointGuard(store.path) if separate_guard else store.checkpoint_guard
        try:
            with guard:
                entered.set()
                assert release.wait(5)
        except BaseException as exc:
            errors.append(exc)
        finally:
            if separate_guard:
                guard.close()
    thread = threading.Thread(target=blocker)
    thread.start()
    assert entered.wait(3)
    async def scenario():
        task = asyncio.create_task(worker._step_guarded('fight_drop_items'))
        try:
            await asyncio.sleep(.05)
            # All 50 game requests must pass while the checkpoint owns its guard.
            requests = asyncio.gather(*(store.wait_for_import() for _ in range(50)))
            await asyncio.wait_for(requests, .2)
            assert await asyncio.wait_for(asyncio.shield(task), .2) == (0, False)
            assert worker.position['fight_drop_items'] == 11
            assert not store.maintenance.is_set() and not store.importing.is_set()
        finally:
            release.set()
            await task
    try:
        asyncio.run(scenario())
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive() and not errors


def test_executor_queue_does_not_pause_game(data):
    store, _, _ = data
    worker = DiagnosticRetention(store)
    entered, release = threading.Event(), threading.Event()
    def blocked_job():
        entered.set()
        assert release.wait(5)
    async def scenario():
        loop = asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=1))
        busy = loop.run_in_executor(None, blocked_job)
        assert entered.wait(3)
        task = asyncio.create_task(worker._step_guarded('fight_drop_items'))
        try:
            await asyncio.sleep(.03)
            await asyncio.wait_for(store.wait_for_import(), .2)
            assert not store.maintenance.is_set()
        finally:
            release.set()
            await busy
            await task
        assert not store.maintenance.is_set() and not store.importing.is_set()
    asyncio.run(scenario())


def test_main_loop_transaction_defers_batch(data):
    store, _, _ = data
    worker = DiagnosticRetention(store)
    async def scenario():
        store.db.execute('BEGIN')
        try:
            assert await worker._step_guarded('fight_drop_items') == (0, False)
            assert store.db.in_transaction
            assert not store.maintenance.is_set() and not store.importing.is_set()
        finally:
            store.db.rollback()
    asyncio.run(scenario())


def test_cancel_queued_cleanup_drains_without_pausing_game(data):
    store, _, _ = data
    worker = DiagnosticRetention(store)
    entered, release = threading.Event(), threading.Event()
    def blocked_job():
        entered.set()
        assert release.wait(5)
    async def scenario():
        loop = asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=1))
        busy = loop.run_in_executor(None, blocked_job)
        assert entered.wait(3)
        task = asyncio.create_task(worker._step_guarded('fight_drop_items'))
        try:
            await asyncio.sleep(.03)
            task.cancel()
            await asyncio.sleep(.03)
            assert not task.done()
            await asyncio.wait_for(store.wait_for_import(), .2)
        finally:
            release.set()
            await busy
            with pytest.raises(asyncio.CancelledError):
                await task
        assert not store.maintenance.is_set() and not store.importing.is_set()
    asyncio.run(scenario())


def test_batch_failure_releases_own_guard_and_barrier(data):
    store, _, _ = data
    worker = DiagnosticRetention(store)
    def fail(table):
        raise RuntimeError('injected ready batch failure')
    worker.step = fail
    async def scenario():
        with pytest.raises(RuntimeError, match='injected ready batch failure'):
            await worker._step_guarded('fight_drop_items')
        assert not store.maintenance.is_set() and not store.importing.is_set()
        assert store.checkpoint_guard.acquire(blocking=False)
        store.checkpoint_guard.release()
        await asyncio.wait_for(store.wait_for_import(), .2)
    asyncio.run(scenario())


def test_checkout_lifecycle_uses_uuid_lookup_without_losing_duplicate_owner_checks(data):
    from x2server.player.diagnostic_retention import condition, live_tables, prune_account
    store, _, _ = data
    db = store.db
    cutoff = 1800000000
    with db:
        db.execute('CREATE INDEX ready_test_entry_uuid ON battle_entries(uuid)')
        db.execute('CREATE INDEX ready_test_entry_owner ON battle_entries(player_id)')
        cases = [('foreign-only', None), ('recent', cutoff+1),
                 ('boundary', cutoff), ('unknown-time', 0), ('old', cutoff-1)]
        for key, stamp in cases:
            db.execute("INSERT INTO economy_runs(uuid,player_id,session_id,section_id,settled) VALUES (?,1,'test',2110801,1)", (key,))
            db.execute('INSERT INTO economy_checkouts VALUES (1,?,?)', (key,key))
            # A foreign old row is deliberately the first matching UUID.
            db.execute('INSERT INTO battle_entries(player_id,request_key,uuid,created_at,response) VALUES (2,?,?,?,?)',
                       (key,key,cutoff-1,b'foreign'))
            if stamp is not None:
                db.execute('INSERT INTO battle_entries(player_id,request_key,uuid,created_at,response) VALUES (1,?,?,?,?)',
                           (key,key,stamp,b'own'))
        predicate = condition('economy_checkouts',live_tables(db))
        sql = 'SELECT t.uuid FROM economy_checkouts t WHERE '+predicate
        assert [r[0] for r in db.execute(sql,{'cutoff':cutoff})] == ['old']
        plan = ' '.join(r[3] for r in db.execute('EXPLAIN QUERY PLAN '+sql,{'cutoff':cutoff}))
        assert 'USING INDEX ready_test_entry_uuid (uuid=?)' in plan
        assert prune_account(db,1,cutoff)['economy_checkouts'] == 1
        assert db.execute('SELECT count(*) FROM economy_checkouts').fetchone()[0] == 4


def test_loop_can_take_checkpoint_guard_before_acknowledging_worker(data):
    store, _, _ = data
    worker = DiagnosticRetention(store)
    async def scenario():
        loop = asyncio.get_running_loop()
        original = loop.call_soon_threadsafe
        available = []
        def post(callback, *args, **kwargs):
            if getattr(callback, '__name__', '') == 'publish':
                def check_and_publish():
                    owned = store.checkpoint_guard.acquire(blocking=False)
                    available.append(owned)
                    if owned:
                        store.checkpoint_guard.release()
                    callback(*args)
                return original(check_and_publish, **kwargs)
            return original(callback, *args, **kwargs)
        loop.call_soon_threadsafe = post
        try:
            await worker._step_guarded('fight_drop_items')
            assert available == [True], 'worker must not hold a lock needed by synchronous login'
        finally:
            loop.call_soon_threadsafe = original
    asyncio.run(scenario())


def test_checkpoint_winning_after_preflight_defers_without_waiting(data):
    store, _, _ = data
    worker = DiagnosticRetention(store)
    entered, release = threading.Event(), threading.Event()
    def blocker():
        with store.checkpoint_guard:
            entered.set()
            assert release.wait(5)
    thread = threading.Thread(target=blocker)
    async def scenario():
        loop = asyncio.get_running_loop()
        original = loop.call_soon_threadsafe
        def post(callback,*args,**kwargs):
            if getattr(callback,'__name__','') == 'publish':
                thread.start()
                assert entered.wait(3)
            return original(callback,*args,**kwargs)
        loop.call_soon_threadsafe = post
        try:
            assert await asyncio.wait_for(worker._step_guarded('fight_drop_items'),.5) == (0,False)
            assert not store.maintenance.is_set() and not store.importing.is_set()
            assert worker.position['fight_drop_items'] == 0
            await asyncio.wait_for(store.wait_for_import(),.2)
        finally:
            loop.call_soon_threadsafe=original
            release.set()
            thread.join(5)
    asyncio.run(scenario())
