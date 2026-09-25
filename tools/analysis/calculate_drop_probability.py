"""Calculate conditional, pre-limit DropProp item probabilities from recovered ARM64 rules.

This does not represent authoritative server drops or Section.DropValueID.
IsADC groups depend on the active Section, TableMgr.mDCTable and item limits;
they are deliberately rejected instead of filled with invented probabilities.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import json
from pathlib import Path

X2 = Path(__file__).resolve().parents[3]
TABLES = X2 / "analysis/drop_archaeology/full_tables"


class UnresolvedDropAlgorithm(ValueError):
    pass


def read_records(table: str) -> list[dict]:
    return json.loads((TABLES / f"{table}.json").read_text(encoding="utf-8"))["records"]


def source_tables():
    groups = {row["DropClass"]: row for row in read_records("dropprop")}
    items = {row["ItemID"]: row for row in read_records("item")}
    names = {row["Key"]: row.get("Chinese", "") for row in read_records("language")}
    return groups, items, names


def marginal(group_id: int, item_id: int, groups: dict, items: dict,
             path: tuple[int, ...] = ()) -> tuple[Fraction, Fraction]:
    """Return (E[pre-limit ItemStruct count], P(no such ItemStruct))."""
    if group_id in path:
        raise UnresolvedDropAlgorithm(f"recursive cycle at {group_id}")
    group = groups.get(group_id)
    if group is None:
        raise UnresolvedDropAlgorithm(f"unknown DropClass {group_id}")
    if group.get("IsADC", {}).get("value") == 1:
        raise UnresolvedDropAlgorithm(f"IsADC group {group_id} requires battle context")
    candidates, weights = group.get("ItemList", []), group.get("Prob", [])
    if len(candidates) != len(weights):
        raise UnresolvedDropAlgorithm(f"ItemList/Prob length mismatch at {group_id}")
    if any(type(weight) is not int or weight < 0 for weight in weights):
        raise UnresolvedDropAlgorithm(f"invalid Prob at {group_id}")

    def child(candidate: int) -> tuple[Fraction, Fraction]:
        if candidate in groups:
            return marginal(candidate, item_id, groups, items, path + (group_id,))
        if candidate in items:
            return (Fraction(1), Fraction(0)) if candidate == item_id else (Fraction(0), Fraction(1))
        if candidate == 0:
            return Fraction(0), Fraction(1)
        raise UnresolvedDropAlgorithm(f"unknown ItemList value {candidate} in {group_id}")

    picks = group.get("Picks", 0)
    if picks < 0:
        # ARM64 tests only the sign. Every Prob[i] is a deterministic repetition
        # count; the magnitude of the negative Picks value is not consulted.
        expected, no_item = Fraction(0), Fraction(1)
        for candidate, count in zip(candidates, weights):
            child_expected, child_no_item = child(candidate)
            expected += count * child_expected
            no_item *= child_no_item ** count
        return expected, no_item
    if picks == 0:
        return Fraction(0), Fraction(1)
    no_drop = group.get("NoDrop", 0)
    if type(no_drop) is not int or no_drop < 0:
        raise UnresolvedDropAlgorithm(f"invalid NoDrop at {group_id}")
    total = no_drop + sum(weights)
    if total <= 0:
        raise UnresolvedDropAlgorithm(f"zero draw weight at {group_id}")
    weighted_expectation, weighted_no_item = Fraction(0), Fraction(no_drop)
    for candidate, weight in zip(candidates, weights):
        child_expected, child_no_item = child(candidate)
        weighted_expectation += weight * child_expected
        weighted_no_item += weight * child_no_item
    return picks * weighted_expectation / total, (weighted_no_item / total) ** picks


def descendant_items(group_id: int, groups: dict, items: dict,
                     path: tuple[int, ...] = ()) -> set[int]:
    if group_id in path:
        raise UnresolvedDropAlgorithm(f"recursive cycle at {group_id}")
    group = groups[group_id]
    if group.get("IsADC", {}).get("value") == 1:
        raise UnresolvedDropAlgorithm(f"IsADC group {group_id} requires battle context")
    result: set[int] = set()
    for candidate in group.get("ItemList", []):
        if candidate in groups:
            result |= descendant_items(candidate, groups, items, path + (group_id,))
        elif candidate in items:
            result.add(candidate)
        elif candidate != 0:
            raise UnresolvedDropAlgorithm(f"unknown ItemList value {candidate} in {group_id}")
    return result


def calculate(group_id: int, groups: dict, items: dict, names: dict) -> dict:
    item_ids = sorted(descendant_items(group_id, groups, items))
    rows = []
    for item_id in item_ids:
        expected, no_item = marginal(group_id, item_id, groups, items)
        probability = 1 - no_item
        name_id = items[item_id].get("NameID")
        name = names.get(name_id) if name_id else None
        # The current extracted language table contains replacement glyphs for
        # some entries; do not present corrupted bytes as verified item names.
        if name and "\ufffd" in name:
            name = None
        rows.append({"item_id": item_id, "name": name,
                     "expected_quantity": str(expected), "expected_count": str(expected),
                     "p_at_least_one": str(probability),
                     "p_at_least_one_decimal": float(probability)})
    return {"drop_class": group_id, "scope": "STATIC_CONDITIONAL_PROBABILITY_PRE_LIMIT",
            "notes": ["One direct successful pick emits ItemStruct.num=1.",
                      "Excludes CheckItemLimit, JudgeDropItem, pickup, Section.DropValueID and server policy."],
            "items": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("drop_class", type=int)
    args = parser.parse_args()
    groups, items, names = source_tables()
    try:
        result = calculate(args.drop_class, groups, items, names)
    except (UnresolvedDropAlgorithm, KeyError) as exc:
        result = {"drop_class": args.drop_class,
                  "scope": "STATIC_CONDITIONAL_PROBABILITY_UNAVAILABLE", "blocker": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
