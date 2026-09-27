"""Export collection rewards from the recovered client tables, with validation."""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TABLES = ROOT.parent / "analysis/drop_archaeology/full_tables"
OUTPUT = ROOT / "src/x2server/data/collection_catalog.json"


def load(name):
    return json.loads((TABLES / f"{name}.json").read_text(encoding="utf-8"))


def build():
    collection, gift = load("collection"), load("gift")
    groups = {row["GiftGroup"] for row in collection["records"]}
    gifts = [row for row in gift["records"] if row["GiftGroup"] in groups]
    assert len(collection["records"]) == 26
    assert len(gifts) == 26 and {row["GiftGroup"] for row in gifts} == groups
    assert all(row["CollectionType"]["value"] == 1 and
               row["ConditionType"]["value"] == 1 and row["CompleteValue1"]
               for row in collection["records"])
    assert all(row["AwardType"]["value"] == 1 for row in gifts)
    return {"source": "OFFICIAL_CLIENT_STATIC", "source_hashes": {
        "Collection": collection["source_hash"], "Gift": gift["source_hash"]},
        "collection": collection["records"], "gifts": gifts}


if __name__ == "__main__":
    OUTPUT.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
