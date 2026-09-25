"""Export fragment synthesis costs and initial hero IDs from indexed client tables."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis/progression"))
from probe import read_tables  # noqa: E402


def main():
    tables, sources, missing = read_tables(["PlayerAttrib", "SkillBase"])
    if missing:
        raise RuntimeError(missing)
    skills = {r["ID"] for r in tables["SkillBase"]}
    rows = []
    for row in tables["PlayerAttrib"]:
        hero_id = row["ID"]
        if not (1000 <= hero_id < 2000 and row.get("IsOpen") == 1
                and row.get("ChipPropID") and row.get("WeapenId") and row.get("ExchangeChip")):
            continue
        rows.append({"hero_id": hero_id, "level": row.get("Level", 1),
            "star": row["DefaultStage"], "fragment_item_id": row["ChipPropID"],
            "fragment_count": row["ExchangeChip"], "artifact_id": row["WeapenId"],
            "profession": row["Profession"],
            "initial_skills": [i for suffix in (0, 1, 2, 3, 5)
                               if (i := hero_id * 10 + suffix) in skills]})
    out = ROOT / "analysis/progression/hero_unlock_catalog.json"
    out.write_text(json.dumps({"sources": sources, "rows": rows,
        "policy": "CONFIRMED_CLIENT_STATIC fragment cost; initial HeroData is REVIVAL_COMPAT"},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} open hero prototypes")


if __name__ == "__main__":
    main()
