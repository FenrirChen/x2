"""Revival system mail is persistent, once per source, and claimed by RewardGrant."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import pytest

from tests.unit.test_battle import packet
from x2server.network.dispatcher import DispatchContext
from x2server.network.session import SessionState
from x2server.player.accounts import AccountStore
from x2server.player.economy import EconomyService
from x2server.player.mail import MailService
from x2server.player.store import PlayerStore
from x2server.player.system_mail import BRILLIANCE, WISH_COIN, CAUSALITY_CARD


def test_welcome_daily_claim_and_restart(tmp_path):
    path = tmp_path / "player.db"
    store = PlayerStore(path)
    accounts = AccountStore(store)
    economy = EconomyService(store)
    mail = MailService(store, economy)
    day = 1_800_000_000
    assert accounts.create("new", "pw", day) == "created"
    assert accounts.create("new", "pw", day) == "duplicate"
    player_id = accounts.get_by_name("new")["player_id"]
    rows = store.db.execute("SELECT * FROM player_mail WHERE player_id=?", (player_id,)).fetchall()
    assert len(rows) == 1 and rows[0]["body"] == "" and rows[0]["title"] == ""
    assert rows[0]["source_key"].startswith("account_welcome:")
    assert accounts.ensure_daily_login_mail(player_id, day)
    assert not accounts.ensure_daily_login_mail(player_id, day + 1800)
    rows = store.db.execute("SELECT * FROM player_mail WHERE player_id=? ORDER BY id", (player_id,)).fetchall()
    assert len(rows) == 2 and rows[1]["body"] == "祝您玩的开心"
    before = store.get(player_id)["snapshot"]
    ctx = DispatchContext("test", "local", SessionState("test", "session", player_id=player_id))
    for row in rows:
        response = asyncio.run(mail.handle(ctx, packet({"mailid": row["id"]}, name="C2L_ReceiveAttachment")))
        assert response.values["code"] == 10
        assert asyncio.run(mail.handle(ctx, packet({"mailid": row["id"]}, name="C2L_ReceiveAttachment"))).values["code"] == 13
    after = store.get(player_id)["snapshot"]
    assert after["crystal"] - before["crystal"] == 3800
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=? AND item_id=?",
                            (player_id, WISH_COIN)).fetchone()[0] == 90
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=? AND item_id=?",
                            (player_id, CAUSALITY_CARD)).fetchone()[0] == 10
    assert BRILLIANCE == 1237902
    accounts.close()
    store.close()
    reopened = PlayerStore(path)
    accounts = AccountStore(reopened)
    assert not accounts.ensure_daily_login_mail(player_id, day + 3600)
    assert accounts.ensure_daily_login_mail(player_id, day + 86400)
    assert reopened.db.execute("SELECT count(*) FROM player_mail WHERE player_id=?", (player_id,)).fetchone()[0] == 3
    accounts.close()
    reopened.close()


def test_concurrent_daily_and_legacy_account(tmp_path):
    path = tmp_path / "player.db"
    store = PlayerStore(path)
    old = store.login("legacy", 1, 100)
    accounts = AccountStore(store)
    assert accounts.create("legacy", "pw", 200, allow_legacy=True) == "created"
    assert store.db.execute("SELECT count(*) FROM player_mail").fetchone()[0] == 0
    player_id = old["id"]
    other = AccountStore(store)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda account: account.ensure_daily_login_mail(player_id, 1_800_000_000),
                                (accounts, other)))
    assert sorted(results) == [False, True]
    assert store.db.execute("SELECT count(*) FROM player_mail WHERE player_id=?", (player_id,)).fetchone()[0] == 1
    other.close()
    accounts.close()
    store.close()


def test_welcome_failure_rolls_back_registration(tmp_path):
    store = PlayerStore(tmp_path / "player.db")
    accounts = AccountStore(store)
    with accounts.db:
        accounts.db.execute("""CREATE TRIGGER fail_welcome BEFORE INSERT ON player_mail
            WHEN NEW.source_key LIKE 'account_welcome:%'
            BEGIN SELECT RAISE(ABORT, 'mail failed'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        accounts.create("nova", "pw", 100)
    assert accounts.get_by_name("nova") is None
    assert store.db.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 0
    accounts.close()
    store.close()
