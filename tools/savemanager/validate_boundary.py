"""Cross-check save_manager.BOUNDARY against the live database schema.

Fails loudly if a persisted table with player ownership is missing from the
boundary, a boundary table is missing from the DB, or a join definition is
stale. This keeps SAVE_DATA_AUDIT.md, save_boundary.json and the
implementation provably in sync.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from x2server.player.save_manager import (  # noqa: E402
    GLOBAL_TABLES, JOIN_OWNERS, PLAYER_TABLES, TABLES_WITH_OWNER_COLUMN,
)


def main(db_path: str) -> int:
    db = sqlite3.connect(db_path)
    live_tables = {r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    errors = []
    for table in PLAYER_TABLES:
        if table not in live_tables:
            errors.append(f"boundary table missing from DB: {table}")
    owned = {table for table in live_tables
             if "player_id" in [c[1] for c in db.execute(f"PRAGMA table_info({table})")]}
    # accounts/players are identity tables (players owns the snapshot column),
    # every other player_id-bearing table must be a direct-owner boundary table.
    for table in sorted(owned - set(TABLES_WITH_OWNER_COLUMN)):
        if table in JOIN_OWNERS or table in GLOBAL_TABLES:
            continue
        errors.append(f"DB table with player_id missing from boundary: {table}")
    for table, (parent, parent_col, child_col) in JOIN_OWNERS.items():
        for other, column in ((table, child_col), (parent, parent_col)):
            if column not in [c[1] for c in db.execute(f"PRAGMA table_info({other})")]:
                errors.append(f"join column missing: {other}.{column}")
        if "player_id" in [c[1] for c in db.execute(f"PRAGMA table_info({table})")]:
            errors.append(f"join-owned table unexpectedly has player_id: {table}")
    # no boundary table may own a player_id-bearing column set we missed
    player_tables_in_db = {r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )} - GLOBAL_TABLES
    unaccounted = player_tables_in_db - set(PLAYER_TABLES)
    if unaccounted:
        errors.append(f"tables not covered by boundary: {sorted(unaccounted)}")
    if errors:
        print("BOUNDARY VALIDATION FAILED:")
        for error in errors:
            print(" -", error)
        return 1
    print(f"boundary OK: {len(PLAYER_TABLES)} player tables "
          f"({len(TABLES_WITH_OWNER_COLUMN)} direct owner, {len(JOIN_OWNERS)} join-owned) "
          f"== live schema {db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "runtime/phase14/player.sqlite3"))
