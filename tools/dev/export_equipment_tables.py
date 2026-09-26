"""Export canonical equipment tables for the server from the audited full-table extracts.

Reads (repo analysis layer, read-only):
  analysis/drop_archaeology/full_tables/equibbase.json
  analysis/drop_archaeology/full_tables/equibstage.json
  analysis/drop_archaeology/full_tables/equibattribbd.json
  analysis/equipment/equibattrib_full.json   (EquibAttrib incl. AttribSRC, re-parsed raw bin)

Writes:
  src/x2server/data/equipment_tables.json

The minor-count tier map is DERIVED from canonical EquibAttribBD rows:
  base = MinorAttrNum of the QQ000000 row, max = MinorAttrNum of the QQ000100 row.
The 65/35 tier choice and the ValueSec chain roll are REVIVAL_COMPATIBILITY /
USER_DECISIONs (docs/decisions/compatibility/equip_attribbd_tier_selection.md,
equip_valuesec_tier_roll.md) and are NOT part of this data file.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FULL = ROOT.parent / "analysis/drop_archaeology/full_tables"
OUT = ROOT / "src/x2server/data/equipment_tables.json"


def main():
    base_rows = json.loads((FULL / "equibbase.json").read_text(encoding="utf-8"))["records"]
    stage_rows = json.loads((FULL / "equibstage.json").read_text(encoding="utf-8"))["records"]
    bd_rows = json.loads((FULL / "equibattribbd.json").read_text(encoding="utf-8"))["records"]
    attrib_rows = json.loads(
        (ROOT / "analysis/equipment/equibattrib_full.json").read_text(encoding="utf-8"))

    equib_base = {}
    for row in base_rows:
        equib_base[str(row["EquibId"])] = {
            "part": row["EquibPart"], "suit": row["EquibSuit"],
            "main_attr_type": row["MainAttrType"], "main_attr_chance": row["MainAttrChance"],
            "minor_attr_type": row["MinorAttrType"], "minor_attr_chance": row["MinorAttrChance"],
        }

    equib_attrib: dict[str, dict[str, dict[str, dict]]] = {}
    for row in attrib_rows:
        star = str(row["rare"])
        src = str(row["src"])
        equib_attrib.setdefault(star, {}).setdefault(src, {})[str(row["type"])] = {
            "value_sec": row["ValueSec"], "chance_sec": row["ChanceSec"]}

    equib_attrib_bd = {}
    for row in bd_rows:
        equib_attrib_bd[str(row["AttrbdID"])] = {
            "equib_quality": row.get("EquibQuality"),
            "minor_attr_num": row.get("MinorAttrNum"),
        }

    minor_count_tiers = {}
    for quality in range(1, 7):
        prefix = f"{10 + quality}"
        base_rows = [r["minor_attr_num"] for rid, r in equib_attrib_bd.items()
                     if rid.startswith(f"{prefix}000000") and r["minor_attr_num"]]
        max_rows = [r["minor_attr_num"] for rid, r in equib_attrib_bd.items()
                    if rid.startswith(f"{prefix}000100") and r["minor_attr_num"]]
        base_values = sorted(set(base_rows))
        max_values = sorted(set(max_rows)) or base_values
        assert len(base_values) == 1, f"star {quality}: ambiguous base MinorAttrNum {base_values}"
        assert len(max_values) == 1, f"star {quality}: ambiguous max MinorAttrNum {max_values}"
        assert max_values[0] >= base_values[0]
        minor_count_tiers[str(quality)] = {"base": base_values[0], "max": max_values[0]}

    equib_stage = {str(r["Stage"]): {"minor_list_min": r["MinorListMin"],
                                     "minor_list_max": r["MinorListMax"],
                                     "equib_value": r["EquibValue"]} for r in stage_rows}

    for star, tiers in minor_count_tiers.items():
        stage = equib_stage[star]
        assert tiers["base"] == stage["minor_list_min"], f"star {star}: base row vs MinorListMin"
        assert tiers["max"] == stage["minor_list_max"], f"star {star}: max row vs MinorListMax"

    data = {
        "source": {
            "equib_base": "analysis/drop_archaeology/full_tables/equibbase.json (126 rows, official 2.4)",
            "equib_stage": "analysis/drop_archaeology/full_tables/equibstage.json (6 rows)",
            "equib_attrib_bd": "analysis/drop_archaeology/full_tables/equibattribbd.json (66 rows)",
            "equib_attrib": "analysis/equipment/equibattrib_full.json (384 rows incl. AttribSRC, re-parsed raw bin)",
            "official_note": "ValueSec/ChanceSec/MinorAttrNum are official client-table values; "
                             "the tier CHOICE (65/35) and the chain roll are REVIVAL_COMPATIBILITY "
                             "USER_DECISIONs and live in code, not in this file.",
        },
        "equib_base": equib_base,
        "equib_attrib": equib_attrib,
        "equib_attrib_bd": equib_attrib_bd,
        "equib_stage": equib_stage,
        "minor_count_tiers": minor_count_tiers,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUT}: base={len(equib_base)} attrib={sum(len(v) for a in equib_attrib.values() for v in a.values())} "
          f"bd={len(equib_attrib_bd)} tiers={minor_count_tiers}")


if __name__ == "__main__":
    main()
