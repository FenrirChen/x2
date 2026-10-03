"""DropValues budget policy — REVIVAL_COMPATIBILITY / USER_DECISION 2026-09-26.

The official per-DropValueID budget values are lost with the official server data
(known_unknowns #1/#2). Revival replaces the former unlimited 27x1,000,000 budget
with a three-tier economy: every AddADCGroup receives the tier's value cap, and
JudgeDropItem (official client code) throttles drops against it.

Tier classification reuses the OFFICIAL SectionTable.DifficultyLevel axis
(E_Difficulty1..10; main-story/unknown sections use 0). It is NOT stamina-derived:
stamina co-varies with difficulty but the tier input is the difficulty ordinal.
Sections without a difficulty level fall back to MID with telemetry.
"""
from __future__ import annotations

TIER_BUDGETS = {"LOW": 1000, "MID": 3000, "HIGH": 5000}  # USER_DECISION 2026-09-26
GROUP_COUNT = 27  # official AddADCGroup universe (Section.DroopLimit2 [0..26])


class DropBudgetCompatibilityPolicy:
    def __init__(self, difficulty_levels: dict[int, int]):
        # section_id -> official DifficultyLevel (0 = none/unknown)
        self.difficulty_levels = {int(k): int(v) for k, v in (difficulty_levels or {}).items()}
        self.unknown_hits: set[int] = set()

    def tier_for(self, section_id: int) -> tuple[str, bool]:
        """Returns (tier, known). LOW <=3, MID 4-6, HIGH >=7; 0/unknown -> MID."""
        level = self.difficulty_levels.get(int(section_id), 0)
        if level <= 0:
            self.unknown_hits.add(int(section_id))
            return "MID", False
        if level <= 3:
            return "LOW", True
        if level <= 6:
            return "MID", True
        return "HIGH", True

    def budget_for(self, section_id: int) -> list[int]:
        tier, _ = self.tier_for(section_id)
        return [TIER_BUDGETS[tier]] * GROUP_COUNT
