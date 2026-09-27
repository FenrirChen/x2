"""Read-only extraction of official 2.4 College economic anchors."""
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
TABLES = ROOT / "analysis/drop_archaeology/full_tables"
OUT = Path(__file__).with_name("official_economic_anchors.json")


def rows(name):
    return json.loads((TABLES / f"{name}.json").read_text(encoding="utf-8"))["records"]


def span(values):
    return {"min": min(values), "median": statistics.median(values), "max": max(values)}


building, levels, stars = (rows(n) for n in ("collegebuilding", "collegelevel", "collegestarlevel"))
explore, recipe, quest = (rows(n) for n in ("collegeexplore", "collegerecipe", "collegequest"))
customer, reset = (rows(n) for n in ("collegecustomer", "collegeequibreset"))
gift = {r["GiftGroup"]: r for r in rows("gift")}
items = {r["ItemID"]: r for r in rows("item")}
language = {r["Key"]: r.get("Chinese", "") for r in rows("language")}
sections = {r["SectionID"]: r for r in rows("sectiontable")}


def gift_summary(group):
    row = gift[group]
    weights = row.get("Probability", [])
    outcomes = [{"item_id": i, "count": n,
                 "probability": weights[k] / sum(weights) if weights else 1,
                 "item_value": items.get(i, {}).get("ItemValue")}
                for k, (i, n) in enumerate(zip(row["GiftValue"], row["Num"]))]
    return {"gift_group": group, "award_type": row["AwardType"]["enum"],
            "outcomes": outcomes, "expected_quantity_by_item": {
                str(i): round(sum(o["count"] * o["probability"] for o in outcomes if o["item_id"] == i), 4)
                for i in sorted({o["item_id"] for o in outcomes})}}


rift = []
for section_id in range(2132101, 2132106):
    section = sections[section_id]
    rift.append({"section_id": section_id, "manual_value": section.get("ManualValue"),
                 "reward_groups": section["MopReward"],
                 "gifts": [gift_summary(i) for i in section["MopReward"]]})

gold_reference = []
for section_id in range(2130101, 2130106):
    section = sections[section_id]
    groups = section.get("MopReward", [])
    gold_reference.append({"section_id": section_id, "reward_groups": groups,
        "deterministic_gold": sum(n for group in groups if gift[group]["AwardType"]["value"] == 1
            for i, n in zip(gift[group]["GiftValue"], gift[group]["Num"]) if i == 1237901)})

anchors = {
    "provenance": "OFFICIAL_CONSTRAINT: official client 2.4 static tables; ItemValue is a rating, not an exchange rate",
    "source_directory": str(TABLES),
    "college_building": {"count": len(building), "ordinary_ids": [r["ID"] for r in building if r["BaseType"]["value"] == 1],
        "wonder_ids": [r["ID"] for r in building if r["BaseType"]["value"] == 2],
        "initial_and_caps": [{"id": r["ID"], "initial_level": r.get("InitialLevel"),
            "initial_star": r.get("InitialStar"), "level_cap": r.get("LevelLimited"),
            "star_cap": r.get("StarLimited"), "building_open": r.get("BuildingOpen", "MISSING")}
            for r in building]},
    "college_level": {"row_count": len(levels), "level_span": span([r["BuildingLevel"] for r in levels]),
        "prerequisite_types": sorted({r.get("PreconditionType", {}).get("enum", "MISSING") for r in levels}),
        "cost": "MISSING", "build_time": "MISSING"},
    "college_star_level": {"row_count": len(stars), "star_span": span([r["BuildingStar"] for r in stars]),
        "limit_levels": sorted({r["LimitLevel"] for r in stars if "LimitLevel" in r}), "cost": "MISSING"},
    "college_wonder_skill": {"row_count": len(rows("collegewonderskill")), "cost": "MISSING"},
    "college_explore": {"row_count": len(explore), "wait_seconds": span([r["WaitTimes"] for r in explore]),
        "power_consume": span([r["PowerConsume"] for r in explore]),
        "rows": [{"id": r["ID"], "wait_seconds": r["WaitTimes"], "power_consume": r["PowerConsume"],
                  "reward_gift": gift_summary(r["Reward"]), "produce_id": r["ProduceID"],
                  "condition": r.get("Conditon")} for r in explore]},
    "college_recipe": {"row_count": len(recipe), "gold": span([r["Gold"] for r in recipe]),
        "pay": span([r["Pay"] for r in recipe]), "wait_seconds": span([r["WaitTimes"] for r in recipe]),
        "input_item_ids": sorted({i for r in recipe for i in r["ItemGroup"]}),
        "output_item_ids": sorted({r["ProductID"] for r in recipe}),
        "rows": [{"id": r["RecipeID"], "level": r["RecipeLevel"],
                  "inputs": list(zip(r["ItemGroup"], r["ItemNum"])), "output": [r["ProductID"], r["ProductNum"]],
                  "gold": r["Gold"], "pay": r["Pay"], "wait_seconds": r["WaitTimes"]} for r in recipe],
        "gold_pay_semantics": "MISSING: do not assume Gold/Pay are craft costs or sale prices"},
    "college_quest": {"row_count": len(quest), "award_type_counts": {name: sum(r["AwardType"]["enum"] == name for r in quest)
        for name in sorted({r["AwardType"]["enum"] for r in quest})},
        "gift_award_groups": sorted({i for r in quest if r["AwardType"]["enum"] == "E_Gift" for i in r["AwardGroup"]}),
        "gold_award_values": sorted({i for r in quest if r["AwardType"]["enum"] == "E_Gold" for i in r["AwardGroup"]})},
    "college_customer": {"row_count": len(customer), "hero_count": sum(r["Type"]["enum"] == "E_Hero" for r in customer),
        "npc_count": sum(r["Type"]["enum"] == "E_NPC" for r in customer)},
    "college_equib_reset": {"row_count": len(reset), "rows": reset},
    "time_rift": {"note": "MopReward includes account EXP, hero EXP and gold; 123780x is the College material part",
        "sections": rift},
    "gold_dungeon_reference": {"note": "Official client MopReward values only; daily access and stamina cost are separate",
        "sections": gold_reference},
    "acceleration_cards": [{"item_id": i, "name": language.get(items[i]["NameID"]),
        "description": language.get(items[i]["DescID"]), "effect": items[i].get("FunctionEff"),
        "seconds": items[i]["EffData"][0]} for i in range(1237831, 1237836)],
    "upgrade_items": [{"item_id": i, "name": language.get(items[i]["NameID"]),
        "description": language.get(items[i]["DescID"]), "item_value": items[i].get("ItemValue")}
        for i in range(1237801, 1237810)],
    "currency_anchors": {"items": [{"item_id": i, "name": language.get(items[i]["NameID"]),
        "item_value": items[i].get("ItemValue")}
        for i in (1237901, 1237902, 1237907, 1237922) if i in items],
        "star_energy_item_id": "MISSING: GrowthBase field, no confirmed account Item mapping",
        "exchange_rates": "MISSING: ItemValue is not a currency exchange rate"},
    "missing_server_only": ["building_upgrade_cost", "wonder_upgrade_cost", "star_energy_rate_and_cap",
        "build_time", "cancel_refund", "customer_generation", "training_reward", "daily_reset_hour"],
}
OUT.write_text(json.dumps(anchors, ensure_ascii=False, indent=2), encoding="utf-8")
print(OUT, "written")
