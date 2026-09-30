"""Export official MapInfo base monster levels for battle entry responses."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "progression"))
from probe import read_tables


def main():
    tables, sources, missing = read_tables(["MapInfo"])
    if missing:
        raise RuntimeError(f"indexed map table missing: {missing}")
    levels = {str(row["MapTypeID"]): row.get("MonsterLevel", 0)
              for row in tables["MapInfo"]}
    output = ROOT / "src/x2server/data/battle_monster_levels.json"
    output.write_text(json.dumps({"provenance": sources, "levels": levels},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(levels)} map monster levels -> {output}")


if __name__ == "__main__":
    main()
