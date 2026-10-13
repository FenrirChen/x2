"""Terminal heart wishes: official tasks/rewards, user-approved daily policy."""
import hashlib
import json
import logging
import random
import sqlite3
from importlib.resources import files

from x2server.messages.economy import TASK, FINISH_RESULT
from x2server.messages.favor import FAVOR_CHANGE_INFO
from x2server.messages.terminal import TERMINAL_SCHEMAS
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from .favor import FavorService, favor_state
from .task_calendar import task_period

LOGGER = logging.getLogger('x2.terminal.wish')


class TerminalWishService:
    KIND = 6
    LIMIT = 3
    CANDIDATES = 3

    def __init__(self, economy):
        self.e, self.store, self.db = economy, economy.store, economy.store.db
        data = json.loads(files('x2server').joinpath('data/terminal_wish_catalog.json').read_text(encoding='utf-8'))
        self.tasks = {r['TaskID']: r for r in data['tasks']}
        self.conditions = data['conditions']
        self.favor = FavorService(self.store, economy, clock=economy.clock)
        self.rng = random.SystemRandom()
        groups = {r['GiftGroup'] for r in data['gifts']}
        # Use the recovered complete reward rows instead of partial old exports.
        self.e.catalog['gifts'] = [r for r in self.e.catalog['gifts'] if r['GiftGroup'] not in groups] + data['gifts']
        with self.e.transaction():
            self.db.execute('''CREATE TABLE IF NOT EXISTS favor_wish_state (
                player_id INTEGER PRIMARY KEY, day INTEGER NOT NULL, state_json TEXT NOT NULL)''')
            self.db.execute('''CREATE TABLE IF NOT EXISTS favor_wish_events (
                player_id INTEGER NOT NULL, event_key TEXT NOT NULL,
                PRIMARY KEY(player_id,event_key))''')
            self.db.execute('''CREATE TABLE IF NOT EXISTS favor_wish_receipts (
                player_id INTEGER NOT NULL, request_key TEXT NOT NULL, digest TEXT NOT NULL,
                day INTEGER NOT NULL, response TEXT NOT NULL,
                PRIMARY KEY(player_id,request_key))''')

    def day(self):
        return task_period(1, int(self.e.clock()))

    def load(self, pid):
        day, _ = self.day()
        row = self.db.execute('SELECT day,state_json FROM favor_wish_state WHERE player_id=?', (pid,)).fetchone()
        if row and row[0] == day:
            return json.loads(row[1])
        state = {'day': day, 'candidates': [], 'tasks': {}, 'accepted': 0}
        self.save(pid, state)
        return state

    def save(self, pid, state):
        self.db.execute('INSERT OR REPLACE INTO favor_wish_state VALUES (?,?,?)',
                        (pid, state['day'], json.dumps(state, sort_keys=True)))

    def expire_day(self, pid):
        """Used by the existing server midnight watcher, without granting rewards."""
        with self.e.transaction():
            row = self.db.execute('SELECT day FROM favor_wish_state WHERE player_id=?', (pid,)).fetchone()
            if not row or row[0] == self.day()[0]:
                return None
            return OutboundMessage('L2C_GameTask', self.values(self.load(pid)))

    def handlers(self):
        return {'C2L_AcceptFavorTask': self.accept}

    def section_available(self, pid, row, snapshot):
        if not row or not row.get('Maps'):
            return False
        gate = row.get('OpenType', {}).get('value', 0)
        param = row.get('OpenParam', 0)
        if gate == 1 and snapshot['level'] < param:
            return False
        if gate == 2 and param and not self.db.execute('SELECT 1 FROM economy_clears WHERE player_id=? AND section_id=?', (pid, param)).fetchone():
            return False
        if gate not in (0, 1, 2):
            return False
        if row['Type'] == 2:
            # Challenges are chapter-specific. Do not offer a future chapter.
            if row['ChapterID'] > snapshot.get('main_chapter', 2010100):
                return False
        if row['Type'] == 3:
            dungeon = self.e.entry_catalog.daily_section_to_dungeon.get(row['SectionID'])
            if dungeon and row['ChapterID'] == dungeon['ID']:
                index = dungeon['SectionID'].index(row['SectionID'])
                if index and not self.db.execute('SELECT 1 FROM economy_clears WHERE player_id=? AND section_id=?', (pid, dungeon['SectionID'][index-1])).fetchone():
                    return False
        return True

    def eligible(self, pid):
        snapshot = self.store.get(pid)['snapshot']
        heroes = {h['id']: h for h in snapshot.get('heroes', []) if h.get('state') == 2 and h['id'] in self.favor.heroes}
        # Read existing base data only; analysis must not create/unlock ruins.
        college = self.db.execute('SELECT state_json FROM college_state WHERE player_id=?', (pid,)).fetchone() if self.db.execute("SELECT 1 FROM sqlite_master WHERE name='college_state'").fetchone() else None
        base = json.loads(college[0]) if college else {}
        ruins = {r['ruinId'] for r in base.get('ruins', []) if isinstance(r, dict)}
        # 34001 is the official initial ruin, lazily materialized by its query.
        ruins.add(34001)
        eligible = []
        for tid, task in sorted(self.tasks.items()):
            hero = heroes.get(task['HeroID'])
            if not hero:
                continue
            condition = self.conditions[str(task['TaskCondition'])]
            kind = condition['CompleteType']['value']
            values = condition.get('CompleteValue2', [0])
            if kind == 11:
                possible = any(self.section_available(pid, self.e.entry_catalog.sections.get(s), snapshot) for s in values)
            elif kind == 25:
                possible = any(r['Type'] == 2 and r.get('DifficultyLevel', 0) in values and
                               self.section_available(pid, r, snapshot) for r in self.e.entry_catalog.sections.values())
            elif kind == 67:
                possible = snapshot['level'] >= 25 and bool(ruins.intersection(values))
            elif kind == 69:
                from .progression import catalog
                possible = snapshot['level'] >= 25 and hero.get('level', 1) < snapshot['level'] and any(r['level'] == hero.get('level', 1) and r.get('next_level') for r in catalog()['hero_level'])
            elif kind == 68:
                possible = any((self.favor.gifts.get(item, {}).get('EffData') or [0])[0] > 0 and self.db.execute('SELECT 1 FROM inventory WHERE player_id=? AND item_id=? AND quantity>=?',
                               (pid, item, condition['CompleteNum'])).fetchone() for item in values)
            else:
                possible = False
            if possible and condition['CompleteNum'] > 0:
                eligible.append(tid)
        return eligible

    def values(self, state, code=10):
        _, deadline = task_period(1, state['day'])
        rows = []
        ids = sorted(map(int, state['tasks'])) if state['tasks'] else state['candidates']
        for tid in ids:
            task = self.tasks[tid]
            progress = state['tasks'].get(str(tid))
            needed = self.conditions[str(task['TaskCondition'])]['CompleteNum']
            status = (4 if progress['claimed'] else 3 if progress['progress'] >= needed else 2) if progress else 0
            rows.append(TASK.encode({'taskId': tid, 'taskStatus': status,
                'taskProgress': progress['progress'] if progress else 0,
                'taskRefreshTime': deadline, 'finishTimes': int(bool(progress and progress['claimed']))}))
        # FavorWishModule explicitly null-checks taskList, so no fake task id is
        # required for the genuine ungenerated state.
        return {'code': code, 'type': 6, 'taskList': rows, 'chapterId': 0}

    def query(self, context, packet, request):
        try:
            return self._query(context, packet, request)
        except (ValueError, KeyError, TypeError, sqlite3.Error) as exc:
            LOGGER.exception('wish query rolled back player=%s', context.session.player_id)
            return OutboundMessage('L2C_GameTask', {'code': 13, 'type': 6})

    def _query(self, context, packet, request):
        pid = context.session.player_id
        with self.e.transaction():
            state = self.load(pid)
            if self.store.get(pid)['snapshot']['level'] < 20 or request.get('chapterId', 0) or request.get('extraType', 0) not in (0, 1):
                return OutboundMessage('L2C_GameTask', self.values(state, 13))
            if request.get('extraType') == 1 and not state['candidates'] and not state['tasks']:
                key = f'{context.session.session_id}:{packet.header.request_id}:analyse'
                digest = hashlib.sha256(packet.body).hexdigest()
                old = self.db.execute('SELECT digest,day FROM favor_wish_receipts WHERE player_id=? AND request_key=?', (pid, key)).fetchone()
                if old and (old[0] != digest or old[1] != state['day']):
                    return OutboundMessage('L2C_GameTask', self.values(state, 173))
                pool = self.eligible(pid)
                if len(pool) < self.CANDIDATES:
                    LOGGER.info('wish analysis unavailable player=%s eligible=%s', pid, len(pool))
                    return OutboundMessage('L2C_GameTask', self.values(state, 173))
                state['candidates'] = self.rng.sample(pool, self.CANDIDATES)
                self.save(pid, state)
                self.db.execute('INSERT OR IGNORE INTO favor_wish_receipts VALUES (?,?,?,?,?)', (pid, key, digest, state['day'], '{}'))
                LOGGER.info('wish candidates player=%s day=%s tasks=%s', pid, state['day'], state['candidates'])
            return OutboundMessage('L2C_GameTask', self.values(state))

    async def accept(self, context, packet):
        if context.session.player_id is None:
            raise ProtocolError('wish acceptance before login')
        try:
            return await self._accept(context, packet)
        except (ValueError, KeyError, TypeError, sqlite3.Error):
            LOGGER.exception('wish acceptance rolled back player=%s', context.session.player_id)
            return OutboundMessage('L2C_AcceptFavorTask', {'code': 13})

    async def _accept(self, context, packet):
        pid = context.session.player_id
        req = TERMINAL_SCHEMAS['C2L_AcceptFavorTask'].decode(packet.body)
        ids = req.get('taskIds', [])
        key = f'{context.session.session_id}:{packet.header.request_id}:accept'
        digest = hashlib.sha256(packet.body).hexdigest()
        with self.e.transaction():
            state = self.load(pid)
            old = self.db.execute('SELECT digest,day FROM favor_wish_receipts WHERE player_id=? AND request_key=?', (pid, key)).fetchone()
            if old:
                code = 10 if old[0] == digest and old[1] == state['day'] else 13
            elif (req.get('type') != 6 or self.store.get(pid)['snapshot']['level'] < 20
                  or len(ids) != self.CANDIDATES or len(set(ids)) != len(ids)
                  or set(ids) != set(state['candidates']) or state['accepted'] + len(ids) > self.LIMIT
                  or state['tasks']):
                code = 13
            else:
                # Candidates remain stable. Temporary material use/job occupancy
                # between analysis and confirmation does not reroll the batch.
                owned = {h['id'] for h in self.store.get(pid)['snapshot'].get('heroes', []) if h.get('state') == 2}
                if any(self.tasks[tid]['HeroID'] not in owned for tid in ids):
                    code = 13
                else:
                    state['tasks'] = {str(tid): {'progress': 0, 'claimed': False, 'accepted_at': int(self.e.clock())} for tid in ids}
                    state['accepted'] += len(ids)
                    self.save(pid, state)
                    self.db.execute('INSERT INTO favor_wish_receipts VALUES (?,?,?,?,?)', (pid, key, digest, state['day'], '{}'))
                    code = 10
                    LOGGER.info('wish accepted player=%s day=%s tasks=%s', pid, state['day'], ids)
            response = OutboundMessage('L2C_AcceptFavorTask', {'code': code})
            TERMINAL_SCHEMAS[response.message_name].encode(response.values)
            return response

    def event(self, pid, key, kind, value, amount, value2=0):
        if kind not in (11, 25, 67, 68, 69) or amount <= 0:
            return
        with self.e.transaction():
            token = f'{kind}:{value}:{value2}:{key}'
            inserted = self.db.execute('INSERT OR IGNORE INTO favor_wish_events VALUES (?,?)', (pid, token))
            if not inserted.rowcount:
                return
            state = self.load(pid)
            changed = False
            for tid, progress in state['tasks'].items():
                condition = self.conditions[str(self.tasks[int(tid)]['TaskCondition'])]
                if progress['claimed'] or condition['CompleteType']['value'] != kind:
                    continue
                if any(condition.get(field, [0]) not in ([0], []) and observed not in condition[field]
                       for field, observed in (('CompleteValue1', value), ('CompleteValue2', value2))):
                    continue
                progress['progress'] = min(condition['CompleteNum'], progress['progress'] + amount)
                changed = True
            if changed:
                self.save(pid, state)

    def battle(self, pid, run, section):
        row = self.db.execute('SELECT team_json FROM battle_entries WHERE player_id=? AND uuid=?', (pid, run)).fetchone()
        if not row:
            return
        config = self.e.entry_catalog.sections[section]
        for hero in set(json.loads(row[0])):
            self.e._event(pid, 'wish-clear:' + run, 11, hero, 1, section)
            if config['Type'] == 2:
                self.e._event(pid, 'wish-difficulty:' + run, 25, hero, 1, config.get('DifficultyLevel', 0))

    def claim(self, pid, tid, favor_changes=None):
        reject = {'code': 13, 'taskId': tid, 'type': 6}
        try:
            with self.e.transaction():
                state = self.load(pid)
                task = self.tasks.get(tid)
                progress = state['tasks'].get(str(tid))
                if not task or not progress or progress['progress'] < self.conditions[str(task['TaskCondition'])]['CompleteNum']:
                    return reject
                source = f"terminal-wish:{state['day']}:{tid}"
                if progress['claimed']:
                    paid = self.db.execute('SELECT rewards FROM economy_grants WHERE player_id=? AND source=?', (pid, source)).fetchone()
                    if not paid:
                        return reject
                    return {'code': 10, 'taskId': tid, 'type': 6, 'rewardData': self.e.reward_bytes({int(k):v for k,v in json.loads(paid[0]).items()})}
                hero = self.favor._owned(pid, task['HeroID'])
                if not hero:
                    return reject
                rewards = self.e.gifts([task['GiftGroup']])
                # Refuse a broken imported claim history rather than grant
                # favor twice when the item grant is already recorded.
                if self.db.execute('SELECT 1 FROM economy_grants WHERE player_id=? AND source=?', (pid, source)).fetchone():
                    return reject
                self.e._grant(pid, source, rewards)
                snapshot = self.store.get(pid)['snapshot']
                hero = next(h for h in snapshot['heroes'] if h['id'] == task['HeroID'] and h.get('state') == 2)
                favor = favor_state(hero, self.favor.heroes[hero['id']]['InitialLevel']).copy()
                before = dict(favor)
                favor['exp'] += task['FavorabilityGift']
                self.favor._advance(hero['id'], favor, hero.get('favor_breaks', []))
                hero['favor'] = favor
                self.e.save_snapshot(pid, snapshot)
                progress['claimed'] = True
                progress['favor_change'] = {'beforeLevel': before['level'], 'beforeExp': before['exp'],
                    'afterLevel': favor['level'], 'afterExp': favor['exp'], 'heroID': hero['id'], 'type': 1}
                self.save(pid, state)
                self.e._event(pid, source, 72, hero['id'], 1)
                result = {'code': 10, 'taskId': tid, 'type': 6, 'rewardData': self.e.reward_bytes(rewards)}
                FINISH_RESULT.encode(result)
                change = FAVOR_CHANGE_INFO.encode(progress['favor_change'])
                LOGGER.info('wish claimed player=%s day=%s task=%s favor=%s rewards=%s', pid, state['day'], tid, task['FavorabilityGift'], rewards)
            if favor_changes is not None:
                favor_changes.append(change)
            return result
        except (ValueError, KeyError, TypeError, sqlite3.Error) as exc:
            LOGGER.warning('wish claim rolled back player=%s task=%s reason=%s', pid, tid, exc)
            return reject

    def pushes(self, pid):
        with self.e.transaction():
            state = self.load(pid)
            if not state['tasks']:
                return ()
            from .hero import encode_hero_data
            heroes = {t['HeroID'] for tid, t in self.tasks.items() if str(tid) in state['tasks']}
            return (OutboundMessage('L2C_TaskUpdate', {'type': 6, 'taskList': self.values(state)['taskList']}),
                OutboundMessage('L2C_HeroUpdate', {'code': 10, 'heros': [encode_hero_data(h, season=self.e.season, player_id=pid) for h in self.store.get(pid)['snapshot']['heroes'] if h['id'] in heroes]}))
