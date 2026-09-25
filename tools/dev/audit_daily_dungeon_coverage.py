"""Classify each indexed DailyDungeon's static entry and fixed reward chain."""
from collections import defaultdict
from importlib.resources import files
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
runtime = files("x2server")


def analyze():
    battle = json.loads(runtime.joinpath("data/battle_entry_catalog.json").read_text(encoding="utf-8"))
    economy = json.loads(runtime.joinpath("data/economy_catalog.json").read_text(encoding="utf-8"))
    sections = {row["SectionID"]: row for row in battle["sections"]}
    groups = defaultdict(list)
    for row in economy["gifts"]:
        groups[row["GiftGroup"]].append(row)
    items = {row["ItemID"]: row for row in economy["items"]}
    currencies = {1237900, 1237901, 1237902, 1237906, 1237907, 1237908, 1237910, 1237911}
    records = []
    for dungeon in battle["daily_dungeons"]:
        ids = dungeon["SectionID"]
        daily = [sid for sid in ids if sid in sections and sections[sid]["Type"] == 3]
        other = [{"section_id": sid, "section_type": sections[sid]["Type"]}
                 for sid in ids if sid in sections and sections[sid]["Type"] != 3]
        missing = [sid for sid in ids if sid not in sections]
        missing_map = [sid for sid in daily if not sections[sid].get("Maps")]
        missing_cost = [sid for sid in daily if type(sections[sid].get("ManualValue")) is not int]
        # ChapterModule.CheckDailySectionFirstChallenge uses list IndexOf,
        # so absent NextSectionID is resolved by DailyDungeon.SectionID order.
        broken_next = [{"from": left, "expected": right, "actual": sections[left]["NextSectionID"]}
                       for left, right in zip(ids, ids[1:]) if left in sections
                       and sections[left].get("NextSectionID") not in (None, right)]
        gift_ids = {gid for sid in daily for field in ("FirVReward", "VReward")
                    for gid in sections[sid].get(field, [])}
        missing_gifts = sorted(gift_ids - groups.keys())
        random_gifts = sorted(gid for gid in gift_ids if any(
            row.get("AwardType", {}).get("value") != 1 or row.get("Probability") for row in groups[gid]))
        unknown_items = sorted({item for gid in gift_ids for row in groups[gid]
                                for item in row.get("GiftValue", []) if item not in items})
        unsupported_destinations = sorted({item for gid in gift_ids for row in groups[gid]
                                           for item in row.get("GiftValue", []) if item in items and
                                           items[item].get("ItemType", {}).get("value") == 16 and item not in currencies})
        reasons = []
        if other:
            reasons.append("NON_DAILY_SECTION_TYPE")
        if missing or missing_map or missing_cost or broken_next or missing_gifts or unknown_items:
            reasons.append("STATIC_CHAIN_INCOMPLETE")
        if random_gifts:
            reasons.append("RANDOM_GIFT_RULE_UNRECOVERED")
        if unsupported_destinations:
            reasons.append("BLOCKED_REWARD_DESTINATION")
        records.append({"dungeon_id": dungeon["ID"], "section_count": len(ids),
            "daily_section_count": len(daily), "non_daily_sections": other,
            "missing_sections": missing, "missing_maps": missing_map,
            "missing_manual_values": missing_cost, "broken_next_links": broken_next,
            "fixed_reward_group_count": len(gift_ids), "missing_gifts": missing_gifts,
            "random_gift_groups": random_gifts, "unknown_items": unknown_items,
            "unsupported_destinations": unsupported_destinations,
            "static_fixed_reward_status": "RESOLVABLE" if not reasons else "PARTIAL",
            "reasons": reasons})
    linked_daily = {section for dungeon in battle["daily_dungeons"]
                    for section in dungeon["SectionID"]
                    if section in sections and sections[section]["Type"] == 3}
    entry_resolvable = []
    for section in sorted(linked_daily):
        row = sections[section]
        gift_ids = list(row.get("FirVReward", [])) + list(row.get("VReward", []))
        gift_rows = [gift for gid in gift_ids for gift in groups[gid]]
        if (not gift_ids or any(not groups[gid] for gid in gift_ids)
                or any(gift.get("AwardType", {}).get("value") != 1 or gift.get("Probability")
                       for gift in gift_rows)
                or any(item not in items or items[item].get("ItemType", {}).get("value") == 10
                       or items[item].get("ItemType", {}).get("value") == 16 and item not in currencies
                       for gift in gift_rows
                       for item in gift.get("GiftValue", []))):
            continue
        entry_resolvable.append(section)
    orphan_daily = sorted(sid for sid, row in sections.items() if row["Type"] == 3 and sid not in linked_daily)
    return {"summary": {"dungeons": len(records), "fully_resolvable_static_fixed_reward":
            sum(r["static_fixed_reward_status"] == "RESOLVABLE" for r in records),
            "special_type_dungeons": sum(bool(r["non_daily_sections"]) for r in records),
            "random_gift_dungeons": sum(bool(r["random_gift_groups"]) for r in records),
            "blocked_destination_dungeons": sum(bool(r["unsupported_destinations"]) for r in records),
            "linked_daily_sections": len(linked_daily),
            "entry_reward_resolvable_daily_sections": len(entry_resolvable),
            "entry_reward_blocked_daily_sections": len(linked_daily) - len(entry_resolvable),
            "orphan_daily_sections": orphan_daily},
            "dungeons": records}


if __name__ == "__main__":
    output = ROOT / "analysis/coverage/daily_dungeon_coverage.json"
    result = analyze()
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False))
