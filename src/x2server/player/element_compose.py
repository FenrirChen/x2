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
while Weekly carries cumulative counts and experience across runs and weeks.
"""
from __future__ import annotations

import json
import hashlib
import logging
from importlib.resources import files
from functools import lru_cache

from x2server.messages.battle import FIGHT_PROFILE
from x2server.messages.core import INT_PAIR
from x2server.messages.element_compose import ELEMENT_COMPOSE_SCHEMAS
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError

LOGGER = logging.getLogger("x2.battle.element")

# 10 = accepted, 13 = refused; the same pair every other X2 response uses.
OK, REFUSED = 10, 13


MAX_WIRE_INT = 2**31 - 1


@lru_cache(maxsize=1)
def formulas():
    data = json.loads(files('x2server').joinpath('data/element_synthesis.json').read_text(encoding='utf8'))
    return {int(row['id']): row for row in data['formulas']}


@lru_cache(maxsize=1)
def endless_sections():
    data = json.loads(files('x2server').joinpath('data/battle_entry_catalog.json').read_text(encoding='utf8'))
    return tuple(row['SectionID'] for row in data['sections'] if row['Type'] == 7)


def cumulative_values(store, player_id):
    """Lifetime confirmed compose history; the ledger is part of full saves.

    Include the current run exactly once. Native InitData reads allComposeTime
    from Weekly and singleComposeTime separately from the current profile; it
    does not add the profile count to the Weekly count again.
    """
    if not store.db.execute("SELECT 1 FROM sqlite_master WHERE name='battle_element_compose'").fetchone():
        rows = []
    else:
        sections = endless_sections()
        slots = ','.join('?' for _ in sections)
        rows = store.db.execute(f"""SELECT c.formula_id, SUM(c.count) FROM battle_element_compose c
            JOIN economy_runs r ON r.uuid=c.run_uuid AND r.player_id=c.player_id
            WHERE c.player_id=? AND c.count BETWEEN 1 AND ? AND r.section_id IN ({slots})
            GROUP BY c.formula_id ORDER BY c.formula_id""", (player_id, MAX_WIRE_INT, *sections)).fetchall()
    known = formulas()
    counts = {fid: min(MAX_WIRE_INT, count) for fid, count in rows if fid in known}
    return {'ElementExpAll': min(MAX_WIRE_INT, sum(known[fid]['exp'] * count for fid, count in counts.items())),
            'FormulaComposeAll': [INT_PAIR.encode({'Key': fid, 'Value': count}) for fid, count in counts.items()]
                or [INT_PAIR.encode({'Key': 0, 'Value': 0})]}


class ElementComposeService:
    # The client caps its own selector well below this; the bound only keeps a
    # hostile count from overflowing the per-run tally.
    MAX_COUNT = 999

    def __init__(self, economy):
        self.economy, self.store = economy, economy.store
        self.formulas = formulas()
        with self.store.db:
            self.store.db.execute("""CREATE TABLE IF NOT EXISTS battle_element_compose (
                player_id INTEGER NOT NULL, run_uuid TEXT NOT NULL, formula_id INTEGER NOT NULL,
                count INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(player_id,run_uuid,formula_id))""")
            self.store.db.execute("""CREATE TABLE IF NOT EXISTS battle_element_compose_receipts (
                player_id INTEGER NOT NULL, request_key TEXT NOT NULL, response BLOB NOT NULL,
                PRIMARY KEY(player_id,request_key))""")

    def handlers(self):
        return {"C2L_ElementCompose": self.compose}

    def _active_run(self, player_id: int, session_id: str) -> str:
        row = self.store.db.execute(
            "SELECT uuid,section_id FROM economy_runs WHERE player_id=? AND session_id=? AND settled=0 ORDER BY rowid DESC LIMIT 1",
            (player_id, session_id)).fetchone()
        if not row:
            return ""
        return row['uuid'] if self.economy.entry_catalog.sections.get(row['section_id'], {}).get('Type') == 7 else ""

    def progress_push(self, player_id):
        from .endless import WEEKLY, weekly_values
        return OutboundMessage('PlayerDataProto', {'Weekly': WEEKLY.encode(
            weekly_values(self.store, player_id, self.economy.clock()))}, data_version=1)

    async def compose(self, context, packet):
        """Acknowledge one element composition and return the produced item."""
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("element compose before login")
        request = ELEMENT_COMPOSE_SCHEMAS["C2L_ElementCompose"].decode(packet.body)
        formula_id = request.get("elementID", 0)
        count = request.get("count", 0)
        key = hashlib.sha256((context.session.session_id + ':' + str(packet.header.request_id)).encode()
                             + packet.body).hexdigest()
        schema = ELEMENT_COMPOSE_SCHEMAS['L2C_ElementCompose']
        cached = self.store.db.execute(
            'SELECT response FROM battle_element_compose_receipts WHERE player_id=? AND request_key=?',
            (player_id, key)).fetchone()
        if cached:
            return OutboundMessage('L2C_ElementCompose', schema.decode(cached[0]),
                                   pushes=(self.progress_push(player_id),))
        formula = self.formulas.get(formula_id)
        if formula is None or not 0 < count <= self.MAX_COUNT:
            LOGGER.info("element compose refused formula=%s count=%s player=%s",
                        formula_id, count, player_id)
            return OutboundMessage("L2C_ElementCompose", {"code": REFUSED, "count": 0})
        # Native MaxComposeNum caps a single operation by ComposeRoundLimit.
        if formula.get('roundLimit') and count > formula['roundLimit']:
            return OutboundMessage('L2C_ElementCompose', {'code': REFUSED, 'count': 0})
        self.economy.endless.ensure_period(player_id)
        run_uuid = self._active_run(player_id, context.session.session_id)
        if not run_uuid:
            LOGGER.info("element compose without an active run formula=%s player=%s",
                        formula_id, player_id)
            return OutboundMessage("L2C_ElementCompose", {"code": REFUSED, "count": 0})
        # Native MaxComposeNum uses numLimit - (allComposeTime - singleComposeTime).
        # The current run is already included in Weekly, so subtract it exactly once.
        if formula.get('numLimit'):
            history = {p['Key']: p['Value'] for raw in cumulative_values(self.store, player_id)['FormulaComposeAll']
                       if (p := INT_PAIR.decode(raw)).get('Key')}
            current = self.store.db.execute('SELECT count FROM battle_element_compose WHERE player_id=? AND run_uuid=? AND formula_id=?',
                                           (player_id, run_uuid, formula_id)).fetchone()
            prior = max(0, history.get(formula_id, 0) - (current[0] if current else 0))
            if count > max(0, formula['numLimit'] - prior):
                return OutboundMessage('L2C_ElementCompose', {'code': REFUSED, 'count': 0})
        values = {'code': OK, 'count': count,
                  'composeItem': [INT_PAIR.encode({'Key': formula['itemId'], 'Value': count})]}
        with self.economy.transaction():
            self.store.db.execute("""INSERT INTO battle_element_compose VALUES (?,?,?,?)
                ON CONFLICT(player_id,run_uuid,formula_id) DO UPDATE SET count=count+excluded.count""",
                (player_id, run_uuid, formula_id, count))
            self.store.db.execute('INSERT INTO battle_element_compose_receipts VALUES (?,?,?)',
                                  (player_id, key, schema.encode(values)))
            self.economy.endless.composed(player_id, run_uuid)
        LOGGER.info("element compose player=%s run=%s formula=%s x%s -> item=%s",
                    player_id, run_uuid, formula_id, count, formula["itemId"])
        return OutboundMessage('L2C_ElementCompose', values, pushes=(self.progress_push(player_id),))

    def settle_grants(self, player_id: int, run_uuid: str, section: int):
        """本局合成的可带出产物, 按 RewardGrant 交给结算入账.

        客户端把合成产物放进 FightItemBag 时 source 是 COMPOSE(3), 而
        SetCheckout_BattleItem 只上报 source==FIGHT(1) 的条目, 所以
        887.outsideItems 里永远看不到合成产物 —— 玩家局内明明拿到了, 结算后
        背包里却没有。这里按 C2L_ElementCompose 自己记下的本局记录补齐: 只发
        useScene==1 (E_Outside) 的产物, E_ReportCurrency 代理 (10/30/60点光能)
        按换算表折成账号光能, 与 outsideItems 同一口径。
        """
        from .economy import EconomyService
        from .reward_system import RewardGrant

        grants = []
        rows = self.store.db.execute(
            "SELECT formula_id, count FROM battle_element_compose WHERE player_id=? AND run_uuid=?",
            (player_id, run_uuid)).fetchall()
        for row in rows:
            formula = self.formulas.get(row['formula_id'])
            count = row['count']
            if formula is None or not 0 < count <= MAX_WIRE_INT:
                continue
            item_id = formula['itemId']
            item = self.economy.items.get(item_id)
            if item is None or item.get('ItemUseScence', {}).get('value') != 1:
                continue
            kind = item.get('ItemType', {}).get('value')
            proxy = (self.economy.report_currency.lookup(item_id)
                     if self.economy.report_currency and kind == 14 else None)
            reason = f'element compose {formula["id"]} x{count}'
            if proxy is not None:
                account_item_id, per_unit = proxy
                grants.append(RewardGrant('REPORT_CURRENCY', section, run_uuid,
                                          account_item_id, per_unit * count, 0, 0, reason=reason))
            elif (item_id in EconomyService.CURRENCIES or item_id == 1237900
                  or kind in EconomyService.STACKABLE_REWARD_TYPES):
                grants.append(RewardGrant('RUNTIME_BATTLE_DROP', section, run_uuid,
                                          item_id, count, 0, 0, reason=reason))
            else:
                LOGGER.info("element compose product %s x%s has no delivery destination",
                            item_id, count)
        return grants

    def profile_fields(self, player_id: int, run_uuid: str) -> dict:
        """FightDataProfile fields for this run's element compositions."""
        rows = self.store.db.execute(
            "SELECT formula_id, count FROM battle_element_compose WHERE player_id=? AND run_uuid=?",
            (player_id, run_uuid)).fetchall()
        rows = [r for r in rows if r['formula_id'] in self.formulas and 0 < r['count'] <= MAX_WIRE_INT]
        if not rows:
            return {}
        element_exp = sum(self.formulas[r["formula_id"]]["exp"] * r["count"]
                          for r in rows if r["formula_id"] in self.formulas)
        return {"elementExp": min(MAX_WIRE_INT, element_exp),
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
