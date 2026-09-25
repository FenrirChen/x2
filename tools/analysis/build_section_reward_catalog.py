"""Classify every canonical SectionTable row without inventing runtime drops."""
from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKSPACE = ROOT / "x2_revive_workspace"
TABLES = ROOT / "analysis/drop_archaeology/full_tables"


def rows(name):
    return json.loads((TABLES / f"{name}.json").read_text(encoding="utf-8"))["records"]


def build():
    sections = rows("sectiontable")
    type_catalog = json.loads((WORKSPACE / "analysis/battle/section_type_catalog.json").read_text(encoding="utf-8"))["types"]
    items = {row["ItemID"]: row for row in rows("item")}
    gifts = defaultdict(list)
    for row in rows("gift"):
        gifts[row["GiftGroup"]].append(row)
    daily = defaultdict(set)
    gold_daily = set()
    for dungeon in rows("dailydungeon"):
        for section_id in dungeon.get("SectionID", []):
            daily[section_id].add(dungeon["ID"])
    extras = defaultdict(list)
    for row in rows("extradroop"):
        if row.get("SectionChoice", {}).get("value") == 1:
            for section_id in row.get("SectionGroup", []):
                extras[section_id].append(row["ID"])
    special_fields = ("ChestReward", "ExpertChestReward", "ChallengeReward1")
    catalog = []
    for row in sections:
        section_id = row["SectionID"]
        section_type = row.get("Type", {}).get("value", 0)
        groups = {source: row.get(field, []) for source, field in (
            ("FIRST_CLEAR_FIXED", "FirVReward"), ("NORMAL_CLEAR_FIXED", "VReward"),
            ("SWEEP_REWARD", "MopReward"))}
        missing_gifts = sorted({group for numbers in groups.values() for group in numbers if group not in gifts})
        special = {field: row[field] for field in special_fields if row.get(field)}
        if extras.get(section_id):
            special["ExtraDroop"] = sorted(extras[section_id])
        preview = row.get("DroopDisplay", [])
        compat = None
        if section_type == 3 and section_id in daily and preview == [1237901]:
            # Only an actual sweep-only Gift with account gold qualifies.
            sweep_only = set(groups["SWEEP_REWARD"]) - set(groups["NORMAL_CLEAR_FIXED"])
            matches = [group for group in sweep_only if len(gifts[group]) == 1
                       and gifts[group][0].get("AwardType", {}).get("value") == 1
                       and gifts[group][0].get("GiftValue") == [1237901]
                       and len(gifts[group][0].get("Num", [])) == 1
                       and type(gifts[group][0]["Num"][0]) is int
                       and gifts[group][0]["Num"][0] > 0]
            if len(matches) == 1:
                compat = {"policy": "REVIVAL_COMPAT_GOLD_DUNGEON",
                          "gift_group": matches[0], "item_id": 1237901,
                          "quantity": gifts[matches[0]][0]["Num"][0]}
                gold_daily.add(section_id)
        profile = {
            "section_id": section_id, "section_type": section_type,
            "section_type_name": row.get("Type", {}).get("enum", "E_UNSET"),
            "chapter_id": row["ChapterID"], "dungeon_ids": sorted(daily[section_id]),
            "first_reward": groups["FIRST_CLEAR_FIXED"],
            "normal_reward": groups["NORMAL_CLEAR_FIXED"],
            "sweep_reward": groups["SWEEP_REWARD"],
            "drop_value_id": row.get("DropValueID"), "droop_display": preview,
            "runtime_drop_sources": ["C2L_CheckoutMainMission.outsideItems"] if row.get("Maps") else [],
            "drop_prop_roots": [], "direct_items": [], "nested_drop_items": [],
            "contains_adc": None, "currency": [], "equipment": [],
            "runtime_source_confidence": "UNKNOWN_PER_SECTION_SPAWN_CLOSURE",
            "runtime_allowlist_mode": "DYNAMIC_ALLOWED",
            "unknown_sources": ["Section.Map->spawned Unit/NpcEvent closure not statically complete"] if row.get("Maps") else [],
            "extra_drop": sorted(extras[section_id]), "special_reward_fields": special,
            "special_source_tables": type_catalog.get(row.get("Type", {}).get("enum", "E_UNSET"), {}).get("supporting_tables", []),
            "missing_gift_groups": missing_gifts,
            "delivery_types": sorted({items[item].get("ItemType", {}).get("enum", "UNKNOWN")
                for numbers in groups.values() for group in numbers for gift in gifts[group]
                for item in gift.get("GiftValue", []) if item in items}),
            "runtime_status": "ENTRY_CAPABILITY_SEPARATE_FROM_REWARD_PROFILE",
            "reward_capabilities": {
                "fixed": "FIXED_REWARD_SUPPORTED" if groups["FIRST_CLEAR_FIXED"] or groups["NORMAL_CLEAR_FIXED"] else "NO_FIXED_GIFT_CONFIG",
                "runtime": "RUNTIME_DROP_SUPPORTED_IF_VALID_BATTLE_RUN",
                "sweep": "SWEEP_SUPPORTED_IF_CLEARED" if groups["SWEEP_REWARD"] else "NO_MOP_REWARD_CONFIG",
                "special": "SPECIAL_REWARD_SOURCE_UNRESOLVED" if special else "NO_SECTION_SPECIAL_FIELD",
                "entry": "ENTRY_REQUIRES_RUNTIME_VALIDATION"},
            "compat_policy": compat,
            "notes": ["DroopDisplay is UI only; DropValueID has no recovered server mapping"]
        }
        catalog.append(profile)
    assert len(catalog) == len({r["section_id"] for r in catalog}) == 3203
    counts = Counter(r["section_type_name"] for r in catalog)
    return {"provenance": "X2 2.4 canonical SectionTable/Gift/Item/DailyDungeon/ExtraDroop",
            "total_sections": len(catalog), "section_type_counts": dict(sorted(counts.items())),
            "gold_compat_sections": sorted(gold_daily), "sections": catalog}


if __name__ == "__main__":
    target = WORKSPACE / "analysis/reward/section_reward_catalog.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    data = build()
    target.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    item_target = WORKSPACE / "src/x2server/data/reward_items.json"
    item_rows = [{field: row[field] for field in ("ItemID", "ItemType", "ItemUseScence", "PileCount") if field in row}
                 for row in rows("item")]
    item_target.write_text(json.dumps(item_rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(len(data["sections"]), len(data["section_type_counts"]), len(data["gold_compat_sections"]))
