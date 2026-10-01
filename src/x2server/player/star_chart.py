"""Persistent, client-table star skills and AI energy. No save unlock cheats."""
from functools import lru_cache
from importlib.resources import files
import hashlib
import json
import logging

from x2server.messages.star_chart import STAR_CHART_SCHEMAS, STAR_MAP, STAR_PAIR, STAR_DAILY
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from .economy import UnresolvedEconomy
from .task_calendar import task_period

LOGGER = logging.getLogger('x2.star_chart')


@lru_cache(maxsize=1)
def catalog():
    return json.loads(files('x2server').joinpath('data/star_chart.json').read_text(encoding='utf-8'))


def unlocked(store, player_id):
    if store is None or not store.db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='economy_clears'").fetchone():
        return set()
    clears = {r[0] for r in store.db.execute(
        'SELECT section_id FROM economy_clears WHERE player_id=?', (player_id,))}
    return {r['ID'] for r in catalog()['abilities'] if r['unlock_section'] in clears}


def state(snapshot, now):
    saved = snapshot.get('star_chart', {})
    day = task_period(1, now)[0]
    return {**saved, 'skills': dict(saved.get('skills', {})),
            'points': saved.get('points', 0), 'auto_add': bool(saved.get('auto_add', False)),
            'day': day, 'charge_count': saved.get('charge_count', 0) if saved.get('day') == day else 0}


def skill_level(current, skill_id):
    return current['skills'].get(str(skill_id), 0)


def skill_param(current, skill_id):
    row = next(r for r in catalog()['skills'] if r['SkillID'] == skill_id)
    return row['Param1'][skill_level(current, skill_id)]


def snapshot_fields(store, player_id, snapshot, now):
    current = state(snapshot, now)
    abilities = unlocked(store, player_id)
    allowed_skills = {skill for a in catalog()['abilities'] if a['ID'] in abilities
                      for skill in a.get('SkillID', [])}
    return {'StarMap': STAR_MAP.encode({
        'StarAbility': [STAR_PAIR.encode({'Key': i, 'Value': 1}) for i in sorted(abilities)],
        # Include explicit level zero entries: the client dictionary and its
        # protobuf dirty-field merger must initialize unlearned skills too.
        'StarSkill': [STAR_PAIR.encode({'Key': i, 'Value': skill_level(current, i)})
                      for i in sorted(allowed_skills)],
        'AIPoint': current['points']}),
        'Daily': STAR_DAILY.encode({'AddAIPointCount': current['charge_count']})}


def consume_battle_ai(economy, player_id, section):
    """Consume canonical ContinueFightConsume inside a battle receipt transaction.

    Revival charges at entry when requested, or at checkout if auto battle was
    enabled during the fight. Replayed entry/checkout receipts never spend again.
    """
    row = catalog()['auto_sections'].get(str(section))
    if not row:
        raise UnresolvedEconomy('section has no auto battle')
    cost = row['cost']
    if cost == 0:
        return 0
    store = economy.store
    snapshot = store.get(player_id)['snapshot']
    current = state(snapshot, int(economy.clock()))
    if 39400 not in unlocked(store, player_id):
        raise UnresolvedEconomy('AI ability locked')
    if row['condition'] == 2 and not store.db.execute(
            'SELECT 1 FROM economy_clears WHERE player_id=? AND section_id=?',
            (player_id, section)).fetchone():
        raise UnresolvedEconomy('auto battle requires a previous clear')
    if current['points'] < cost:
        raise UnresolvedEconomy('insufficient AI points')
    current['points'] -= cost
    snapshot['star_chart'] = current
    economy.save_snapshot(player_id, snapshot)
    return cost


