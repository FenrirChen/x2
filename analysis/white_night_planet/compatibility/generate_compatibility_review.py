"""Generate non-runtime College proposal config and per-parameter review sheet."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def p(value, unit, source, reason, confidence="medium", *, constraint="", impact="", sensitivity="medium", evidence="", decision_required=None):
    assert source in {"OFFICIAL", "REVIVAL_COMPATIBILITY", "UNKNOWN"}
    return {"value": value, "unit": unit, "source": source, "reason": reason,
            "confidence": confidence, "official_constraint": constraint,
            "economic_impact": impact, "sensitivity": sensitivity, "evidence": evidence,
            "user_decision_required": (source == "REVIVAL_COMPATIBILITY") if decision_required is None else decision_required}


O = "OFFICIAL"
C = "REVIVAL_COMPATIBILITY"
U = "UNKNOWN"
A = "official_economic_anchors.json"
cfg = {
    "status": p("PROPOSAL / NOT APPROVED / NOT IMPLEMENTED", "status", C, "Review only; no runtime loader", "high"),
    "version": p(1, "schema version", C, "Replaceable policy package", "high"),
    "building": {
        "ordinary_ids": p(list(range(701, 709)), "ids", O, "CollegeBuilding", "high", evidence=A),
        "material_tier_by_target_level": p([[2, 5, 1237801], [6, 10, 1237802], [11, 15, 1237803], [16, 20, 1237804], [21, 25, 1237805], [26, 40, 1237805]], "target-level bands", C, "Five Time Rift tiers map to growth bands; tier 6 reserved for star promotion", constraint="1237801..6 are College upgrade items; static level prerequisites still gate", impact="Time Rift remains meaningful without making rare 6-star material a per-level tax", sensitivity="high", evidence=A),
        "material_count_formula": p("1+ceil(target_level/8)", "items/upgrade", C, "2 at level 2; 5 near level 30", impact="1-2 Time Rift runs per late upgrade", sensitivity="high"),
        "gold_cost_formula": p("round_to_50(500+85*target_level**1.45)", "gold/upgrade", C, "Power growth below exponential", impact="~600 at level 2; ~12k at level 30", sensitivity="high"),
        "time_seconds_formula": p("min(28800,300+43.2*target_level**2)", "seconds/upgrade", C, "Minutes early; 2-8 hours mid/late", impact="Avoids multi-day wall", sensitivity="medium"),
        "prerequisites": p("CollegeLevel.PreconditionType/Value and CollegeStarLevel.LimitLevel", "static rule", O, "Native static gating", "high", evidence=A),
        "queue_slots": p(1, "ordinary build queue", C, "One BuildQueue object in GrowthBase; UI concurrent use still to verify", constraint="BuildQueue message exists", sensitivity="medium"),
    },
    "wonder": {
        "ids": p(list(range(721, 728)), "initial open IDs", O, "728 BuildingOpen missing; do not auto-open", "high", evidence=A),
        "level_material_count_formula": p("2+ceil(target_level/7)", "items/upgrade", C, "Wonder is a separate slower track", sensitivity="high"),
        "level_gold_cost_formula": p("round_to_50(1200+140*target_level**1.45)", "gold/upgrade", C, "Higher than ordinary building without exponential cost", sensitivity="high"),
        "level_time_seconds_formula": p("min(43200,900+64.8*target_level**2)", "seconds/upgrade", C, "15 minutes early, max 12 hours", sensitivity="medium"),
        "star_material_tier": p("target_star", "1237801..6 tier", C, "All six official star materials have a role", constraint="Star caps/LimitLevel from CollegeStarLevel", sensitivity="high", evidence=A),
        "star_material_count": p([2, 3, 3, 2, 2, 1], "items by target star 1..6", C, "6-star drop is rare in fifth Time Rift tier", sensitivity="high", evidence=A),
        "star_gold_cost_formula": p("round_to_50(3000*target_star**1.5)", "gold/star", C, "Milestone sink; no premium currency", sensitivity="high"),
        "queue_slots": p(1, "wonder queue", C, "Separate WonderQueue object", constraint="WonderQueue message exists", sensitivity="medium"),
        "building_728_unlock": p("DEFER", "rule", U, "Missing BuildingOpen and no server unlock sample", "low", evidence=A),
    },
    "star_energy": {
        "rate_per_hour": p(2, "energy/hour", C, "Explore PowerConsume is exactly 2 per hour across all 15 rows", constraint="Explore costs 6..72 for 3..36 hours", impact="Continuous single dispatch roughly consumes generated energy", sensitivity="high", evidence=A),
        "warehouse_cap": p(96, "energy", C, "Covers longest 72-energy dispatch with reserve", impact="No unlimited stockpile", sensitivity="high", evidence=A),
        "offline_accrual_cap_hours": p(24, "hours/logout interval", C, "Once-daily login gets full production; 2/4/8/12 hours would starve long dispatch", impact="Max 48 energy per long absence at base rate", sensitivity="high"),
        "settlement": p("min(cap,current+floor(min(elapsed,offline_cap)*rate))", "server-clock formula", C, "Timestamp only moves forward; settle before cost or grant", sensitivity="high"),
        "building_rate_bonus": p("DEFER", "rule", U, "EffectType links need exact native consumer mapping", "low", evidence=A),
        "power_exchange": p("DEFER", "rule", U, "238/249 conversion rate unknown", "low"),
    },
    "acceleration": {
        "allowed_item_ids": p(list(range(1237831, 1237836)), "item IDs", O, "Item.FunctionEff=E_SpeedUp; descriptions specify building upgrade", "high", evidence=A),
        "seconds_by_item": p({"1237831": 600, "1237832": 3600, "1237833": 7200, "1237834": 14400, "1237835": 28800}, "seconds/card", O, "Item.EffData", "high", evidence=A),
        "policy": p("consume named card; end=max(now,end-card_seconds); no premium-currency fallback", "rule", C, "Use existing obtainable cards, never free bypass", impact="Existing acceleration stock gains purpose", sensitivity="medium"),
        "overflow_carry": p(False, "bool", C, "Card shortens active queue only; no banked negative time", sensitivity="low"),
    },
    "cancel_refund": {
        "recommended_fraction": p(1.0, "fraction of unearned base inputs", C, "No output or completion reward before finish; receipt prevents loop", impact="No progress tax; speed cards already spent are not refunded", sensitivity="medium"),
        "alternatives": p(["0.8 flat", "max(0,1-elapsed/total)"], "candidate rules", C, "80% is a sink; proportional is less predictable", sensitivity="medium"),
        "speed_card_refund": p(False, "bool", C, "Consumed card is a separate completed transaction", sensitivity="medium"),
    },
    "queues": {
        "explore_slots": p(2, "concurrent dispatches", C, "Candidate pending UI-slot verification", impact="Max two timed sources", sensitivity="high"),
        "training_slots": p(2, "concurrent trainees", C, "Candidate pending UI-slot verification", sensitivity="medium"),
        "alchemy_production_positions": p(5, "client positions", O, "591 native handler resets five slots", "high", evidence="phase0_response_audit.md"),
        "alchemy_open_slots": p("DEFER", "count", U, "Which of five positions start open is not proven", "low"),
    },
    "explore": {
        "duration_and_cost": p("CollegeExplore.WaitTimes and PowerConsume", "seconds and energy", O, "15 static rows; 3..36h and 6..72 energy", "high", evidence=A),
        "success_rate": p(1.0, "probability", C, "No failure result rule recovered", impact="Predictable timed return", sensitivity="medium"),
        "reward_policy": p("one weight-normalized resolution of CollegeExplore.Reward Gift; no second roll or multiplier", "rule", C, "Gift weights sum to 1000; current EconomyService.gifts accepts only 100 and cannot be called unchanged", impact="Long missions yield less per hour; convenience is their advantage", sensitivity="high", evidence=A),
        "gift_resolver_gate": p("DEFER until a tested weighted-Gift resolver supports sum=1000 and all reward destinations", "implementation gate", U, "Current daily Gift resolver rejects these weights; no runtime shortcut", "high", evidence="src/x2server/player/economy.py"),
        "hero_occupancy": p("same hero cannot occupy two Explore or Explore+Training", "rule", C, "Prevent duplicate utilization", sensitivity="high"),
        "early_finish": p("DEFER", "rule", U, "Only card/use path should be enabled when proven", "low"),
        "cancel_refund_fraction": p(1.0, "energy fraction", C, "No reward granted on cancel; no server-clock exploit", sensitivity="medium"),
    },
    "training": {
        "duration_seconds": p(14400, "seconds", C, "Four-hour candidate, subject to UI timer and EXP scale audit", sensitivity="medium"),
        "exp_reward": p("DEFER", "hero EXP", U, "No College training reward table or server sample", "low"),
        "cost": p("DEFER", "items/energy", U, "No trustworthy training cost", "low"),
        "occupancy": p("shared hero ledger with Explore", "rule", C, "No simultaneous assignment", sensitivity="high"),
    },
    "alchemy": {
        "recipe_inputs_outputs_time": p("CollegeRecipe.ItemGroup/ItemNum/ProductID/ProductNum/WaitTimes", "static", O, "60 exact recipes", "high", evidence=A),
        "gold_pay_semantics": p("DEFER", "rule", U, "Gold/Pay field roles not proven; never charge/credit from names", "low", evidence=A),
        "recipe_unlock": p("DEFER", "rule", U, "591 initial recipe EXP state missing", "low"),
        "extra_rng": p(False, "bool", C, "Do not roll another result over deterministic ProductID", sensitivity="medium"),
        "economic_value": p("DEFER", "gold-equivalent", U, "ItemValue 9999 for inputs and 1 for outputs is not exchange value", "low", evidence=A),
    },
    "customer": {
        "pool": p("CollegeCustomer 42 rows; CollegeQuest 120 rows", "static", O, "No new NPC or quest IDs", "high", evidence=A),
        "active_positions": p(5, "client positions", O, "591 handler resets five customer positions", "high", evidence="phase0_response_audit.md"),
        "generation_weights": p("DEFER", "weights", U, "No original server frequency or eligibility", "low"),
        "refresh": p("DEFER", "cooldown/free count", U, "Manual-refresh eligibility/cost not proven", "low"),
        "order_reward": p("use CollegeQuest.AwardType/AwardGroup only after exact price/cost validation", "rule", C, "Official rows are 41 Gift, 77 Gold, 2 Buff; validation order is a proposed safeguard", constraint="CollegeQuest.AwardType/AwardGroup", sensitivity="high", evidence=A),
        "client_price_trust": p(False, "bool", C, "Ignore client plusPrice/discountPrice as authority", sensitivity="high"),
    },
    "pray": {
        "static_cost_and_time": p("CollegeBuilding.PrayItem/PrayItemNum/PrayWaitTimes", "static", O, "Wonder rows supply 3000 gold + one 1237840 and 28800 seconds", "high", evidence=A),
        "daily_limit": p("DEFER", "count", U, "No proven original cap", "low"),
        "reward_mapping": p("DEFER", "Gift/fragment map", U, "Description says matching source Hero fragments; exact reward IDs absent", "low"),
    },
    "washing": {
        "cost_options": p("CollegeEquibReset rows 1..5; prefer gold-side Item1 list", "rule", C, "Official table lists gold and crystal alternatives; route preference is a policy choice", constraint="CollegeEquibReset rows 1..5", sensitivity="high", evidence=A),
        "daily_attempt_cap": p(10, "attempts/day", C, "Balanced candidate; compare 5/20/unlimited", impact="Limits random reroll search without pay pressure", sensitivity="high"),
        "affix_generation": p("DEFER; reuse EquipmentInstanceFactory constraints if proven", "rule", U, "Slot-lock and reroll mapping not closed", "low"),
        "crystal_route": p("DEFER", "rule", U, "Avoid premium-currency drain until reviewed", "low"),
    },
    "assist": {
        "policy": p("OUT_OF_SCOPE", "rule", C, "User decision on 2026-09-27: optional social assist is excluded from College implementation", "high", evidence="protocol_matrix.csv; user decision", decision_required=False),
    },
    "daily_reset": {
        "timezone": p("Asia/Shanghai", "IANA zone", C, "Match current Revival daily task and gift calendar", "high", evidence="src/x2server/player/task_calendar.py"),
        "hour": p(0, "local hour", C, "Match current Revival daily task boundary; official College hour unknown", "high", sensitivity="medium"),
        "clock": p("ServerClock", "authority", C, "Never trust client time", "high"),
    },
    "errors": {
        "success_code": p(10, "protocol code", O, "Native 591/623 success comparison", "high", evidence="phase0_response_audit.md"),
        "generic_reject_code": p(13, "protocol code", C, "Existing Revival unsupported/error fallback; exact original per-cause codes unknown", sensitivity="low"),
        "internal_reasons": p(["not_owned", "insufficient", "busy", "not_finished", "already_claimed", "invalid_state", "limit_reached"], "reason labels", C, "Separate validation and logs even if wire maps to generic reject", sensitivity="low"),
    },
    "transaction": {
        "boundary": p("validate -> compute -> debit -> state -> reward -> receipt -> commit -> respond", "SQLite transaction", C, "Cancellation/finish/retry races cannot mint resources", "high"),
    },
    "presets": {
        "CONSERVATIVE": {
            "material_cost_multiplier": p(1.25, "x", C, "Slower material progression", sensitivity="high"),
            "gold_cost_multiplier": p(1.25, "x", C, "Higher gold sink", sensitivity="high"),
            "build_time_multiplier": p(1.3, "x", C, "Longer queues", sensitivity="medium"),
            "energy_rate_per_hour": p(1.5, "energy/hour", C, "Lower dispatch cadence", sensitivity="high"),
            "offline_cap_hours": p(12, "hours", C, "Less idle accrual", sensitivity="high"),
            "washing_cap": p(5, "attempts/day", C, "Restrictive comparison", sensitivity="high")},
        "BALANCED": {
            "material_cost_multiplier": p(1.0, "x", C, "Recommended baseline", sensitivity="high"),
            "gold_cost_multiplier": p(1.0, "x", C, "Recommended baseline", sensitivity="high"),
            "build_time_multiplier": p(1.0, "x", C, "Recommended baseline", sensitivity="medium"),
            "energy_rate_per_hour": p(2.0, "energy/hour", C, "Matches Explore 2 energy/hour", sensitivity="high"),
            "offline_cap_hours": p(24, "hours", C, "Supports once-daily play", sensitivity="high"),
            "washing_cap": p(10, "attempts/day", C, "Recommended candidate", sensitivity="high")},
        "RELAXED": {
            "material_cost_multiplier": p(0.75, "x", C, "Faster collection play", sensitivity="high"),
            "gold_cost_multiplier": p(0.75, "x", C, "Lighter gold sink", sensitivity="high"),
            "build_time_multiplier": p(0.7, "x", C, "Shorter queues", sensitivity="medium"),
            "energy_rate_per_hour": p(3.0, "energy/hour", C, "More dispatch capacity", sensitivity="high"),
            "offline_cap_hours": p(24, "hours", C, "Keep cap bounded", sensitivity="high"),
            "washing_cap": p(20, "attempts/day", C, "Generous reroll ceiling", sensitivity="high")},
    },
}

(ROOT / "college_compatibility_draft.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

with (ROOT / "parameter_review.csv").open("w", encoding="utf-8-sig", newline="") as handle:
    writer = csv.writer(handle)
    writer.writerow(["Domain", "Parameter", "Official Constraint", "Proposed Value", "Unit", "Reason", "Economic Impact", "Sensitivity", "Evidence", "User Decision Required"])
    def visit(prefix, value):
        if isinstance(value, dict) and "source" in value:
            if value["source"] == C and value["user_decision_required"]:
                writer.writerow([prefix.split(".")[0], prefix, value["official_constraint"], json.dumps(value["value"], ensure_ascii=False),
                    value["unit"], value["reason"], value["economic_impact"], value["sensitivity"],
                    value["evidence"], "YES"])
        elif isinstance(value, dict):
            for key, child in value.items():
                visit(f"{prefix}.{key}" if prefix else key, child)
    visit("", cfg)
print("proposal config and review CSV written")
