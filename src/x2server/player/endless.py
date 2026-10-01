"""Client-configured temporal gate entry, durable battle profiles and task rewards."""
import json
import logging
import time
from functools import lru_cache
from importlib.resources import files
from x2server.messages.lobby import LOBBY_SCHEMAS
from x2server.messages.battle import BATTLE_SCHEMAS, FIGHT_PROFILE
from x2server.messages.economy import TASK
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema
from x2server.messages.core import INT_PAIR

PROFILE_CURRENCY = ProtoSchema('ProfileCurrency', tuple(F(i, n, K.INT32) for i, n in
    enumerate(('consumeNum','pickupNum','currentNum','typeId'),1)))
KILLS = ProtoSchema('FightKillMonster', (F(1,'normalMonsterNum',K.INT32), F(2,'bossMonsterNum',K.INT32),
    F(3,'eliteMonsterNum',K.INT32), F(4,'killDetail',K.MESSAGE,repeated=True)))


@lru_cache(maxsize=1)
def catalog():
    return json.loads(files('x2server').joinpath('data/endless.json').read_text(encoding='utf-8'))


class EndlessService:
    def __init__(self, economy):
        self.economy, self.store = economy, economy.store
        self.tasks = {r['EndlessDungeonTaskID']: r for r in catalog()['tasks']}
        with self.store.db:
            self.store.db.execute('CREATE TABLE IF NOT EXISTS endless_task_receipts (player_id INTEGER, request_key TEXT, task_id INTEGER, response BLOB, PRIMARY KEY(player_id,request_key,task_id))')
            self.store.db.execute('''CREATE TABLE IF NOT EXISTS endless_profiles (
                player_id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, section_id INTEGER NOT NULL,
                profile BLOB NOT NULL, updated_at INTEGER NOT NULL)''')
            self.store.db.execute('''CREATE TABLE IF NOT EXISTS endless_tasks (
                player_id INTEGER NOT NULL, task_id INTEGER NOT NULL, progress INTEGER NOT NULL DEFAULT 0,
                claimed INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(player_id,task_id))''')
            self.store.db.execute('''CREATE TABLE IF NOT EXISTS endless_observations (
                player_id INTEGER NOT NULL, run_id TEXT NOT NULL, kind INTEGER NOT NULL,
                value INTEGER NOT NULL, amount INTEGER NOT NULL,
                PRIMARY KEY(player_id,run_id,kind,value))''')

    def handlers(self):
        return {'C2L_CheckFightProfile': self.check_profile}

    async def check_profile(self, context, packet):
        player = context.session.player_id
        if player is None:
            raise ProtocolError('profile query before login')
        req = LOBBY_SCHEMAS['C2L_CheckFightProfile'].decode(packet.body)
        values = {'code': 10, 'isProfileExist': False, 'isProfileValid': False}
        if req.get('profileType') == 2:
            # Both final client seasons point to each other. Original calendar
            # is expired: compatibility keeps the final 2060101 chapter open.
            values.update(weeklyId=2060101, currentWeek=272, sectionId=2110291, layer=0, heroIds=[])
            row = self.store.db.execute('SELECT * FROM endless_profiles WHERE player_id=?', (player,)).fetchone()
            if row and self.active_run(row['run_id'], player):
                profile = FIGHT_PROFILE.decode(row['profile'])
                team = self.store.db.execute('SELECT team_json FROM battle_entries WHERE uuid=?', (row['run_id'],)).fetchone()
                values.update(isProfileExist=True, isProfileValid=True, sectionId=row['section_id'],
                              layer=profile.get('layer', 0), heroIds=json.loads(team[0]) if team else [],
                              weeklyId=self.economy.entry_catalog.sections[row['section_id']]['ChapterID'])
        logging.getLogger('x2.endless').info('temporal gate profile player=%s request=%s response=%s', player, req, values)
        return OutboundMessage('L2C_CheckFightProfile', values)

    def active_run(self, run_id, player):
        return self.store.db.execute('SELECT 1 FROM economy_runs WHERE uuid=? AND player_id=? AND settled=0', (run_id, player)).fetchone()

    def save(self, player, entry, req):
        section = req['missionId']
        if self.economy.entry_catalog.sections[section]['Type'] != 7 or not self.active_run(entry['uuid'], player):
            return
        if not 0 <= req.get('layer', 0) <= 1000 or req.get('sceneId', 0) not in (0, *self.economy.entry_catalog.sections[section]['Maps']):
            raise ValueError('invalid temporal gate layer/map')
        prior = self.store.db.execute('SELECT profile FROM endless_profiles WHERE player_id=? AND run_id=?', (player, entry['uuid'])).fetchone()
        profile = FIGHT_PROFILE.decode(prior[0] if prior else entry['fightDataProfile'])
        if req.get('layer', 0) < profile.get('layer', 0):
            return  # An earlier retried report cannot rewind a newer save.
        profile.update(layer=req.get('layer', 0), isProfileValid=True)
        for source, dest in (('fightTime','passTime'), ('sceneId','sceneId'), ('relicList','relicList'),
                ('randomSeed','randomSeed'), ('monsterRoomList','monsterRoomList'), ('heros','herosProfile'),
                ('currency','currencyProfile'), ('npcData','npcData'), ('buyCount','buyCount'),
                ('dropItem','packProfile'), ('killMonster','killMonster')):
            if source in req:
                profile[dest] = req[source]
        self.store.db.execute('''INSERT INTO endless_profiles VALUES (?,?,?,?,?)
            ON CONFLICT(player_id) DO UPDATE SET run_id=excluded.run_id,section_id=excluded.section_id,
            profile=excluded.profile,updated_at=excluded.updated_at''',
            (player, entry['uuid'], section, FIGHT_PROFILE.encode(profile), int(time.time())))
        self.observe(player, entry['uuid'], 59, section, req.get('layer', 0))
        for raw in req.get('currency', []):
            currency = PROFILE_CURRENCY.decode(raw)
            self.observe(player, entry['uuid'], 38, currency.get('typeId', 0), currency.get('pickupNum', 0))
        kills = KILLS.decode(req.get('killMonster', b''))
        detail = [INT_PAIR.decode(raw) for raw in kills.get('killDetail', [])]
        if len(detail) <= 512 and sum(r.get('Value', 0) for r in detail) <= 100000:
            for row in detail:
                self.observe(player, entry['uuid'], 1, row.get('Key', 0), row.get('Value', 0))

    def observe(self, player, run, kind, value, amount):
        if not 0 <= amount <= 100000:
            return
        old = self.store.db.execute('SELECT amount FROM endless_observations WHERE player_id=? AND run_id=? AND kind=? AND value=?',
                                   (player, run, kind, value)).fetchone()
        delta = max(0, amount - (old[0] if old else 0))
        if not delta:
            return
        self.store.db.execute('''INSERT INTO endless_observations VALUES (?,?,?,?,?)
            ON CONFLICT(player_id,run_id,kind,value) DO UPDATE SET amount=MAX(amount,excluded.amount)''', (player, run, kind, value, amount))
        for task, row in self.tasks.items():
            condition = row['condition']
            if condition['CompleteType']['value'] != kind or condition.get('CompleteValue1', [0]) not in ([0], []) and value not in condition['CompleteValue1']:
                continue
            self.store.db.execute('''INSERT INTO endless_tasks(player_id,task_id,progress) VALUES (?,?,?)
                ON CONFLICT(player_id,task_id) DO UPDATE SET progress=MIN(?,progress+excluded.progress)''',
                (player, task, delta, condition['CompleteNum'][-1]))

    def task_values(self, player, chapter):
        level = self.store.get(player)['snapshot']['level']
        tasks, light = [], 0
        for task, row in self.tasks.items():
            if chapter not in row['ChapterId'] or level < row['AcceptLevel']:
                continue
            state = self.store.db.execute('SELECT progress,claimed FROM endless_tasks WHERE player_id=? AND task_id=?', (player, task)).fetchone()
            progress, claimed = tuple(state) if state else (0, 0)
            targets = row['condition']['CompleteNum']
            stage = min(claimed, len(targets) - 1)
            status = 4 if claimed == len(targets) else 3 if progress >= targets[stage] else 2
            tasks.append(TASK.encode({'taskId': task, 'taskStatus': status, 'taskProgress': min(progress,targets[stage]),
                'stage': stage, 'finishTimes': claimed, 'difficulty': 0}))
            light += sum(row['VomLimit'][:claimed])
        return {'code': 10, 'type': 12, 'chapterId': chapter, 'taskList': tasks,
                'chapterTaskPoint': light, 'chapterTaskTotalPoint': 880}

    def claim(self, player, task, request_key):
        from .economy import UnresolvedEconomy
        values = {'code': 13, 'type': 12, 'taskId': task}
        row = self.tasks.get(task)
        if not row or self.store.get(player)['snapshot']['level'] < row['AcceptLevel']:
            return values
        try:
            with self.economy.transaction():
                from x2server.messages.economy import FINISH_RESULT
                cache = self.store.db.execute('SELECT response FROM endless_task_receipts WHERE player_id=? AND request_key=? AND task_id=?', (player,request_key,task)).fetchone()
                if cache:
                    return FINISH_RESULT.decode(cache[0])
                state = self.store.db.execute('SELECT progress,claimed FROM endless_tasks WHERE player_id=? AND task_id=?', (player,task)).fetchone()
                if not state or state[1] >= len(row['condition']['CompleteNum']) or state[0] < row['condition']['CompleteNum'][state[1]]:
                    return values
                rewards = self.economy.gifts([row['GiftGroup'][state[1]]])
                self.economy._grant(player, f'endless-task:{task}:{state[1]}', rewards)
                self.store.db.execute('UPDATE endless_tasks SET claimed=claimed+1 WHERE player_id=? AND task_id=?', (player,task))
                values.update(code=10, rewardData=self.economy.reward_bytes(rewards))
                self.store.db.execute('INSERT INTO endless_task_receipts VALUES (?,?,?,?)', (player,request_key,task,FINISH_RESULT.encode(values)))
        except UnresolvedEconomy as exc:
            logging.getLogger('x2.endless').info('task claim rejected player=%s task=%s reason=%s', player,task,exc)
        return values
