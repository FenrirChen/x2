import sqlite3

import pytest

from tools.prepare_hero_mobility_account import prepare
from x2server.player.store import PlayerStore


def test_preparation_backs_up_and_preserves_level(tmp_path):
    database = tmp_path / "player.db"
    backup = tmp_path / "backup" / "before.db"
    store = PlayerStore(database)
    player = store.login("revival", 1, 100)
    original = dict(player["snapshot"], level=60, main_chapter=1, main_section=1, gold=27)
    store.save_snapshot(1, original, player["revision"])
    store.close()

    prepare(database, backup)

    with sqlite3.connect(backup) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    before = PlayerStore(backup)
    after = PlayerStore(database)
    try:
        assert before.get(1)["snapshot"] == original
        saved = after.get(1)["snapshot"]
        assert saved["level"] == 60 and saved["gold"] == 27
        assert (saved["main_chapter"], saved["main_section"]) == (2010000, 2110001)
        assert saved["heroes"][0]["id"] == 1003 and saved["mobility"]["power"] == 149
        with pytest.raises(FileExistsError):
            prepare(database, backup)
    finally:
        before.close()
        after.close()
