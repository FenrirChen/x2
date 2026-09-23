"""Opt-in local account fixture; back up SQLite before bypassing the opening battle."""
import argparse
import sqlite3
from pathlib import Path

from x2server.player.store import PlayerStore


def prepare(database: Path, backup: Path, player_id: int = 1) -> None:
    if not database.is_file():
        raise ValueError("log in once to create the player database first")
    if backup.exists() or backup.resolve() == database.resolve():
        raise ValueError("backup must be a new, separate file")
    backup.parent.mkdir(parents=True, exist_ok=True)
    store = PlayerStore(database)
    try:
        player = store.get(player_id)
        with sqlite3.connect(backup) as destination:
            store.db.backup(destination)
        snapshot = dict(player["snapshot"])
        # MainHallFSM.NetSyncUpdate 0x13BBC00 checks BaseInfo.MainSection == 0.
        # Only bypass the opening battle; do not unlock every chapter or module.
        snapshot["main_chapter"] = max(snapshot.get("main_chapter", 0), 1)
        snapshot["main_section"] = max(snapshot.get("main_section", 0), 1)
        store.save_snapshot(player_id, snapshot, player["revision"])
    finally:
        store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--player-id", type=int, default=1)
    args = parser.parse_args()
    prepare(args.database, args.backup, args.player_id)
    print("Opening-battle bypass saved; previous database retained in backup.")
