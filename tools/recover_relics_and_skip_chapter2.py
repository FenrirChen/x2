"""One-time repair for confirmed checkout relics and player 1's test save."""

import argparse
import json
import sqlite3
from pathlib import Path

from x2server.messages.battle import BATTLE_SCHEMAS, CHECKOUT, OUTSIDE_ITEM


CHAPTER_ID = 2010200
LAST_SECTION = 2110106
TEST_PLAYER_ID = 1


def repair(db):
    catalog = json.loads(Path(__file__).resolve().parents[1].joinpath(
        "src/x2server/data/economy_catalog.json").read_text(encoding="utf-8"))
    chapter_sections = [row["SectionID"] for row in catalog["sections"]
                        if row["ChapterID"] == CHAPTER_ID]
    if chapter_sections != list(range(2110101, LAST_SECTION + 1)):
        raise RuntimeError(f"chapter 2 route changed: {chapter_sections}")
    reward_items = json.loads(Path(__file__).resolve().parents[1].joinpath(
        "src/x2server/data/reward_items.json").read_text(encoding="utf-8"))
    relic_ids = {row["ItemID"] for row in reward_items
                 if row.get("ItemType", {}).get("value") == 4}
    recovered = set()
    with db:
        for player_id, raw_checkout, raw_response in db.execute("""SELECT e.player_id,w.checkout,r.response
            FROM battle_checkout_wire w JOIN battle_entries e ON e.uuid=w.uuid
            JOIN battle_receipts r ON r.uuid=w.uuid"""):
            receipt = BATTLE_SCHEMAS["L2C_CheckoutMainMission"].decode(raw_response)
            if receipt.get("result") != 10 or not receipt.get("success"):
                continue
            checkout = CHECKOUT.decode(raw_checkout)
            for raw_item in checkout.get("mazeItems", []):
                item = OUTSIDE_ITEM.decode(raw_item)
                if item.get("id") in relic_ids and item.get("num", 0) > 0:
                    recovered.add((player_id, item["id"]))
        for player_id, item_id in sorted(recovered):
            db.execute("""INSERT OR IGNORE INTO inventory(player_id,item_id,quantity)
                VALUES (?,?,1)""", (player_id, item_id))

        row = db.execute("SELECT snapshot,revision FROM players WHERE id=?",
                         (TEST_PLAYER_ID,)).fetchone()
        if row is None:
            raise RuntimeError("test save player 1 missing")
        snapshot = json.loads(row[0])
        if snapshot.get("main_chapter") != CHAPTER_ID or snapshot.get("main_section") not in chapter_sections:
            raise RuntimeError("test save is no longer in chapter 2")
        for section_id in chapter_sections:
            db.execute("""INSERT OR IGNORE INTO economy_clears(player_id,section_id,first_uuid)
                VALUES (?,?,?)""", (TEST_PLAYER_ID, section_id, f"test-skip-chapter2:{section_id}"))
        db.execute("""CREATE TABLE IF NOT EXISTS chapter_dp_floors (
            player_id INTEGER NOT NULL, chapter_id INTEGER NOT NULL,
            minimum_dp INTEGER NOT NULL CHECK(minimum_dp>=0), reason TEXT NOT NULL,
            PRIMARY KEY(player_id,chapter_id))""")
        db.execute("""INSERT INTO chapter_dp_floors VALUES (?,?,?,?)
            ON CONFLICT(player_id,chapter_id) DO UPDATE SET
            minimum_dp=max(minimum_dp,excluded.minimum_dp)""",
            (TEST_PLAYER_ID, CHAPTER_ID, 10, "test-save chapter 2 skip"))
        snapshot["main_section"] = LAST_SECTION
        changed = db.execute("""UPDATE players SET snapshot=?,revision=revision+1
            WHERE id=? AND revision=?""", (json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
            TEST_PLAYER_ID, row[1]))
        if changed.rowcount != 1:
            raise RuntimeError("test save changed during repair")
    return sorted(recovered), chapter_sections


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    connection = sqlite3.connect(args.database)
    try:
        relics, chapters = repair(connection)
        print(f"Recovered relic collections: {relics}")
        print(f"Test player 1 chapter 2 cleared: {chapters}")
    finally:
        connection.close()
