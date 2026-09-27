"""Offline expectation model for the unapproved College balance proposal.

This is NOT a server rule or a forecast for real players. Time Rift runs and one
gold-dungeon run/day are exogenous assumptions; stamina and account progression
are excluded. DEFER systems produce zero rather than invented rewards.
"""
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
ANCHORS = json.loads((HERE / "official_economic_anchors.json").read_text(encoding="utf-8"))
CONFIG = json.loads((HERE / "college_compatibility_draft.json").read_text(encoding="utf-8"))
TABLES = ROOT / "analysis/drop_archaeology/full_tables"
BUILDINGS = json.loads((TABLES / "collegebuilding.json").read_text(encoding="utf-8"))["records"]
LEVELS = {r["BuildID"]: r for r in json.loads((TABLES / "collegelevel.json").read_text(encoding="utf-8"))["records"]}
EXPLORE = ANCHORS["college_explore"]["rows"]
RIFT = ANCHORS["time_rift"]["sections"]


def v(path):
    node = CONFIG
    for part in path.split("."):
        node = node[part]
    return node["value"]


def expected_gift(group):
    result = defaultdict(float)
    for outcome in group["outcomes"]:
        result[outcome["item_id"]] += outcome["probability"] * outcome["count"]
    return result


def round50(x):
    return int(round(x / 50) * 50)


def tier(target):
    for lo, hi, item in v("building.material_tier_by_target_level"):
        if lo <= target <= hi:
            return item
    raise ValueError(target)


def eligible(row, target, levels):
    static = LEVELS[row["LevelID"][target - 1]]
    required = static.get("PreconditionValue")
    kind = static.get("PreconditionType", {}).get("enum")
    if kind == "E_AccountLevel" and required is not None:
        return 60 >= required
    if kind == "E_Building01Level" and required is not None:
        return levels[701] >= required
    return required is None


def login_hours(visits):
    return {1: (12,), 2: (8, 20), 3: (8, 14, 20)}[visits]


