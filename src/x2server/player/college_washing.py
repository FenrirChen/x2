"""Native 1055-1058 washing: paid previews, protected affixes and atomic saves.

Costs/count bounds/gates are recovered from 2.4. Value selection uses the
existing Revival equipment factory's documented compatibility distribution.
"""
import hashlib
import json
import logging
import random
import sqlite3
import uuid
from collections import Counter
from importlib.resources import files

from x2server.messages.college import COLLEGE_SCHEMAS
from x2server.messages.equipment import EQUIP_PARAM, HERO_EQUIP
from x2server.network.dispatcher import OutboundMessage
from .equipment import EquipmentService
from .equipment_factory import EquipmentInstanceFactory, weighted_choice_index, roll_value_sec
from .task_calendar import task_period

LOGGER = logging.getLogger('x2.college.washing')


def settle_washing_day(state, now):
    day = task_period(1, now)[0]
    if state.get('washing_day') != day:
        state['washing_day'], state['washing_count_day'] = day, 0


class WashingDenied(ValueError):
    def __init__(self, code=13):
        self.code = code


class CollegeWashingService:
    FLOWS = ('WashingRoomRandomAttri', 'WashingRoomOpt')

    def __init__(self, repo, economy, upgrades):
        self.repo, self.economy, self.upgrades = repo, economy, upgrades
        self.db = repo.store.db
        self.equipment = EquipmentService(repo.store, economy)
        self.factory = EquipmentInstanceFactory(rng=random.SystemRandom())
        self.rules = json.loads(files('x2server').joinpath('data/college_washing.json').read_text(encoding='utf-8'))
        self.cost_rows = {r['ID']: r for r in self.rules['costs']}
        with repo.transaction():
            self.db.execute('''CREATE TABLE IF NOT EXISTS college_washing_pending (
                player_id INTEGER PRIMARY KEY, equip_id INTEGER NOT NULL,
                fingerprint TEXT NOT NULL, candidate TEXT NOT NULL, session_id TEXT NOT NULL)''')
            self.db.execute('''CREATE TABLE IF NOT EXISTS college_washing_receipts (
                player_id INTEGER NOT NULL, receipt_key TEXT NOT NULL, digest TEXT NOT NULL,
                equip_id INTEGER NOT NULL, response TEXT NOT NULL,
                PRIMARY KEY(player_id,receipt_key))''')

    def row(self, pid, eid):
        row = self.db.execute('SELECT id,type_id,star,level,exp,param FROM equipment_instances '
                              'WHERE player_id=? AND id=?', (pid, eid)).fetchone()
        if row is None:
            raise WashingDenied()
        return dict(zip(('id', 'type_id', 'star', 'level', 'exp', 'param'), row))

    @staticmethod
    def fingerprint(row):
        return json.dumps([row['star'], row['level'], row['exp'], json.loads(row['param'])], sort_keys=True)

    def roll(self, star, src, kind):
        ladder = self.factory._attr_ladder(star, src, kind)
        return roll_value_sec(*ladder, self.factory.rng)

    def monthcard(self, pid, now):
        if not self.db.execute("SELECT 1 FROM sqlite_master WHERE name='gift_package_claims'").fetchone():
            return False
        row = self.db.execute('SELECT MAX(claimed_at) FROM gift_package_claims WHERE player_id=? AND package_id=2700001', (pid,)).fetchone()
        return bool(row and row[0] is not None and
                    0 <= (task_period(1, now)[0] - task_period(1, row[0])[0]) // 86400 < 30)

    def costs(self, pid, state, op, param):
        count = state['washing_count_day']
        limit = self.rules['daily_limits'][int(self.monthcard(pid, self.repo.clock.now()))]
        column = 1 if count < limit else 2
        row = self.cost_rows[op]
        discount = self.repo.catalog.effect(state, 708, 20)[0]
        locks = sum(bool(param.get(f'lock{s}')) for s in range(1, 7))
        rates = self.rules['lock_rates']
        factor = rates[min(locks, len(rates)-1)] if op in (2, 5) else 1000
        costs = Counter()
        for item, num in zip(row[f'Item{column}'], row[f'Num{column}'], strict=True):
            costs[item] += (num * discount * factor + 999999) // 1000000
        return costs

    def bonuses(self, pid, row):
        bonuses = Counter()
        growth = self.db.execute('SELECT growth_value FROM equipment_main_growth WHERE player_id=? AND equip_id=?', (pid, row['id'])).fetchone()
        if growth:
            bonuses[1] = growth[0] * row['level']
        for slot, value in self.db.execute('SELECT attribute_slot,bonus FROM equipment_enhancements WHERE player_id=? AND equip_id=?', (pid, row['id'])):
            bonuses[slot] += value
        # Migrated/seeded equipment can predate the growth ledgers. Preserve
        # its existing enhancement contribution rather than silently rolling
        # a levelled item as level zero. For incomplete history, infer the
        # nearest legal initial tier; no bonus is written to account gear.
        param = json.loads(row['param'])
        for slot in range(1, 7):
            kind = param.get(f'at{slot}', 0)
            if kind:
                ladder, _ = self.factory._attr_ladder(row['star'], '0' if slot == 1 else '2', kind)
                value = param.get(f'av{slot}', 0)
                estimated = value - bonuses[slot]
                base = min(ladder, key=lambda initial: abs(initial-estimated))
                bonuses[slot] = value-base
        return bonuses

    def apply(self, pid, state, flow, req, session):
        eid = req.get('equipID', 0)
        row = self.row(pid, eid)
        stored_param = json.loads(row['param'])
        param = {f'{kind}{s}': int(stored_param.get(f'{kind}{s}', 0))
                 for s in range(1, 7) for kind in ('at', 'av', 'lock')}
        star = row['star']
        self.factory.validate(row['type_id'], star, 1)
        preview = flow == 'WashingRoomRandomAttri'
        op = 5 if preview else req.get('opt', 0)
        if op not in range(1, 6):
            raise WashingDenied()
        allowed = self.repo.catalog.effect(state, 708, 12, star=True)
        if op not in allowed:
            raise WashingDenied(57)
        pending = self.db.execute('SELECT fingerprint,candidate,session_id FROM college_washing_pending WHERE player_id=? AND equip_id=?', (pid, eid)).fetchone()
        fingerprint = self.fingerprint(row)
        result = {'code': 10, 'param': param}
        if not preview and op == 5:
            if not pending or pending[0] != fingerprint or req.get('equipParam'):
                raise WashingDenied()
            param = json.loads(pending[1])
        elif preview and pending and pending[0] == fingerprint and pending[2] != session:
            # Resuming the last paid preview in a new session is free. A new
            # preview in the same session is the native ReWash action.
            self.db.execute('UPDATE college_washing_pending SET session_id=? WHERE player_id=?', (session, pid))
            result['param'] = json.loads(pending[1])
            return result
        else:
            minors = [s for s in range(2, 7) if param[f'at{s}']]
            counts = self.factory.data['minor_count_tiers'][str(star)]
            if op == 1:
                if len(minors) >= counts['max']:
                    raise WashingDenied()
                base = self.factory.data['equib_base'][str(row['type_id'])]
                used = {param[f'at{s}'] for s in minors}
                choices = [(t, w) for t, w in zip(base['minor_attr_type'], base['minor_attr_chance'], strict=True) if t not in used]
                if not choices:
                    raise WashingDenied()
                kinds, weights = map(list, zip(*choices))
                kind = kinds[weighted_choice_index(kinds, weights, self.factory.rng)]
                slot = next(s for s in range(2, 7) if not param[f'at{s}'])
                param[f'at{slot}'], param[f'av{slot}'] = kind, self.roll(star, '2', kind)
            elif op == 2:
                candidates = [s for s in minors if not param[f'lock{s}']]
                if len(minors) <= counts['base'] or not candidates:
                    raise WashingDenied()
                removed = self.factory.rng.choice(candidates)
                survivors = [s for s in minors if s != removed]
                original = dict(param)
                for s in range(2, 7):
                    for kind in ('at', 'av', 'lock'):
                        param[f'{kind}{s}'] = 0
                self.db.execute('DELETE FROM equipment_enhancements WHERE player_id=? AND equip_id=? AND attribute_slot=?', (pid, eid, removed))
                for target, old in enumerate(survivors, 2):
                    for kind in ('at', 'av', 'lock'):
                        param[f'{kind}{target}'] = original[f'{kind}{old}']
                    if old != target:
                        self.db.execute('UPDATE equipment_enhancements SET attribute_slot=? WHERE player_id=? AND equip_id=? AND attribute_slot=?', (target, pid, eid, old))
            elif op == 3:
                requested = EQUIP_PARAM.decode(req.get('equipParam', b''))
                if any(requested.get(f'{k}{s}', 0) != param[f'{k}{s}'] for s in range(1, 7) for k in ('at', 'av')):
                    raise WashingDenied()
                locks = [requested.get(f'lock{s}', 0) for s in range(1, 7)]
                if (any(v not in (0, 1) for v in locks) or sum(locks) > self.rules['lock_limit']
                        or any(v and not param[f'at{s}'] for s, v in enumerate(locks, 1))
                        or sum(v != param[f'lock{s}'] for s, v in enumerate(locks, 1)) != 1):
                    raise WashingDenied()
                param.update({f'lock{s}': v for s, v in enumerate(locks, 1)})
            elif op == 4:
                if row['level'] <= 0:
                    raise WashingDenied()
                bonuses = self.bonuses(pid, row)
                for s in range(1, 7):
                    kind = param[f'at{s}']
                    if not kind:
                        continue
                    ladder, _ = self.factory._attr_ladder(star, '0' if s == 1 else '2', kind)
                    initial = param[f'av{s}'] - bonuses[s]
                    # Old imported gear may predate enhancement ledgers. Use
                    # the nearest legal initial tier, never retain growth at 0.
                    param[f'av{s}'] = min(ladder, key=lambda value: abs(value-initial))
                exp = self.equipment.exp_costs[row['level']]
                # Reset keeps the item: do not grant its intrinsic soul value
                # or the dismantle-only star multiplier. Apply the recovered
                # loss curve to invested soul, capped at that investment.
                invested = exp['cumulative_exp']
                refund = min(invested, max(0, invested * (1000-exp['loss_exp']) // 1000))
                result['rewards'] = {1237906: refund} if refund else {}
            elif preview:
                if not any(param[f'at{s}'] and not param[f'lock{s}'] for s in range(1, 7)):
                    raise WashingDenied()
                bonuses = self.bonuses(pid, row)
                for s in range(1, 7):
                    if param[f'at{s}'] and not param[f'lock{s}']:
                        param[f'av{s}'] = self.roll(star, '0' if s == 1 else '2', param[f'at{s}']) + bonuses[s]
            snapshot = self.repo.store.get(pid)['snapshot']
            # Delete/lock have changed local param; expenses refer to the
            # original lock count shown by the native confirmation window.
            costs = self.costs(pid, state, op, stored_param)
            code = self.upgrades._charge(pid, snapshot, costs)
            if code != 10:
                raise WashingDenied(code)
            state['washing_count_day'] += 1
        result['param'] = param
        if preview:
            self.db.execute('INSERT OR REPLACE INTO college_washing_pending VALUES (?,?,?,?,?)',
                            (pid, eid, fingerprint, json.dumps(param, sort_keys=True), session))
        else:
            self.db.execute('DELETE FROM college_washing_pending WHERE player_id=? AND equip_id=?', (pid, eid))
            self.db.execute('UPDATE equipment_instances SET param=? WHERE player_id=? AND id=?', (json.dumps(param, sort_keys=True), pid, eid))
            if op == 4:
                self.db.execute('UPDATE equipment_instances SET level=0,exp=0 WHERE player_id=? AND id=?', (pid, eid))
                for table in ('equipment_enhancements', 'equipment_main_growth'):
                    self.db.execute(f'DELETE FROM {table} WHERE player_id=? AND equip_id=?', (pid, eid))
                if result.get('rewards'):
                    self.economy._grant(pid, 'washing-reset:' + uuid.uuid4().hex, result['rewards'])
                    result['rewardData'] = self.economy.reward_bytes(result['rewards']).hex()
                result.pop('rewards', None)
        return result

    def handle(self, context, packet, flow, req):
        pid, eid = context.session.player_id, req.get('equipID', 0)
        session = context.session.session_id
        key = f'{session}:{packet.header.request_id}:{flow}'
        digest = hashlib.sha256(packet.body).hexdigest()
        try:
            with self.repo.transaction():
                state = self.repo.load(pid)
                self.repo.settle(state)
                self.row(pid, eid)
                cached = self.db.execute('SELECT digest,equip_id,response FROM college_washing_receipts WHERE player_id=? AND receipt_key=?', (pid, key)).fetchone()
                if cached:
                    if cached[0] != digest or cached[1] != eid:
                        raise WashingDenied()
                    values = json.loads(cached[2])
                    values['washingCountDay'] = state['washing_count_day']
                else:
                    values = self.apply(pid, state, flow, req, session)
                    values['washingCountDay'] = state['washing_count_day']
                    # Encode before commit; any invalid wire result rolls back
                    # costs, preview, refund, equipment, count and receipt.
                    COLLEGE_SCHEMAS['L2C_' + flow].encode(self.wire(values, req))
                    self.db.execute('INSERT INTO college_washing_receipts VALUES (?,?,?,?,?)', (pid, key, digest, eid, json.dumps(values)))
                self.repo.save(pid, state)
                changed = next(raw for raw in self.equipment.values(pid)['equip'] if HERO_EQUIP.decode(raw)['id'] == eid)
                before = (OutboundMessage('L2C_EquipUpdate', {'code': 10, 'equip': [changed]}),
                          OutboundMessage('L2C_QueryGrowthBase', self.repo.growth_base(pid)), *self.economy.pushes(pid))
                for message in before:
                    from x2server.messages.core import CORE_SCHEMAS
                    CORE_SCHEMAS[message.message_name].encode(message.values)
            return OutboundMessage('L2C_' + flow, self.wire(values, req), before_response=before)
        except (WashingDenied, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
            code = exc.code if isinstance(exc, WashingDenied) else 13
            LOGGER.warning('washing refused player=%s equip=%s flow=%s opt=%s code=%s reason=%s', pid, eid, flow, req.get('opt'), code, exc)
            return OutboundMessage('L2C_' + flow, self.wire({'code': code}, req))

    @staticmethod
    def wire(values, req):
        result = {**values, 'equipID': req.get('equipID', 0)}
        if 'opt' in req:
            result['opt'] = req['opt']
        if 'param' in result:
            result['equipParam'] = EQUIP_PARAM.encode(result.pop('param'))
        if 'rewardData' in result:
            result['rewardData'] = bytes.fromhex(result['rewardData'])
        return result
