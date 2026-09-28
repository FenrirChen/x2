"""Minimal new-player state for the Revival account layer.

The original account backend and its first-login grants are unavailable. These
values are explicit compatibility defaults, never copied from the test save.
"""

from __future__ import annotations


def new_player_snapshot() -> dict:
    """Return an independent, legal level-one snapshot for one new account."""
    return {
        "nickname": "Revival", "level": 1, "exp": 0,
        "gold": 0, "crystal": 0, "hero_exp": 0, "equip_exp": 0,
        "show": 0, "heroes": [],
        # RoleExp level 1 gives a 60-point stamina cap. Starting full is a
        # Revival compatibility choice; no other items or heroes are granted.
        "mobility": {"power": 60},
    }
