"""Client-configured temporal gate entry, durable battle profiles and task rewards."""
import json
import logging
import time
from contextlib import nullcontext
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


WEEKLY = ProtoSchema('WeeklyProto', (
    F(1,'EndlessWeekVowOfStone',K.INT32), F(2,'WeeklyRefreshTime',K.INT32),
    F(3,'EndlessWeekMaxVowOfStone',K.INT32), F(4,'EndlessWeekExp',K.INT32),
    F(5,'FormulaComposeAll',K.MESSAGE,repeated=True), F(6,'ElementExpAll',K.INT32),
    F(7,'PassMission',K.MESSAGE,repeated=True), F(8,'MaxWeeklyRefreshTime',K.INT32)))
PERIOD = -38
NAMESPACE = 'endless-week'


def week_start(now):
    # Unix Thursday -> Monday; account calendar is Beijing, 00:00.
    days=(int(now)+8*3600)//86400
    return (days-(days+3)%7)*86400-8*3600


def ensure_week(store,player,now):
    start=week_start(now)
    # Existing activity state is already inside the full save boundary.
    with store.db if not store.db.in_transaction else nullcontext():
        row=store.db.execute('SELECT value FROM activity_state WHERE player_id=? AND period=? AND namespace=? AND state_key=?',
                             (player,PERIOD,NAMESPACE,'state')).fetchone()
        state=json.loads(row[0]) if row else {'week':start,'light':0}
        if state['week']!=start:
            # Cap-upgrade achievements persist; only this week's acquisition/save resets.
            for table in ('endless_profiles',):
                store.db.execute('DELETE FROM '+table+' WHERE player_id=?',(player,))
            store.db.execute('UPDATE economy_runs SET settled=1 WHERE player_id=? AND settled=0 AND section_id IN (2110191,2110192,2110193,2110194,2110291,2110292,2110293,2110294)',(player,))
            state={'week':start,'light':0}
        # Upgrade recovers only confirmed light grants made in this week.
        if not row:
            for source,raw,stamp in store.db.execute('SELECT source,rewards,created_at FROM economy_grants WHERE player_id=? AND created_at>=?',(player,start)):
                if source.startswith('battle:'):
                    run=store.db.execute('SELECT section_id FROM economy_runs WHERE uuid=? AND player_id=?',(source[7:],player)).fetchone()
                    if run and run[0] in (2110191,2110192,2110193,2110194,2110291,2110292,2110293,2110294):
                        state['light']+=json.loads(raw).get('1237913',0)
        if not row or json.loads(row[0])['week']!=start:
            store.db.execute('INSERT INTO activity_state VALUES (?,?,?,?,?) ON CONFLICT(player_id,period,namespace,state_key) DO UPDATE SET value=excluded.value',
                             (player,PERIOD,NAMESPACE,'state',json.dumps(state)))
    return state


def weekly_values(store,player,now):
    ready=store.db.execute("SELECT 1 FROM sqlite_master WHERE name='endless_tasks'").fetchone()
    state=ensure_week(store,player,now) if ready else {'week':week_start(now),'light':0}
    rows={r['EndlessDungeonTaskID']:r for r in catalog()['tasks']}
    bonus=sum(sum(rows[t]['VomLimit'][:n]) for t,n in store.db.execute('SELECT task_id,claimed FROM endless_tasks WHERE player_id=?',(player,)) if t in rows) if ready else 0
    zero=[INT_PAIR.encode({'Key':0,'Value':0})]
    return {'EndlessWeekVowOfStone':state['light'],'WeeklyRefreshTime':state['week'],
            'EndlessWeekMaxVowOfStone':bonus,'MaxWeeklyRefreshTime':state['week'],
            'EndlessWeekExp':0,'ElementExpAll':0,'FormulaComposeAll':zero,'PassMission':zero}


