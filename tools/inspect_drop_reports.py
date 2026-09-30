"""Read-only 264 report diagnostics, independent of the running business server."""
import argparse
import json
import sqlite3
from pathlib import Path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    with sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute("SELECT id,player_id,uuid,recorded_at,context,decoded FROM fight_drop_observations ORDER BY id DESC LIMIT ?", (max(1, min(args.limit, 1000)),))
        print(json.dumps([dict(row) for row in rows], ensure_ascii=False, indent=2))
