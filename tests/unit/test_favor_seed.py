"""The test-save top-up is repeatable and never mints beyond the target."""
from tools.dev.seed_favor_test_gifts import seed
from x2server.player.store import PlayerStore


def test_seed_official_favor_gifts_is_idempotent(tmp_path):
    path = tmp_path / "test.sqlite3"
    store = PlayerStore(path)
    store.login("revival", 1, 0)
    with store.db:
        store.db.execute("CREATE TABLE inventory (player_id INTEGER, item_id INTEGER, quantity INTEGER, PRIMARY KEY(player_id,item_id))")
        store.db.execute("INSERT INTO inventory VALUES (1,1204000,37)")
        store.db.execute("INSERT INTO inventory VALUES (1,1204001,150)")
    first = seed(path)
    second = seed(path)
    assert len(first["items"]) == 59
    assert next(r for r in first["items"] if r["item_id"] == 1204000)["new_count"] == 100
    assert next(r for r in first["items"] if r["item_id"] == 1204001)["new_count"] == 150
    assert all(r["old_count"] == r["new_count"] for r in second["items"])
    store.close()
