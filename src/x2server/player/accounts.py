"""Revival compatibility account layer (REVIVAL_COMPATIBILITY).

Persists accounts that the original publisher's account service used to own:
`/register` creates one, `/loginwithpw` verifies it, and each account is bound
to exactly one player row in PlayerStore. Passwords are stored as salted
PBKDF2 hashes, never in plaintext.
"""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
import json
import threading
from typing import Any

from .store import PlayerStore
from .new_player import new_player_snapshot
from .mail import ensure_mail_schema
from .system_mail import insert_system_mail

PBKDF2_ITERATIONS = 100_000
MAX_USERNAME = 64
MAX_PASSWORD = 128


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        parts = stored.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        if not 1 <= iterations <= 1_000_000:
            return False
        salt, expected = bytes.fromhex(parts[2]), bytes.fromhex(parts[3])
        if len(salt) != 16 or len(expected) != 32:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return secrets.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False


class AccountStore:
    """Thread-safe HTTP store; registration commits account and player together."""

    def __init__(self, store: PlayerStore) -> None:
        # ThreadingHTTPServer invokes this store from worker threads. PlayerStore's
        # event-loop connection must never be shared with them.
        self.db = sqlite3.connect(store.path, check_same_thread=False, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self._lock = threading.RLock()
        with self.db:
            self.db.execute("CREATE UNIQUE INDEX IF NOT EXISTS accounts_player_id_unique "
                            "ON accounts(player_id)")
            ensure_mail_schema(self.db)

    def create(self, username: str, password: str, now: int, *, allow_legacy: bool = False) -> str:
        """Create both rows atomically; only the configured seed can claim a legacy player."""
        if not username or not username.strip() or not password:
            raise ValueError("username and password must be nonempty")
        if len(username) > MAX_USERNAME or len(password) > MAX_PASSWORD:
            raise ValueError("username or password too long")
        if any(not ch.isprintable() for ch in username):
            raise ValueError("username contains control characters")
        password_hash = hash_password(password)
        with self._lock:
            try:
                self.db.execute("BEGIN IMMEDIATE")
                if self.db.execute("SELECT 1 FROM accounts WHERE username=?", (username,)).fetchone():
                    self.db.rollback()
                    return "duplicate"
                existing = self.db.execute("SELECT id FROM players WHERE account=?", (username,)).fetchone()
                if existing and not allow_legacy:
                    self.db.rollback()
                    return "duplicate"
                if existing:
                    player_id = existing["id"]
                else:
                    cursor = self.db.execute(
                        "INSERT INTO players(account,created_at,login_count,snapshot,revision) "
                        "VALUES (?,?,0,?,1)",
                        (username, now, json.dumps(new_player_snapshot(), ensure_ascii=False)))
                    player_id = cursor.lastrowid
                cursor = self.db.execute(
                    "INSERT INTO accounts(username,password_hash,created_at,status,player_id) "
                    "VALUES (?,?,?,'active',?)", (username, password_hash, now, player_id))
                if not existing:
                    if not insert_system_mail(self.db, player_id, cursor.lastrowid, "welcome", now):
                        raise sqlite3.IntegrityError("welcome mail was not inserted")
                self.db.commit()
            except sqlite3.IntegrityError as exc:
                self.db.rollback()
                if exc.sqlite_errorcode in (sqlite3.SQLITE_CONSTRAINT_UNIQUE,
                                            sqlite3.SQLITE_CONSTRAINT_PRIMARYKEY):
                    return "duplicate"
                raise
            except BaseException:
                self.db.rollback()
                raise
        return "created"

    def ensure_daily_login_mail(self, player_id: int, now: int) -> bool:
        with self._lock:
            try:
                self.db.execute("BEGIN IMMEDIATE")
                row = self.db.execute("SELECT account_id FROM accounts WHERE player_id=? AND status='active'",
                                      (player_id,)).fetchone()
                if row is None:
                    raise ValueError("player has no active account")
                created = insert_system_mail(self.db, player_id, row["account_id"], "daily_login", now)
                self.db.commit()
                return created
            except BaseException:
                self.db.rollback()
                raise

    def verify(self, username: str, password: str, now: int) -> dict[str, Any] | None:
        with self._lock:
            row = self.db.execute("SELECT * FROM accounts WHERE username=?", (username,)).fetchone()
            if row is None or row["status"] != "active" or row["player_id"] is None or not verify_password(password, row["password_hash"]):
                return None
            with self.db:
                self.db.execute("UPDATE accounts SET last_login_at=? WHERE account_id=?",
                                (now, row["account_id"]))
            return dict(row)

    def get_by_id(self, account_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self.db.execute("SELECT * FROM accounts WHERE account_id=?", (account_id,)).fetchone()
            return dict(row) if row is not None else None

    def get_by_name(self, username: str) -> dict[str, Any] | None:
        with self._lock:
            row = self.db.execute("SELECT * FROM accounts WHERE username=?", (username,)).fetchone()
            return dict(row) if row is not None else None

    def get_by_player(self, player_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self.db.execute("SELECT a.* FROM accounts a JOIN players p "
                                  "ON p.id=a.player_id AND p.account=a.username "
                                  "WHERE a.player_id=?", (player_id,)).fetchone()
            return dict(row) if row is not None else None

    def close(self) -> None:
        with self._lock:
            self.db.close()
