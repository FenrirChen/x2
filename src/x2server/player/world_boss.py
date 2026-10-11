"""Persistent exploration and player-owned daily Boss sessions for 时序之门."""
import asyncio
import hashlib
import json
import logging
import os
import secrets
import time
import weakref
from collections import Counter
from functools import lru_cache
from importlib.resources import files

from x2server.messages.world_boss import (WORLD_BOSS_SCHEMAS as W, SEARCH, SLOT,
    CONTAINER, INT_CONTAINER, QUESTION, QUESTION_EVENT, BOSS, BOSS_PLAYER, PLAYER, INFO, DAILY)
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY
from x2server.protocol.errors import ProtocolError

LOG = logging.getLogger('x2.world_boss')

@lru_cache(maxsize=1)
def catalog():
    return json.loads(files('x2server').joinpath('data/world_boss.json').read_text(encoding='utf-8'))

def day(now):
    return (int(now)+8*3600)//86400


def personal_monster_level(store, player):
    level = max(1, min(100, int(store.get(player)['snapshot']['level'])))
    return 10 if level < 30 else level // 10 * 10

def account_state(store, player, now):
    row = store.db.execute('SELECT day,state FROM world_boss_accounts WHERE player_id=?', (player,)).fetchone()
    if row and row['day'] == day(now):
        state=json.loads(row['state'])
        # Admission alone is not proof that the client entered combat.
        # Reconstruct only acknowledged battles, including after a relog.
        counts=store.db.execute('''SELECT b.type_id,count(*) n FROM world_boss_members m
            JOIN world_boss_runs b USING(boss_id) WHERE m.player_id=? AND m.charged=1
            AND b.group_id=? GROUP BY b.type_id''',(player,str(day(now)))).fetchall()
        state['world_challenges']=sum(r['n'] for r in counts if r['type_id']<2040200)
        state['normal_challenges']=sum(r['n'] for r in counts if r['type_id']>=2040200)
        return state
    return {'searches':0, 'world_challenges':0, 'normal_challenges':0, 'final':False, 'slots':[]}

def snapshot_fields(store, player, now):
    if store is None or not store.db.execute("SELECT 1 FROM sqlite_master WHERE name='world_boss_accounts'").fetchone():
        return {}, b''
    state = account_state(store, player, now)
    slots, questions, events, bosses = [], [], [], []
    for index, slot in enumerate(state['slots']):
        slots.append(CONTAINER.encode({'idx':index, 'val':SLOT.encode({
            'Event':slot['event'] if not slot.get('done') else 0, 'Value':slot['value']})}))
        if 'questions' in slot:
            questions.append(CONTAINER.encode({'idx':index, 'val':QUESTION.encode({
                'Step':slot['step'], 'Question':[INT_CONTAINER.encode({'idx':i,'val':q}) for i,q in enumerate(slot['questions'])]})}))
        if 'choice' in slot:
            events.append(CONTAINER.encode({'idx':index, 'val':QUESTION_EVENT.encode({
                'ID':slot['value'], 'Event':slot['choice'], 'Value':slot['choice_value']})}))
        if 'boss' in slot:
            row = store.db.execute('SELECT * FROM world_boss_runs WHERE boss_id=?',(slot['boss'],)).fetchone()
            if row:
                member = store.db.execute('SELECT damage FROM world_boss_members WHERE boss_id=? AND player_id=?',(slot['boss'],player)).fetchone()
                bosses.append(CONTAINER.encode({'idx':index,'val':BOSS.encode({
                    'BossID':slot.get('ticket',row['boss_id']),'ID':row['type_id'],'Group':row['group_id'],'Start':row['created'],
                    'State':row['state'],'FinderId':row['finder'],'FinderName':row['finder_name'],
                    'World':int(row['type_id']<2040200),'StateFinishTime':row['finish'],
                    'MaxHP':row['max_hp'],'CurHP':row['hp'],'JoinPlayerNum':0,'Level':row['monster_level'],
                    'SelfPlayer':BOSS_PLAYER.encode({'Name':store.get(player)['snapshot']['nickname'],
                        'Damage':member[0] if member else 0,'Order':1 if member else 0})})}))
    return {'WorldBossSearch':SEARCH.encode({'Slots':slots,'WorldBoss':bosses,
        'WorldBossQuestion':questions,'WorldBossQuestionEvent':events})}, DAILY.encode({
            # IsFinalBoxAward (0x136f2a0) tests UsedExploreTimes > TotalExploreTimes.
            'WorldBossSearchTimes':state['searches']+int(state['final']),'WorldBossChallengeTimes':state['world_challenges'],
            'NormalBossChallengeTimes':state['normal_challenges']})

