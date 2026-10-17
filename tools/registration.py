"""Live persistent registration switch; invoke with the service's exact DB path."""
import argparse
import sqlite3
from pathlib import Path
from contextlib import closing
from x2server.player.db_guard import CheckpointGuard


def configure(database, action):
    path = Path(database).resolve(strict=True)
    if action == 'status':
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=1)) as db:
            db.execute('SELECT account_id FROM accounts LIMIT 0')
            if not db.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name='server_settings'").fetchone():
                return True
            row = db.execute("SELECT value FROM server_settings WHERE key='registration_enabled'").fetchone()
            return row is None or row[0] == '1'
    with closing(CheckpointGuard(path)) as guard, guard, closing(sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=30)) as db, db:
        db.execute('PRAGMA wal_autocheckpoint=0')
        db.execute('BEGIN IMMEDIATE')
        # Refuse unrelated databases; do not silently create an empty database.
        db.execute('SELECT account_id FROM accounts LIMIT 0')
        db.execute('CREATE TABLE IF NOT EXISTS server_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        if action != 'status':
            if action not in ('open', 'close'):
                raise ValueError('invalid registration action')
            db.execute("INSERT INTO server_settings VALUES ('registration_enabled',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       ('1' if action == 'open' else '0',))
        row = db.execute("SELECT value FROM server_settings WHERE key='registration_enabled'").fetchone()
        enabled = row is None or row[0] == '1'
    return enabled


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('open', 'close', 'status'))
    parser.add_argument('--database', required=True)
    args = parser.parse_args()
    enabled = configure(args.database, args.action)
    print('registration=' + ('open' if enabled else 'closed'))


if __name__ == '__main__':
    main()
