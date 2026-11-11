import sqlite3

from tools.diag.activity_shop_buy_probe import snapshot_database


def test_probe_snapshot_includes_uncheckpointed_wal(tmp_path):
    source, target = tmp_path / 'live.db', tmp_path / 'copy.db'
    with sqlite3.connect(source) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA wal_autocheckpoint=0')
        db.execute('CREATE TABLE sample (value INTEGER)')
        db.execute('INSERT INTO sample VALUES (42)')
        db.commit()
        snapshot_database(source, target)
        with sqlite3.connect(target) as copy:
            assert copy.execute('SELECT value FROM sample').fetchall() == [(42,)]
        assert db.execute('SELECT value FROM sample').fetchall() == [(42,)]
