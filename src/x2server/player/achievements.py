"""Persistent native achievements backed by authoritative state and receipts."""
from collections import Counter
import hashlib
from importlib.resources import files
import json
import logging

from x2server.messages.achievements import ACHIEVEMENT_SCHEMAS, ACHV, OVERVIEW
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY


class AchievementService:
    def __init__(self, economy):
        self.economy = economy
        self.store = economy.store
        self.catalog = json.loads(files('x2server').joinpath('data/achievements.json').read_text(encoding='utf-8'))
        self.rows = {int(i): r for i, r in self.catalog['achievements'].items()}
        self.timed_sections = sorted({i for r in self.rows.values() if r['rule']['kind'] == 'timed_clear' for i in r['rule']['ids']})
        from .favor import catalog
        self.initial_favor = {r['HeroID']: r['InitialLevel'] for r in catalog()['favorabilityhero']}
        with self.store.db:
            self.store.db.execute('''CREATE TABLE IF NOT EXISTS achievements (
                player_id INTEGER NOT NULL, achv_id INTEGER NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0, claimed INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(player_id,achv_id))''')
            self.store.db.execute('''CREATE TABLE IF NOT EXISTS achievement_events (
                player_id INTEGER NOT NULL, event_key TEXT NOT NULL,
                event_type INTEGER NOT NULL, amount INTEGER NOT NULL,
                PRIMARY KEY(player_id,event_key))''')
            self.store.db.execute('''CREATE TABLE IF NOT EXISTS achievement_receipts (
                player_id INTEGER NOT NULL, request_key TEXT NOT NULL, response BLOB NOT NULL,
                PRIMARY KEY(player_id,request_key))''')

    def handlers(self):
        return {n: self.handle for n in ACHIEVEMENT_SCHEMAS if n.startswith('C2L_')}

    def record(self, player_id, key, event_type, amount=1):
        if amount <= 0:
            return
        with self.economy.transaction():
            self.store.db.execute('INSERT OR IGNORE INTO achievement_events VALUES (?,?,?,?)',
                                  (player_id, key, event_type, amount))

    def login(self, player_id):
        from .task_calendar import task_period
        day = task_period(1, int(self.economy.clock()))[0]
        self.record(player_id, f'login:{day}', 58)

    def refresh(self, player_id):
        snapshot = self.store.get(player_id)['snapshot']
        heroes = [h for h in snapshot.get('heroes', []) if h.get('state') == 2]
        has_equipment = self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='equipment_instances'").fetchone()
        equipment = self.store.db.execute('SELECT level,star,type_id FROM equipment_instances WHERE player_id=?', (player_id,)).fetchall() if has_equipment else []
        has_college = self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='college_state'").fetchone()
        college_row = self.store.db.execute('SELECT state_json FROM college_state WHERE player_id=?', (player_id,)).fetchone() if has_college else None
        if college_row:
            college = json.loads(college_row[0])
        else:
            from .college import initial_state
            college = initial_state()
        building_levels = {r['buildingId']: r['buildingLevel'] for r in college.get('buildings', []) + college.get('wonders', [])}
        inventory = Counter({r[0]: r[1] for r in self.store.db.execute(
            'SELECT item_id,quantity FROM inventory WHERE player_id=? AND quantity>0', (player_id,))})
        # Socketing moves jewels out of inventory; they are still owned.
        for hero in heroes:
            inventory.update(int(i) for i in hero.get('god_equip', {}).get('jewels', {}).values() if int(i) > 0)
        events = dict(self.store.db.execute('SELECT event_type,SUM(amount) FROM achievement_events WHERE player_id=? GROUP BY event_type', (player_id,)))
        # Reuse previously recorded login-day evidence, without replaying claims.
        days = {r[0].split(':')[1] for r in self.store.db.execute(
            "SELECT event_key FROM achievement_events WHERE player_id=? AND event_type=58 AND event_key LIKE 'login:%'", (player_id,))}
        days.update(r[0].split(':')[2] for r in self.store.db.execute(
            "SELECT event_key FROM economy_events WHERE player_id=? AND event_key LIKE 'challenge:loginday:%'", (player_id,)))
        events[58] = len(days)
        # Existing touch logs are durable and span days; do not count them again as events.
        has_touch = self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='favor_touch_log'").fetchone()
        if has_touch:
            events[19] = self.store.db.execute('SELECT COALESCE(SUM(count),0) FROM favor_touch_log WHERE player_id=?', (player_id,)).fetchone()[0]
        clears = {r[0] for r in self.store.db.execute('SELECT section_id FROM economy_clears WHERE player_id=?', (player_id,))}
        has_battles = self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='battle_checkout_wire'").fetchone()
        timed_clears = {}
        if has_battles:
            from x2server.messages.battle import CHECKOUT, BATTLE_SCHEMAS
            placeholders = ','.join('?' for _ in self.timed_sections)
            for run in self.store.db.execute('''SELECT r.section_id,w.checkout,b.response FROM economy_runs r
                JOIN battle_checkout_wire w ON w.uuid=r.uuid JOIN battle_receipts b ON b.uuid=r.uuid
                WHERE r.player_id=? AND r.settled=1 AND r.section_id IN (''' + placeholders + ')', (player_id, *self.timed_sections)):
                checkout = CHECKOUT.decode(run[1])
                receipt = BATTLE_SCHEMAS['L2C_CheckoutMainMission'].decode(run[2])
                seconds = receipt.get('fightTimeLength', 0)
                if receipt.get('result') == 10 and checkout.get('success') and checkout.get('sectionId') == run[0] and seconds > 0:
                    timed_clears[run[0]] = min(seconds, timed_clears.get(run[0], seconds))
        def favor(h):
            return h.get('favor', {}).get('level', self.initial_favor.get(h['id'], 1))
        with self.economy.transaction():
            for achv_id, row in self.rows.items():
                rule = row['rule']; kind = rule['kind']; minimum = rule.get('minimum', 0)
                progress = 0
                if kind == 'account_level': progress = snapshot['level']
                elif kind == 'login_days': progress = events.get(58, 0)
                elif kind == 'event': progress = events.get(rule['event'], 0)
                elif kind == 'hero_count': progress = len(heroes)
                elif kind in ('hero_level', 'hero_star'): progress = sum(h.get(kind[5:], 0) >= minimum for h in heroes)
                elif kind == 'artifact_star': progress = sum(h.get('god_equip', {}).get('star', 0) >= minimum for h in heroes)
                elif kind == 'favor_count': progress = sum(favor(h) >= minimum for h in heroes)
                elif kind == 'hero_favor': progress = max((favor(h) for h in heroes if h['id'] == rule['hero']), default=0)
                elif kind == 'equipment_count': progress = len(equipment)
                elif kind == 'equipment_level': progress = sum(r[0] >= minimum for r in equipment)
                elif kind == 'equipment_star': progress = sum(r[1] >= minimum for r in equipment)
                elif kind == 'item_count': progress = sum(inventory[i] for i in rule['ids'])
                elif kind == 'building_level': progress = building_levels.get(rule['id'], 0)
                elif kind == 'sections_clear': progress = int(all(i in clears for i in rule['ids']))
                elif kind == 'timed_clear': progress = int(any(0 < timed_clears.get(i, 0) <= rule['seconds'] for i in rule['ids']))
                elif kind in ('equipment_named', 'equipment_set'):
                    parts = [rule['parts'][str(r[2])] for r in equipment if r[1] == 6 and str(r[2]) in rule['parts']]
                    # Six copies of one slot are not a full set.
                    progress = int(len(set(parts)) == 6) if kind == 'equipment_set' else len(parts)
                self.store.db.execute('INSERT OR IGNORE INTO achievements(player_id,achv_id) VALUES (?,?)', (player_id, achv_id))
                # Reaching a condition remains achieved after consuming an item.
                self.store.db.execute('UPDATE achievements SET progress=MAX(progress,?) WHERE player_id=? AND achv_id=?',
                    (min(progress, row['targets'][-1]), player_id, achv_id))

    def states(self, player_id):
        self.refresh(player_id)
        return {r[0]: (r[1], r[2]) for r in self.store.db.execute('SELECT achv_id,progress,claimed FROM achievements WHERE player_id=?', (player_id,)) if r[0] in self.rows}

    def value(self, achv_id, state):
        progress, claimed = state; targets = self.rows[achv_id]['targets']
        stage = min(claimed, len(targets) - 1)
        return {'achvId': achv_id, 'stage': stage, 'achvProgress': progress,
                'status': 2 if claimed == len(targets) else 1 if progress >= targets[stage] else 0}

    def points(self, states, group=None):
        return sum(sum(progress >= t for t in self.rows[i]['targets']) for i, (progress, _) in states.items()
                   if group is None or self.rows[i]['group'] == group)

    def overview(self, player_id, states):
        picked = {int(r[0].split(':')[-1]) for r in self.store.db.execute(
            "SELECT source FROM economy_grants WHERE player_id=? AND source LIKE 'achievement-point:%'", (player_id,))}
        return {'code': 10, 'achvOverViewData': [OVERVIEW.encode({'achvType': g, 'achvProgress': self.points(states, g)}) for g in range(1, 5)],
                'achvPoint': self.points(states), 'achvPointMax': sum(len(r['targets']) for r in self.rows.values()),
                # Native GetOverView indexes every tier: 0 locked, 1 ready, 2 claimed.
                'achvPointRewardList': [2 if i in picked else 1 if self.points(states) >= t else 0
                    for i, t in enumerate(self.catalog['point_targets'])]}

    async def handle(self, context, packet):
        player_id = context.session.player_id
        if player_id is None: raise ProtocolError('achievement request before login')
        name = CORE_MESSAGE_REGISTRY.name_for(packet.message_id)
        req = ACHIEVEMENT_SCHEMAS[name].decode(packet.body); reply = name.replace('C2L_', 'L2C_')
        if name == 'C2L_ReCountAchv':
            # This is a refresh hint, never authority to mint progress or rewards.
            if len(req.get('conditions', [])) > 512 or len(req.get('extras', [])) > 512:
                return OutboundMessage(reply, {'code': 13})
            return OutboundMessage(reply, {'code': 10}, pushes=(self.update(player_id),))
        states = self.states(player_id)
        if name == 'C2L_AchvOverView': return OutboundMessage(reply, self.overview(player_id, states))
        if name == 'C2L_AchvDetialData':
            group = req.get('achvType', 0); start = req.get('startIndex', 0); end = req.get('endIndex', 0)
            values = {'code': 13, 'achvType': group, 'achvDataList': []}
            if group in range(1, 5) and 0 <= start <= end and end - start <= 30:
                # Native GetDetailData treats an absent protobuf list as another
                # full page. Code 97 is its explicit end-of-list branch.
                visible = [i for i, r in sorted(self.rows.items()) if r['group'] == group
                    and (not r['previous'] or states.get(r['previous'], (0, 0))[1] == len(self.rows[r['previous']]['targets']))]
                page=[ACHV.encode(self.value(i, states[i])) for i in visible[start:end]]
                values.update(code=10 if page else 97, achvDataList=page)
            return OutboundMessage(reply, values)
        point = name == 'C2L_AchvPointReward'; field = 'achvPointId' if point else 'achvId'; target = req.get(field, 0 if point else -1)
        values = {'code': 13, field: target, 'status': 0}
        key = hashlib.sha256(f'{context.session.session_id}:{packet.header.request_id}:{name}:'.encode() + packet.body).hexdigest()
        from .economy import UnresolvedEconomy
        try:
            with self.economy.transaction():
                cached = self.store.db.execute('SELECT response FROM achievement_receipts WHERE player_id=? AND request_key=?', (player_id, key)).fetchone()
                if cached:
                    values = ACHIEVEMENT_SCHEMAS[reply].decode(cached[0])
                else:
                    if point:
                        if target not in range(len(self.catalog['point_targets'])) or self.points(states) < self.catalog['point_targets'][target]:
                            return OutboundMessage(reply, values)
                        source = f'achievement-point:{target}'; group = self.catalog['point_gifts'][target]
                    else:
                        if target not in self.rows or self.value(target, states[target])['status'] != 1:
                            return OutboundMessage(reply, values)
                        previous = self.rows[target]['previous']
                        if previous and states[previous][1] != len(self.rows[previous]['targets']): return OutboundMessage(reply, values)
                        stage = states[target][1]; source = f'achievement:{target}:{stage}'; group = self.rows[target]['gifts'][stage]
                    if self.store.db.execute('SELECT 1 FROM economy_grants WHERE player_id=? AND source=?', (player_id, source)).fetchone():
                        return OutboundMessage(reply, values)
                    rewards = self.economy.gifts([group])
                    self.economy._grant(player_id, source, rewards)
                    if not point:
                        self.store.db.execute('UPDATE achievements SET claimed=claimed+1 WHERE player_id=? AND achv_id=?', (player_id, target))
                    values.update(code=10, status=2, rewardData=self.economy.reward_bytes(rewards))
                    self.store.db.execute('INSERT INTO achievement_receipts VALUES (?,?,?)', (player_id, key, ACHIEVEMENT_SCHEMAS[reply].encode(values)))
                    logging.getLogger('x2.achievements').info('achievement claimed player=%s source=%s', player_id, source)
        except UnresolvedEconomy as exc:
            logging.getLogger('x2.achievements').info('achievement rejected player=%s id=%s reason=%s', player_id, target, exc)
            return OutboundMessage(reply, values)
        return OutboundMessage(reply, values, before_response=self.economy.pushes(player_id))

    def update(self, player_id):
        states = self.states(player_id)
        return OutboundMessage('L2C_AchvUpdate', {'achvDataList': [ACHV.encode(self.value(i, s)) for i, s in states.items()],
                                               'achvPoint': self.points(states)})
