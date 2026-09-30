"""Section reward source classification and validated client battle drop intake."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import json
import logging
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
    """2026-09-26: the gold-dungeon manual-play MopReward compat was removed —
    manual gold now comes from E_ReportCurrency pouch conversion (superseded,
    see docs/history/SUPERSEDED_KNOWLEDGE.md)."""


class ReportCurrencyResolver:
    """E_ReportCurrency (FunctionEff=14) battle proxies -> account currency.

    Official semantics: these items are battle-internal currency representatives
    (EffData=[currencyBucket, perUnitValue], no Icon/name by design); the settlement
    converts them into the account currency instead of granting them as items.
    The bucket->account-item mapping is table-derived (the E_Currency Item whose
    EffData==[bucket]); unknown buckets are never guessed (parked upstream).
    """

    def __init__(self, data):
        data = data or {}
        # item_id -> {"bucket", "per_unit", "account_item_id"}
        self.mapping = {int(k): v for k, v in (data.get("items") or {}).items()}
        # proxies the export could not resolve to an account currency: park, never guess
        self.unresolvable = {int(k) for k in (data.get("unresolvable") or [])}

    def lookup(self, item_id):
        entry = self.mapping.get(item_id)
        if not entry:
            return None
        return entry["account_item_id"], entry["per_unit"]


class RuntimeDropResolver:
    MAX_ENTRY_QUANTITY = 100_000
    MAX_TOTAL_QUANTITY = 1_000_000
    EQUIP_MAX_ENTRY_QUANTITY = 99

    def __init__(self, items, equipment_types=None, report_currency=None):
        self.items = items
        # callable item_id -> bool: part-level equib with a canonical EquibBase row
        self.equipment_types = equipment_types
        # ReportCurrencyResolver: E_ReportCurrency proxies -> account currency
        self.report_currency = report_currency

    def resolve(self, *, run, profile, outside_items, success):
        """Return (deliverable, pending, blocked, equipment) without rerolling DropProp.

        Equipment outsideItems (ItemType E_Equip with a canonical EquibBase row) are
        NOT delivered as stackable grants nor parked as pending: the client's drop
        pipeline already fixed (TypeId, Star), so they are returned as specs for
        EquipmentInstanceFactory. Star must be in the official 1..6 band.
        """
        from .economy import EconomyService, UnresolvedEconomy

        if run is None or run["settled"] or run["section_id"] != profile["section_id"]:
            raise UnresolvedEconomy("missing, settled or mismatched battle run")
        if outside_items and not success:
            # A quit/lost run still reports its in-run items (局内商店 purchases,
            # picked drops). Acknowledge the run end but grant none of them: the
            # client clears its own in-stage counters at settlement.
            logging.getLogger("x2.rewards").info(
                "failed run section=%s keeps %d outsideItems ungranted",
                profile["section_id"], len(outside_items))
            outside_items = []
        if len(outside_items) > 512:
            raise UnresolvedEconomy("too many outsideItems")
        grants, pending, blocked, equipment = [], [], [], []
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
            if self.report_currency and kind == 14 and item_id in self.report_currency.mapping:
                # E_ReportCurrency proxy: convert to the account currency instead of
                # granting the faceless item (official settlement semantics).
                account_item_id, per_unit = self.report_currency.lookup(item_id)
                grants.append(RewardGrant("REPORT_CURRENCY", profile["section_id"], run["uuid"],
                                          account_item_id, per_unit * quantity, 0, e_num,
                                          reason=f"proxy {item_id} x{quantity}"))
            elif (self.report_currency and kind == 14
                  and item_id in self.report_currency.unresolvable):
                pending.append(grant)
                blocked.append({"item_id": item_id, "reason": "UNRESOLVED_REPORT_CURRENCY",
                                "quality": quality, "eNum": e_num})
            elif item_id in EconomyService.CURRENCIES or item_id == 1237900 or kind in EconomyService.STACKABLE_REWARD_TYPES:
                grants.append(grant)
            elif kind == 10 and self.equipment_types and self.equipment_types(item_id):
                if not 1 <= quality <= 6 or not 0 < quantity <= self.EQUIP_MAX_ENTRY_QUANTITY:
                    raise UnresolvedEconomy(f"equipment outsideItem {item_id} has illegal star/quantity")
                equipment.append({"item_id": item_id, "quantity": quantity, "quality": quality})
            else:
                # Preserve exact instance metadata; it is not a delivered item.
                pending.append(grant)
                blocked.append({"item_id": item_id, "reason": "UNRESOLVED_INSTANCE_DELIVERY",
                                "quality": quality, "eNum": e_num})
        return grants, pending, blocked, equipment


def sum_grants(grants):
    result = Counter()
    for grant in grants:
        result[grant.item_id] += grant.quantity
    return dict(result)


def audit_grants(grants):
    return [asdict(grant) for grant in grants]
