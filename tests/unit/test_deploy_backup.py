import sqlite3
from contextlib import closing

import pytest

from tools.deploy_backup import backup_database


def make_db(path):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('CREATE TABLE archive(id INTEGER PRIMARY KEY, value BLOB)')
        db.executemany('INSERT INTO archive(value) VALUES (?)', [(bytes(range(256)) * 64,)] * 20)
    return path


def test_verified_copy_keeps_all_rows_and_reports_stages(tmp_path):
    source = make_db(tmp_path / 'player.sqlite3')
    original = source.read_bytes()
    messages = []
    target = tmp_path / 'predeploy.bak'
    assert backup_database(source, target, log=messages.append) == target
    assert source.read_bytes() == original
    with closing(sqlite3.connect(source)) as a, closing(sqlite3.connect(target)) as b:
        assert a.execute('SELECT * FROM archive').fetchall() == b.execute('SELECT * FROM archive').fetchall()
        assert b.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert not target.with_name(target.name + '.partial').exists()
    assert any('BACKUP_COPY_DONE' in m for m in messages)
    assert any('BACKUP_CHECK_OK' in m for m in messages)
    assert any(m == f'DB_BACKUP={target}' for m in messages)


def test_wal_backup_contains_committed_data_not_uncommitted_changes(tmp_path):
    source = make_db(tmp_path / 'player.sqlite3')
    target = tmp_path / 'predeploy.bak'
    with closing(sqlite3.connect(source)) as writer:
        writer.execute('PRAGMA journal_mode=WAL')
        with writer:
            writer.execute("INSERT INTO archive(value) VALUES ('committed')")
        writer.execute("INSERT INTO archive(value) VALUES ('not-committed')")
        backup_database(source, target)
        with closing(sqlite3.connect(target)) as copied:
            assert copied.execute("SELECT COUNT(*) FROM archive WHERE value='committed'").fetchone()[0] == 1
            assert copied.execute("SELECT COUNT(*) FROM archive WHERE value='not-committed'").fetchone()[0] == 0
        writer.rollback()


@pytest.mark.parametrize('collision', ['final', 'partial'])
def test_existing_backups_are_never_replaced(tmp_path, collision):
    source = make_db(tmp_path / 'player.sqlite3')
    target = tmp_path / 'predeploy.bak'
    protected = target if collision == 'final' else target.with_name(target.name + '.partial')
    protected.write_bytes(b'previous recovery file')
    with pytest.raises(FileExistsError):
        backup_database(source, target)
    assert protected.read_bytes() == b'previous recovery file'


def test_invalid_source_never_publishes_success_or_changes_old_backup(tmp_path):
    source = tmp_path / 'damaged.sqlite3'
    source.write_bytes(b'invalid database' * 100)
    old = tmp_path / 'old.bak'
    old.write_bytes(b'keep old backup')
    target = tmp_path / 'new.bak'
    messages = []
    with pytest.raises(sqlite3.DatabaseError):
        backup_database(source, target, log=messages.append)
    assert not target.exists()
    assert not target.with_name(target.name + '.partial').exists()
    assert not any(m.startswith('DB_BACKUP=') for m in messages)
    assert old.read_bytes() == b'keep old backup'
    assert source.read_bytes() == b'invalid database' * 100


def test_exclusive_writer_cannot_make_backup_wait_forever(tmp_path):
    source = make_db(tmp_path / 'player.sqlite3')
    target = tmp_path / 'blocked.bak'
    with closing(sqlite3.connect(source)) as writer:
        writer.execute('BEGIN EXCLUSIVE')
        with pytest.raises(TimeoutError):
            backup_database(source, target, timeout=.05, interval=.01)
        assert not target.exists()
        writer.rollback()
    backup_database(source, target)


def test_same_file_and_missing_source_are_rejected(tmp_path):
    source = make_db(tmp_path / 'player.sqlite3')
    original = source.read_bytes()
    with pytest.raises(ValueError):
        backup_database(source, source)
    with pytest.raises(FileNotFoundError):
        backup_database(tmp_path / 'missing', tmp_path / 'new.bak')
    assert source.read_bytes() == original


def test_integrity_failure_after_copy_never_publishes_backup(tmp_path):
    source = make_db(tmp_path / 'player.sqlite3')
    with closing(sqlite3.connect(source)) as db, db:
        db.execute('CREATE TABLE constrained(amount INTEGER CHECK(amount>=0))')
        db.execute('PRAGMA ignore_check_constraints=ON')
        db.execute('INSERT INTO constrained VALUES (-1)')
    original = source.read_bytes()
    target = tmp_path / 'invalid.bak'
    messages = []
    with pytest.raises(sqlite3.DatabaseError):
        backup_database(source, target, log=messages.append)
    assert any('BACKUP_COPY_DONE' in m for m in messages)
    assert not any(m.startswith('DB_BACKUP=') for m in messages)
    assert not target.exists()
    assert not target.with_name(target.name + '.partial').exists()
    assert source.read_bytes() == original
