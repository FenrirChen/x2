"""Preview or repair one explicitly selected early-Revival tutorial account.

Never scans for candidates or changes another player. Default is read-only.
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from x2server.player.new_player import new_player_snapshot


def repair(path: Path, player_id: int, account: str, *, apply: bool = False) -> str:
    mode = "rw" if apply else "ro"
    db = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode={mode}", uri=True)
    try:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT p.*, a.username FROM players p JOIN accounts a "
                         "ON a.player_id=p.id AND a.username=p.account "
                         "WHERE p.id=? AND p.account=?", (player_id, account)).fetchone()
        if row is None:
            raise ValueError("selected player/account pair is not registered")
        old = json.loads(row["snapshot"])
        if (old.get("nickname") != "Revival" or old.get("heroes") != [] or
            old.get("bootstrap_version") is not None or old.get("guide_groups") or
            old.get("guide_steps") or old.get("main_chapter") or old.get("main_section") or
            old.get("level") != 1 or old.get("exp") != 0):
            raise ValueError("player is not an untouched early-registration tutorial snapshot")
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='economy_clears'").fetchone():
            if db.execute("SELECT 1 FROM economy_clears WHERE player_id=? LIMIT 1", (player_id,)).fetchone():
                raise ValueError("player has section clear progress")
        tutorial = new_player_snapshot(skip_tutorial=False)
        fresh = dict(old, nickname="", heroes=tutorial["heroes"], show=1003,
                     bootstrap_version=1, tutorial_mode="tutorial")
        if apply:
            with db:
                updated = db.execute("UPDATE players SET snapshot=?, revision=revision+1 "
                    "WHERE id=? AND revision=?", (json.dumps(fresh, ensure_ascii=False),
                    player_id, row["revision"]))
                if updated.rowcount != 1:
                    raise ValueError("concurrent player update")
        return "applied" if apply else "eligible: dry run, no database changes"
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--player-id", type=int, required=True)
    parser.add_argument("--account", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(repair(args.database, args.player_id, args.account, apply=args.apply))
