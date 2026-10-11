"""User-defined event calendar and period-scoped persistence.

Old periods stay in the database for audit and retries. A fresh namespace, rather
than deleting rows, resets gameplay without touching the account or inventory.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from importlib.resources import files
import json
import os


@dataclass(frozen=True)
class ActivityPeriod:
    index: int
    start: int
    end: int
    theme: dict


class ActivityRotation:
    SECONDS = 5 * 86400
    ANCHOR = int(datetime(2026, 10, 10, tzinfo=timezone(timedelta(hours=8))).timestamp())

    def __init__(self, store, clock):
        self.store, self.clock = store, clock
        # Local acceptance can advance the event calendar without changing the
        # game clock, daily resets, or the production calendar default.
        self.anchor = int(os.environ.get('X2_ACTIVITY_ANCHOR', self.ANCHOR))
        self.catalog = json.loads(files('x2server').joinpath(
            'data/activity_rotation_catalog.json').read_text(encoding='utf-8'))
        self.themes = self.catalog['themes']
        # Preserve historical state IDs when a theme is retired from the calendar.
        self.state_cycle_size = self.catalog.get('state_cycle_size', len(self.themes))
        self.state_slots = {t.get('state_slot', i): i for i, t in enumerate(self.themes)}
        self.section_groups = {sid: t['group'] for t in self.themes for sid in t['section_ids']}
        if len(self.section_groups) != sum(len(t['section_ids']) for t in self.themes):
            raise ValueError('activity sections belong to multiple themes')
        self.section_groups.update({sid: -1 for sid in self.catalog.get('closed_section_ids', [])})
        with store.db:
            store.db.execute('''CREATE TABLE IF NOT EXISTS activity_state (
                player_id INTEGER NOT NULL, period INTEGER NOT NULL,
                namespace TEXT NOT NULL, state_key TEXT NOT NULL, value TEXT NOT NULL,
                PRIMARY KEY(player_id,period,namespace,state_key))''')
            store.db.execute('''CREATE TABLE IF NOT EXISTS activity_events (
                player_id INTEGER NOT NULL, period INTEGER NOT NULL, event_key TEXT NOT NULL,
                PRIMARY KEY(player_id,period,event_key))''')
            store.db.execute('''CREATE TABLE IF NOT EXISTS activity_runs (
                uuid TEXT PRIMARY KEY, player_id INTEGER NOT NULL, period INTEGER NOT NULL,
                section_id INTEGER NOT NULL, created_at INTEGER NOT NULL,
                settled INTEGER NOT NULL DEFAULT 0)''')
            store.db.execute('''CREATE TABLE IF NOT EXISTS activity_receipts (
                player_id INTEGER NOT NULL, request_key TEXT NOT NULL, period INTEGER NOT NULL,
                message TEXT NOT NULL, response BLOB NOT NULL,
                PRIMARY KEY(player_id,request_key))''')

    def at(self, now=None):
        now = int(self.clock() if now is None else now)
        if now < self.anchor:
            return None
        calendar_index = (now - self.anchor) // self.SECONDS
        cycle, slot = divmod(calendar_index, len(self.themes))
        theme = self.themes[slot]
        index = cycle * self.state_cycle_size + theme.get('state_slot', slot)
        start = self.anchor + calendar_index * self.SECONDS
        return ActivityPeriod(index, start, start + self.SECONDS, theme)

    def get(self, player, period, namespace, key, default=None):
        row = self.store.db.execute('''SELECT value FROM activity_state
            WHERE player_id=? AND period=? AND namespace=? AND state_key=?''',
            (player, period.index, namespace, str(key))).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, player, period, namespace, key, value):
        self.store.db.execute('''INSERT INTO activity_state VALUES (?,?,?,?,?)
            ON CONFLICT(player_id,period,namespace,state_key) DO UPDATE SET value=excluded.value''',
            (player, period.index, namespace, str(key), json.dumps(value, separators=(',', ':'))))

    def once(self, player, period, key):
        return bool(self.store.db.execute('INSERT OR IGNORE INTO activity_events VALUES (?,?,?)',
            (player, period.index, key)).rowcount)

    def activity(self, activity_id, period=None):
        period = period or self.at()
        return next((a for a in period.theme['activities'] if a['ActivityID'] == activity_id), None) if period else None

    def of_type(self, kind, period=None):
        period = period or self.at()
        return next((a for a in period.theme['activities'] if a['ActivityType']['value'] == kind), None) if period else None

    def bind_run(self, player, section, uuid):
        if section not in self.section_groups:
            return
        period = self.at()
        if period is None or self.section_groups[section] != period.theme['group']:
            raise ValueError('activity is closed')
        self.store.db.execute('INSERT INTO activity_runs VALUES (?,?,?,?,?,0)',
            (uuid, player, period.index, section, int(self.clock())))

    def run_period(self, player, uuid):
        row = self.store.db.execute('SELECT * FROM activity_runs WHERE uuid=? AND player_id=?',
                                    (uuid, player)).fetchone()
        if row is None:
            return None
        # A fight opened before the boundary can finish in its original period.
        if not 0 <= int(self.clock()) - row['created_at'] <= 3600:
            raise ValueError('expired activity run')
        cycle, state_slot = divmod(row['period'], self.state_cycle_size)
        if state_slot not in self.state_slots:
            raise ValueError('activity is closed')
        slot = self.state_slots[state_slot]
        start = self.anchor + (cycle * len(self.themes) + slot) * self.SECONDS
        return ActivityPeriod(row['period'], start, start + self.SECONDS, self.themes[slot])
