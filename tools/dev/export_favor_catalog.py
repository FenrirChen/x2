"""Export only official client favor tables and eligible gift items."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TABLES = ROOT.parent / "analysis/drop_archaeology/full_tables"
OUTPUT = ROOT / "src/x2server/data/favor_catalog.json"
NAMES = ("favorabilityhero", "favorabilitylevel", "favorabilityfetters",
         "favorabilityfiles", "favorabilitydairy")


def build():
    result = {"source": "OFFICIAL_CLIENT_STATIC", "source_hashes": {}}
    for name in (*NAMES, "item"):
        table = json.loads((TABLES / f"{name}.json").read_text(encoding="utf-8"))
        result["source_hashes"][name] = table["source_hash"]
        if name == "item":
            result["gifts"] = [row for row in table["records"] if
                row.get("FunctionEff", {}).get("enum") == "E_AddFavorability" and
                row.get("ItemUseScence", {}).get("value") == 1]
        else:
            result[name] = table["records"]
    assert len(result["gifts"]) == 59
    return result


if __name__ == "__main__":
    OUTPUT.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