class EndlessService:
    def __init__(self, economy):
        self.economy, self.store = economy, economy.store
        self.tasks = {r['EndlessDungeonTaskID']: r for r in catalog()['tasks']}
        with self.store.db:
            self.store.db.execute('''CREATE TABLE IF NOT EXISTS activity_state (
                player_id INTEGER NOT NULL,period INTEGER NOT NULL,namespace TEXT NOT NULL,
                state_key TEXT NOT NULL,value TEXT NOT NULL,PRIMARY KEY(player_id,period,namespace,state_key))''')
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

    def ensure_period(self,player):
        return ensure_week(self.store,player,self.economy.clock())

    def refresh_week(self,player):
        row=self.store.db.execute('SELECT value FROM activity_state WHERE player_id=? AND period=? AND namespace=? AND state_key=?',
                                  (player,PERIOD,NAMESPACE,'state')).fetchone()
        if row and json.loads(row[0])['week']==week_start(self.economy.clock()):
            return None
        self.ensure_period(player)
        return OutboundMessage('PlayerDataProto',{'Weekly':WEEKLY.encode(weekly_values(self.store,player,self.economy.clock()))},data_version=1)

    def battle_rewards(self,player,source,rewards):
        if not source.startswith('battle:') or not rewards.get(1237913):
            return rewards
        run=source[7:]
        row=self.store.db.execute('SELECT section_id FROM economy_runs WHERE uuid=? AND player_id=?',(run,player)).fetchone()
        if not row or self.economy.entry_catalog.sections.get(row[0],{}).get('Type')!=7:
            return rewards
        state=self.ensure_period(player)
        bonus=weekly_values(self.store,player,self.economy.clock())['EndlessWeekMaxVowOfStone']
        amount=min(rewards[1237913],max(0,880+bonus-state['light']))
        result=dict(rewards)
        result[1237913]=amount
        if not amount:
            del result[1237913]
        state['light']+=amount
        self.store.db.execute('UPDATE activity_state SET value=? WHERE player_id=? AND period=? AND namespace=? AND state_key=?',
                              (json.dumps(state),player,PERIOD,NAMESPACE,'state'))
        self.observe(player,run,38,913,amount)
        return result

    def handlers(self):
        return {'C2L_CheckFightProfile': self.check_profile}

    async def check_profile(self, context, packet):
        player = context.session.player_id
        if player is None:
            raise ProtocolError('profile query before login')
        self.ensure_period(player)
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
        self.ensure_period(player)
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
            self.observe(player, entry['uuid'], 38, currency.get('typeId', 0),
                max(currency.get('pickupNum', 0), currency.get('currentNum', 0) + currency.get('consumeNum', 0)))
        kills = KILLS.decode(req.get('killMonster', b''))
        detail = [INT_PAIR.decode(raw) for raw in kills.get('killDetail', [])]
        if len(detail) <= 512 and sum(r.get('Value', 0) for r in detail) <= 100000:
            for row in detail:
                self.observe(player, entry['uuid'], 1, row.get('Key', 0), row.get('Value', 0))

    def observe(self, player, run, kind, value, amount, value2=0):
        self.ensure_period(player)
        if not 0 <= amount <= 100000:
            return
        matched = []
        for task, row in self.tasks.items():
            condition = row['condition']
            if (condition['CompleteType']['value'] == kind
                    and (condition.get('CompleteValue1', [0]) in ([0], []) or value in condition['CompleteValue1'])
                    and (condition.get('CompleteValue2', [0]) in ([0], []) or value2 in condition['CompleteValue2'])):
                matched.append((task, condition))
        if not matched:
            return
        old = self.store.db.execute('SELECT amount FROM endless_observations WHERE player_id=? AND run_id=? AND kind=? AND value=?',
                                   (player, run, kind, value)).fetchone()
        delta = max(0, amount - (old[0] if old else 0))
        if not delta:
            return
        self.store.db.execute('''INSERT INTO endless_observations VALUES (?,?,?,?,?)
            ON CONFLICT(player_id,run_id,kind,value) DO UPDATE SET amount=MAX(amount,excluded.amount)''', (player, run, kind, value, amount))
        for task, condition in matched:
            self.store.db.execute('''INSERT INTO endless_tasks(player_id,task_id,progress) VALUES (?,?,?)
                ON CONFLICT(player_id,task_id) DO UPDATE SET progress=MIN(?,progress+excluded.progress)''',
                (player, task, delta, condition['CompleteNum'][-1]))

    def completed(self, player, run, section, team):
        if self.economy.entry_catalog.sections.get(section, {}).get('Type') != 7:
            return
        self.observe(player, run, 63, section, 1, len(set(team)))

    def composed(self, player, run):
        section = self.store.db.execute('SELECT section_id FROM economy_runs WHERE uuid=? AND player_id=?',
                                        (run, player)).fetchone()
        if not section or self.economy.entry_catalog.sections.get(section[0], {}).get('Type') != 7:
            return
        fields = self.economy.element_compose.profile_fields(player, run)
        from x2server.messages.core import INT_PAIR
        count = sum(INT_PAIR.decode(raw).get('Value', 0) for raw in fields.get('formulaCompose', []))
        self.observe(player, run, 61, 0, count)
        self.observe(player, run, 65, 0, fields.get('elementExp', 0))

    def task_values(self, player, chapter):
        self.repair(player)
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
                'chapterTaskPoint': light, 'chapterTaskTotalPoint': sum(sum(r['VomLimit']) for r in self.tasks.values())}

    def repair(self, player):
        """Rebuild omitted events from server compose rows and saved checkouts."""
        from x2server.messages.battle import CHECKOUT, PROFILE_HERO
        self.ensure_period(player)
        marker='endless-repair-v3'
        with self.economy.transaction():
            if self.store.db.execute("SELECT 1 FROM economy_events WHERE player_id=? AND event_key=?", (player,marker)).fetchone():
                return
            if not self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='battle_entries'").fetchone():
                return
            for source,raw in self.store.db.execute('SELECT source,rewards FROM economy_grants WHERE player_id=?',(player,)).fetchall():
                if source.startswith('battle:'):
                    run=self.store.db.execute('SELECT section_id FROM economy_runs WHERE uuid=? AND player_id=?',(source[7:],player)).fetchone()
                    if run and self.economy.entry_catalog.sections.get(run[0],{}).get('Type')==7:
                        self.observe(player,source[7:],38,913,json.loads(raw).get('1237913',0))
            for row in self.store.db.execute('SELECT DISTINCT c.run_uuid FROM battle_element_compose c JOIN battle_entries e ON e.uuid=c.run_uuid WHERE c.player_id=?', (player,)).fetchall():
                self.composed(player, row[0])
            if not self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='battle_checkout_wire'").fetchone():
                return
            for run, section, team, raw, reply in self.store.db.execute('''
                SELECT e.uuid,n.section_id,e.team_json,w.checkout,r.response FROM battle_entries e
                JOIN economy_runs n ON n.uuid=e.uuid AND n.player_id=e.player_id
                JOIN battle_checkout_wire w ON w.uuid=e.uuid JOIN battle_receipts r ON r.uuid=e.uuid
                WHERE e.player_id=? AND e.section_type=7''', (player,)).fetchall():
                result = BATTLE_SCHEMAS['L2C_CheckoutMainMission'].decode(reply)
                if result.get('result') != 10:
                    continue
                request = CHECKOUT.decode(raw)
                counts = {}
                for raw_detail in KILLS.decode(request.get('killMonster', b'')).get('killDetail', [])[:512]:
                    detail = INT_PAIR.decode(raw_detail)
                    if 0 < detail.get('Value', 0) <= 10000:
                        unit = detail.get('Key', 0)
                        counts[unit] = counts.get(unit, 0) + detail['Value']
                if sum(counts.values()) <= 100000:
                    for unit, count in counts.items():
                        self.observe(player, run, 1, unit, count)
                if not result.get('success'):
                    continue
                survivors = {h.get('heroId') for h in map(PROFILE_HERO.decode, request.get('heros', []))
                             if h.get('state', 0) == 0} & set(json.loads(team))
                self.completed(player, run, section, survivors)
            if self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='fight_drop_observations'").fetchone():
                for run, section, raw in self.store.db.execute('''SELECT o.uuid,n.section_id,o.body FROM fight_drop_observations o
                    JOIN economy_runs n ON n.uuid=o.uuid AND n.player_id=o.player_id
                    WHERE o.player_id=? AND n.section_type=7''', (player,)).fetchall():
                    report = BATTLE_SCHEMAS['C2L_FightDropData'].decode(raw)
                    self.observe(player, run, 59, section, report.get('layer', 0))
                    for raw_currency in report.get('currency', []):
                        currency = PROFILE_CURRENCY.decode(raw_currency)
                        self.observe(player, run, 38, currency.get('typeId', 0),
                            max(currency.get('pickupNum', 0), currency.get('currentNum', 0) + currency.get('consumeNum', 0)))
                    for raw_detail in KILLS.decode(report.get('killMonster', b'')).get('killDetail', [])[:512]:
                        detail = INT_PAIR.decode(raw_detail)
                        self.observe(player, run, 1, detail.get('Key', 0), detail.get('Value', 0))
            self.store.db.execute("INSERT OR IGNORE INTO economy_events VALUES (?, ?)", (player,marker))

    def claim(self, player, task, request_key):
        from .economy import UnresolvedEconomy
        values = {'code': 13, 'type': 12, 'taskId': task}
        row = self.tasks.get(task)
        if not row or self.store.get(player)['snapshot']['level'] < row['AcceptLevel']:
            return values
        self.repair(player)
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
