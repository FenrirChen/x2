"""Revival compatibility account layer: hashing, creation and player binding."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from x2server.player.accounts import AccountStore, hash_password, verify_password
from x2server.player.store import PlayerStore


def make_store(tmp_path):
    store = PlayerStore(tmp_path / "player.db")
    return store, AccountStore(store)


def test_password_hash_roundtrip_and_format():
    stored = hash_password("s3cret")
    assert stored.startswith("pbkdf2_sha256$100000$") and stored.count("$") == 3
    assert verify_password("s3cret", stored)
    assert not verify_password("wrong", stored)
    assert not verify_password("s3cret", "garbage")


def test_create_duplicate_and_verify(tmp_path):
    store, accounts = make_store(tmp_path)
    assert accounts.create("nova", "pw1", 100) == "created"
    assert accounts.create("nova", "pw2", 101) == "duplicate"
    assert accounts.verify("nova", "pw1", 102)["account_id"] == 1
    assert accounts.verify("nova", "pw2", 103) is None
    assert accounts.verify("ghost", "pw1", 104) is None
    row = accounts.get_by_name("nova")
    assert row["last_login_at"] == 102 and row["status"] == "active"
    assert accounts.get_by_id(999) is None


def test_create_rejects_blank_and_oversized(tmp_path):
    store, accounts = make_store(tmp_path)
    with pytest.raises(ValueError):
        accounts.create("", "pw", 1)
    with pytest.raises(ValueError):
        accounts.create("user", "", 1)
    with pytest.raises(ValueError):
        accounts.create("u" * 65, "pw", 1)
    with pytest.raises(ValueError):
        accounts.create("bad\nname", "pw", 1)


def test_registration_binds_player_before_return(tmp_path):
    store, accounts = make_store(tmp_path)
    accounts.create("nova", "pw", 1)
    account = accounts.get_by_name("nova")
    assert account["player_id"] == store.get(1)["id"]
    assert accounts.get_by_player(1)["username"] == "nova"


def test_version1_database_migrates_without_touching_players(tmp_path):
    path = tmp_path / "legacy.db"
    db = sqlite3.connect(path)
    with db:
        db.execute("CREATE TABLE players (id INTEGER PRIMARY KEY, account TEXT NOT NULL UNIQUE,"
                   " created_at INTEGER NOT NULL, login_count INTEGER NOT NULL DEFAULT 0,"
                   " snapshot TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1)")
        db.execute("INSERT INTO players VALUES (1, 'revival', 5, 3, '{\"level\": 60}', 9)")
        db.execute("PRAGMA user_version=1")
    db.close()

    store = PlayerStore(path)
    accounts = AccountStore(store)
    player = store.get(1)
    assert player["snapshot"] == {"level": 60} and player["revision"] == 9
    assert accounts.get_by_name("revival") is None  # no fabricated credentials
    assert accounts.create("revival", "pw", 50, allow_legacy=True) == "created"
    assert accounts.get_by_name("revival")["player_id"] == 1
    assert store.get(1)["snapshot"] == {"level": 60}
    assert store.db.execute("PRAGMA user_version").fetchone()[0] == 2


def test_registration_allocates_fresh_ids(tmp_path):
    store, accounts = make_store(tmp_path)
    accounts.create("revival", "pw", 1)
    accounts.create("nova", "pw", 3)
    assert accounts.get_by_name("revival")["player_id"] == 1
    assert accounts.get_by_name("nova")["player_id"] == 2
    assert store.get(2)["snapshot"]["nickname"] == "Revival"
    assert store.get(1)["login_count"] == 0


def test_registration_rolls_back_player_on_account_failure(tmp_path):
    store, accounts = make_store(tmp_path)
    accounts.db.execute("CREATE TRIGGER fail_account BEFORE INSERT ON accounts "
                        "BEGIN SELECT RAISE(ABORT, 'injected account failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        accounts.create("nova", "pw", 1)
    assert store.db.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 0
    assert store.db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0
    accounts.db.execute("DROP TRIGGER fail_account")
    accounts.db.execute("CREATE TRIGGER fail_player BEFORE INSERT ON players "
                        "BEGIN SELECT RAISE(ABORT, 'injected bootstrap failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        accounts.create("nova", "pw", 1)
    assert store.db.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 0
    assert store.db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0


def test_concurrent_duplicate_registration_has_one_player(tmp_path):
    store, accounts = make_store(tmp_path)
    rival = AccountStore(store)  # independent SQLite connection, as in another worker
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda n: (accounts if n % 2 else rival).create("nova", "pw", 1), range(8)))
    assert results.count("created") == 1
    assert results.count("duplicate") == 7
    assert store.db.execute("SELECT COUNT(*) FROM players WHERE account='nova'").fetchone()[0] == 1
    assert store.db.execute("SELECT COUNT(*) FROM accounts WHERE username='nova'").fetchone()[0] == 1
    rival.close()
