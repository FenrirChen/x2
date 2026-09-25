"""Export SectionTable reward references from already extracted client tables."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis/economy"))
from audit_probe import data as base
from targeted_probe import data as extra


def export():
    groups = {group for section in base["SectionTable"]
              for field in ("VReward", "FirVReward")
              for group in section.get(field, [])}
    gifts = [row for row in extra["Gift"] if row["GiftGroup"] in groups]
    item_ids = {item for row in gifts for item in row.get("GiftValue", [])}
    items = [row for row in base["Item"] if row["ItemID"] in item_ids]
    result = {"provenance": "CONFIRMED_CLIENT_STATIC; no inferred rewards",
              "gifts": gifts, "items": items}
    target = ROOT / "src/x2server/data/battle_rewards_catalog.json"
    target.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print({"referenced_groups": len(groups), "gift_rows": len(gifts), "items": len(items),
           "missing_groups": len(groups - {row["GiftGroup"] for row in gifts})})


if __name__ == "__main__":
    export()
