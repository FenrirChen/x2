"""Bounded runtime indexes from the checked-in progression audit."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def export():
    data = {}
    for key in ("player_level", "hero_level", "hero_star", "skill_progression", "weapon_progression"):
        source = json.loads((ROOT / f"analysis/progression/{key}.json").read_text(encoding="utf-8"))
        rows = source["rows"]
        if key == "skill_progression":
            rows = [r for r in rows if r["skill_id"] in (10030, 10031, 10032, 10033, 10035)]
        data[key] = rows
    data["provenance"] = "CONFIRMED_CLIENT_STATIC costs; Revival transactional rules are documented separately"
    data["hero_unlock"] = json.loads((ROOT / "analysis/progression/hero_unlock_catalog.json").read_text(encoding="utf-8"))["rows"]
    base = ROOT / "analysis/progression/battle_base_1003.json"
    data["battle_base_1003"] = json.loads(base.read_text(encoding="utf-8"))
    path = ROOT / "src/x2server/data/progression_catalog.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({k: len(v) for k, v in data.items() if isinstance(v, list)})


if __name__ == "__main__":
    export()
