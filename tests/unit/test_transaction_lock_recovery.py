"""Real SQLite contention: failed commits must not poison game/login connections."""
import sqlite3

import pytest

from x2server.player.accounts import AccountStore
from x2server.player.college import CollegeStateRepository
from x2server.player.economy import EconomyService
from x2server.player.equip_plans import EquipPlanService
from x2server.player.friend_currency import ITEM_ID, LIMIT, repair
from x2server.player.store import PlayerStore
from x2server.player.transactions import transaction

SERVICES = (EconomyService, CollegeStateRepository, EquipPlanService)


@pytest.fixture
def env(tmp_path):
    store = PlayerStore(tmp_path / "contention.sqlite3")
    store.db.execute("PRAGMA journal_mode=DELETE")
    store.login("lock-test", 1, 0)
    accounts = AccountStore(store)
    with store.db:
        store.db.execute("CREATE TABLE inventory (player_id INTEGER, item_id INTEGER, quantity INTEGER)")
        store.db.execute("INSERT INTO inventory VALUES (1,?,?)", (ITEM_ID, LIMIT + 50))
    # Production mode is unchanged; shorten only the intentional test conflict.
    assert store.db.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    store.db.execute("PRAGMA busy_timeout=30")
    accounts.db.execute("PRAGMA busy_timeout=30")
    reader = sqlite3.connect(store.path, timeout=.03)
    yield store, accounts, reader
    reader.close()
    accounts.close()
    store.close()


def service_for(cls, store):
    service = object.__new__(cls)
    service.store = store
    return service


def quantity(db):
    return db.execute("SELECT quantity FROM inventory WHERE player_id=1").fetchone()[0]


@pytest.mark.parametrize("cls", (*SERVICES, None), ids=("economy", "college", "equip-plan", "friend-cap"))
def test_commit_busy_rolls_back_and_keeps_login_readable(env, cls, caplog):
    store, accounts, reader = env
    reader.execute("BEGIN DEFERRED")
    reader.execute("SELECT * FROM inventory").fetchall()
    # Same-process second connection, like a concurrent save export.
    with pytest.raises(sqlite3.OperationalError, match="locked"):
        if cls is None:
            repair(store, 1)
        else:
            with service_for(cls, store).transaction():
                store.db.execute("UPDATE inventory SET quantity=1 WHERE player_id=1")
    assert not store.db.in_transaction
    assert quantity(store.db) == LIMIT + 50
    # This SELECT also failed indefinitely with the old implementation.
    assert accounts.verify("missing-account", "unused", 0) is None
    assert "stage=commit" in caplog.text and "SQLITE_BUSY" in caplog.text
    reader.rollback()
    if cls is None:
        assert repair(store, 1) == 1
        expected = LIMIT
    else:
        with service_for(cls, store).transaction():
            store.db.execute("UPDATE inventory SET quantity=2 WHERE player_id=1")
        expected = 2
    assert not store.db.in_transaction
    assert quantity(accounts.db) == expected


@pytest.mark.parametrize("cls", SERVICES)
def test_inner_service_never_commits_or_discards_outer_work(env, cls):
    store, accounts, reader = env
    service = service_for(cls, store)
    with pytest.raises(ValueError, match="outer failed"):
        with transaction(store.db):
            store.db.execute("UPDATE players SET login_count=7 WHERE id=1")
            with service.transaction():
                store.db.execute("UPDATE inventory SET quantity=3 WHERE player_id=1")
            assert quantity(accounts.db) == LIMIT + 50
            raise ValueError("outer failed")
    assert not store.db.in_transaction
    assert quantity(accounts.db) == LIMIT + 50
    with transaction(store.db):
        store.db.execute("UPDATE players SET login_count=8 WHERE id=1")
        with pytest.raises(ValueError, match="inner failed"):
            with service.transaction():
                store.db.execute("UPDATE inventory SET quantity=4 WHERE player_id=1")
                raise ValueError("inner failed")
        assert store.db.in_transaction
        assert quantity(store.db) == LIMIT + 50
    assert accounts.db.execute("SELECT login_count FROM players WHERE id=1").fetchone()[0] == 8


def test_nested_friend_repair_is_not_early_committed(env):
    store, accounts, reader = env
    with pytest.raises(ValueError):
        with transaction(store.db):
            assert repair(store, 1) == 1
            assert quantity(store.db) == LIMIT
            assert quantity(accounts.db) == LIMIT + 50
            raise ValueError("cancel grant")
    assert quantity(accounts.db) == LIMIT + 50
    assert not store.db.in_transaction


@pytest.mark.parametrize("nested", (False, True))
def test_sqlite_automatic_rollback_preserves_original_exception(env, nested):
    store, accounts, reader = env
    store.db.execute("CREATE TABLE unique_values (value INTEGER UNIQUE)")
    with store.db:
        store.db.execute("INSERT INTO unique_values VALUES (1)")
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        with transaction(store.db):
            if nested:
                with transaction(store.db):
                    store.db.execute("INSERT OR ROLLBACK INTO unique_values VALUES (1)")
            else:
                store.db.execute("INSERT OR ROLLBACK INTO unique_values VALUES (1)")
    assert not store.db.in_transaction
    assert accounts.verify("missing-account", "unused", 0) is None


def test_deferred_constraint_failure_at_commit_does_not_leak_transaction(env):
    store, accounts, reader = env
    store.db.execute("PRAGMA foreign_keys=ON")
    store.db.execute("CREATE TABLE deferred_child (owner INTEGER REFERENCES players(id) DEFERRABLE INITIALLY DEFERRED)")
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        with transaction(store.db):
            store.db.execute("INSERT INTO deferred_child VALUES (999)")
    assert not store.db.in_transaction
    assert store.db.execute("SELECT * FROM deferred_child").fetchall() == []
    with transaction(store.db):
        store.db.execute("INSERT INTO deferred_child VALUES (1)")
    assert accounts.db.execute("SELECT owner FROM deferred_child").fetchone()[0] == 1
