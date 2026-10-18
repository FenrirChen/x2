"""DropValues policy — USER_DECISION 2026-09-26 and 2026-10-10.

The official per-DropValueID budget values are lost with the official server data
(known_unknowns #1/#2). Revival replaces the former unlimited 27x1,000,000 budget
with a three-tier economy: every AddADCGroup receives the tier's value cap, and
JudgeDropItem (official client code) throttles drops against it.

Tier classification reuses the OFFICIAL SectionTable.DifficultyLevel axis
(E_Difficulty1..10; main-story/unknown sections use 0). It is NOT stamina-derived:
stamina co-varies with difficulty but the tier input is the difficulty ordinal.
Sections without a difficulty level fall back to MID with telemetry.
Approved 2026-10-10: only group 5 on exported eligible sections is overridden
using 100%=3000; official per-section percentages precede a compatibility curve.
Battlepass, unknown difficulty and unconfirmed equipment sources keep the tiers.
Approved 2026-10-18: group 28 adds the four E_Maze element crystals at a fixed
3000 so the weekly element section can hand out its synthesis material.
"""
from __future__ import annotations

import json
from importlib.resources import files

TIER_BUDGETS = {"LOW": 1000, "MID": 3000, "HIGH": 5000}  # USER_DECISION 2026-09-26
LEGACY_GROUP_COUNT = 27
STORY_GROUP_COUNT = 28  # PR12 array; group 27 holds 25 E_Outside rows (13 story/gift).
GROUP_COUNT = 29  # PR 2026-10-18: group 28 holds the four E_Maze element crystals.
STORY_GROUP = 27
STORY_GROUP_BUDGET = 3000  # Approved PR12 replacement; ItemValue is 1.
CRYSTAL_GROUP = 28
CRYSTAL_GROUP_BUDGET = 3000  # Approved 2026-10-18; ItemValue is 12 (≈250 crystals a run).
BEASTLORD_GROUP = 5


class DropBudgetCompatibilityPolicy:
    def __init__(self, difficulty_levels: dict[int, int]):
        # section_id -> official DifficultyLevel (0 = none/unknown)
        self.difficulty_levels = {int(k): int(v) for k, v in (difficulty_levels or {}).items()}
        self.unknown_hits: set[int] = set()
        rules = json.loads(files('x2server').joinpath('data/beastlord_budget_rules.json').read_text(encoding='utf8'))
        self.version = rules['version'] + ':story-28-element-crystal-v1'
        self.beastlord_budgets = {int(key): int(row['budget']) for key, row in rules['sections'].items()}

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
        budgets = [TIER_BUDGETS[tier]] * GROUP_COUNT
        budgets[STORY_GROUP] = STORY_GROUP_BUDGET
        budgets[CRYSTAL_GROUP] = CRYSTAL_GROUP_BUDGET
        section_id = int(section_id)
        if section_id in self.difficulty_levels and section_id in self.beastlord_budgets:
            budgets[BEASTLORD_GROUP] = self.beastlord_budgets[section_id]
        return budgets
