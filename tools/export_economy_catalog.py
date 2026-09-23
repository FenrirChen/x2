"""Export a bounded runtime catalog from the existing client audit, without rescanning APKs."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis/economy"))
from audit_probe import data as base
from targeted_probe import data as extra


def export():
    audit = json.loads((ROOT / "analysis/economy/task_tables.json").read_text(encoding="utf-8"))
    by_id = {s["SectionID"]: s for s in base["SectionTable"]}
    sections, seen = [], set()
    next_id = 2110001
    while next_id in by_id and next_id not in seen:
        seen.add(next_id)
        sections.append(by_id[next_id])
        next_id = by_id[next_id].get("NextSectionID", 0)
    tasks = extra["DailyTask"]
    control = extra["TaskControl"][0]
    groups = set(control["DailyGiftGroup"] + control["WeeklyGiftGroup"])
    for task in tasks:
        groups.add(task["GiftGroup"])
    for section in sections:
        groups.update(section.get("FirVReward", []))
        groups.update(section.get("VReward", []))
    gifts = [g for g in extra["Gift"] if g["GiftGroup"] in groups]
    needed_items = {i for g in gifts for i in g.get("GiftValue", [])}
    candidates = [i for i in base["Item"] if i.get("QuickBuyID")]
    needed_items.update(i["ItemID"] for i in candidates)
    # Confirmed progression material metadata; no synthetic shop/drop rules.
    materials = json.loads((ROOT / "analysis/progression/material_links.json").read_text(encoding="utf-8"))
    needed_items.update(r["material_item_id"] for r in materials["rows"])
    needed_items.update(range(1237900, 1237930))
    catalog = {"provenance": "CONFIRMED_CLIENT_STATIC; runtime policies are separate",
        "sections": sections, "tasks": tasks, "task_conditions": {
            str(t["source_id"]): t["condition"] for t in audit["records"]},
        "task_control": control, "gifts": gifts,
        "items": [i for i in base["Item"] if i["ItemID"] in needed_items],
        "shops": base["ShopConfig"], "goods": base["ShopGoodsGroup"]}
    target = ROOT / "src/x2server/data/economy_catalog.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"sections": len(sections), "tasks": len(tasks), "gifts": len(gifts), "items": len(catalog["items"])})


if __name__ == "__main__":
    export()
