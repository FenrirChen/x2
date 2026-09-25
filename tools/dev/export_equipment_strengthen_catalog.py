"""Export quality/attribute increment ranges for 3-level equipment events."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis/progression"))
from probe import read_tables  # noqa: E402


def main():
    tables, sources, missing = read_tables(["EquibAttrib"])
    if missing:
        raise RuntimeError(missing)
    rows = []
    for row in tables["EquibAttrib"]:
        if row.get("AttribSRC") == 3 and row.get("ValueSec"):
            rows.append({"quality": row["EquibRare"], "attribute": row["AttrType"],
                         "value_range": row["ValueSec"], "chance": row.get("ChanceSec", [])})
    path = ROOT / "analysis/progression/equipment_strengthen_catalog.json"
    path.write_text(json.dumps({"source": sources["EquibAttrib"], "rows": rows,
        "interpretation": "AttribSRC 3 candidate range for compatibility strengthen events; random roll is REVIVAL_COMPAT"},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} strengthen candidate rows")


if __name__ == "__main__":
    main()
