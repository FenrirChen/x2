"""Cross-index each DailyDungeon reward surface without inventing runtime drops."""
from collections import defaultdict
from importlib.resources import files
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def build():
    root = files("x2server").joinpath("data")
    battle = json.loads(root.joinpath("battle_entry_catalog.json").read_text(encoding="utf-8"))
    economy = json.loads(root.joinpath("economy_catalog.json").read_text(encoding="utf-8"))
    sections = {s["SectionID"]: s for s in economy["daily_sections"]}
    all_sections = {s["SectionID"]: s for s in battle["sections"]}
    gifts = defaultdict(list)
    for gift in economy["gifts"]:
        gifts[gift["GiftGroup"]].append(gift)
    items = {item["ItemID"]: item for item in economy["items"]}
    currencies = {1237900, 1237901, 1237902, 1237906, 1237907, 1237908, 1237910, 1237911}

    def fixed_chain_supported(groups):
        for group in groups:
            rows = gifts.get(group, [])
            if not rows:
                return False
            for row in rows:
                ids, nums, weights = row.get("GiftValue", []), row.get("Num", []), row.get("Probability", [])
                kind = row.get("AwardType", {}).get("value")
                if (kind not in (1, 2) or not ids or len(ids) != len(nums)
                        or kind == 1 and bool(weights)
                        or kind == 2 and (len(weights) != len(ids) or sum(weights) != 100)):
                    return False
                for item, count in zip(ids, nums):
                    if item not in items or type(count) is not int or count < 0:
                        return False
                    item_type = items[item].get("ItemType", {}).get("value")
                    if item_type == 10 or item_type == 16 and item not in currencies:
                        return False
        return True

    def reward(groups):
        result = defaultdict(int)
        unresolved = []
        for group in groups:
            rows = gifts.get(group, [])
            if not rows:
                unresolved.append({"group": group, "reason": "MISSING_GIFT"})
            for row in rows:
                if row.get("AwardType", {}).get("value") != 1 or row.get("Probability"):
                    unresolved.append({"group": group, "reason": "NON_FIXED_GIFT"})
                    continue
                for item, count in zip(row.get("GiftValue", []), row.get("Num", [])):
                    if item not in items or count < 1:
                        unresolved.append({"group": group, "reason": "INVALID_ITEM_OR_AMOUNT"})
                    else:
                        result[item] += count
        return {"gift_groups": groups, "fixed_items": dict(sorted(result.items())), "unresolved": unresolved}

    dungeons = []
    for dungeon in battle["daily_dungeons"]:
        ids = dungeon["SectionID"]
        rows = [sections[x] for x in ids if x in sections]
        previews = sorted({item for row in rows for item in
                           row.get("DroopDisplay", []) + row.get("DroopDisplayProbability", [])})
        normal_previews = sorted({item for row in rows for item in row.get("DroopDisplay", [])})
        other_types = {sid: all_sections[sid]["Type"] for sid in ids if sid in all_sections and sid not in sections}
        item_meta = {item: {"item_type": items[item].get("ItemType", {}).get("enum"),
                            "name_id": items[item].get("NameID")} for item in previews if item in items}
        section_data = []
        for sid in ids:
            row = sections.get(sid)
            if row is None:
                section_data.append({"section_id": sid, "section_type": other_types.get(sid),
                                     "status": "OUTSIDE_DAILY_REWARD_CATALOG"})
                continue
            preview = row.get("DroopDisplay", [])
            primary = preview[0] if len(preview) == 1 else None
            item_type = items.get(primary, {}).get("ItemType", {}).get("value") if primary is not None else None
            drop_supported = (primary is not None and primary in items and item_type != 10
                              and (item_type != 16 or primary in currencies))
            fixed_supported = fixed_chain_supported(row.get("FirVReward", []) + row.get("VReward", []))
            section_data.append({"section_id": sid, "section_type": 3,
                "first_clear_fixed": reward(row.get("FirVReward", [])),
                "normal_fixed": reward(row.get("VReward", [])),
                "normal_drop": {"drop_value_id": row.get("DropValueID"),
                    "preview_items": row.get("DroopDisplay", []),
                    "preview_probability_items": row.get("DroopDisplayProbability", []),
                    "official_quantity_rule_status": "UNRESOLVED",
                    "official_probability_rule_status": "UNRESOLVED",
                    "revival_compat_item_id": primary if drop_supported else None,
                    "revival_compat_quantity": 1 if drop_supported else None,
                    "runtime_status": "REVIVAL_COMPAT" if drop_supported else "BLOCKED_BY_MISSING_DATA"},
                "sweep_reward": reward(row.get("MopReward", [])),
                "entry_reward_supported": bool(drop_supported and fixed_supported)})
        if not rows:
            status = "BLOCKED_BY_MISSING_DATA"
        elif all(s["entry_reward_supported"] for s in section_data):
            status = "REVIVAL_COMPAT"
        elif len(normal_previews) == 1:
            status = "PARTIAL"
        else:
            status = "PARTIAL" if previews else "BLOCKED_BY_MISSING_DATA"
        dungeons.append({"dungeon_id": dungeon["ID"], "name": rows[0].get("NameChina") if rows else None,
            "section_ids": ids, "section_types": {str(sid): all_sections[sid]["Type"]
                for sid in ids if sid in all_sections},
            "primary_resource_item_id": normal_previews[0] if len(normal_previews) == 1 else None,
            "preview_resource_item_ids": normal_previews,
            "preview_probability_item_ids": sorted(set(previews) - set(normal_previews)),
            "item_metadata": item_meta,
            "evidence": ["SectionTable.DroopDisplay", "DailySectionCell.Refresh RVA 0x168AF9C"] if rows else [],
            "status": status, "sections": section_data})
    return {"summary": {"dungeons": len(dungeons),
        "revival_compat_dungeons": sum(d["status"] == "REVIVAL_COMPAT" for d in dungeons),
        "revival_compat_sections": sum(s.get("entry_reward_supported", False) for d in dungeons for s in d["sections"]),
        "single_preview_resource": sum(d["primary_resource_item_id"] is not None for d in dungeons),
        "multi_preview_resource": sum(len(d["preview_resource_item_ids"]) > 1 for d in dungeons),
        "no_daily_preview": sum(not d["preview_resource_item_ids"] for d in dungeons)},
        "dungeons": dungeons}


if __name__ == "__main__":
    target = ROOT / "analysis/battle/daily_dungeon_reward_audit.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    audit = build()
    target.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(target)
