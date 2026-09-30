"""Export supported wish pools from the recovered client tables."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from analysis.progression.probe import read_tables

data, _, missing = read_tables(["DrawParam", "Gift"])
if missing:
    raise SystemExit(f"missing wish tables: {missing}")
gifts = {row["GiftGroup"]: row for row in data["Gift"]}
pools = {}
for row in data["DrawParam"]:
    kind = row.get("DrawnType", {}).get("enum", "E_Hero")
    if row["DrawnID"] not in (22201, 22203) and kind not in ("E_Up", "E_Limited", "E_Jewel"):
        continue
    groups = {}
    for kind, field in (("common", "CommonPrize"), ("security", "SecurityPrize"), ("top", "TopPrize")):
        gift = gifts[row[field]]
        groups[kind] = [{"item_id": i, "quantity": n, "weight": p}
            for i, n, p in zip(gift["GiftValue"], gift["Num"],
                gift.get("Probability") or [1] * len(gift["GiftValue"]))]
    if row.get("LimitPrize"):
        gift = gifts[row["LimitPrize"]]
        groups["limit"] = [{"item_id": i, "quantity": n, "weight": p}
            for i, n, p in zip(gift["GiftValue"], gift["Num"],
                gift.get("Probability") or [1] * len(gift["GiftValue"]))]
    pools[str(row["DrawnID"])] = {"draw_count_id": row["DrawnCount"],
        "type": row.get("DrawnType", {}).get("enum", "E_Hero"),
        "ticket_item_id": 1237000 + row["ItemConsum"][0],
        "one_ticket": row["ItemConsum"][1], "one_crystal": row["CurrencyThird"][1],
        "three_star_security": row["ThreeStarSecurityNum"],
        "hero_security": row.get("SecurityNum", 0),
        "limit_num": row.get("LimitNum", 0), "limit_items": row.get("LimitItem", []),
        "groups": groups,
        "one_power_of_light": row.get("Currency", [0, 0])[1]}
target = ROOT / "src/x2server/data/wish_catalog.json"
target.write_text(json.dumps(pools, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(target)
