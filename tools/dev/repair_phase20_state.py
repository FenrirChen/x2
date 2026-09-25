"""One-time, guarded repair of the Phase 20 test player's earlier compat writes."""
import json
import secrets
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATABASE = ROOT / "runtime/phase14/player.sqlite3"
BACKUPS = ROOT / "runtime/backups"
KEY = "phase20-artifact-progress-slots-enhancement-v1"


def main():
    db = sqlite3.connect(DATABASE)
    try:
        db.execute("PRAGMA busy_timeout=5000")
        db.execute("""CREATE TABLE IF NOT EXISTS repair_history (
            repair_key TEXT PRIMARY KEY, applied_at TEXT NOT NULL, backup_path TEXT NOT NULL)""")
        if db.execute("SELECT 1 FROM repair_history WHERE repair_key=?", (KEY,)).fetchone():
            print("already applied; no changes")
            return
        raw, revision = db.execute("SELECT snapshot,revision FROM players WHERE id=1 AND account='revival'").fetchone()
        snapshot = json.loads(raw)
        artifact = next(h for h in snapshot["heroes"] if h["id"] == 1003)["god_equip"]
        if artifact != {"compat": "REVIVAL_COMPAT", "id": 1503, "level": 0, "star": 5}:
            raise RuntimeError(f"unexpected artifact state; no repair: {artifact}")
        worn = [e for h in snapshot["heroes"] for e in h.get("equips", [])]
        if not worn or any(not 1 <= e["position"] <= 6 for e in worn):
            raise RuntimeError("unexpected equipment positions; no repair")
        rows = db.execute("SELECT id,star,level,param FROM equipment_instances WHERE player_id=1 AND level>=3").fetchall()
        if any(level != 3 for _, _, level, _ in rows):
            raise RuntimeError("equipment beyond expected level; no repair")

        BACKUPS.mkdir(parents=True, exist_ok=True)
        backup = BACKUPS / f"before-phase20-state-repair-{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(3)}.sqlite3"
        with sqlite3.connect(backup) as target:
            db.backup(target)

        weapon = json.loads((ROOT / "analysis/progression/weapon_progression.json").read_text(encoding="utf-8"))
        ranks = {r["rank"]: r for r in weapon["rows"] if r["profession"] == 303}
        delta = Counter()
        for rank in range(1, 5):
            row = ranks[rank]
            delta[1237901] += row["level_up_gold_cost"]
            for material in row["level_up_materials"]:
                delta[material["material_item_id"]] += material["material_num"]
        for _ in range(4):
            delta[1237901] -= ranks[1]["level_up_gold_cost"]
            for material in ranks[1]["level_up_materials"]:
                delta[material["material_item_id"]] -= material["material_num"]
        increments = json.loads((ROOT / "analysis/progression/equipment_strengthen_catalog.json").read_text(encoding="utf-8"))
        ranges = {(r["quality"], r["attribute"]): r["value_range"] for r in increments["rows"]}

        with db:
            for hero in snapshot["heroes"]:
                for equip in hero.get("equips", []):
                    equip["position"] -= 1
            artifact.update(star=1, level=40)
            snapshot["gold"] += delta.pop(1237901)
            for item_id, amount in delta.items():
                result = db.execute("UPDATE inventory SET quantity=quantity+? WHERE player_id=1 AND item_id=? AND quantity+?>=0",
                                    (amount, item_id, amount))
                if result.rowcount != 1:
                    raise RuntimeError(f"missing inventory for correction {item_id}")
            changed = db.execute("UPDATE players SET snapshot=?,revision=revision+1 WHERE id=1 AND revision=?",
                                 (json.dumps(snapshot, ensure_ascii=False), revision))
            if changed.rowcount != 1:
                raise RuntimeError("player revision changed during repair")
            db.execute("""CREATE TABLE IF NOT EXISTS equipment_enhancements (
                player_id INTEGER NOT NULL, equip_id INTEGER NOT NULL,
                level INTEGER NOT NULL, attribute_slot INTEGER NOT NULL, bonus INTEGER NOT NULL,
                PRIMARY KEY(player_id,equip_id,level))""")
            for equip_id, quality, _, raw_param in rows:
                if db.execute("SELECT 1 FROM equipment_enhancements WHERE player_id=1 AND equip_id=? AND level=3", (equip_id,)).fetchone():
                    continue
                param = json.loads(raw_param)
                candidates = [slot for slot in range(2, 7) if (quality, param.get(f"at{slot}")) in ranges]
                slot = secrets.choice(candidates)
                bounds = ranges[(quality, param[f"at{slot}"])]
                bonus = secrets.randbelow(bounds[-1] - bounds[0] + 1) + bounds[0]
                param[f"av{slot}"] += bonus
                db.execute("UPDATE equipment_instances SET param=? WHERE player_id=1 AND id=?",
                           (json.dumps(param, sort_keys=True), equip_id))
                db.execute("INSERT INTO equipment_enhancements VALUES (?,?,?,?,?)", (1, equip_id, 3, slot, bonus))
            db.execute("INSERT INTO repair_history VALUES (?,?,?)", (KEY, datetime.now().isoformat(), str(backup)))
        print(json.dumps({"backup": str(backup), "revision": revision + 1,
                          "artifact": artifact, "worn_positions_corrected": len(worn),
                          "level3_attributes_corrected": len(rows)}, ensure_ascii=False))
    finally:
        db.close()


if __name__ == "__main__":
    main()
