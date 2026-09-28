"""SQLite player storage. Initial values are explicit local compatibility defaults."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

DEFAULT_SNAPSHOT: dict[str, Any] = {"nickname": "Revival", "level": 1,
    "gold": 0, "crystal": 0, "exp": 0, "show": 0}


class PlayerStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1, 2):
            self.db.close()
            raise ValueError("unsupported player database version")
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

    def save_snapshot(
        self, player_id: int, snapshot: dict[str, Any], expected_revision: int
    ) -> int:
        """Optimistic update; conflicting writes roll back instead of losing progress."""
        if not isinstance(snapshot.get("nickname"), str):
            raise ValueError("nickname must be a string")
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
        encoded = json.dumps(snapshot, ensure_ascii=False, allow_nan=False, sort_keys=True)
        with self.db:
            cursor = self.db.execute(
                "UPDATE players SET snapshot=?, revision=revision+1 WHERE id=? AND revision=?",
                (encoded, player_id, expected_revision))
            if cursor.rowcount != 1:
                raise ValueError("player revision conflict")
        return expected_revision + 1