def simulate(preset, visits, days):
    modifiers = {k: x["value"] for k, x in CONFIG["presets"][preset].items()}
    open_rows = [r for r in BUILDINGS if r["ID"] != 728]
    levels = {r["ID"]: r["InitialLevel"] for r in open_rows}
    materials = defaultdict(float)
    rift_materials_earned = defaultdict(float)
    upgrade_materials_spent = defaultdict(float)
    gold = 0.0
    college_gold_receipts = 0.0
    college_gold_spent = 0.0
    rift_gold_receipts = 0.0
    energy = 0.0
    energy_generated = 0.0
    energy_spent = 0.0
    dispatch_rewards = defaultdict(float)
    dispatches = []
    queues = {1: None, 2: None}
    completed_upgrades = 0
    completed_dispatches = 0
    last_time = 0
    rift_runs = 0
    # A real account must earn this gold and spend stamina on both dungeon types.
    external_gold = 14552  # official 2130104 deterministic gold from its MopReward
    for day in range(days):
        for index, hour in enumerate(login_hours(visits)):
            now = day * 24 + hour
            delta = min(now - last_time, modifiers["offline_cap_hours"])
            gained = min(96 - energy, max(0, delta) * modifiers["energy_rate_per_hour"])
            energy += gained
            energy_generated += gained
            last_time = now
            if index == 0:
                gold += external_gold
            for queue_type, queue in list(queues.items()):
                if queue and queue[0] <= now:
                    levels[queue[1]] += 1
                    completed_upgrades += 1
                    queues[queue_type] = None
            for finish, gift in list(dispatches):
                if finish <= now:
                    for item, amount in expected_gift(gift).items():
                        dispatch_rewards[item] += amount
                        if item == 1237901:
                            gold += amount
                            college_gold_receipts += amount
                    completed_dispatches += 1
                    dispatches.remove((finish, gift))

            # Each login permits one assumed Time Rift run. Choose the material
            # tier of the lowest-level upgrade that the level-60 account can do.
            candidates = []
            for row in open_rows:
                target = levels[row["ID"]] + 1
                if target <= row["LevelLimited"] and eligible(row, target, levels):
                    candidates.append((levels[row["ID"]], row["ID"], row, target))
            if candidates:
                _, _, target_row, target = min(candidates)
                item = tier(target)
                stage = min(4, item - 1237801)
            else:
                stage = 4
            for gift in RIFT[stage]["gifts"]:
                for item, amount in expected_gift(gift).items():
                    if 1237801 <= item <= 1237806:
                        materials[item] += amount
                        rift_materials_earned[item] += amount
                    elif item == 1237901:
                        gold += amount
                        rift_gold_receipts += amount
            rift_runs += 1

            for kind in (1, 2):
                if queues[kind] is not None:
                    continue
                eligible_rows = sorted((levels[r["ID"]], r["ID"], r) for r in open_rows
                    if r["BaseType"]["value"] == kind and levels[r["ID"]] < r["LevelLimited"]
                    and eligible(r, levels[r["ID"]] + 1, levels))
                for current, ident, row in eligible_rows:
                    target = current + 1
                    item = tier(target)
                    base_count = 1 + math.ceil(target / 8) if kind == 1 else 2 + math.ceil(target / 7)
                    count = math.ceil(base_count * modifiers["material_cost_multiplier"])
                    base_gold = (500 + 85 * target**1.45) if kind == 1 else (1200 + 140 * target**1.45)
                    cost = round50(base_gold * modifiers["gold_cost_multiplier"])
                    if materials[item] < count or gold < cost:
                        continue
                    materials[item] -= count
                    upgrade_materials_spent[item] += count
                    gold -= cost
                    college_gold_spent += cost
                    time_seconds = min(28800, 300 + 43.2 * target**2) if kind == 1 else min(43200, 900 + 64.8 * target**2)
                    queues[kind] = (now + time_seconds / 3600 * modifiers["build_time_multiplier"], ident)
                    break
            # Match mission duration to login rhythm so energy is spent on
            # existing long missions rather than repeatedly farming 3h tasks.
            mission = {1: EXPLORE[10], 2: EXPLORE[6], 3: EXPLORE[4]}[visits]
            if len(dispatches) < v("queues.explore_slots") and energy >= mission["power_consume"]:
                energy -= mission["power_consume"]
                energy_spent += mission["power_consume"]
                dispatches.append((now + mission["wait_seconds"] / 3600, mission["reward_gift"]))
    return {"preset": preset, "logins_per_day": visits, "days": days,
            "average_building_level": round(sum(levels[i] for i in range(701, 709)) / 8, 2),
            "average_wonder_level": round(sum(levels[i] for i in range(721, 728)) / 7, 2),
            "completed_upgrades": completed_upgrades, "rift_runs_assumed": rift_runs,
            "energy_generated": round(energy_generated, 1), "energy_spent": round(energy_spent, 1),
            "energy_end": round(energy, 1), "dispatches_claimed": completed_dispatches,
            "dispatch_gold_expected": round(dispatch_rewards[1237901], 1),
            "dispatch_reward_vector_expected": {str(k): round(amount, 2) for k, amount in sorted(dispatch_rewards.items())},
            "alchemy_outputs": 0, "washing_actual": 0,
            "washing_potential_ceiling": days * modifiers["washing_cap"],
            "college_gold_receipts": round(college_gold_receipts, 1),
            "college_gold_spent": round(college_gold_spent, 1),
            "college_gold_net": round(college_gold_receipts - college_gold_spent, 1),
            "rift_gold_receipts": round(rift_gold_receipts, 1),
            "external_gold_assumed": external_gold * days,
            "unspent_material_vector": {str(k): round(x, 2) for k, x in sorted(materials.items())},
            "rift_materials_earned": {str(k): round(x, 2) for k, x in sorted(rift_materials_earned.items())},
            "upgrade_materials_spent": {str(k): round(x, 2) for k, x in sorted(upgrade_materials_spent.items())},
            "resource_net_vector": {"college_gold": round(college_gold_receipts - college_gold_spent, 1),
                "energy": round(energy_generated - energy_spent, 1),
                **{str(k): round(materials[k], 2) for k in sorted(materials)}},
            "limitations": "expected gifts; level-60 account; one external gold dungeon/day; 1 Rift run/login; no stamina model; alchemy/training/customers/pray/washing DEFER"}


def dispatch_rates():
    result = []
    for mission in EXPLORE:
        hours = mission["wait_seconds"] / 3600
        rewards = expected_gift(mission["reward_gift"])
        result.append({"id": mission["id"], "hours": hours, "energy": mission["power_consume"],
                       "expected_gold_per_hour": round(rewards[1237901] / hours, 2),
                       "expected_gold_total": round(rewards[1237901], 2),
                       "gold_vs_three_hour_rate": round((rewards[1237901] / hours) /
                           (expected_gift(EXPLORE[0]["reward_gift"])[1237901] / 3), 3)})
    return result


if __name__ == "__main__":
    runs = [simulate(preset, visits, days) for preset in CONFIG["presets"]
            for visits in (1, 2, 3) for days in (1, 7, 30, 90)]
    output = {"status": "PROPOSAL EXPECTATION MODEL; NOT RUNTIME", "runs": runs,
              "dispatch_gold_rates": dispatch_rates(),
              "arbitrage_checks": {
                  "alchemy": "DEFER: Gold/Pay semantics and customer reward loop not known; no modeled profitable loop",
                  "cancellation": "full refund only of unearned inputs; no reward or spent speed card returned",
                  "energy": "warehouse capped at 96; offline accrual bounded by preset hours",
                  "gift": "one official Gift roll per dispatch; no second random roll or multiplier"}}
    (HERE / "simulation_results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    with (HERE / "simulation_summary.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = [key for key in runs[0] if key not in {"dispatch_reward_vector_expected", "unspent_material_vector",
            "rift_materials_earned", "upgrade_materials_spent", "resource_net_vector", "limitations"}]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: r[key] for key in fields} for r in runs)
    print("simulation results written", len(runs), "scenarios")
