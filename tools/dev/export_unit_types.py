"""Export official UnitBase ID -> UnitType for battle task accounting."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
source = root.parent / "analysis/drop_archaeology/full_tables/unitbase.json"
target = root / "src/x2server/data/unit_types.json"
rows = json.loads(source.read_text(encoding="utf-8"))["records"]
mapping = {str(row["ID"]): row["UnitType"]["value"] for row in rows
           if row.get("UnitType")}
target.write_text(json.dumps(mapping, sort_keys=True, separators=(",", ":")), encoding="utf-8")
print(f"{len(mapping)} official unit types -> {target}")
