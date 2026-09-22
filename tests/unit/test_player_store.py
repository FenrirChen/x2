import sqlite3
import pytest
from x2server.player.store import PlayerStore


def test_restart_and_login_preserve_saved_snapshot(tmp_path):
    path = tmp_path / "player.db"
    store = PlayerStore(path)
    first = store.login("lab", 1, 100)
    changed = dict(first["snapshot"], nickname="Saved", gold=37)
    assert store.save_snapshot(1, changed, first["revision"]) == 2
    store.close()
    store = PlayerStore(path)
    try:
        restored = store.login("lab", 1, 200)
        assert restored["snapshot"] == changed
        assert restored["created_at"] == 100
        assert restored["login_count"] == 2
        assert restored["revision"] == 2
        with pytest.raises(ValueError, match="revision"):
            store.save_snapshot(1, dict(changed, gold=99), 1)
        with pytest.raises(ValueError, match="identity"):
            store.login("other", 1, 300)
        assert store.get(1) == restored
    finally:
        store.close()


def test_future_database_version_is_not_overwritten(tmp_path):
    path = tmp_path / "future.db"
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=99")
    with pytest.raises(ValueError, match="version"):
        PlayerStore(path)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 99
