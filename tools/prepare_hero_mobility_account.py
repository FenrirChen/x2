"""Upgrade only the existing 60-level local test snapshot, with a fresh backup."""

import argparse
import sqlite3
from pathlib import Path

from x2server.player.store import PlayerStore


def prepare(database: Path, backup: Path) -> None:
    if not database.is_file():
        raise FileNotFoundError(database)
    if backup.exists():
        raise FileExistsError(backup)
    store = PlayerStore(database)
    try:
        player = store.get(1)
        current = player["snapshot"]
        if player["account"] != "revival" or current.get("level") != 60:
            raise ValueError("expected the existing 60-level revival account")
        if (current.get("main_chapter"), current.get("main_section")) != (1, 1):
            raise ValueError("expected the Phase 15 placeholder chapter and section")
        if "heroes" in current or "mobility" in current:
            raise ValueError("Hero or Mobility data already exists")
        backup.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(backup) as target:
            store.db.backup(target)
        updated = dict(current,
            main_chapter=2010000, main_section=2110001,
            heroes=[{"id": 1003, "state": 2, "level": 1, "star": 1}],
            mobility={"power": 149, "shop_power_fetch_time": 0,
                      "section_power_fetch_time": 0, "dbp_next_refresh_time": 0})
        store.save_snapshot(1, updated, player["revision"])
    finally:
        store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    arguments = parser.parse_args()
    prepare(arguments.database, arguments.backup)