class StarChartService:
    def __init__(self, store, economy):
        self.store, self.economy = store, economy
        self.skills = {r['SkillID']: r for r in catalog()['skills']}
        self.owners = {i: a['ID'] for a in catalog()['abilities'] for i in a.get('SkillID', [])}
        with store.db:
            store.db.execute('''CREATE TABLE IF NOT EXISTS star_chart_receipts (
                player_id INTEGER NOT NULL, request_key TEXT NOT NULL, message TEXT NOT NULL,
                response BLOB NOT NULL, PRIMARY KEY(player_id,request_key))''')

    def handlers(self):
        return {name: self.handle for name in STAR_CHART_SCHEMAS if name.startswith('C2L_')}

    def spend(self, player_id, snapshot, costs):
        for item, amount in costs.items():
            if amount < 0:
                raise UnresolvedEconomy('invalid star cost')
            if not amount:
                continue
            currency = self.economy.CURRENCIES.get(item)
            if currency:
                if snapshot.get(currency, 0) < amount:
                    raise UnresolvedEconomy('insufficient star currency')
                snapshot[currency] -= amount
            elif not self.store.db.execute('''UPDATE inventory SET quantity=quantity-?
                    WHERE player_id=? AND item_id=? AND quantity>=?''',
                    (amount, player_id, item, amount)).rowcount:
                raise UnresolvedEconomy('insufficient star item')

    def charge(self, player_id, snapshot, current):
        count = current['charge_count']
        ladder = catalog()['charge_costs']
        if (39400 not in unlocked(self.store, player_id)
                or count >= min(len(ladder), skill_param(current, 394001))
                or current['points'] >= skill_param(current, 394004)):
            raise UnresolvedEconomy('AI charge locked/limit/full')
        cost = max(0, ladder[count] - skill_param(current, 394002))
        self.spend(player_id, snapshot, {1237922: cost})
        current['points'] = min(skill_param(current, 394004),
                                current['points'] + skill_param(current, 394003))
        current['charge_count'] += 1

    async def handle(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError('star chart requested before login')
        from x2server.protocol.registry import CORE_MESSAGE_REGISTRY
        name = CORE_MESSAGE_REGISTRY.name_for(packet.message_id)
        request = STAR_CHART_SCHEMAS[name].decode(packet.body)
        response = name.replace('C2L_', 'L2C_', 1)
        schema = STAR_CHART_SCHEMAS[response]
        key = hashlib.sha256((context.session.session_id + ':' + str(packet.header.request_id)
                              + ':' + name).encode() + packet.body).hexdigest()
        try:
            with self.economy.transaction():
                cached = self.store.db.execute('''SELECT response FROM star_chart_receipts
                    WHERE player_id=? AND request_key=?''', (player_id, key)).fetchone()
                if cached:
                    values = schema.decode(cached[0])
                else:
                    snapshot = self.store.get(player_id)['snapshot']
                    current = state(snapshot, self.economy.clock())
                    abilities = unlocked(self.store, player_id)
                    values = {'code': 10}
                    if name == 'C2L_StarSkillUp':
                        skill = request.get('skillID', 0)
                        target = request.get('targetLevel', 0)
                        row = self.skills.get(skill)
                        level = skill_level(current, skill)
                        if (not row or self.owners.get(skill) not in abilities
                                or target != level + 1 or not 1 <= target <= row['SkillLevel']):
                            raise UnresolvedEconomy('star skill locked/invalid target')
                        ids, nums = row['MaxLevelID'][level]['Items'], row['MaxLevelNum'][level]['Items']
                        if len(ids) != len(nums) or len(set(ids)) != len(ids):
                            raise UnresolvedEconomy('star skill cost unresolved')
                        self.spend(player_id, snapshot, dict(zip(ids, nums)))
                        current['skills'][str(skill)] = target
                        values.update(skillID=skill, targetLevel=target)
                    elif name == 'C2L_AddAIPoint':
                        self.charge(player_id, snapshot, current)
                        values.update(AIPoint=current['points'], AddAIPointCount=current['charge_count'])
                    else:
                        enabled = request.get('open', False)
                        if enabled and (39400 not in abilities or skill_level(current, 394005) < 1):
                            raise UnresolvedEconomy('auto charge skill locked')
                        current['auto_add'] = enabled
                    snapshot['star_chart'] = current
                    self.economy.save_snapshot(player_id, snapshot)
                    self.store.db.execute('INSERT INTO star_chart_receipts VALUES (?,?,?,?)',
                        (player_id, key, response, schema.encode(values)))
        except UnresolvedEconomy as exc:
            LOGGER.info('star request denied player=%s message=%s reason=%s', player_id, name, exc)
            return OutboundMessage(response, {'code': 13})
        LOGGER.info('star request player=%s message=%s result=%s', player_id, name, values)
        # OnStarSkillUp/OnAddAIPoint read NetSyncData inside their response callback.
        return OutboundMessage(response, values, before_response=self.economy.pushes(player_id))
