"""Retain 48h of audited diagnostic copies; never prune reward or task data.

No battle/receipt/body/ledger is removed. Missing lifecycle evidence fails closed.
"""
import asyncio
from contextlib import closing
import logging
import sqlite3
import time

LOGGER = logging.getLogger('x2.diagnostic_retention')
KEEP_SECONDS = 48 * 3600
TABLES = ('fight_drop_items', 'fight_drop_claims', 'fight_drop_observations',
          'battle_shop_purchases', 'battle_shop_pickups', 'economy_checkouts')


def live_tables(db):
    return {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def condition(table, live):
    """SQL boolean for fixed alias t and named parameter :cutoff."""
    def age(expr):
        return f'({expr} IS NOT NULL AND {expr}>0 AND {expr}<:cutoff)'
    def settled(player, run):
        return (f'EXISTS (SELECT 1 FROM economy_runs r WHERE r.uuid={run} '
                f'AND r.player_id={player} AND r.settled=1)')
    if table not in live or 'economy_runs' not in live:
        return '0'
    if table in ('battle_shop_purchases', 'battle_shop_pickups'):
        return (age('t.created_at') + ' AND NOT EXISTS (SELECT 1 FROM economy_runs r '
                'WHERE r.player_id=t.player_id AND r.settled=0 '
                'AND (r.section_id=t.section_id OR t.section_id=0))')
    if table == 'fight_drop_observations':
        return age('t.recorded_at') + ' AND ' + settled('t.player_id', 't.uuid')
    if table in ('fight_drop_items', 'fight_drop_claims'):
        if 'fight_drop_observations' not in live:
            return '0'
        return ('EXISTS (SELECT 1 FROM fight_drop_observations o WHERE o.id=t.report_id '
                'AND ' + age('o.recorded_at') + ' AND ' + settled('o.player_id', 'o.uuid') + ')')
    if table == 'economy_checkouts' and 'battle_entries' in live:
        return ('EXISTS (SELECT 1 FROM battle_entries e WHERE e.uuid=t.uuid '
                'AND e.player_id=t.player_id AND ' + age('e.created_at') + ') AND '
                + settled('t.player_id', 't.uuid'))
    return '0'


def export_parts(table, columns, live):
    eligible = condition(table, live)
    if table == 'fight_drop_observations':
        projection = ','.join(
            f"CASE WHEN {eligible} THEN '{{}}' ELSE t.{col} END AS {col}"
            if col in ('decoded', 'context') else f't.{col}' for col in columns)
        return projection, '1'
    return 't.*', f'NOT ({eligible})'


def prune_account(db, player, cutoff):
    """Inside import transaction: cleanup rolls back with the imported state."""
    live, changed = live_tables(db), {}
    for table in TABLES:
        if table not in live:
            continue
        if table in ('fight_drop_items', 'fight_drop_claims'):
            if 'fight_drop_observations' not in live:
                continue
            # Use the child primary key's report_id prefix; never scan every
            # other player's child records for a single-account import.
            parent = condition('fight_drop_observations', live)
            changed[table] = db.execute(
                f'DELETE FROM {table} WHERE report_id IN (SELECT t.id '
                'FROM fight_drop_observations t WHERE t.player_id=:player '
                f'AND ({parent}))', {'player': player, 'cutoff': cutoff}).rowcount
            continue
        own = 't.player_id=:player'
        sql = (f"UPDATE {table} AS t SET decoded='{{}}',context='{{}}' WHERE "
               if table == 'fight_drop_observations' else f'DELETE FROM {table} AS t WHERE ')
        extra = " AND (decoded IS NOT '{}' OR context IS NOT '{}')" if table == 'fight_drop_observations' else ''
        changed[table] = db.execute(sql + own + ' AND (' + condition(table, live) + ')' + extra,
                                   {'player': player, 'cutoff': cutoff}).rowcount
    return changed


def prune_plan(plan, cutoff):
    """After archive validation, trim copies before acquiring the write barrier.

    Avoid inserting megabytes of expired text only to UPDATE them immediately.
    The transaction-level SQL pruning remains the final authoritative check.
    """
    pid, rows = plan.source_player_id, plan.rows
    if 'economy_runs' not in rows:
        return {}  # A future/partial format must not turn unknown lifecycle into expiry.
    runs = {r['uuid']: r for r in rows.get('economy_runs', []) if r.get('player_id') == pid}
    entries = {r['uuid']: r for r in rows.get('battle_entries', []) if r.get('player_id') == pid}
    def old(stamp):
        return type(stamp) is int and 0 < stamp < cutoff
    def settled(key):
        return runs.get(key, {}).get('settled') == 1
    reports = {r['id'] for r in rows.get('fight_drop_observations', [])
               if r.get('player_id') == pid and old(r.get('recorded_at')) and settled(r.get('uuid'))}
    active = {r.get('section_id') for r in runs.values() if r.get('settled') == 0}
    changed = {}
    for table in TABLES:
        original = rows.get(table, [])
        if table == 'fight_drop_observations':
            count = 0
            for row in original:
                if row['id'] in reports:
                    count += int(row.get('decoded') != '{}' or row.get('context') != '{}')
                    row.update(decoded='{}', context='{}')
            changed[table] = count
            continue
        if table in ('fight_drop_items', 'fight_drop_claims'):
            keep = lambda r: r.get('report_id') not in reports
        elif table in ('battle_shop_purchases', 'battle_shop_pickups'):
            keep = lambda r: (not old(r.get('created_at')) or r.get('section_id') in active
                              or r.get('section_id') == 0 and bool(active))
        else:
            keep = lambda r: not (settled(r.get('uuid')) and old(entries.get(r.get('uuid'), {}).get('created_at')))
        rows[table] = [r for r in original if keep(r)]
        changed[table] = len(original) - len(rows[table])
    return changed


class DiagnosticRetention:
    def __init__(self, store, clock=time.time, batch_size=128):
        if not 1 <= batch_size <= 1024:
            raise ValueError('diagnostic batch size out of bounds')
        self.store, self.clock, self.batch_size = store, clock, batch_size
        self.position = {t: 0 for t in TABLES}

    def step(self, table):
        if table not in TABLES:
            raise ValueError('not an audited diagnostic table')
        with self.store.import_write(), closing(sqlite3.connect(
                self.store.path, timeout=.1, isolation_level=None)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA wal_autocheckpoint=0')
            db.execute('PRAGMA cache_size=-2048')
            live = live_tables(db)
            if table not in live:
                self.position[table] = 0
                return 0, True
            db.execute('BEGIN IMMEDIATE')
            try:
                # Keyset scan bounds examined rows even when no row is expired.
                rows = db.execute(f'SELECT rowid FROM {table} WHERE rowid>? ORDER BY rowid LIMIT ?',
                                  (self.position[table], min(2, self.batch_size) if table == 'fight_drop_observations' else self.batch_size)).fetchall()
                changed = 0
                if rows:
                    sql = (f"UPDATE {table} AS t SET decoded='{{}}',context='{{}}' WHERE "
                           if table == 'fight_drop_observations' else f'DELETE FROM {table} AS t WHERE ')
                    extra = " AND (decoded IS NOT '{}' OR context IS NOT '{}')" if table == 'fight_drop_observations' else ''
                    changed = db.execute(sql + 't.rowid>=:low AND t.rowid<=:high AND (' + condition(table, live) + ')' + extra,
                        {'low': rows[0][0], 'high': rows[-1][0],
                         'cutoff': int(self.clock()) - KEEP_SECONDS}).rowcount
                db.execute('COMMIT')
            except BaseException:
                db.execute('ROLLBACK')
                raise
            self.position[table] = rows[-1][0] if rows else 0
            return changed, len(rows) < (min(2, self.batch_size) if table == 'fight_drop_observations' else self.batch_size)

    async def _step_guarded(self, table):
        # Publish on the game loop BEFORE submitting the worker. Setting the
        # maintenance event is separate so completion cannot clear a new save
        # import writer's flag. Setting only the importing event in the worker
        # races a synchronous handler's read->write
        # transaction and can cause SQLITE_BUSY_SNAPSHOT even in WAL mode.
        self.store.maintenance.set()
        try:
            future = asyncio.get_running_loop().run_in_executor(None, self.step, table)
            try:
                return await asyncio.shield(future)
            except asyncio.CancelledError:
                while not future.done():
                    try:
                        await asyncio.shield(future)
                    except asyncio.CancelledError:
                        continue
                future.result()
                raise
        finally:
            self.store.maintenance.clear()

    async def watch(self, interval=900, pause=.05):
        while True:
            totals = {}
            for table in TABLES:
                self.position[table] = 0
                while True:
                    await self.store.wait_for_import()
                    if self.store.db.in_transaction:
                        await asyncio.sleep(pause)
                        continue
                    try:
                        changed, done = await self._step_guarded(table)
                    except sqlite3.OperationalError as exc:
                        from .transactions import is_database_busy
                        if not is_database_busy(exc):
                            LOGGER.exception('diagnostic retention schema/error table=%s', table)
                            break
                        LOGGER.warning('diagnostic retention deferred table=%s error=%s', table, type(exc).__name__)
                        await asyncio.sleep(1)
                        continue
                    totals[table] = totals.get(table, 0) + changed
                    if done:
                        break
                    await asyncio.sleep(pause)
            LOGGER.info('diagnostic retention complete keep_hours=48 rows=%s', totals)
            await asyncio.sleep(interval)
