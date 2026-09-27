"""Persistent College base snapshot. Phase 1 only; no production or unlock rules."""

from __future__ import annotations

import json
from importlib.resources import files

from x2server.messages.lobby import BUILDING_BASE_INFO
from .server_clock import ServerClock


def initial_state() -> dict:
    """Copy only initial levels/stars explicitly present in CollegeBuilding."""
    rows = json.loads(files("x2server").joinpath("data/college_initial_buildings.json").read_text(encoding="utf-8"))
    buildings, wonders = [], []
    for row in rows:
        info = {"buildingId": row["id"], "buildingLevel": row["level"]}
        if "star" in row:
            info["buildingStar"] = row["star"]
        (buildings if row["type"] == "building" else wonders).append(info)
    return {"version": 1, "buildings": buildings, "wonders": wonders,
            "star_energy": 0, "warehouse_gold": 0, "extra_power": 0,
            "gold_gain_time": 0, "star_gain_time": 0, "washing_count_day": 0,
            "explore": [], "training": [], "pray": [], "ruins": [],
            "alchemy": {"recipe_exp": [], "customers": [], "production_bars": [],
                        "elements": [], "buff_type": 0, "buff_count": 0}}


class CollegeStateRepository:
    def __init__(self, store, clock=None):
        self.store = store
        self.clock = clock or ServerClock()
        with store.db:
            store.db.execute("""CREATE TABLE IF NOT EXISTS college_state (
                player_id INTEGER PRIMARY KEY REFERENCES players(id),
                version INTEGER NOT NULL, state_json TEXT NOT NULL,
                created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)""")

    def load(self, player_id: int) -> dict:
        now = self.clock.now()
        with self.store.db:
            self.store.db.execute("""INSERT OR IGNORE INTO college_state
                (player_id,version,state_json,created_at,updated_at) VALUES (?,?,?,?,?)""",
                (player_id, 1, json.dumps(initial_state(), sort_keys=True), now, now))
        row = self.store.db.execute("SELECT state_json FROM college_state WHERE player_id=?", (player_id,)).fetchone()
        return json.loads(row[0])

    def save(self, player_id: int, state: dict) -> None:
        if state.get("version") != 1:
            raise ValueError("unsupported college state version")
        with self.store.db:
            cursor = self.store.db.execute("""UPDATE college_state SET state_json=?,updated_at=?
                WHERE player_id=? AND version=1""",
                (json.dumps(state, sort_keys=True), self.clock.now(), player_id))
            if cursor.rowcount != 1:
                raise ValueError("college state missing or version mismatch")

    def growth_base(self, player_id: int) -> dict:
        state = self.load(player_id)
        result = {"buildingList": [BUILDING_BASE_INFO.encode(row) for row in state["buildings"]],
                  "civilization": [BUILDING_BASE_INFO.encode(row) for row in state["wonders"]],
                  "starEnergy": state["star_energy"], "warehouseGold": state["warehouse_gold"],
                  "extraPower": state["extra_power"], "goldGainTime": state["gold_gain_time"],
                  "starGainTime": state["star_gain_time"], "washingCountDay": state["washing_count_day"],
                  "exploreList": state["explore"], "trainingList": state["training"],
                  "prayQueue": state["pray"]}
        return result