class WorldBossService:
    def __init__(self, economy):
        self.economy, self.store = economy, economy.store
        data = catalog()
        self.activity = data['activity']
        self.policy = data['compatibility']
        self.bosses = {r['BossID']:r for r in data['bosses']}
        self.explore = {r.get('EventType',{}).get('value',0):r for r in data['explore']}
        self.events = {r['EventID']:r for r in data['events']}
        self.answers = {r['QaID']:r for r in data['answers']}
        self.boxes = {r['BoxID']:r for r in data['boxes']}
        self.mail_templates = {r['id']:r for r in data['mail_templates']}
        self.map_levels=json.loads(files('x2server').joinpath('data/battle_monster_levels.json').read_text(encoding='utf-8'))['levels']
        self.identity = None
        self.clients = {}
        self.lobby_sessions = {}
        self.radar_sent = {}
        with self.store.db:
            from .mail import ensure_mail_schema
            ensure_mail_schema(self.store.db)
            self.store.db.execute('CREATE TABLE IF NOT EXISTS world_boss_accounts (player_id INTEGER PRIMARY KEY,day INTEGER NOT NULL,state TEXT NOT NULL)')
            self.store.db.execute('''CREATE TABLE IF NOT EXISTS world_boss_runs (
                boss_id TEXT PRIMARY KEY,type_id INTEGER NOT NULL,group_id TEXT NOT NULL,created INTEGER NOT NULL,
                state INTEGER NOT NULL,finish INTEGER NOT NULL,max_hp INTEGER NOT NULL,hp INTEGER NOT NULL,
                finder INTEGER NOT NULL,finder_name TEXT NOT NULL)''')
            if 'monster_level' not in {r[1] for r in self.store.db.execute('PRAGMA table_info(world_boss_runs)')}:
                self.store.db.execute('ALTER TABLE world_boss_runs ADD COLUMN monster_level INTEGER NOT NULL DEFAULT 30')
            self.store.db.execute('''CREATE TABLE IF NOT EXISTS world_boss_members (
                boss_id TEXT NOT NULL,player_id INTEGER NOT NULL,team TEXT NOT NULL DEFAULT '[]',
                damage INTEGER NOT NULL DEFAULT 0,active INTEGER NOT NULL DEFAULT 0,run_id TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(boss_id,player_id))''')
            columns={r[1] for r in self.store.db.execute('PRAGMA table_info(world_boss_members)')}
            if 'retry_at' not in columns:
                self.store.db.execute('ALTER TABLE world_boss_members ADD COLUMN retry_at INTEGER NOT NULL DEFAULT 0')
            if 'charged' not in columns:
                self.store.db.execute('ALTER TABLE world_boss_members ADD COLUMN charged INTEGER NOT NULL DEFAULT 0')
            if 'combat_confirmed' not in columns:
                self.store.db.execute('ALTER TABLE world_boss_members ADD COLUMN combat_confirmed INTEGER NOT NULL DEFAULT 0')
                # Code migration repairs tickets spent by previous admission-
                # only versions. Preserve real battles using persisted evidence.
                self.store.db.execute('UPDATE world_boss_members SET charged=0')
                tables={r[0] for r in self.store.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                for table in ('fight_drop_observations','battle_receipts'):
                    if table in tables:
                        self.store.db.execute(f'''UPDATE world_boss_members SET charged=1,combat_confirmed=1
                            WHERE EXISTS (SELECT 1 FROM {table} r WHERE r.uuid=world_boss_members.run_id)''')
                self.store.db.execute('UPDATE world_boss_members SET charged=1,combat_confirmed=1 WHERE damage>0')
            self.store.db.execute('''CREATE TABLE IF NOT EXISTS world_boss_days (
                day INTEGER PRIMARY KEY,boss_id TEXT NOT NULL UNIQUE,type_id INTEGER NOT NULL)''')
            self.store.db.execute('''CREATE TABLE IF NOT EXISTS world_boss_player_days (
                player_id INTEGER NOT NULL,day INTEGER NOT NULL,boss_id TEXT NOT NULL UNIQUE,
                type_id INTEGER NOT NULL,PRIMARY KEY(player_id,day))''')
            self.store.db.execute('''CREATE TABLE IF NOT EXISTS world_boss_tickets (
                ticket TEXT PRIMARY KEY,boss_id TEXT NOT NULL,player_id INTEGER NOT NULL,
                UNIQUE(boss_id,player_id))''')
            self.store.db.execute('''CREATE TABLE IF NOT EXISTS world_boss_receipts (
                player_id INTEGER NOT NULL,request_key TEXT NOT NULL,response_name TEXT NOT NULL,response BLOB NOT NULL,
                PRIMARY KEY(player_id,request_key))''')

    def now(self):
        return int(self.economy.clock())

    def client_id(self, boss_id, player):
        row=self.store.db.execute('SELECT ticket FROM world_boss_tickets WHERE boss_id=? AND player_id=?',(boss_id,player)).fetchone()
        if row:
            return row[0]
        ticket=secrets.token_urlsafe(32)
        self.store.db.execute('INSERT INTO world_boss_tickets VALUES (?,?,?)',(ticket,boss_id,player))
        return ticket

    def internal_id(self, boss_id):
        row=self.store.db.execute('SELECT boss_id FROM world_boss_tickets WHERE ticket=?',(boss_id,)).fetchone()
        return row[0] if row else boss_id

    def handlers(self):
        return {n:self.handle for n in W if n.startswith(('C2L_','C2W_'))}

    def save(self, player, state):
        self.store.db.execute('INSERT INTO world_boss_accounts VALUES (?,?,?) ON CONFLICT(player_id) DO UPDATE SET day=excluded.day,state=excluded.state',
            (player,day(self.now()),json.dumps(state,ensure_ascii=False)))

    def rewards(self, player, source, group, multiplier=1):
        rewards = self.economy.gifts([group], allow_daily_random=True)
        rewards = {i:n*multiplier for i,n in rewards.items() if n*multiplier>0}
        return self.economy.reward_bytes(self.economy._grant(player,source,rewards))

    def slot(self, state, index):
        if type(index) is not int or not 0<=index<len(state['slots']):
            raise ValueError('invalid slot')
        return state['slots'][index]

    def choice(self, player, state, req, key):
        index, answer = req.get('slotIdx',0), req.get('aOrb',0)
        slot = self.slot(state,index)
        if slot.get('done') or 'choice' in slot or answer not in (0,1):
            raise ValueError('choice already resolved/invalid')
        event = self.events[slot['value']]
        # OnClickBtnA/OnClickBtnB send 0/1 (0x136892c / 0x1368a44).
        kind = event.get(f'AnswerType{answer+1}',{}).get('value',0)
        value = event.get(f'AnswerParam{answer+1}',0)
        slot.update(choice=kind,choice_value=value)
        reward = b''
        if kind == 1:
            if value not in self.boxes:
                raise ValueError('unknown box')
        elif kind == 2:
            pool = [r['QaID'] for r in self.answers.values() if r['QaType']==value]
            if not pool:
                raise ValueError('missing question pool')
            count = min(len(pool),self.explore[3]['AnswerLimitNumber'])
            questions = []
            for _ in range(count):
                questions.append(pool.pop(secrets.randbelow(len(pool))))
            slot.update(questions=questions,step=0)
        elif kind == 3:
            reward = self.rewards(player,key,self.boxes[value]['BoxReward'])
            slot['done'] = True
        else:
            raise ValueError('unsupported event branch')
        return {'code':10,'slotIdx':index,'rewardData':reward}

    def letter(self, player, state, req, key):
        index, step, answer = req.get('slotIdx',0),req.get('questIdx',0),req.get('answerIdx',0)
        slot = self.slot(state,index)
        if slot.get('done') or 'questions' not in slot or step != slot['step'] or not 0<=step<len(slot['questions']):
            raise ValueError('stale/invalid question')
        question = self.answers[slot['questions'][step]]
        # RandomSortAnwser 0x14dfbdc stores 0..N-1 in ContentIndex.
        if not 0<=answer<len(question['AnswerName']):
            raise ValueError('invalid answer')
        reward = self.rewards(player,key,question['AnswerReward'][answer],question['RewardNum'][answer])
        slot['step']+=1
        slot['done']=slot['step']==len(slot['questions'])
        return {'code':10,'slotIdx':index,'questIdx':step,'answerIdx':answer,'rewardData':reward}

    def chest(self, player, state, req, key):
        index = req.get('slotId',0)
        if index == -1:
            if state['final'] or state['searches']<self.activity['ExploreNumber']:
                raise ValueError('final chest not ready/claimed')
            reward = self.rewards(player,key,self.activity['ExploreReward'])
            state['final']=True
        else:
            slot = self.slot(state,index)
            if slot.get('done') or slot.get('choice')!=1:
                raise ValueError('chest not ready/claimed')
            box = self.boxes[slot['choice_value']]
            cost = box.get('BoxCost',0)
            currency = box.get('CurrencyType',0)
            if cost:
                from .progression import ProgressionService
                snapshot = self.store.get(player)['snapshot']
                # CurrencyType 902 is the native account crystal (1237902).
                if currency != 902:
                    raise ValueError('unknown chest currency')
                # Constructor performs schema setup and commits: reuse only the
                # stateless spending operation inside this reward transaction.
                spender=object.__new__(ProgressionService)
                spender.store,spender.economy=self.store,self.economy
                spender.spend(player,snapshot,{1237902:cost})
                self.economy.save_snapshot(player,snapshot)
            reward = self.rewards(player,key,box['BoxReward'])
            slot['done']=True
        return {'code':10,'slotId':index,'rewardData':reward}

    def _credit_adventure(self, player, key):
        """每次派遣神格探险计一次每日/周常任务（CompleteType 16 E_HeroAdventure）。

        对应每日任务 630007「通过时空之门进行 1 次遗迹探险」与周常 630107
        「通过时空之门进行 10 次探险」。handle() 已把整段包在自己的事务里，所以这里
        用内部的 ``_event`` 记账（不另开事务）；随后 handle 的 ``pushes()`` 会带上
        ``L2C_TaskUpdate``，任务页才能即时刷新。
        """
        self.economy._event(player, f"worldboss-search:{key}",
                            self.economy.TASK_EVENT_HERO_ADVENTURE, 0, 1)

    def search(self, player, state, key):
        if state['searches']>=self.activity['ExploreNumber']:
            raise ValueError('daily exploration exhausted')
        if not any(s['event']==self.explore[0]['ID'] for s in state['slots']):
            boss_id=self.ensure_boss_slot(player,state)
            state['searches']+=1
            self._credit_adventure(player,key)
            boss=self.get_boss(boss_id)
            return {'code':10,'bossEvent':self.explore[0]['ID'],'eventVal':boss['type_id'],
                'slotIdx':len(state['slots'])-1,'bossId':self.client_id(boss_id,player),'bossGroup':boss['group_id']}
        candidates = []
        for kind, weight in enumerate(self.activity['EventProbability']):
            row = self.explore[kind]
            count = sum(1 for slot in state['slots'] if slot['event']==row['ID'] and not slot.get('done'))
            if weight>0 and count<row.get('EventLimitNumber',0):
                candidates.extend([kind]*weight)
        if not candidates:
            raise ValueError('resolve current events first')
        kind = candidates[secrets.randbelow(len(candidates))]
        event_type = 1 if kind==2 else 2
        pool = [r for r in self.events.values() if r.get('Type',{}).get('value',0)==event_type]
        event = pool[secrets.randbelow(len(pool))]
        index = len(state['slots'])
        state['slots'].append({'event':self.explore[kind]['ID'],'value':event['EventID']})
        state['searches']+=1
        self._credit_adventure(player,key)
        return {'code':10,'bossEvent':self.explore[kind]['ID'],'eventVal':event['EventID'],'slotIdx':index}

    def boss_hp(self, static, monster_level, *, personal=False):
        data = catalog()
        attr = next(r for r in data['attributes'] if r['ID']==static['MonsterID'])
        bonus = next((r for r in data['level_bonus'] if r['MonsterLevel']==monster_level),None)
        multiplier = bonus['HPMaxLevelBonus'] if bonus else 1000
        # Native PropertyUpdate switches from permille to integer multipliers at 36.
        hp = (int((multiplier * 0.001) * attr['HPMax']) if monster_level < 36
              else attr['HPMax'] * multiplier) + attr.get('HPMaxCOR', 0)
        return max(1, hp // 10) if personal else hp

    def create_boss(self, boss_id, static, finder=0, nickname='Revival', *, player=None):
        monster_level = personal_monster_level(self.store, player) if player is not None else self.monster_level(static)
        hp = self.boss_hp(static, monster_level, personal=player is not None)
        self.store.db.execute('''INSERT OR IGNORE INTO world_boss_runs
            (boss_id,type_id,group_id,created,state,finish,max_hp,hp,finder,finder_name,monster_level)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
            (boss_id,static['BossID'],str(day(self.now())),self.now(),1,
                (day(self.now())+1)*86400-8*3600,hp,hp,finder,nickname,monster_level))

    def monster_level(self, static):
        if static.get('MonsterLevel'):
            return static['MonsterLevel']
        # Common Boss rows omit MonsterLevel. Use the same recovered map
        # level as L2C_FightData.monsterInitLevel, rather than choosing a level.
        maps=self.economy.entry_catalog.sections[static['StageID']]['Maps']
        return self.map_levels[str(maps[0])]

    def public_bosses(self, player):
        today=day(self.now())
        selected=self.store.db.execute('SELECT * FROM world_boss_player_days WHERE player_id=? AND day=?',(player,today)).fetchone()
        if not selected:
            static=self.bosses[self.policy['daily_boss_id']]
            if static.get('BossType',{}).get('value',0)!=0:
                raise ValueError('daily Boss must use a world Boss configuration')
            boss_id=f'world:{today}:player:{player}:{static["BossID"]}'
            self.create_boss(boss_id,static,player=player)
            legacy=f'world:{today}:{static["BossID"]}'
            member=self.store.db.execute('SELECT * FROM world_boss_members WHERE boss_id=? AND player_id=?',(legacy,player)).fetchone()
            if member:
                # Split old shared state using ONLY this player's contribution.
                # Another player's damage/death never transfers to this Boss.
                boss=self.store.db.execute('SELECT * FROM world_boss_runs WHERE boss_id=?',(boss_id,)).fetchone()
                hp=max(0,boss['max_hp']-member['damage'])
                self.store.db.execute('UPDATE world_boss_runs SET hp=?,state=? WHERE boss_id=?',
                    (hp,3 if hp==0 else (2 if member['run_id'] else 1),boss_id))
                self.store.db.execute('''INSERT INTO world_boss_members
                    (boss_id,player_id,team,damage,active,run_id,retry_at,charged,combat_confirmed)
                    VALUES (?,?,?,?,?,?,?,?,?)''',(boss_id,player,member['team'],member['damage'],
                    member['active'],member['run_id'],member['retry_at'],member['charged'],member['combat_confirmed']))
                # Retain legacy damage audit, but remove its active binding and
                # charge so one battle UUID/ticket cannot count twice.
                self.store.db.execute("UPDATE world_boss_members SET active=0,run_id='',charged=0 WHERE boss_id=? AND player_id=?",(legacy,player))
            self.store.db.execute('INSERT INTO world_boss_player_days VALUES (?,?,?,?)',(player,today,boss_id,static['BossID']))
            return boss_id
        boss_id = selected['boss_id']
        boss = self.store.db.execute('SELECT * FROM world_boss_runs WHERE boss_id=?', (boss_id,)).fetchone()
        # Keep the level fixed for an unfinished combat UUID, including reconnects.
        active = self.store.db.execute('''SELECT 1 FROM world_boss_members m
            JOIN economy_runs r ON r.uuid=m.run_id WHERE m.boss_id=? AND r.settled=0''', (boss_id,)).fetchone()
        if boss and boss['state'] in (1,2) and not active:
            level = personal_monster_level(self.store, player)
            hp = self.boss_hp(self.bosses[boss['type_id']], level, personal=True)
            if level != boss['monster_level'] or hp != boss['max_hp']:
                remaining = max(0, hp - (boss['max_hp'] - boss['hp']))
                self.store.db.execute('UPDATE world_boss_runs SET monster_level=?,max_hp=?,hp=?,state=? WHERE boss_id=?',
                    (level,hp,remaining,3 if remaining == 0 else boss['state'],boss_id))
        return boss_id

    def ensure_boss_slot(self, player, state):
        """The radar displays discovered slots, not just the 415 listing."""
        boss_id=self.public_bosses(player)
        ticket=self.client_id(boss_id,player)
        row=self.get_boss(boss_id)
        # Upgrade old discovered slots without adding another daily Boss.
        # Never renumber previously issued chest/question indices.
        slot=next((s for s in state['slots'] if s['event']==self.explore[0]['ID']),None)
        if slot is None:
            slot={}
            state['slots'].append(slot)
        slot.update(event=self.explore[0]['ID'],value=row['type_id'],boss=boss_id,ticket=ticket)
        slot['done']=row['state'] in (3,4)
        return boss_id

    def info(self, boss, player, *, combat=False):
        static = self.bosses[boss['type_id']]
        members = list(self.store.db.execute('SELECT * FROM world_boss_members WHERE boss_id=? ORDER BY damage DESC,player_id',(boss['boss_id'],)))
        ranks = []
        own = PLAYER.encode({'name':self.store.get(player)['snapshot']['nickname'],'damage':0,'order':0,'id':player})
        for index, member in enumerate(members,1):
            snapshot = self.store.get(member['player_id'])['snapshot']
            team = json.loads(member['team'])
            skin=0
            if team and self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='appearance_wear'").fetchone():
                worn=self.store.db.execute('SELECT skin_id FROM appearance_wear WHERE player_id=? AND hero_id=? AND type=1',(member['player_id'],team[0])).fetchone()
                skin=worn[0] if worn else 0
            wire = PLAYER.encode({'name':snapshot['nickname'],'damage':member['damage'],'order':index,
                'leaderTypeId':team[0] if team else 0,'id':member['player_id'],'showTypeId':team[0] if team else 0,'level':snapshot['level'],'leaderSkinId':skin})
            ranks.append(wire)
            if member['player_id']==player:
                own=wire
        return {'bossId':self.client_id(boss['boss_id'],player),'typeId':boss['type_id'],'group':boss['group_id'],
            'findTime':boss['created'],'state':boss['state'],'stateFinishTime':boss['finish'],
            'finderId':boss['finder'],'finderName':boss['finder_name'],
            # Type=6 FightData is accepted only after entering MassScene.
            # Faking a common Boss skips that scene and silently discards 126.
            'worldBoss':static.get('BossType',{}).get('value',0)==0,
            'maxHp':boss['max_hp'],'curHp':boss['hp'],'topPlayers':ranks[:10],'joinRound':1,'selfPlayer':own,
            'joinPlayerNum':sum(m['active'] for m in members),'level':boss['monster_level']}

    def get_boss(self, boss_id, group=None):
        boss_id=self.internal_id(boss_id)
        row = self.store.db.execute('SELECT * FROM world_boss_runs WHERE boss_id=?',(boss_id,)).fetchone()
        if not row or group is not None and group!=row['group_id']:
            raise ValueError('unknown boss/group')
        if row['state'] in (1,2) and row['finish']<=self.now():
            self.store.db.execute('UPDATE world_boss_runs SET state=4 WHERE boss_id=?',(boss_id,))
            row=self.store.db.execute('SELECT * FROM world_boss_runs WHERE boss_id=?',(boss_id,)).fetchone()
        if row['state'] in (3,4):
            self.finalize_rewards(row)
        return row

    def mail_reward(self, player, boss, template_id, category):
        key=f'worldboss:{boss["boss_id"]}:{category}'
        if self.store.db.execute('SELECT 1 FROM player_mail WHERE player_id=? AND source_key=?',(player,key)).fetchone():
            return
        template=self.mail_templates[template_id]
        rewards=self.economy.gifts([template['gift']],allow_daily_random=True)
        self.store.db.execute('''INSERT INTO player_mail
            (player_id,sender,title,body,created_at,attachments,source_key)
            VALUES (?,?,?,?,?,?,?)''',(player,'白夜学院',template['title'],template['body'],
                self.now(),json.dumps(rewards,sort_keys=True),key))
        LOG.info('Boss reward mail player=%s boss=%s template=%s gift=%s',
            player,boss['boss_id'],template_id,template['gift'])

    def finalize_rewards(self, boss):
        """Boss rank awards are MailInfo -> Gift, separate from 887 pickups."""
        static=self.bosses[boss['type_id']]
        members=self.store.db.execute('''SELECT player_id,damage FROM world_boss_members
            WHERE boss_id=? AND damage>=? ORDER BY damage DESC,player_id''',
            (boss['boss_id'],max(1,static.get('LowestDamage',0)))).fetchall()
        regions=static.get('RewardRegion',[])
        for rank,member in enumerate(members,1):
            tier=next((i for i,maximum in enumerate(regions) if rank<=maximum),len(regions))
            template=static['ChallengeReward'][min(tier,len(static['ChallengeReward'])-1)]
            self.mail_reward(member['player_id'],boss,template,'rank')
        if boss['finder'] and static.get('FindReward') and boss['hp']==0:
            self.mail_reward(boss['finder'],boss,static['FindReward'],'finder')

    async def watch(self, interval=1.0):
        """Expire personal battles, persist awards and notify their fighters."""
        while True:
            await asyncio.sleep(interval)
            with self.economy.transaction():
                expired=list(self.store.db.execute('''SELECT boss_id FROM world_boss_runs
                    WHERE state IN (1,2) AND finish<=?''',(self.now(),)))
                for row in expired:
                    self.get_boss(row['boss_id'])
            for row in expired:
                await self.broadcast(row['boss_id'],None)
            self.lobby_sessions={key:val for key,val in self.lobby_sessions.items() if val[1]>self.now()}

    def confirm_battle(self, player, run, *, allow_settled=False):
        member=self.store.db.execute('''SELECT m.*,e.settled FROM world_boss_members m
            JOIN economy_runs e ON e.uuid=m.run_id AND e.player_id=m.player_id
            WHERE m.player_id=? AND m.run_id=?''',(player,run)).fetchone()
        if not member or member['charged'] or (member['settled'] and not allow_settled):
            return False
        self.store.db.execute('''UPDATE world_boss_members SET charged=1,combat_confirmed=1
            WHERE boss_id=? AND player_id=?''',(member['boss_id'],player))
        LOG.info('Boss combat confirmed player=%s boss=%s run=%s',player,member['boss_id'],run)
        return True

    def finish_battle(self, player, run, success=False, *, confirmed=False):
        member=self.store.db.execute('''SELECT m.boss_id,m.charged,b.type_id FROM world_boss_members m
            JOIN world_boss_runs b USING(boss_id) WHERE m.player_id=? AND m.run_id=?''',(player,run)).fetchone()
        if not member:
            return
        if confirmed:
            self.confirm_battle(player,run,allow_settled=True)
        elif not member['charged']:
            # Replacing an entry that never reached combat is an abandonment,
            # not a completed challenge or a death deserving a penalty.
            self.store.db.execute("UPDATE world_boss_members SET active=0,run_id='',retry_at=0 WHERE player_id=? AND run_id=?",(player,run))
            return
        retry_at=-1 if success else self.now()+self.bosses[member['type_id']].get('DeadPenaltyTime',0)
        self.store.db.execute('UPDATE world_boss_members SET active=0,retry_at=? WHERE player_id=? AND run_id=?',(retry_at,player,run))

    def rejoin(self, member):
        if not member['run_id']:
            return
        run=self.store.db.execute('SELECT settled FROM economy_runs WHERE uuid=?',(member['run_id'],)).fetchone()
        if run and not run['settled']:
            entry=self.store.db.execute('SELECT created_at FROM battle_entries WHERE uuid=? AND player_id=?',
                (member['run_id'],member['player_id'])).fetchone()
            if not member['charged'] and (not entry or int(time.time())-entry['created_at']>3600):
                # A 126 which never loaded cannot remain a permanent stale
                # resume target. Abandon it through the existing refund path.
                self.economy.refund_battle(member['player_id'],member['run_id'])
                self.store.db.execute('UPDATE economy_runs SET settled=1 WHERE uuid=?',(member['run_id'],))
                self.store.db.execute("UPDATE world_boss_members SET run_id='',retry_at=0 WHERE boss_id=? AND player_id=?",(member['boss_id'],member['player_id']))
            return  # Reconnecting resumes this UUID, without a new cost.
        if member['retry_at']<=0 or self.now()<member['retry_at']:
            raise ValueError('challenge completed or death cooldown')
        self.store.db.execute("UPDATE world_boss_members SET run_id='',retry_at=0 WHERE boss_id=? AND player_id=?",(member['boss_id'],member['player_id']))

    def query(self, player, req):
        selected=self.public_bosses(player)
        boss_id = req.get('bossId','')
        if boss_id:
            if self.internal_id(boss_id)!=selected:
                raise ValueError('Boss is not today\'s scheduled instance')
            rows=[self.get_boss(boss_id,req.get('bossGroup',''))]
        else:
            rows=[self.get_boss(selected)]
        return {'code':10,'bossInfos':[INFO.encode(self.info(r,player)) for r in rows],'bossId':boss_id,
            'entry':f'{os.getenv("X2_PUBLIC_HOST","10.0.2.2")}:{os.getenv("X2_GAME_PORT","29000")}'}

    def select_heroes(self, player, req):
        boss=self.get_boss(req.get('bossId',''),req.get('bossGroup',''))
        if boss['boss_id']!=self.public_bosses(player):
            raise ValueError('Boss is not owned by this player today')
        team=req.get('heroList',[])
        owned={h['id'] for h in self.store.get(player)['snapshot']['heroes'] if h.get('state')==2}
        if not 1<=len(team)<=3 or len(set(team))!=len(team) or not set(team)<=owned:
            raise ValueError('invalid team')
        member=self.store.db.execute('SELECT * FROM world_boss_members WHERE boss_id=? AND player_id=?',(boss['boss_id'],player)).fetchone()
        if not member or not member['active']:
            raise ValueError('hero selection before joining')
        if member['run_id'] and set(team)!=set(json.loads(member['team'])):
            raise ValueError('cannot replace active battle team')
        self.store.db.execute('UPDATE world_boss_members SET team=? WHERE boss_id=? AND player_id=?',(json.dumps(team),boss['boss_id'],player))
        return {'code':10,'bossId':self.client_id(boss['boss_id'],player),'bossGroup':boss['group_id']}

    def act(self, player, state, req, network=False):
        boss=self.get_boss(req.get('bossid',''),None if network else req.get('bossGroup',''))
        if boss['boss_id']!=self.public_bosses(player):
            raise ValueError('Boss is not today\'s scheduled instance')
        action=req.get('act',0)
        static=self.bosses[boss['type_id']]
        member=self.store.db.execute('SELECT * FROM world_boss_members WHERE boss_id=? AND player_id=?',(boss['boss_id'],player)).fetchone()
        values={'code':10,'bossid':self.client_id(boss['boss_id'],player),'act':action}
        if action==1:
            if boss['state'] not in (1,2):
                raise ValueError('boss no longer available')
            if not network:
                counter='world_challenges' if static.get('BossType',{}).get('value',0)==0 else 'normal_challenges'
                limit=self.explore[0 if counter=='world_challenges' else 1]['ChallengeLimitNumber']
                if not member:
                    if state[counter]>=limit:
                        raise ValueError('daily challenge exhausted')
                    team=[h['id'] for h in self.store.get(player)['snapshot']['heroes'] if h.get('state')==2][:3]
                    self.store.db.execute('INSERT INTO world_boss_members(boss_id,player_id,team,active) VALUES (?,?,?,1)',(boss['boss_id'],player,json.dumps(team)))
                else:
                    self.rejoin(member)
                    self.store.db.execute('UPDATE world_boss_members SET active=1 WHERE boss_id=? AND player_id=?',(boss['boss_id'],player))
            elif not member:
                raise ValueError('network join without lobby admission')
            else:
                self.rejoin(member)
                self.store.db.execute('UPDATE world_boss_members SET active=1 WHERE boss_id=? AND player_id=?',(boss['boss_id'],player))
            member=self.store.db.execute('SELECT * FROM world_boss_members WHERE boss_id=? AND player_id=?',(boss['boss_id'],player)).fetchone()
            if network:
                raw_team=req.get('value',[])
                team=[hero for hero in raw_team if hero!=0]
                owned={h['id'] for h in self.store.get(player)['snapshot']['heroes'] if h.get('state')==2}
                if len(raw_team)>3 or not 1<=len(team)<=3 or len(set(team))!=len(team) or not set(team)<=owned:
                    LOG.info('Boss team rejected player=%s heroes=%s',player,raw_team[:8])
                    raise ValueError('invalid network team')
                if member['run_id'] and set(team)!=set(json.loads(member['team'])):
                    raise ValueError('cannot replace active battle team')
                if not member['charged']:
                    counter='world_challenges' if static.get('BossType',{}).get('value',0)==0 else 'normal_challenges'
                    limit=self.explore[0 if counter=='world_challenges' else 1]['ChallengeLimitNumber']
                    if state[counter]>=limit:
                        raise ValueError('daily challenge exhausted')
                self.store.db.execute('UPDATE world_boss_members SET team=? WHERE boss_id=? AND player_id=?',(json.dumps(team),boss['boss_id'],player))
            if network and boss['state']==1:
                self.store.db.execute('UPDATE world_boss_runs SET state=2 WHERE boss_id=?',(boss['boss_id'],))
        elif action==2:
            if not member:
                raise ValueError('leave without admission')
            self.store.db.execute('UPDATE world_boss_members SET active=0 WHERE boss_id=? AND player_id=?',(boss['boss_id'],player))
        elif action==3 and network:
            amounts=req.get('value',[])
            if not member or not member['active'] or not member['run_id'] or len(amounts)!=1 or not 0<=amounts[0]<=boss['max_hp']:
                raise ValueError('invalid/unbound damage')
            run=self.store.db.execute('SELECT player_id,settled FROM economy_runs WHERE uuid=?',(member['run_id'],)).fetchone()
            if not run or run['player_id']!=player or run['settled']:
                raise ValueError('damage after battle settlement')
            # Monster.Hurt 0x1c01778 emits the accumulated damage since its
            # previous flush, then clears that accumulator at 0x1c017e4.
            # Equal damage in two different requests is two genuine attacks.
            # world_boss_receipts protects transport retries of each request.
            delta=min(amounts[0],boss['hp'])
            if boss['state']==2 and delta:
                self.confirm_battle(player,member['run_id'])
                self.store.db.execute('UPDATE world_boss_members SET damage=damage+? WHERE boss_id=? AND player_id=?',(delta,boss['boss_id'],player))
                hp=max(0,boss['hp']-delta)
                self.store.db.execute('UPDATE world_boss_runs SET hp=?,state=? WHERE boss_id=?',(hp,3 if hp==0 else 2,boss['boss_id']))
        else:
            raise ValueError('unknown boss action')
        if network:
            values['bossInfo']=INFO.encode(self.info(self.get_boss(boss['boss_id']),player,combat=True))
        return values

    def battle_admission(self, player, section, team, *, allow_bound=False):
        rows=self.store.db.execute('''SELECT m.*,b.type_id,b.state FROM world_boss_members m
            JOIN world_boss_runs b USING(boss_id)
            JOIN world_boss_player_days d ON d.boss_id=b.boss_id AND d.player_id=m.player_id
            WHERE m.player_id=? AND m.active=1 AND b.state=2 AND d.day=?''',(player,day(self.now()))).fetchall()
        match=next((r for r in rows if self.bosses[r['type_id']]['StageID']==section and set(json.loads(r['team']))==set(team)),None)
        if not match:
            raise ValueError('Boss battle has no matching admitted team')
        if match['run_id'] and not allow_bound:
            raise ValueError('Boss battle already entered')
        return match['boss_id']

    def resume_battle(self, player, section, team):
        boss_id=self.battle_admission(player,section,team,allow_bound=True)
        member=self.store.db.execute('SELECT run_id FROM world_boss_members WHERE boss_id=? AND player_id=?',(boss_id,player)).fetchone()
        if not member['run_id']:
            return None
        row=self.store.db.execute('''SELECT e.response FROM battle_entries e JOIN economy_runs r USING(uuid)
            WHERE e.player_id=? AND e.uuid=? AND r.settled=0''',(player,member['run_id'])).fetchone()
        if not row:
            raise ValueError('cannot resume settled Boss battle')
        from x2server.messages.battle import BATTLE_SCHEMAS
        return BATTLE_SCHEMAS['L2C_FightData'].decode(row['response'])

    def bind_battle(self, player, section, team, run):
        boss_id=self.battle_admission(player,section,team)
        self.store.db.execute('UPDATE world_boss_members SET run_id=? WHERE boss_id=? AND player_id=?',(run,boss_id,player))

    async def broadcast(self, boss_id, excluded, actor=None, action=None):
        for connection,(reference,player,bid) in list(self.clients.items()):
            send=reference()
            if send is None:
                self.clients.pop(connection,None)
                continue
            if bid!=boss_id or connection==excluded:
                continue
            try:
                with self.economy.transaction():
                    values=self.info(self.get_boss(boss_id),player,combat=True)
                await send(OutboundMessage('WorldBossInfo',values),0)
                if actor is not None and action in (1,2):
                    own=self.info(self.get_boss(boss_id),actor)['selfPlayer']
                    await send(OutboundMessage('W2C_WorldBossPlayerAct',
                        {'player':own,'bossid':values['bossId'],'act':action,'clubId':0,'clubMemberNum':0}),0)
            except (ConnectionError,TimeoutError):
                self.clients.pop(connection,None)

    async def handle(self, context, packet):
        from .economy import UnresolvedEconomy
        name=CORE_MESSAGE_REGISTRY.name_for(packet.message_id)
        req=W[name].decode(packet.body)
        network=name=='C2W_WorldBossAct'
        response='W2C_WorldBossAct' if network else name.replace('C2L_','L2C_')
        player=context.session.player_id
        if network:
            claimed=req.get('playerid',0)
            if player is None:
                token_ok=self.identity is not None and self.identity.validates_game_identity(claimed,req.get('token',''))
                admission=self.lobby_sessions.get(context.session.session_id)
                session_ok=bool(context.session.session_id and admission and admission[0]==claimed and admission[1]>self.now())
                # Native SetC2WAct leaves token and header session empty. The
                # opaque boss ID delivered through the authenticated lobby is
                # a player-specific capability, never a predictable public ID.
                ticket=self.store.db.execute('''SELECT b.state,b.finish FROM world_boss_tickets t
                    JOIN world_boss_members m ON m.boss_id=t.boss_id AND m.player_id=t.player_id
                    JOIN world_boss_runs b ON b.boss_id=t.boss_id
                    WHERE t.ticket=? AND t.player_id=?''',(req.get('bossid',''),claimed)).fetchone()
                ticket_ok=bool(ticket and ticket['state'] in (1,2) and ticket['finish']>self.now())
                if not token_ok and not session_ok and not ticket_ok:
                    LOG.info('Boss network authentication rejected player=%s token_present=%s session_present=%s',claimed,bool(req.get('token')),bool(context.session.session_id))
                    return OutboundMessage(response,{'code':13,'act':req.get('act',0),'bossid':req.get('bossid','')})
                context.session.player_id=player=claimed
                if not context.session.session_id:
                    # Native Boss request IDs restart at 1 for each socket.
                    # Give this authenticated connection its own receipt scope.
                    context.session.session_id=secrets.token_urlsafe(24)
            elif claimed!=player:
                raise ProtocolError('Boss network player mismatch')
        if player is None:
            raise ProtocolError('Boss request before login')
        key=hashlib.sha256((context.session.session_id+':'+str(packet.header.request_id)+':'+name).encode()+packet.body).hexdigest()
        failed={'code':13,**{k:v for k,v in req.items() if k in ('bossId','bossGroup','bossid','act','slotId','slotIdx','questIdx','answerIdx')}}
        try:
            with self.economy.transaction():
                if self.store.get(player)['snapshot']['level']<self.activity['OpenLever']:
                    raise ValueError('level requirement')
                cached=self.store.db.execute('SELECT * FROM world_boss_receipts WHERE player_id=? AND request_key=?',(player,key)).fetchone()
                if cached:
                    values=W[response].decode(cached['response'])
                    if network:
                        if self.internal_id(req.get('bossid',''))!=self.public_bosses(player):
                            raise ValueError('retired or foreign Boss receipt')
                        # Replaying an old damage receipt must not restore an
                        # obsolete HP/state on the client after newer attacks.
                        values['bossInfo']=INFO.encode(self.info(self.get_boss(req.get('bossid','')),player,combat=True))
                else:
                    state=account_state(self.store,player,self.now())
                    if name=='C2L_WorldBossSearch':values=self.search(player,state,key)
                    elif name=='C2L_WorldBossQuestSelect':values=self.choice(player,state,req,key)
                    elif name=='C2L_WorldBossOpenSearchChest':values=self.chest(player,state,req,key)
                    elif name=='C2L_WorldBossLetter':values=self.letter(player,state,req,key)
                    elif name=='C2L_QueryWorldBossInfo':
                        self.ensure_boss_slot(player,state)
                        values=self.query(player,req)
                    elif name=='C2L_WorldBossSelectHero':values=self.select_heroes(player,req)
                    else:values=self.act(player,state,req,network)
                    # Never let a Boss kill reappear as a live radar slot.
                    if network and req.get('act')==3:
                        self.ensure_boss_slot(player,state)
                    self.save(player,state)
                    if name!='C2L_QueryWorldBossInfo':
                        self.store.db.execute('INSERT INTO world_boss_receipts VALUES (?,?,?,?)',(player,key,response,W[response].encode(values)))
            LOG.info('Boss request name=%s player=%s code=10 boss=%s slot=%s',name,player,self.internal_id(req.get('bossid',req.get('bossId',''))),values.get('slotIdx',values.get('slotId','-')))
            if network:
                send=getattr(context,'send',None)
                if send:
                    self.clients[context.connection_id]=(weakref.WeakMethod(send),player,self.internal_id(req['bossid']))
                await self.broadcast(self.internal_id(req['bossid']),context.connection_id,
                    actor=player if not cached else None,action=req.get('act'))
                if req.get('act')==2:
                    self.clients.pop(context.connection_id,None)
            elif name=='C2L_WorldBossAct' and req.get('act')==1:
                self.lobby_sessions[context.session.session_id]=(player,self.now()+3600)
            # Client callbacks inspect NetSyncData immediately, so account
            # counters and event states must precede the response.
            sync=not network and name not in ('C2L_QueryWorldBossInfo','C2L_WorldBossSelectHero')
            before=self.economy.pushes(player) if sync else ()
            if name=='C2L_QueryWorldBossInfo':
                fields,_=snapshot_fields(self.store,player,self.now())
                # A data-change callback may itself query details. Send only
                # changed radar data per authenticated session to stop loops.
                radar_key=(player,context.session.session_id)
                if self.radar_sent.get(radar_key)!=fields['WorldBossSearch']:
                    self.radar_sent[radar_key]=fields['WorldBossSearch']
                    before=(OutboundMessage('PlayerDataProto',fields,data_version=1),)
            return OutboundMessage(response,values,before_response=before)
        except (ValueError,KeyError,UnresolvedEconomy) as exc:
            LOG.info('Boss request rejected name=%s player=%s reason=%s',name,player,exc)
            return OutboundMessage(response,failed)
