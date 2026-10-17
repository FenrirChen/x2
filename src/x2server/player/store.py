"""SQLite player storage. Initial values are explicit local compatibility defaults."""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import threading
import time
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

from .db_guard import CheckpointGuard
from .transactions import is_database_busy

DEFAULT_SNAPSHOT: dict[str, Any] = {"nickname": "Revival", "level": 1,
    "gold": 0, "crystal": 0, "exp": 0, "show": 0}


def validate_snapshot(snapshot: dict[str, Any]) -> None:
    """Shared shape rules for players.snapshot; used on write and save import."""
    if not isinstance(snapshot.get("nickname"), str):
        raise ValueError("nickname must be a string")
    if 'nick_count' in snapshot and (type(snapshot['nick_count']) is not int
            or not 0 <= snapshot['nick_count'] <= 2**31 - 1):
        raise ValueError('nick_count must be a nonnegative int32')
    if type(snapshot.get("level")) is not int or snapshot["level"] < 1:
        raise ValueError("level must be positive")
    for name in ("gold", "crystal", "exp", "show", "main_chapter", "main_section"):
        if name in snapshot and (type(snapshot[name]) is not int or snapshot[name] < 0):
            raise ValueError(f"{name} must be a nonnegative integer")
    if "mobility" in snapshot:
        mobility = snapshot["mobility"]
        if not isinstance(mobility, dict) or type(mobility.get("power")) is not int or mobility["power"] < 0:
            raise ValueError("mobility power must be a nonnegative integer")
        for name in ("shop_power_fetch_time", "section_power_fetch_time", "dbp_next_refresh_time"):
            if name in mobility and (type(mobility[name]) is not int or mobility[name] < 0):
                raise ValueError(f"mobility {name} must be a nonnegative integer")
    if "heroes" in snapshot:
        heroes = snapshot["heroes"]
        if not isinstance(heroes, list):
            raise ValueError("heroes must be a list")
        ids = set()
        for hero in heroes:
            if not isinstance(hero, dict) or any(type(hero.get(name)) is not int or hero[name] < minimum
                    for name, minimum in (("id", 1), ("state", 0), ("level", 1), ("star", 0))):
                raise ValueError("hero identity, state, level and star must be nonnegative integers")
            if hero["id"] in ids:
                raise ValueError("duplicate hero id")
            ids.add(hero["id"])


class PlayerStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.importing = threading.Event()
        self.checkpoint_guard = CheckpointGuard(path)
        self.db = sqlite3.connect(path, timeout=.05)
        self.db.row_factory = sqlite3.Row
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1, 2):
            self.db.close()
            self.checkpoint_guard.close()
            raise ValueError("unsupported player database version")
        mode = self.db.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        if mode != 'wal':
            self.db.close()
            self.checkpoint_guard.close()
            raise RuntimeError('player database requires local-filesystem WAL support')
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA wal_autocheckpoint=0")
        with self.db:
            self.db.execute("""CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY, account TEXT NOT NULL UNIQUE,
                created_at INTEGER NOT NULL, login_count INTEGER NOT NULL DEFAULT 0,
                snapshot TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1)""")
            # Version 2 adds the Revival compatibility account layer; existing
            # player rows and their snapshots are untouched by this migration.
            self.db.execute("""CREATE TABLE IF NOT EXISTS accounts (
                account_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
                created_at INTEGER NOT NULL, last_login_at INTEGER,
                status TEXT NOT NULL DEFAULT 'active', player_id INTEGER)""")
            if version < 2:
                self.db.execute("PRAGMA user_version=2")

    async def wait_for_import(self):
        # Never synchronously wait for the HTTP import writer on the game loop.
        while self.importing.is_set():
            await asyncio.sleep(.01)

    @contextmanager
    def import_write(self):
        self.importing.set()
        try:
            with self.checkpoint_guard:
                yield
        finally:
            self.importing.clear()

    async def checkpoint_watch(self, interval=5):
        # Single checkpoint owner. Disable auto-checkpoint on every app writer;
        # in particular never race a checkpoint against an HTTP writer/reset.
        while True:
            await asyncio.sleep(interval)
            if self.importing.is_set() or not self.checkpoint_guard.acquire(blocking=False):
                continue
            try:
                if not self.db.in_transaction:
                    started = time.monotonic()
                    try:
                        result = self.db.execute('PRAGMA wal_checkpoint(PASSIVE)').fetchone()
                        if time.monotonic() - started > .5:
                            logging.getLogger('x2.database').warning('checkpoint slow elapsed=%.3fs result=%s', time.monotonic() - started, tuple(result))
                    except sqlite3.OperationalError as exc:
                        if not is_database_busy(exc):
                            logging.getLogger('x2.database').exception('checkpoint failed')
            finally:
                self.checkpoint_guard.release()

    def login(self, account: str, player_id: int, now: int) -> dict[str, Any]:
        """Create once and increment atomically; never replace an existing snapshot."""
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO players VALUES (?, ?, ?, 0, ?, 1)",
                            (player_id, account, now, json.dumps(DEFAULT_SNAPSHOT)))
            row = self.db.execute("SELECT * FROM players WHERE id=?", (player_id,)).fetchone()
            if row is None or row["account"] != account:
                raise ValueError("player/account identity conflict")
            self.db.execute("UPDATE players SET login_count=login_count+1 WHERE id=?", (player_id,))
            return self.get(player_id)

    def get(self, player_id: int) -> dict[str, Any]:
        row = self.db.execute("SELECT * FROM players WHERE id=?", (player_id,)).fetchone()
        if row is None:
            raise KeyError(player_id)
        result = dict(row)
        result["snapshot"] = json.loads(result["snapshot"])
        return result

    def close(self) -> None:
        self.db.close()
        self.checkpoint_guard.close()

    def backup_to(self, destination: Path) -> None:
        """Consistent SQLite online backup; never overwrite a file or commit callers."""
        destination = Path(destination)
        if destination.resolve() == self.path.resolve() or destination.exists():
            raise ValueError("backup destination must be a new file")
        if self.db.in_transaction:
            raise ValueError("backup must run between player transactions")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(destination)) as target:
            self.db.backup(target, pages=256)

    def save_snapshot(
        self, player_id: int, snapshot: dict[str, Any], expected_revision: int
    ) -> int:
        """Optimistic update; conflicting writes roll back instead of losing progress."""
        validate_snapshot(snapshot)
        encoded = json.dumps(snapshot, ensure_ascii=False, allow_nan=False, sort_keys=True)
        with self.db:
            cursor = self.db.execute(
                "UPDATE players SET snapshot=?, revision=revision+1 WHERE id=? AND revision=?",
                (encoded, player_id, expected_revision))
            if cursor.rowcount != 1:
                raise ValueError("player revision conflict")
        return expected_revision + 1
