"""Top up the explicitly named test save's official favor gifts to a target."""
import argparse
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE = ROOT / "runtime/phase14/player.sqlite3"
DEFAULT_REPORT = ROOT / "analysis/external_merge/favor_test_gifts_seed.json"


def seed(database, player_id=1, target=100):
    if target < 1 or target > 999999:
        raise ValueError("invalid target")
    catalog = json.loads((ROOT / "src/x2server/data/favor_catalog.json").read_text(encoding="utf-8"))
    language = json.loads((ROOT.parent / "analysis/drop_archaeology/full_tables/language.json").read_text(encoding="utf-8"))
    names = {row["Key"]: row["Chinese"] for row in language["records"] if row.get("Chinese")}
    gift_rows = catalog["gifts"]
    if len(gift_rows) != 59:
        raise ValueError("official favor gift set changed")
    db = sqlite3.connect(database, timeout=10)
    try:
        db.execute("BEGIN IMMEDIATE")
        player = db.execute("SELECT account FROM players WHERE id=?", (player_id,)).fetchone()
        if player is None or player[0] != "revival":
            raise ValueError("target is not the named Revival test account")
        report = []
        for row in gift_rows:
            item_id = row["ItemID"]
            old = db.execute("SELECT quantity FROM inventory WHERE player_id=? AND item_id=?",
                             (player_id, item_id)).fetchone()
            old_count = old[0] if old else 0
            new_count = max(old_count, target)
            if new_count != old_count:
                db.execute("""INSERT INTO inventory(player_id,item_id,quantity) VALUES (?,?,?)
                    ON CONFLICT(player_id,item_id) DO UPDATE SET quantity=excluded.quantity""",
                    (player_id, item_id, new_count))
            report.append({"item_id": item_id, "name": names.get(row["NameID"], str(row["NameID"])),
                           "old_count": old_count, "new_count": new_count})
        db.commit()
        return {"database": str(database), "player_id": player_id, "target": target,
                "source": "official Item.FunctionEff=E_AddFavorability, ItemUseScence=E_Outside",
                "items": report}
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--player-id", type=int, default=1)
    parser.add_argument("--target", type=int, default=100)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    result = seed(args.database, args.player_id, args.target)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"seeded {len(result['items'])} official favor gift types; target={args.target}")
