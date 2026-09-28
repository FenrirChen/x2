"""Minimal new-player state for the Revival account layer.

The original account backend and its first-login grants are unavailable. These
values are explicit compatibility defaults, never copied from the test save.
"""

from __future__ import annotations
import os


def new_player_snapshot(*, skip_tutorial: bool | None = None) -> dict:
    """Return an independent, legal level-one snapshot for one new account."""
    if skip_tutorial is None:
        skip_tutorial = os.getenv("X2_SKIP_TUTORIAL", "false").lower() == "true"
    return {
        "nickname": "Revival" if skip_tutorial else "", "level": 1, "exp": 0,
        "gold": 0, "crystal": 0, "hero_exp": 0, "equip_exp": 0,
        "show": 1003 if not skip_tutorial else 0,
        "heroes": ([] if skip_tutorial else [{"id": 1003, "state": 2, "level": 1,
            "star": 1, "exp": 0, "equips": [], "compat": "REVIVAL_TUTORIAL"}]),
        "bootstrap_version": 1,
        "tutorial_mode": "skip" if skip_tutorial else "tutorial",
        # RoleExp level 1 gives a 60-point stamina cap. Starting full is a
        # Revival compatibility choice; no other items or heroes are granted.
        "mobility": {"power": 60},
    }
