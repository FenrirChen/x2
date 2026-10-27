from tests.unit.test_economy import env
from x2server.player.task_calendar import task_period


def test_steady_task_period_checks_do_not_rewrite_or_scan_each_task(env):
    store, economy, _ = env
    economy.ensure_periods(1)
    before = store.db.total_changes
    queries = []
    store.db.set_trace_callback(queries.append)
    try:
        economy.ensure_periods(1)
    finally:
        store.db.set_trace_callback(None)
    assert len(queries) <= 12, queries
    assert store.db.total_changes == before
    assert not store.db.in_transaction


def test_batched_task_repair_preserves_paid_claims_level_unlock_and_rollover(env):
    store, economy, _ = env
    now = [int(economy.clock())]; economy.clock = lambda: now[0]
    economy.ensure_periods(1)
    task = 630019
    start, _ = task_period(1, now[0])
    with economy.transaction():
        economy._grant(1, f'task:1:{start}:{task}', {1237901: 1})
        store.db.execute('UPDATE economy_tasks SET progress=0,claimed=0 WHERE player_id=1 AND task_id=?',(task,))
    economy.ensure_periods(1)
    assert tuple(store.db.execute('SELECT progress,claimed FROM economy_tasks WHERE player_id=1 AND task_id=?',(task,)).fetchone()) == (1,1)
    # Missing eligible rows are restored even inside an already created period.
    with economy.transaction():
        store.db.execute('DELETE FROM economy_tasks WHERE player_id=1 AND task_id=?',(task,))
    economy.ensure_periods(1)
    assert tuple(store.db.execute('SELECT progress,claimed FROM economy_tasks WHERE player_id=1 AND task_id=?',(task,)).fetchone()) == (1,1)
    now[0] += 86400
    economy.ensure_periods(1)
    assert tuple(store.db.execute('SELECT progress,claimed FROM economy_tasks WHERE player_id=1 AND task_id=?',(task,)).fetchone()) == (0,0)
    now[0] -= 86400
    economy.ensure_periods(1)
    assert tuple(store.db.execute('SELECT progress,claimed FROM economy_tasks WHERE player_id=1 AND task_id=?',(task,)).fetchone()) == (0,0)


def test_achievement_refresh_is_read_only_when_progress_is_unchanged(env):
    store, economy, _ = env
    economy.achievements.refresh(1)
    before = store.db.total_changes
    economy.achievements.refresh(1)
    assert store.db.total_changes == before
    assert not store.db.in_transaction


def test_period_check_cache_observes_external_writes_and_local_rollback(env):
    import sqlite3
    from contextlib import closing
    store, economy, _ = env
    economy.ensure_periods(1)
    task = 630019
    with closing(sqlite3.connect(store.path)) as other:
        other.execute('DELETE FROM economy_tasks WHERE player_id=1 AND task_id=?',(task,));other.commit()
    economy.ensure_periods(1)
    assert store.db.execute('SELECT 1 FROM economy_tasks WHERE player_id=1 AND task_id=?',(task,)).fetchone()
    with store.db:
        store.db.execute('DELETE FROM economy_tasks WHERE player_id=1 AND task_id=?',(task,))
    try:
        with economy.transaction():
            economy.ensure_periods(1)
            raise ValueError('roll back newly repaired task')
    except ValueError:
        pass
    assert not store.db.execute('SELECT 1 FROM economy_tasks WHERE player_id=1 AND task_id=?',(task,)).fetchone()
    economy.ensure_periods(1)
    assert store.db.execute('SELECT 1 FROM economy_tasks WHERE player_id=1 AND task_id=?',(task,)).fetchone()
