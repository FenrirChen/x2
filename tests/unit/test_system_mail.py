"""Revival system mail is persistent, once per source, and claimed by RewardGrant."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import pytest

from tests.unit.test_battle import packet
from x2server.network.dispatcher import DispatchContext
from x2server.network.session import SessionState
from x2server.player.accounts import AccountStore, hash_password
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
    assert rows[0]["source_key"] == f"welcome_mail:{accounts.get_by_name('new')['account_id']}"
    assert not accounts.ensure_welcome_mail(player_id, day + 1)
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
    assert not accounts.ensure_welcome_mail(player_id, day + 2)
    assert store.db.execute("SELECT count(*) FROM player_mail WHERE player_id=?", (player_id,)).fetchone()[0] == 2
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


def test_legacy_first_login_welcome_is_once_even_after_claim(tmp_path):
    path = tmp_path / "player.db"
    store = PlayerStore(path)
    store.login("legacy", 1, 100)
    accounts = AccountStore(store)
    with accounts.db:
        accounts.db.execute("INSERT INTO accounts(username,password_hash,created_at,status,player_id) "
                            "VALUES (?,?,?,?,?)", ("legacy", hash_password("pw"), 100, "active", 1))
    assert store.db.execute("SELECT count(*) FROM player_mail WHERE player_id=1").fetchone()[0] == 0
    assert accounts.ensure_welcome_mail(1, 200)
    assert not accounts.ensure_welcome_mail(1, 201)
    row = store.db.execute("SELECT * FROM player_mail WHERE player_id=1").fetchone()
    assert row["source_key"].startswith("welcome_mail:")
    economy = EconomyService(store)
    mail = MailService(store, economy)
    ctx = DispatchContext("test", "local", SessionState("test", "session", player_id=1))
    assert asyncio.run(mail.handle(ctx, packet({"mailid": row["id"]},
        name="C2L_ReceiveAttachment"))).values["code"] == 10
    assert not accounts.ensure_welcome_mail(1, 202)
    assert store.db.execute("SELECT count(*) FROM player_mail WHERE player_id=1").fetchone()[0] == 1
    accounts.close()
    store.close()


def test_old_welcome_source_key_and_concurrent_ensure_do_not_duplicate(tmp_path):
    path = tmp_path / "player.db"
    store = PlayerStore(path)
    store.login("legacy", 1, 100)
    accounts = AccountStore(store)
    with accounts.db:
        accounts.db.execute("INSERT INTO accounts(username,password_hash,created_at,status,player_id) "
                            "VALUES (?,?,?,?,?)", ("legacy", hash_password("pw"), 100, "active", 1))
        account_id = accounts.db.execute("SELECT account_id FROM accounts WHERE username='legacy'").fetchone()[0]
        accounts.db.execute("INSERT INTO player_mail(player_id,sender,title,body,created_at,attachments,source_key) "
            "VALUES (1,'解神者 Revival','','',100,?,?)",
            ('{"1237902": 3600, "1237914": 80}', f"account_welcome:{account_id}"))
    assert not accounts.ensure_welcome_mail(1, 200)
    assert store.db.execute("SELECT count(*) FROM player_mail").fetchone()[0] == 1
    # A second account row emulates another concurrent server worker.
    other = AccountStore(store)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda account: account.ensure_welcome_mail(1, 1_800_000_000),
                                (accounts, other)))
    assert sorted(results) == [False, False]
    assert store.db.execute("SELECT count(*) FROM player_mail WHERE player_id=1").fetchone()[0] == 1
    # A player with no historical welcome receives exactly one under concurrent login.
    store.login("fresh", 2, 100)
    with accounts.db:
        accounts.db.execute("INSERT INTO accounts(username,password_hash,created_at,status,player_id) "
                            "VALUES (?,?,?,?,?)", ("fresh", hash_password("pw"), 100, "active", 2))
    with ThreadPoolExecutor(max_workers=2) as pool:
        fresh_results = list(pool.map(lambda account: account.ensure_welcome_mail(2, 1_800_000_000),
                                      (accounts, other)))
    assert sorted(fresh_results) == [False, True]
    assert store.db.execute("SELECT count(*) FROM player_mail WHERE player_id=2").fetchone()[0] == 1
    other.close()
    accounts.close()
    store.close()


def test_welcome_failure_rolls_back_registration(tmp_path):
    store = PlayerStore(tmp_path / "player.db")
    accounts = AccountStore(store)
    with accounts.db:
        accounts.db.execute("""CREATE TRIGGER fail_welcome BEFORE INSERT ON player_mail
            WHEN NEW.source_key LIKE 'welcome_mail:%'
            BEGIN SELECT RAISE(ABORT, 'mail failed'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        accounts.create("nova", "pw", 100)
    assert accounts.get_by_name("nova") is None
    assert store.db.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 0
    accounts.close()
    store.close()
