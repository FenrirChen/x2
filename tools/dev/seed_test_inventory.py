"""Safely ensure progression resources and test equipment on an existing account."""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "runtime/phase14/player.sqlite3"
CURRENCY_FIELDS = {1237901: "gold", 1237902: "crystal", 1237906: "equip_exp", 1237907: "hero_exp"}


def read_json(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def selected_ids(preset: str) -> set[int]:
    ids = set()
    if preset in ("currencies", "hero", "artifact", "equipment", "progression"):
        ids.add(1237901)
    if preset in ("currencies", "progression"):
        ids.update((1237902, 1237907))
    if preset in ("equipment", "progression"):
        # Item 1237906 has E_Currency / EffData 906 = EquibExp (兽魂).
        ids.add(1237906)
    if preset in ("hero", "progression"):
        ids.update((1237907, 1201000, 1201003))
        for row in read_json("analysis/progression/skill_progression.json")["rows"]:
            if row["skill_id"] in (10030, 10031, 10032, 10033, 10035):
                ids.update(m["material_item_id"] for m in row["materials"])
    if preset in ("artifact", "progression"):
        for row in read_json("analysis/progression/weapon_progression.json")["rows"]:
            if row["profession"] == 303:
                ids.update(m["material_item_id"] for key in ("level_up_materials", "fuse_materials")
                           for m in row[key])
    if preset == "progression":
        ids.update(r["material_item_id"] for r in read_json("analysis/progression/material_links.json")["rows"]
                   if r["item_type"] not in ("E_Equip", "E_Currency"))
    return ids


def backup_database(source: sqlite3.Connection, database: Path) -> Path:
    folder = database.parent.parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for suffix in range(1000):
        candidate = folder / f"before-test-inventory-{stamp}{f'-{suffix}' if suffix else ''}.sqlite3"
        if not candidate.exists():
            with sqlite3.connect(candidate) as target:
                source.backup(target)
            return candidate
    raise RuntimeError("could not allocate a unique backup name")


def seed(args: argparse.Namespace) -> None:
    database = args.database.resolve()
    if not database.is_file():
        raise SystemExit(f"active database does not exist: {database}")
    ids = selected_ids(args.preset)
    material_rows = {r["material_item_id"]: r for r in read_json("analysis/progression/material_links.json")["rows"]}
    item_rows = {r["ItemID"]: r for r in read_json("src/x2server/data/economy_catalog.json")["items"]}
    with sqlite3.connect(database, timeout=30) as db:
        db.row_factory = sqlite3.Row
        selector = "id=?" if args.player.isdecimal() else "account=?"
        row = db.execute(f"SELECT id,account,snapshot,revision FROM players WHERE {selector}",
                         (int(args.player) if args.player.isdecimal() else args.player,)).fetchone()
        if row is None:
            raise SystemExit(f"player not found: {args.player}")
        player_id = row["id"]
        snapshot = json.loads(row["snapshot"])
        equipment_catalog = read_json("analysis/progression/equipment_seed_catalog.json")["rows"] if args.preset in ("equipment", "progression") else []
        has_equipment_table = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='equipment_instances'").fetchone() is not None
        existing_types = ({r[0] for r in db.execute("SELECT type_id FROM equipment_instances WHERE player_id=? AND marker='TEST_COMPAT_INSTANCE'", (player_id,))}
                          if has_equipment_table else set())
        equipment_to_create = [r for r in equipment_catalog if r["type_id"] not in existing_types]
        currency_changes = []
        item_changes = []
        for item_id in sorted(ids):
            if item_id in CURRENCY_FIELDS:
                field = CURRENCY_FIELDS[item_id]
                old = int(snapshot.get(field, 0))
                target = (args.radiance_amount if item_id == 1237902 else
                          args.hero_exp_amount if item_id == 1237907 else
                          args.equipment_exp_amount if item_id == 1237906 else args.currency_amount)
                new = max(old, target) if args.mode == "ensure" else old + target
                if new > 2_000_000_000:
                    raise SystemExit(f"currency {item_id} exceeds safe int32 range")
                if new != old:
                    snapshot[field] = new
                    currency_changes.append((item_id, old, new))
                continue
            meta = material_rows.get(item_id)
            if not meta or meta["item_type"] in ("E_Equip", "E_Currency"):
                raise SystemExit(f"item {item_id} is not a confirmed stackable progression material")
            old_row = db.execute("SELECT quantity FROM inventory WHERE player_id=? AND item_id=?", (player_id, item_id)).fetchone()
            old = old_row[0] if old_row else 0
            target = args.fragment_amount if meta["item_type"] == "E_Chip" else args.material_amount
            pile = item_rows.get(item_id, {}).get("PileCount")
            if pile and pile > 0:
                target = min(target, pile)
            new = max(old, target) if args.mode == "ensure" else old + target
            if new > 2_000_000_000:
                raise SystemExit(f"item {item_id} exceeds safe int32 range")
            if new != old:
                item_changes.append((item_id, old, new))
        backup = None
        if not args.dry_run and (currency_changes or item_changes or equipment_to_create):
            backup = backup_database(db, database)
            db.execute("BEGIN IMMEDIATE")
            try:
                if currency_changes:
                    result = db.execute("UPDATE players SET snapshot=?,revision=revision+1 WHERE id=? AND revision=?",
                        (json.dumps(snapshot, ensure_ascii=False, sort_keys=True), player_id, row["revision"]))
                    if result.rowcount != 1:
                        raise RuntimeError("player revision changed; no inventory changes committed")
                for item_id, _, new in item_changes:
                    db.execute("INSERT INTO inventory(player_id,item_id,quantity) VALUES (?,?,?) "
                               "ON CONFLICT(player_id,item_id) DO UPDATE SET quantity=excluded.quantity",
                               (player_id, item_id, new))
                if equipment_to_create:
                    db.execute("""CREATE TABLE IF NOT EXISTS equipment_instances (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, player_id INTEGER NOT NULL,
                        type_id INTEGER NOT NULL, level INTEGER NOT NULL DEFAULT 0,
                        exp INTEGER NOT NULL DEFAULT 0, star INTEGER NOT NULL,
                        param TEXT NOT NULL, marker TEXT NOT NULL,
                        UNIQUE(player_id,type_id,marker))""")
                    for equip in equipment_to_create:
                        db.execute("INSERT INTO equipment_instances(player_id,type_id,level,exp,star,param,marker) VALUES (?,?,0,0,?,?,?)",
                                   (player_id, equip["type_id"], equip["star"],
                                    json.dumps(equip["param"], sort_keys=True), equip["marker"]))
                db.commit()
            except BaseException:
                db.rollback()
                raise
        print(f"Player: {player_id} ({row['account']})")
        print(f"Preset: {args.preset}; mode: {args.mode}; dry-run: {args.dry_run}")
        for item_id, old, new in currency_changes:
            print(f"Currency {item_id}: {old} -> {new}")
        print(f"Stackable materials: {len(item_changes)} changed / {len(ids - CURRENCY_FIELDS.keys())} selected")
        print(f"Equipment instances: {len(existing_types)} existing; {len(equipment_to_create)} {'planned' if args.dry_run else 'created'}")
        print(f"Backup: {backup if backup else 'none (no changes)'}")
        if item_changes:
            print("Material changes:", ", ".join(f"{i}:{old}->{new}" for i, old, new in item_changes))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--player", default="1", help="existing player id or account")
    parser.add_argument("--preset", choices=("currencies", "hero", "artifact", "equipment", "progression"), default="progression")
    parser.add_argument("--mode", choices=("ensure", "add"), default="ensure")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--currency-amount", type=int, default=10_000_000)
    parser.add_argument("--radiance-amount", type=int, default=100_000)
    parser.add_argument("--hero-exp-amount", type=int, default=10_000_000)
    parser.add_argument("--equipment-exp-amount", type=int, default=10_000_000)
    parser.add_argument("--material-amount", type=int, default=999)
    parser.add_argument("--fragment-amount", type=int, default=999)
    args = parser.parse_args()
    if min(args.currency_amount, args.radiance_amount, args.hero_exp_amount, args.equipment_exp_amount,
           args.material_amount, args.fragment_amount) < 0:
        parser.error("amounts must be nonnegative")
    seed(args)


if __name__ == "__main__":
    main()
