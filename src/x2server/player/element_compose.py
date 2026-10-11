"""元素合成 (element compose) for 元素之章 (endless weekly) battles.

The client turns three in-stage element crystals (1103006..1103009) into one
product using one of the 64 ordered recipes of the ElementSynthesis table, then
sends ``C2L_ElementCompose`` (495) and waits for ``L2C_ElementCompose`` (496).
With no handler registered the module never fired its callback and the compose
page froze, which also looked like "合成没修".

The crystals live and die inside the battle: they are battle-only items the
account bag never holds, and no client message reports how many were picked. So
this service trusts the picked formula and count, records a per-run tally, and
answers with the produced item. The tally is echoed back through
FightDataProfile (elementExp + formulaCompose) when a mid-battle run is resumed,
which is the only channel the client reads that state from.
"""
from __future__ import annotations

import json
import logging
from importlib.resources import files

from x2server.messages.battle import FIGHT_PROFILE
from x2server.messages.core import INT_PAIR
from x2server.messages.element_compose import ELEMENT_COMPOSE_SCHEMAS
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError

LOGGER = logging.getLogger("x2.battle.element")

# 10 = accepted, 13 = refused; the same pair every other X2 response uses.
OK, REFUSED = 10, 13


class ElementComposeService:
    # The client caps its own selector well below this; the bound only keeps a
    # hostile count from overflowing the per-run tally.
    MAX_COUNT = 999

    def __init__(self, economy):
        self.economy, self.store = economy, economy.store
        catalog = json.loads(
            files("x2server").joinpath("data/element_synthesis.json").read_text(encoding="utf-8"))
        self.formulas = {int(row["id"]): row for row in catalog["formulas"]}
        with self.store.db:
            self.store.db.execute("""CREATE TABLE IF NOT EXISTS battle_element_compose (
                player_id INTEGER NOT NULL, run_uuid TEXT NOT NULL, formula_id INTEGER NOT NULL,
                count INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(player_id,run_uuid,formula_id))""")

    def handlers(self):
        return {"C2L_ElementCompose": self.compose}

    def _active_run(self, player_id: int) -> str:
        row = self.store.db.execute(
            "SELECT uuid FROM economy_runs WHERE player_id=? AND settled=0 ORDER BY rowid DESC LIMIT 1",
            (player_id,)).fetchone()
        return row["uuid"] if row else ""

    async def compose(self, context, packet):
        """Acknowledge one element composition and return the produced item."""
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("element compose before login")
        request = ELEMENT_COMPOSE_SCHEMAS["C2L_ElementCompose"].decode(packet.body)
        formula_id = request.get("elementID", 0)
        count = request.get("count", 0)
        formula = self.formulas.get(formula_id)
        if formula is None or not 0 < count <= self.MAX_COUNT:
            LOGGER.info("element compose refused formula=%s count=%s player=%s",
                        formula_id, count, player_id)
            return OutboundMessage("L2C_ElementCompose", {"code": REFUSED, "count": 0})
        run_uuid = self._active_run(player_id)
        if not run_uuid:
            LOGGER.info("element compose without an active run formula=%s player=%s",
                        formula_id, player_id)
            return OutboundMessage("L2C_ElementCompose", {"code": REFUSED, "count": 0})
        with self.store.db:
            self.store.db.execute("""INSERT INTO battle_element_compose VALUES (?,?,?,?)
                ON CONFLICT(player_id,run_uuid,formula_id) DO UPDATE SET count=count+excluded.count""",
                (player_id, run_uuid, formula_id, count))
        LOGGER.info("element compose player=%s run=%s formula=%s x%s -> item=%s",
                    player_id, run_uuid, formula_id, count, formula["itemId"])
        return OutboundMessage("L2C_ElementCompose", {
            "code": OK, "count": count,
            "composeItem": [INT_PAIR.encode({"Key": formula["itemId"], "Value": count})]})

    def profile_fields(self, player_id: int, run_uuid: str) -> dict:
        """FightDataProfile fields for this run's element compositions."""
        rows = self.store.db.execute(
            "SELECT formula_id, count FROM battle_element_compose WHERE player_id=? AND run_uuid=?",
            (player_id, run_uuid)).fetchall()
        if not rows:
            return {}
        element_exp = sum(self.formulas[r["formula_id"]]["exp"] * r["count"]
                          for r in rows if r["formula_id"] in self.formulas)
        return {"elementExp": element_exp,
                "formulaCompose": [INT_PAIR.encode({"Key": r["formula_id"], "Value": r["count"]})
                                   for r in rows]}

    def refresh_profile(self, player_id: int, run_uuid: str, raw_profile: bytes) -> bytes:
        """Merge the run's element-compose tally into a stored FightDataProfile."""
        fields = self.profile_fields(player_id, run_uuid)
        if not fields:
            return raw_profile
        profile = FIGHT_PROFILE.decode(raw_profile)
        profile.update(fields)
        return FIGHT_PROFILE.encode(profile)