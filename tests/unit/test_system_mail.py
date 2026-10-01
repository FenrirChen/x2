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
from x2server.player.system_mail import BRILLIANCE, WISH_COIN, CAUSALITY_CARD, PURE_CRYSTAL
from x2server.player.system_mail import HERO_CHOICE_BOX, deliver_hero_choice


def test_choice_mail_registration_backfill_claim_delete_and_restart(tmp_path):
    import json
    path = tmp_path / 'choice.db'
    store = PlayerStore(path)
    accounts = AccountStore(store)
    store.login('legacy', 1, 100)
    assert deliver_hero_choice(store, 200) == (1, [])
    assert accounts.create('new', 'pw', 201) == 'created'
    new_id = accounts.get_by_name('new')['player_id']
    assert not accounts.ensure_hero_choice_mail(new_id, 202)
    assert deliver_hero_choice(store, 203) == (0, [])
    economy = EconomyService(store)
    mail = MailService(store, economy)
    for player_id in (1, new_id):
        row = store.db.execute("SELECT * FROM player_mail WHERE player_id=? AND source_key LIKE 'hero_choice_%'",
                               (player_id,)).fetchone()
        assert json.loads(row['attachments']) == {str(HERO_CHOICE_BOX): 1}
        ctx = DispatchContext('test', 'local', SessionState('test', 'session', player_id=player_id))
        req = packet({'mailid': row['id']}, name='C2L_ReceiveAttachment')
        assert asyncio.run(mail.handle(ctx, req)).values['code'] == 10
        assert asyncio.run(mail.handle(ctx, req)).values['code'] == 13
        assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=? AND item_id=?',
                                (player_id, HERO_CHOICE_BOX)).fetchone()[0] == 1
        with store.db:
            store.db.execute('UPDATE player_mail SET deleted=1 WHERE id=?', (row['id'],))
    assert deliver_hero_choice(store, 204) == (0, [])
    accounts.close()
    store.close()
    reopened = PlayerStore(path)
    assert deliver_hero_choice(reopened, 300) == (0, [])
    assert reopened.db.execute("SELECT count(*) FROM player_mail WHERE source_key LIKE 'hero_choice_%'").fetchone()[0] == 2
    reopened.close()


def test_choice_mail_concurrent_ensure_and_atomic_registration_failure(tmp_path):
    store = PlayerStore(tmp_path / 'choice.db')
    accounts = AccountStore(store)
    assert accounts.create('new', 'pw', 100) == 'created'
    player_id = accounts.get_by_name('new')['player_id']
    # Emulate an older account predating this reward policy.
    with accounts.db:
        accounts.db.execute("DELETE FROM player_mail WHERE source_key LIKE 'hero_choice_%'")
    other = AccountStore(store)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda a: a.ensure_hero_choice_mail(player_id, 200), (accounts, other)))
    assert sorted(results) == [False, True]
    with accounts.db:
        accounts.db.execute("""CREATE TRIGGER fail_choice BEFORE INSERT ON player_mail
            WHEN NEW.source_key LIKE 'hero_choice_%'
            BEGIN SELECT RAISE(ABORT, 'choice mail failed'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        accounts.create('failed', 'pw', 300)
    assert accounts.get_by_name('failed') is None
    assert not store.db.execute("SELECT 1 FROM players WHERE account='failed'").fetchone()
    other.close()
    accounts.close()
    store.close()


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
    assert len(rows) == 2 and rows[0]["body"] == "" and rows[0]["title"] == ""
    assert rows[0]["source_key"] == f"welcome_mail:{accounts.get_by_name('new')['account_id']}"
    assert not accounts.ensure_welcome_mail(player_id, day + 1)
    assert accounts.ensure_daily_login_mail(player_id, day)
    assert not accounts.ensure_daily_login_mail(player_id, day + 1800)
    rows = store.db.execute("SELECT * FROM player_mail WHERE player_id=? ORDER BY id", (player_id,)).fetchall()
    assert len(rows) == 3 and rows[2]["body"] == "祝您玩的开心"
    before = store.get(player_id)["snapshot"]
    ctx = DispatchContext("test", "local", SessionState("test", "session", player_id=player_id))
    for row in rows:
        response = asyncio.run(mail.handle(ctx, packet({"mailid": row["id"]}, name="C2L_ReceiveAttachment")))
        assert response.values["code"] == 10
        assert asyncio.run(mail.handle(ctx, packet({"mailid": row["id"]}, name="C2L_ReceiveAttachment"))).values["code"] == 13
    assert not accounts.ensure_welcome_mail(player_id, day + 2)
    assert store.db.execute("SELECT count(*) FROM player_mail WHERE player_id=?", (player_id,)).fetchone()[0] == 3
    after = store.get(player_id)["snapshot"]
    assert after["crystal"] - before["crystal"] == 3800
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=? AND item_id=?",
                            (player_id, WISH_COIN)).fetchone()[0] == 90
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=? AND item_id=?",
                            (player_id, CAUSALITY_CARD)).fetchone()[0] == 10
    assert BRILLIANCE == 1237902
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=? AND item_id=?',
                            (player_id, PURE_CRYSTAL)).fetchone()[0] == 10
    accounts.close()
    store.close()
    reopened = PlayerStore(path)
    accounts = AccountStore(reopened)
    assert not accounts.ensure_daily_login_mail(player_id, day + 3600)
    assert accounts.ensure_daily_login_mail(player_id, day + 86400)
    assert reopened.db.execute("SELECT count(*) FROM player_mail WHERE player_id=?", (player_id,)).fetchone()[0] == 4
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
