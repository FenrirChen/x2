"""Section reward source classification and validated client battle drop intake."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import json
from pathlib import Path

from x2server.messages.battle import OUTSIDE_ITEM


@dataclass(frozen=True)
class RewardGrant:
    source: str
    section_id: int
    run_id: str
    item_id: int
    quantity: int
    quality: int = 0
    e_num: int = 0
    official_or_compat: str = "OFFICIAL"
    reason: str = ""


class SectionRewardCatalog:
    def __init__(self):
        target = Path(__file__).resolve().parents[3] / "analysis/reward/section_reward_catalog.json"
        data = json.loads(target.read_text(encoding="utf-8"))
        self.sections = {row["section_id"]: row for row in data["sections"]}
        if len(self.sections) != data["total_sections"]:
            raise ValueError("duplicate Section reward profile")

    def get(self, section_id):
        return self.sections.get(section_id)


def expand_drop_roots(roots, drop_groups):
    """Expand proven DropClass roots; ADC makes the Item allowlist non-strict."""
    direct, nested, seen = set(), set(), set()
    dynamic_adc = False

    def visit(group_id, depth=0, path=()):
        nonlocal dynamic_adc
        if group_id in path:
            raise ValueError(f"cyclic DropClass {group_id}")
        key = (group_id, bool(depth))
        if key in seen:
            return
        seen.add(key)
        group = drop_groups.get(group_id)
        if group is None:
            raise ValueError(f"unknown DropClass {group_id}")
        if group.get("IsADC", {}).get("value") == 1:
            dynamic_adc = True
            return
        for item_id in group.get("ItemList", []):
            if item_id in drop_groups:
                visit(item_id, depth + 1, path + (group_id,))
            elif item_id:
                (nested if depth else direct).add(item_id)

    for group_id in roots:
        visit(group_id)
    return {"direct_items": sorted(direct), "nested_drop_items": sorted(nested),
            "contains_adc": dynamic_adc,
            "mode": "DYNAMIC_ALLOWED" if dynamic_adc else "STRICT_STATIC"}


class RewardCompatibilityPolicy:
    GOLD_DUNGEON_MANUAL_USE_MOP_REWARD = {
        "source": "COMPAT_GOLD_DUNGEON", "official": False,
        "user_authorized": True, "date": "2026-09-25",
        "reason": "Manual gold resource stage uses its own official MopReward gold quantity."
    }

    @classmethod
    def manual_gold(cls, profile, run_id):
        config = profile.get("compat_policy")
        if not config or config.get("policy") != "REVIVAL_COMPAT_GOLD_DUNGEON":
            return None
        return RewardGrant("COMPAT_GOLD_DUNGEON", profile["section_id"], run_id,
                           config["item_id"], config["quantity"],
                           official_or_compat="REVIVAL_COMPAT",
                           reason="official section MopReward quantity; manual-only user policy")


class RuntimeDropResolver:
    MAX_ENTRY_QUANTITY = 100_000
    MAX_TOTAL_QUANTITY = 1_000_000

    def __init__(self, items):
        self.items = items

    def resolve(self, *, run, profile, outside_items, success):
        """Return (deliverable, pending, blocked) without rerolling DropProp."""
        from .economy import EconomyService, UnresolvedEconomy

        if run is None or run["settled"] or run["section_id"] != profile["section_id"]:
            raise UnresolvedEconomy("missing, settled or mismatched battle run")
        if outside_items and not success:
            raise UnresolvedEconomy("failed battle cannot export outsideItems")
        if len(outside_items) > 512:
            raise UnresolvedEconomy("too many outsideItems")
        grants, pending, blocked = [], [], []
        total = 0
        for raw in outside_items:
            item = OUTSIDE_ITEM.decode(raw)
            item_id, quantity = item.get("id"), item.get("num")
            quality, e_num = item.get("quality", 0), item.get("eNum", 0)
            if (type(item_id) is not int or item_id not in self.items or
                    type(quantity) is not int or not 0 < quantity <= self.MAX_ENTRY_QUANTITY or
                    type(quality) is not int or not 0 <= quality <= 2**31 - 1 or
                    type(e_num) is not int or not 0 <= e_num <= 2**31 - 1):
                raise UnresolvedEconomy("invalid outsideItems entry")
            total += quantity
            if total > self.MAX_TOTAL_QUANTITY:
                raise UnresolvedEconomy("outsideItems total exceeds local bound")
            row = self.items[item_id]
            if row.get("ItemUseScence", {}).get("value") != 1:
                raise UnresolvedEconomy(f"battle-only item {item_id} cannot leave battle")
            grant = RewardGrant("RUNTIME_BATTLE_DROP", profile["section_id"], run["uuid"],
                                item_id, quantity, quality, e_num,
                                reason="client FightItemBag outsideItems")
            if profile.get("runtime_allowlist_mode") == "STRICT_STATIC":
                if item_id not in set(profile.get("direct_items", [])) | set(profile.get("nested_drop_items", [])):
                    raise UnresolvedEconomy(f"outside Item {item_id} outside static drop domain")
            elif profile.get("runtime_allowlist_mode") != "DYNAMIC_ALLOWED":
                raise UnresolvedEconomy("unclassified runtime allowlist")
            kind = row.get("ItemType", {}).get("value")
            if item_id in EconomyService.CURRENCIES or item_id == 1237900 or kind in EconomyService.STACKABLE_REWARD_TYPES:
                grants.append(grant)
            else:
                # Preserve exact instance metadata; it is not a delivered item.
                pending.append(grant)
                blocked.append({"item_id": item_id, "reason": "UNRESOLVED_INSTANCE_DELIVERY",
                                "quality": quality, "eNum": e_num})
        return grants, pending, blocked


def sum_grants(grants):
    result = Counter()
    for grant in grants:
        result[grant.item_id] += grant.quantity
    return dict(result)


def audit_grants(grants):
    return [asdict(grant) for grant in grants]
