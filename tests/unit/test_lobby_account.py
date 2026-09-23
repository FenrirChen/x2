import pytest

from tools.prepare_lobby_account import prepare
from x2server.player.store import PlayerStore
from x2server.player.login import LoginService
from x2server.messages.core import BASE_INFO


def test_account_bypass_is_opt_in_backed_up_and_preserves_progress(tmp_path):
    database, backup = tmp_path / "player.db", tmp_path / "before.db"
    store = PlayerStore(database)
    player = store.login("lab", 1, 100)
    store.save_snapshot(1, dict(player["snapshot"], gold=37), player["revision"])
    original = store.get(1)
    store.close()
    prepare(database, backup)
    store = PlayerStore(database)
    saved = store.get(1)
    store.close()
    assert saved["snapshot"]["main_section"] == 1
    assert saved["snapshot"]["gold"] == 37
    assert saved["login_count"] == original["login_count"]
    assert saved["revision"] == original["revision"] + 1
    base = BASE_INFO.decode(LoginService.snapshot_push(saved).values["BaseInfo"])
    assert base["MainChapter"] == 1 and base["MainSection"] == 1
    with pytest.raises(ValueError, match="new, separate"):
        prepare(database, backup)
    recovered = PlayerStore(backup)
    assert recovered.get(1) == original
    recovered.close()


def test_account_bypass_does_not_reset_later_progress(tmp_path):
    database = tmp_path / "player.db"
    store = PlayerStore(database)
    player = store.login("lab", 1, 100)
    store.save_snapshot(1, dict(player["snapshot"], main_chapter=4, main_section=8), 1)
    store.close()
    prepare(database, tmp_path / "before.db")
    store = PlayerStore(database)
    assert store.get(1)["snapshot"]["main_section"] == 8
    assert store.get(1)["snapshot"]["main_chapter"] == 4
    store.close()
