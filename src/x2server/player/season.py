"""Origin Paradox, independent of theme activity rotation and account identity."""
from collections import Counter
from functools import lru_cache
from importlib.resources import files
import hashlib
import json
import logging
import os
import random

from x2server.messages.season import SEASON_SCHEMAS, encode
from x2server.messages.economy import TASK, TREASURE_BOX, ECONOMY_SCHEMAS
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY
from .economy import UnresolvedEconomy
from .task_calendar import task_period
from .season_schedule import current_season, ANCHOR, DURATION


def ev(value):
    return value.get('value', 0) if isinstance(value, dict) else value or 0


@lru_cache(maxsize=1)
def catalog():
    return json.loads(files('x2server').joinpath('data/season_catalog.json').read_text('utf8'))


class SeasonService:
    ACTIVITY = 74001
    CONFIG = 10000
    GROUP = 16
    TASK_KIND = 15
    ACTIVE_ITEM = 1237999
    EXP_ITEM = 1291001
    POINT_ITEM = 1291002
    # Friend coin gifting is not restored; do not assign its impossible task.
    UNAVAILABLE_TASK_EVENTS = {71}

    def __init__(self, economy, *, enabled=None, instance=None):
        self.e, self.store = economy, economy.store
        self.enabled = os.getenv('X2_ORIGIN_SEASON_ENABLED', '0') == '1' if enabled is None else enabled
        self.base_instance = instance or os.getenv('X2_ORIGIN_SEASON_INSTANCE', 'origin-review-1')
        if not self.instance or len(self.instance) > 100:
            raise ValueError('invalid season instance')
        self.data = catalog()
        self.bp = next(r for r in self.data['battlepass'] if r['BattlepassID'] == self.CONFIG)
        self.activities = [r for r in self.data['activityreal']
                           if r['ActivityID'] in (self.ACTIVITY, self.ACTIVITY + 1)
                           and r.get('ActivityGroup') == self.GROUP]
        self.configs = {r['ID']: r for r in self.data['seasonconfig'] if self.ACTIVITY in r['SeasonID']}
        self.section_configs = {sid: r for r in self.configs.values() for sid in r['SectionGroup']}
        self.sections = {r['SectionID']: r for r in self.data['sectiontable'] if r['SectionID'] in self.section_configs}
        self.levels = {r['ID']: r for r in self.data['battlepasslevel'] if r['BattlepassID'] == self.CONFIG}
        self.conditions = {r['TaskConditionID']: r for r in self.data['taskcondition']}
        self.lines = {r['AchievementConditionID']: r for r in self.data['taskconditionline']}
        fixed = {i for group in self.bp['BpTaskFixed'] for i in group['Items']}
        pools = set(self.bp['BpTaskRandom'])
        self.tasks = {r['BattlepassTaskID']: r for r in self.data['battlepasstask']
                      if ev(r.get('IsUse')) == 1 and (r['BattlepassTaskID'] in fixed or r.get('GroupID') in pools)}
        self.achievements = {r['AchievementID']: r for r in self.data['battlepassachievement']
                             if r['ActivityID'] == self.ACTIVITY and ev(r.get('IsUse')) == 1}
        self.talents = {r['TalentID']: r for r in self.data['battlepasstalent']}
        self.ranks = [r for r in self.data['battlepassrank'] if r['ActivityID'] == self.ACTIVITY]
        self.stage_stars = {r['HeroStage']: r.get('BigStarNum', 0) for r in self.data['playerstage']}
        self.items = {r['ItemID']: r for r in self.data['item'] if r.get('ItemID')}
        self.unit_types = {int(k): v for k, v in json.loads(files('x2server').joinpath('data/unit_types.json').read_text('utf8')).items()}
        self.sent_state = {}
        self.sent_task_ids = {}
        from .season_shop import SeasonShop
        self.shop = SeasonShop(self)
        from .season_artifact import SeasonArtifact
        self.artifact = SeasonArtifact(self)
        with self.e.transaction():
            self.store.db.execute('''CREATE TABLE IF NOT EXISTS season_calendar (
                instance_id TEXT PRIMARY KEY,activity_id INTEGER NOT NULL,start_sec INTEGER NOT NULL,
                end_sec INTEGER NOT NULL,closed INTEGER NOT NULL DEFAULT 0)''')
            self.store.db.execute('''CREATE TABLE IF NOT EXISTS season_state (
                player_id INTEGER NOT NULL,instance_id TEXT NOT NULL,state_json TEXT NOT NULL,
                PRIMARY KEY(player_id,instance_id))''')
            self.store.db.execute('''CREATE TABLE IF NOT EXISTS season_events (
                player_id INTEGER NOT NULL,instance_id TEXT NOT NULL,event_key TEXT NOT NULL,
                PRIMARY KEY(player_id,instance_id,event_key))''')
            self.store.db.execute('''CREATE TABLE IF NOT EXISTS season_receipts (
                player_id INTEGER NOT NULL,instance_id TEXT NOT NULL,request_key TEXT NOT NULL,
                message TEXT NOT NULL,response BLOB NOT NULL,
                PRIMARY KEY(player_id,instance_id,request_key))''')
            self.store.db.execute('''CREATE TABLE IF NOT EXISTS season_runs (
                uuid TEXT PRIMARY KEY,player_id INTEGER NOT NULL,instance_id TEXT NOT NULL,
                config_id INTEGER NOT NULL,section_id INTEGER NOT NULL,settled INTEGER NOT NULL DEFAULT 0,
                success INTEGER NOT NULL DEFAULT 0)''')
            if self.enabled:
                schedule = current_season(self.e.clock())
                start = schedule['start'] if schedule and schedule['key'] == 'origin' else ANCHOR
                self.store.db.execute('INSERT OR IGNORE INTO season_calendar VALUES (?,?,?,?,0)',
                                     (self.instance, self.ACTIVITY, start, start + DURATION))
                self.store.db.execute('UPDATE season_calendar SET start_sec=?,end_sec=? WHERE instance_id=?',
                                     (start, start + DURATION, self.instance))
                for row in self.store.db.execute('SELECT id FROM players').fetchall():
                    if self.active(row[0]):
                        self._state(row[0])  # Capture growth baselines at activation, not at first page visit.

    def handlers(self):
        return {name: self.handle for name in SEASON_SCHEMAS if name.startswith('C2L_')}

    @property
    def instance(self):
        period = current_season(self.e.clock())
        cycle = period['cycle'] if period else 0
        return self.base_instance if cycle == 0 else f'{self.base_instance}:cycle:{cycle}'

    def calendar(self):
        period = current_season(self.e.clock())
        if not period or period['key'] != 'origin':
            return None
        row = self.store.db.execute('SELECT * FROM season_calendar WHERE instance_id=?', (self.instance,)).fetchone()
        return row or {'instance_id':self.instance,'activity_id':self.ACTIVITY,
                       'start_sec':period['start'],'end_sec':period['end'],'closed':0}

    def active(self, player=None):
        row = self.calendar() if self.enabled else None
        return bool(row and not row['closed'] and row['start_sec'] <= self.e.clock() < row['end_sec']
                    and (player is None or self.store.get(player)['snapshot']['level'] >= 20))

    def require(self, player):
        if not self.active(player):
            raise UnresolvedEconomy('Origin Paradox closed or requires account level 20')

    def initial(self, player):
        heroes = self.store.get(player)['snapshot'].get('heroes', [])
        return {'exp': 0, 'points': 0, 'levels_claimed': {}, 'talents': {}, 'max_layer': 0, 'unlocked_layer': 1,
                'last_config': min(self.configs), 'sign_day': 0, 'bought_levels': 0,
                'stats': {}, 'tasks': {}, 'task_claimed': [], 'achievements_claimed': [],
                'achievement_floors': {}, 'point_claimed': [], 'relics': [],
                'baseline_heroes': {str(h['id']): {'level': h.get('level', 1), 'star': h.get('star', 1),
                    'artifact': (h.get('god_equip') or {}).get('star', 0)} for h in heroes},
                'hero_growth': {}, 'equip_growth': {}, 'equip_obtained': {}, 'items_obtained': {},
                'chapter_layers': {}, 'timed_layers': {}, 'week': 0, 'week_exp': 0,
                'refreshes': 0, 'selected_tasks': [], 'kill_counts': {}, 'task_stages': {}}

    def unlocked_layer(self, state):
        """Admission frontier is independent of the highest actually cleared floor."""
        return min(max(r['Level'] for r in self.configs.values()),
                   max(1, state.get('unlocked_layer', 1), state.get('max_layer', 0) + 1))

    @staticmethod
    def skipped_layers(seconds):
        # User policy uses strict intervals: exactly 5 or 10 minutes skips none.
        return 2 if 0 < seconds < 300 else 1 if 300 < seconds < 600 else 0

    def state(self, player):
        with self.e.transaction():
            return self._state(player)

    def _state(self, player):
        row = self.store.db.execute('SELECT state_json FROM season_state WHERE player_id=? AND instance_id=?',
                                    (player, self.instance)).fetchone()
        state = json.loads(row[0]) if row else self.initial(player)
        state['unlocked_layer'] = self.unlocked_layer(state)
        if state.get('last_config') not in self.configs:
            # Imported/legacy state must never select a different season's page.
            layer = self.unlocked_layer(state)
            state['last_config'] = next(r['ID'] for r in self.configs.values() if r['Level'] == layer)
        week = task_period(2, int(self.e.clock()))[0]
        if state['week'] != week:
            state.update(week=week, week_exp=0, refreshes=0, tasks={}, task_claimed=[], task_stages={},
                         selected_tasks=self.choose_tasks(player, week))
        if state.get('weekly_active_period') != week:
            prefix = f'season:{self.instance}:task:{week}:'
            state['weekly_active'] = sum(json.loads(r[0]).get(str(self.ACTIVE_ITEM), 0) for r in self.store.db.execute(
                'SELECT rewards FROM economy_grants WHERE player_id=? AND substr(source,1,?)=?', (player, len(prefix), prefix)))
            state['weekly_active_period'] = week
            state['weekly_box_claimed'] = []
        self.repair_selected_tasks(player, state)
        self.write(player, state)
        return state

    def write(self, player, state):
        self.store.db.execute('INSERT INTO season_state VALUES (?,?,?) ON CONFLICT(player_id,instance_id) '
            'DO UPDATE SET state_json=excluded.state_json', (player, self.instance, json.dumps(state, separators=(',', ':'))))

    def once(self, player, key):
        return bool(self.store.db.execute('INSERT OR IGNORE INTO season_events VALUES (?,?,?)',
                                         (player, self.instance, key)).rowcount)

    def choose_tasks(self, player, week):
        selected = list(self.bp['BpTaskFixed'][0]['Items'])
        rng = random.Random(f'{player}:{self.instance}:{week}')
        for group in self.bp['BpTaskRandom']:
            pool = [tid for tid, row in self.tasks.items() if row.get('GroupID') == group and self.task_available(tid)]
            if pool:
                selected.append(rng.choice(pool))
        return selected

    def task_available(self, tid):
        row = self.tasks[tid]
        condition = (self.lines[row['TaskConditionID']] if ev(row['TaskConditionType']) == 1
                     else self.conditions[row['TaskConditionID']])
        return ev(condition['CompleteType']) not in self.UNAVAILABLE_TASK_EVENTS

    def repair_selected_tasks(self, player, state):
        selected = state['selected_tasks']
        for index, tid in enumerate(list(selected)):
            if self.task_available(tid):
                continue
            group = self.tasks[tid].get('GroupID')
            pool = [i for i, row in self.tasks.items() if row.get('GroupID') == group
                    and i not in selected and i not in state['task_claimed'] and self.task_available(i)]
            if pool:
                selected[index] = random.Random(f'{player}:{self.instance}:{state["week"]}:repair:{tid}').choice(pool)
        state['selected_tasks'] = [tid for tid in selected if self.task_available(tid)]
        return state

    def task_condition(self, tid, state):
        row = self.tasks[tid]
        if ev(row['TaskConditionType']) == 1:
            line = self.lines[row['TaskConditionID']]
            stage = min(state.setdefault('task_stages', {}).get(str(tid), 0), len(line['CompleteNum']) - 1)
            return dict(line, CompleteNum=line['CompleteNum'][stage]), line['CompleteNum'][-1], stage, len(line['CompleteNum'])
        condition = self.conditions[row['TaskConditionID']]
        return condition, condition['CompleteNum'], 0, 1

    def daily_gift(self, player, task_id, ordinary):
        if self.active(player):
            row = next((r for r in self.data['dailytask'] if r['DailyTaskID'] == task_id), None)
            if row and row.get('GiftGroupSeason'):
                return row['GiftGroupSeason']  # Replacement includes the ordinary rewards.
        return ordinary

    def base_info(self, state):
        # Native sign UI uses calendar dates and a hard-coded 05:00 boundary.
        # Project the Beijing-midnight entitlement into the client's clock:
        # current time means claimed today, zero means available. Sending the
        # stored midnight falsely reopens the chest after 05:00. This is only
        # a display marker; persisted day and reward receipts stay authoritative.
        now = int(self.e.clock())
        sign_time = now if state['sign_day'] == task_period(1, now)[0] else 0
        return {'exp': state['exp'], 'type': 3, 'configId': self.CONFIG,
                'refreshTaskCount': min(state['refreshes'], len(self.bp['BpTaskRefresh']) - 1),
                'lastBattlePassSign': sign_time, 'weekMaxExp': state['week_exp']}

    def base_values(self, player):
        state = self.state(player)
        return {'code': 10, 'baseInfo': encode('BattlePassBaseInfo', self.base_info(state)),
                'rewardInfo': [encode('BattlePassRewardInfo', {'id': i,
                    'lastReceivedType': 3 if str(i) in state['levels_claimed'] else 0}) for i in self.levels]}

    def mission_values(self, player):
        state = self.state(player)
        level = self.unlocked_layer(state)
        next_id = next(r['ID'] for r in self.configs.values() if r['Level'] == level)
        last_id = next((r['ID'] for r in self.configs.values() if r['Level'] == state['max_layer']), 0)
        return {'code': 10, 'maxSeasonId': next_id, 'lastSeasonId': state['last_config'],
                'maxPassId': last_id, 'levelRewardList': [0],
                'maxChallengepassId': 0, 'lastChallengepassId': 0}

    def activity_values(self):
        if not self.active():
            return []
        from x2server.messages.activity import encode as activity_encode
        row = self.calendar()
        values = []
        for source in self.activities:
            data = {'actId': source['ActivityID'], 'state': 1, 'activityParentType': ev(source['ActivityParentType']),
                'actType': ev(source['ActivityType']), 'startTime': row['start_sec'], 'endTime': row['end_sec'],
                'openLever': source['OpenLever'], 'activityGroup': source['ActivityGroup'],
                'activityName': source['ActivityName'], 'openParam': [0],
                'activityReward': source.get('ActivityReward') or [0],
                'activityDataItems': [activity_encode('ActivityDataItem', {'index': 0,
                    'itemParams': [activity_encode('ItemData', {'id': 0, 'num': 0})]})]}
            for i in range(1, 5):
                data[f'param{i}'] = source.get(f'ActivityParam{i}') or [0]
            values.append(activity_encode('ActivityData', data))
        return values

    def accept_reward(self, player, source, rewards):
        """Called inside Economy._grant after its source receipt check."""
        if not self.active(player):
            return rewards
        state = self.state(player)
        rewards = dict(rewards)
        for item, count in rewards.items():
            state['items_obtained'][str(item)] = state['items_obtained'].get(str(item), 0) + count
        state['weekly_active'] = state.get('weekly_active', 0) + rewards.get(self.ACTIVE_ITEM, 0)
        exp = rewards.get(self.EXP_ITEM, 0)
        points = rewards.get(self.POINT_ITEM, 0)
        if exp:
            if source.startswith(f'season:{self.instance}:task:'):
                exp = min(exp, max(0, self.bp['BpTaskExpLimit'] - state['week_exp']))
                state['week_exp'] += exp
            before = state['exp'] // self.bp['LevelExp']
            state['exp'] = min(max(r['ReceiveExp'] for r in self.levels.values()), state['exp'] + exp)
            after = state['exp'] // self.bp['LevelExp']
            # Native table's additional level reward is Gift797005 (one talent point).
            for r in self.levels.values():
                if before < r['Level'] <= after:
                    points += sum(1 for gift in r.get('unknown_field_10', []) if gift == 797005)
        state['points'] += points
        self.write(player, state)
        if self.EXP_ITEM in rewards:
            if exp:
                rewards[self.EXP_ITEM] = exp
            else:
                del rewards[self.EXP_ITEM]
        return rewards

    def grant(self, player, category, key, groups):
        from .bag_items import grant_bag_rewards
        rewards = self.e.gifts(groups, allow_daily_random=True)
        source = f'season:{self.instance}:{category}:{key}'
        reward_data = grant_bag_rewards(self.e, player, source, rewards, 0)
        return rewards, reward_data

    def spend(self, player, item, amount):
        if type(amount) is not int or amount < 0:
            raise UnresolvedEconomy('invalid season cost')
        if not amount:
            return
        if item in self.e.CURRENCIES:
            state = self.store.get(player)['snapshot']
            field = self.e.CURRENCIES[item]
            if state.get(field, 0) < amount:
                raise UnresolvedEconomy('insufficient season currency')
            state[field] -= amount
            self.e.save_snapshot(player, state)
        else:
            charged = self.store.db.execute('UPDATE inventory SET quantity=quantity-? WHERE player_id=? AND item_id=? AND quantity>=?',
                                           (amount, player, item, amount))
            if not charged.rowcount:
                raise UnresolvedEconomy('insufficient season item')

    def event(self, player, key, kind, value=0, amount=1, value2=0):
        if kind == 10 and value == 900:
            self.event(player, key + ':season-power', 96, 0, amount)
        if kind in (1, 2) and key.startswith('kills:'):
            return  # Per-unit peaks below own season task credits, avoiding checkout/late-report doubles.
        if key == 'login':
            key += ':' + str(task_period(1, int(self.e.clock()))[0])
        if not self.active(player) or amount <= 0 or not self.once(player, 'event:' + key + ':' + str(kind)):
            return
        state = self.state(player)
        for tid in state['selected_tasks']:
            row = self.tasks[tid]
            condition, maximum, _, _ = self.task_condition(tid, state)
            if ev(condition['CompleteType']) != kind:
                continue
            if any(condition.get(field) not in (None, [], [0], [-1]) and observed not in condition[field]
                   for field, observed in [('CompleteValue1', value), ('CompleteValue2', value2)]):
                continue
            state['tasks'][str(tid)] = min(maximum, state['tasks'].get(str(tid), 0) + amount)
        heroes = self.store.get(player)['snapshot'].get('heroes', [])
        for h in heroes:
            baseline = state['baseline_heroes'].get(str(h['id']), {})
            changed = {k: v for k, v in {'level': h.get('level', 1), 'star': h.get('star', 1),
                         'artifact': (h.get('god_equip') or {}).get('star', 0)}.items() if v > baseline.get(k, 0)}
            if changed:
                state['hero_growth'].setdefault(str(h['id']), {}).update(changed)
        if key.startswith('equip-strengthen:'):
            equip_id = key.split(':')[1]
            row = self.store.db.execute('SELECT level FROM equipment_instances WHERE player_id=? AND id=?', (player, equip_id)).fetchone()
            if row:
                state['equip_growth'][equip_id] = row[0]
        self.write(player, state)

    def kills(self, player, uuid, units, *, confirmed=False):
        if not self.active(player):
            return
        run = self.store.db.execute('SELECT section_type FROM economy_runs WHERE uuid=? AND player_id=?', (uuid, player)).fetchone()
        if not run or run['section_type'] == 5:
            return
        if not confirmed:
            from x2server.messages.battle import BATTLE_SCHEMAS
            receipt = self.store.db.execute('SELECT response FROM battle_receipts WHERE uuid=?', (uuid,)).fetchone()
            if not receipt or not BATTLE_SCHEMAS['L2C_CheckoutMainMission'].decode(receipt[0]).get('success'):
                return
        for unit, count in units.items():
            if type(count) is not int or not 0 < count <= 10000:
                continue
            state = self.state(player)
            key = f'{uuid}:{unit}'
            previous = state.setdefault('kill_counts', {}).get(key, 0)
            if count > previous:
                event_key = f'kill-unit:{key}:{count}'
                self.event(player, event_key, 1, unit, count - previous)
                if unit in self.unit_types:
                    self.event(player, event_key + ':type', 2, self.unit_types[unit], count - previous)
                state = self.state(player)
                state.setdefault('kill_counts', {})[key] = count
                self.write(player, state)

    def loot(self, player, uuid, equipment, relics):
        if not self.active(player) or not self.once(player, 'loot:' + uuid):
            return
        state = self.state(player)
        for tid in state['selected_tasks']:
            condition, maximum, _, _ = self.task_condition(tid, state)
            kind = ev(condition['CompleteType'])
            if kind not in (36, 37):
                continue
            types, qualities = condition.get('CompleteValue2', []), condition.get('CompleteValue1', [])
            any_quality = qualities in ([], [0], [-1])
            count = 0
            if 10 in types:
                count += sum(any_quality or row['star'] in qualities for row in equipment)
            if 4 in types:
                count += sum(any_quality or ev(self.e.items.get(i, {}).get('ItemQuality')) in qualities for i in set(relics))
            old = state['tasks'].get(str(tid), 0)
            state['tasks'][str(tid)] = min(maximum, old + count if kind == 36 else max(old, count))
        self.write(player, state)

    def task_values(self, player):
        if not self.active(player):
            return {'code': 13, 'type': self.TASK_KIND, 'activityId': self.ACTIVITY, 'taskList': [], 'boxList': []}
        with self.e.transaction():
            state = self.state(player)
            tasks = []
            building_row = self.store.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='college_state'").fetchone()
            college = self.store.db.execute('SELECT state_json FROM college_state WHERE player_id=?', (player,)).fetchone() if building_row else None
            buildings = json.loads(college[0]).get('buildings', []) if college else []
            for tid in state['selected_tasks']:
                condition, _, stage, _ = self.task_condition(tid, state)
                target = condition['CompleteNum']
                progress = state['tasks'].get(str(tid), 0)
                if ev(condition['CompleteType']) == 80:
                    progress = max(progress, int(any(b.get('buildingId') in condition.get('CompleteValue1', []) and b.get('buildingLevel', 0) >= condition.get('CompleteValue2', [0])[0] for b in buildings)))
                    state['tasks'][str(tid)] = progress
                tasks.append(TASK.encode({'taskId': tid, 'taskProgress': progress,
                    'taskStatus': 4 if tid in state['task_claimed'] else 3 if progress >= target else 2,
                    'taskRefreshTime': task_period(2, int(self.e.clock()))[1], 'activityId': self.ACTIVITY,
                    'stage': stage,
                    'finishTimes': state.setdefault('task_stages', {}).get(str(tid), int(tid in state['task_claimed']))}))
            self.write(player, state)
            return {'code': 10, 'type': self.TASK_KIND, 'activityId': self.ACTIVITY, 'taskList': tasks, 'boxList': self.weekly_boxes(state)}

    def weekly_boxes(self, state):
        return [TREASURE_BOX.encode({'boxId': i, 'pickStatus': 2 if i in state.get('weekly_box_claimed', [])
            else 1 if state.get('weekly_active', 0) >= target else 0, 'activityId': 0})
            for i, target in enumerate(self.e.catalog['task_control']['BpActiveValueNumber'])]

    def claim_weekly_box(self, context, packet, req):
        player = context.session.player_id
        reject = {'code': 13, **req}
        token = 'weekly-box:' + hashlib.sha256(f'{context.session.session_id}:{packet.header.request_id}'.encode() + packet.body).hexdigest()
        try:
            with self.e.transaction():
                self.require(player)
                state = self.state(player)
                saved = self.store.db.execute('SELECT response FROM season_receipts WHERE player_id=? AND instance_id=? AND request_key=?',
                    (player, self.instance, token)).fetchone()
                if saved:
                    values = ECONOMY_SCHEMAS['L2C_PickTreasureBox'].decode(saved[0])
                else:
                    i = req.get('boxId', -1)
                    targets = self.e.catalog['task_control']['BpActiveValueNumber']
                    if (type(i) is not int or i not in range(len(targets)) or req.get('param', 0)
                            or req.get('activityId', 0) not in (0, self.ACTIVITY)
                            or state.get('weekly_active', 0) < targets[i] or i in state.get('weekly_box_claimed', [])):
                        raise UnresolvedEconomy('season weekly box unavailable')
                    state.setdefault('weekly_box_claimed', []).append(i)
                    self.write(player, state)
                    _, reward = self.grant(player, 'weekly-box', f"{state['week']}:{i}",
                        [self.e.catalog['task_control']['BpGiftGroup'][i]])
                    values = {'code': 10, **req, 'rewardData': reward}
                    self.store.db.execute('INSERT INTO season_receipts VALUES (?,?,?,?,?)',
                        (player, self.instance, token, 'L2C_PickTreasureBox', ECONOMY_SCHEMAS['L2C_PickTreasureBox'].encode(values)))
        except UnresolvedEconomy:
            values = reject
        return OutboundMessage('L2C_PickTreasureBox', values, before_response=self.e.pushes(player) if values['code'] == 10 else ())

    def claim_task(self, player, tid):
        self.require(player)
        self.task_values(player)
        state = self.state(player)
        if tid not in state['selected_tasks'] or tid in state['task_claimed']:
            raise UnresolvedEconomy('season task unavailable or claimed')
        condition, _, stage, stages = self.task_condition(tid, state)
        if state['tasks'].get(str(tid), 0) < condition['CompleteNum']:
            raise UnresolvedEconomy('season task unfinished')
        state.setdefault('task_stages', {})[str(tid)] = stage + 1
        if stage + 1 >= stages:
            state['task_claimed'].append(tid)
        state['stats']['tasks'] = state['stats'].get('tasks', 0) + 1
        self.write(player, state)
        _, reward = self.grant(player, 'task', f"{state['week']}:{tid}:{stage}", [self.tasks[tid]['GiftGroup'][min(stage, len(self.tasks[tid]['GiftGroup']) - 1)]])
        next_task = next(raw for raw in self.task_values(player)['taskList'] if TASK.decode(raw)['taskId'] == tid)
        return {'code': 10, 'type': self.TASK_KIND, 'taskId': tid, 'activityId': self.ACTIVITY,
                'rewardData': reward, 'nextTask': next_task}

    def claim_task_response(self, player, tid, token=None):
        try:
            with self.e.transaction():
                from x2server.messages.economy import FINISH_RESULT
                cached = self.store.db.execute('SELECT response FROM season_receipts WHERE player_id=? AND instance_id=? AND request_key=?', (player, self.instance, token)).fetchone() if token else None
                if cached:
                    return FINISH_RESULT.decode(cached[0])
                result = self.claim_task(player, tid)
                if token:
                    self.store.db.execute('INSERT INTO season_receipts VALUES (?,?,?,?,?)', (player, self.instance, token, 'FinishResult', FINISH_RESULT.encode(result)))
                return result
        except UnresolvedEconomy:
            return {'code': 13, 'type': self.TASK_KIND, 'taskId': tid, 'activityId': self.ACTIVITY}

    def admission(self, player, section):
        self.require(player)
        config = self.section_configs[section]
        state = self.state(player)
        if config['Level'] > self.unlocked_layer(state):
            raise UnresolvedEconomy('previous season level not completed')
        balance = self.store.db.execute('SELECT quantity FROM inventory WHERE player_id=? AND item_id=?',
                                        (player, config.get('ConsumeItem', 0))).fetchone()
        if config.get('ConsumeNum', 0) and (not balance or balance[0] < config['ConsumeNum']):
            raise UnresolvedEconomy('insufficient season ticket')

    def bind_run(self, player, section, uuid):
        self.require(player)
        config = self.section_configs[section]
        state = self.state(player)
        if config['Level'] > self.unlocked_layer(state):
            raise UnresolvedEconomy('previous season level not completed')
        self.spend(player, config.get('ConsumeItem', 0), config.get('ConsumeNum', 0))
        state['last_config'] = config['ID']
        self.write(player, state)
        self.store.db.execute('INSERT INTO season_runs VALUES (?,?,?,?,?,0,0)',
            (uuid, player, self.instance, config['ID'], section))

    def completed(self, player, uuid, success, seconds, equipment=(), relics=()):
        run = self.store.db.execute('SELECT * FROM season_runs WHERE uuid=? AND player_id=?', (uuid, player)).fetchone()
        if not run:
            return
        if run['settled']:
            return
        if run['instance_id'] != self.instance or not self.active(player):
            if not success:
                self.store.db.execute('UPDATE season_runs SET settled=1 WHERE uuid=?', (uuid,))
                return  # Abandon an expired run without crediting the new instance.
            raise UnresolvedEconomy('season battle belongs to an expired instance')
        self.store.db.execute('UPDATE season_runs SET settled=1,success=? WHERE uuid=?', (int(success), uuid))
        if not success:
            config = self.configs[run['config_id']]
            self.e._grant(player, f'season:{self.instance}:refund:{uuid}', {config['ConsumeItem']: config['ConsumeNum']})
            return
        state = self.state(player)
        config = self.configs[run['config_id']]
        state['max_layer'] = max(state['max_layer'], config['Level'])
        skipped = self.skipped_layers(seconds)
        state['unlocked_layer'] = min(max(r['Level'] for r in self.configs.values()),
                                     max(self.unlocked_layer(state), config['Level'] + 1 + skipped))
        logging.getLogger('x2.season').info(
            'tower clear player=%s floor=%s seconds=%s skipped=%s unlocked=%s',
            player, config['Level'], seconds, skipped, state['unlocked_layer'])
        state['stats']['passes'] = state['stats'].get('passes', 0) + 1
        state['stats']['pass_time'] = state['stats'].get('pass_time', 0) + max(0, seconds)
        chapter = self.sections[run['section_id']].get('NumerChina', '')
        state['chapter_layers'][chapter] = max(state['chapter_layers'].get(chapter, 0), config['Level'])
        if seconds > 0:
            layer = str(config['Level'])
            state['timed_layers'][layer] = min(seconds, state['timed_layers'].get(layer, seconds))
        for instance in equipment:
            state['equip_obtained'][str(instance['id'])] = instance['star']
        relics = set(relics)
        state['relics'] = sorted(set(state['relics']) | relics)
        self.write(player, state)
        self.loot(player, uuid, equipment, relics)
        self.event(player, f'season-pass:{uuid}', 97, 20)

    def report_npcs(self, player, uuid, reports):
        from x2server.messages.battle import DROP_REPORT_NPC
        if not self.active(player) or not self.store.db.execute('SELECT 1 FROM economy_runs WHERE player_id=? AND uuid=? AND section_type!=5', (player, uuid)).fetchone():
            return
        for raw in reports[:512]:
            report = DROP_REPORT_NPC.decode(raw)
            npc, count = report.get('id', 0), report.get('count', 0)
            if not 0 < count <= 1000:
                continue
            state = self.state(player)
            key = f'{uuid}:{npc}'
            previous = state.setdefault('npc_counts', {}).get(key, 0)
            if count > previous:
                self.event(player, f'season-npc:{key}:{count}', 27, npc, count - previous)
                state = self.state(player)
                state.setdefault('npc_counts', {})[key] = count
                self.write(player, state)

    def battle_spend(self, player, uuid, key, currency, amount):
        if not self.active(player) or not self.store.db.execute('SELECT 1 FROM economy_runs WHERE player_id=? AND uuid=? AND section_type!=5', (player, uuid)).fetchone():
            return
        if not self.once(player, 'shop-spend:' + key):
            return
        self.event(player, key, 32, currency, amount)
        state = self.state(player)
        count_key = f'{uuid}:{currency}'
        total = state.setdefault('run_spend', {}).get(count_key, 0) + amount
        state['run_spend'][count_key] = total
        for tid in state['selected_tasks']:
            condition, maximum, _, _ = self.task_condition(tid, state)
            if ev(condition['CompleteType']) == 33 and currency in condition.get('CompleteValue1', []):
                state['tasks'][str(tid)] = min(maximum, max(state['tasks'].get(str(tid), 0), total))
        self.write(player, state)

    def achievement_values(self, player):
        state = self.state(player)
        for hero in self.store.get(player)['snapshot'].get('heroes', []):
            baseline = state['baseline_heroes'].get(str(hero['id']), {})
            observed = {'level': hero.get('level', 1), 'star': hero.get('star', 1),
                        'artifact': (hero.get('god_equip') or {}).get('star', 0)}
            changed = {key: value for key, value in observed.items() if value > baseline.get(key, 0)}
            if changed:
                state['hero_growth'].setdefault(str(hero['id']), {}).update(changed)
        result = []
        for aid, row in self.achievements.items():
            rule = row.get('rule', {'kind': 'unsupported'})
            kind, target = rule['kind'], rule.get('target', 1)
            if kind == 'max_layer':
                progress = state['max_layer']
            elif kind == 'relics':
                progress = len(state['relics'])
            elif kind == 'level':
                progress = state['exp'] // self.bp['LevelExp']
            elif kind == 'hero_level':
                progress = sum(v.get('level', 0) >= rule['minimum'] for v in state['hero_growth'].values())
            elif kind == 'hero_star':
                progress = sum(self.stage_stars.get(v.get('star', 0), 0) >= rule['minimum'] for v in state['hero_growth'].values())
            elif kind == 'artifact_star':
                progress = sum(v.get('artifact', 0) >= rule['minimum'] for v in state['hero_growth'].values())
            elif kind == 'equip_level':
                progress = sum(v >= rule['minimum'] for v in state['equip_growth'].values())
            elif kind == 'equip_star':
                progress = sum(v >= rule['minimum'] for v in state['equip_obtained'].values())
            elif kind == 'items':
                progress = sum(state['items_obtained'].get(str(i), 0) for i in rule['items'])
            elif kind == 'timed_layer':
                seconds = state['timed_layers'].get(str(rule['layer']), 0)
                progress = int(0 < seconds <= rule['seconds'])
            elif kind == 'chapter_layer':
                progress = int(state['chapter_layers'].get(rule['chapter'], 0) >= rule['layer'])
            else:
                progress = state['stats'].get(kind, 0) if kind != 'unsupported' else 0
            progress = max(progress, state['achievement_floors'].get(str(aid), 0))
            state['achievement_floors'][str(aid)] = min(progress, target)
            wire_target = row.get('wire_target', target)
            wire_progress = min(progress, wire_target) if wire_target == target else wire_target if progress >= target else 0
            result.append({'achvId': aid, 'achvProgress': wire_progress, 'stage': int(aid in state['achievements_claimed']),
                           'status': 2 if aid in state['achievements_claimed'] else 1 if progress >= target else 0})
        self.write(player, state)
        return result

    def owned_relics(self, player):
        from .login import relic_item_ids
        valid = relic_item_ids()
        result = {r[0] for r in self.store.db.execute(
            'SELECT item_id FROM inventory WHERE player_id=? AND quantity>0', (player,)) if r[0] in valid}
        # Preserve collection unlocks from older season occurrences and legacy
        # saves even if their inventory read model missed the carried-out relic.
        for row in self.store.db.execute('SELECT state_json FROM season_state WHERE player_id=?', (player,)):
            result.update(i for i in json.loads(row[0]).get('relics', []) if i in valid)
        return sorted(result)

    def talent_values(self, player):
        state = self.state(player)
        return {'code': 10, 'leftPoint': state['points'], 'info': [encode('TalentInfo',
            {'id': i, 'level': state['talents'].get(str(i), 0)}) for i in self.talents]}

    def attributes(self, player):
        if not self.active(player):
            return {}
        state = self.state(player)
        bonus = Counter()
        for tid, level in state['talents'].items():
            row = self.talents[int(tid)]
            for attr in row['AttribId']:
                if attr:
                    bonus[attr] += level * row['LevelValue']
        return dict(bonus)

    def battle_talents(self, player):
        if not self.active(player):
            return []
        state = self.state(player)
        allocated = [(tid, row) for tid, row in self.talents.items() if state['talents'].get(str(tid), 0)]
        if not allocated:
            allocated = [(min(self.talents), self.talents[min(self.talents)])]
        return [encode('TalentAttr', {'id': tid, 'level': state['talents'].get(str(tid), 0),
            'upValue': row.get('LevelValue', 0) * state['talents'].get(str(tid), 0), 'attrId': row.get('AttribId') or [0],
            'passiveId': row.get('PassiveID', 0)}) for tid, row in allocated]

    def operate(self, player, op, req, token):
        self.require(player)
        state = self.state(player)
        if op == 'QueryBattlePassInfo':
            return self.base_values(player)
        if op == 'BattlePassMissionInfo':
            return self.mission_values(player)
        if op == 'BuyBattlePassLevel':
            count = req.get('buyCount', 0)
            if type(count) is not int or not 1 <= count <= self.bp['LevelBuyMax'] - state['bought_levels']:
                raise UnresolvedEconomy('invalid purchased level count')
            if state['exp'] // self.bp['LevelExp'] + count > max(r['Level'] for r in self.levels.values()):
                raise UnresolvedEconomy('season level limit')
            self.spend(player, 1237902, count * self.bp['LevelPrice'])
            state['bought_levels'] += count
            self.write(player, state)
            self.e._grant(player, f'season:{self.instance}:buy-level:{token}', {self.EXP_ITEM: count * self.bp['LevelExp']})
            return {'code': 10, 'baseInfo': encode('BattlePassBaseInfo', self.base_info(self.state(player)))}
        if op == 'SignBattlePass':
            day = task_period(1, int(self.e.clock()))[0]
            if state['sign_day'] == day:
                raise UnresolvedEconomy('season sign already collected')
            state['sign_day'] = day
            state['stats']['signs'] = state['stats'].get('signs', 0) + 1
            self.write(player, state)
            _, rewards = self.grant(player, 'sign', day, [self.bp['DailyLoginExp'][2]])
            return {'code': 10, 'rewardData': rewards,
                    'baseInfo': encode('BattlePassBaseInfo', self.base_info(self.state(player)))}
        if op == 'ReceiveBattlePass':
            ids = req.get('configIds', [])
            available = [i for i, row in self.levels.items() if row['ReceiveExp'] <= state['exp'] and str(i) not in state['levels_claimed']]
            ids = ids or available
            if not ids or len(ids) != len(set(ids)) or any(i not in available for i in ids):
                raise UnresolvedEconomy('season level reward unavailable')
            groups = []
            for i in ids:
                groups.extend(self.levels[i][f'GiftGroup{tier:02d}'] for tier in (1, 2, 3) if self.levels[i].get(f'GiftGroup{tier:02d}'))
                state['levels_claimed'][str(i)] = 3
            self.write(player, state)
            _, reward = self.grant(player, 'level', ':'.join(map(str, sorted(ids))), groups)
            return {'code': 10, 'rewardData': reward, 'rewardInfo': [encode('BattlePassRewardInfo',
                {'id': i, 'lastReceivedType': 3}) for i in ids]}
        if op == 'RefreshBattleTask':
            tid = req.get('taskId')
            if tid not in state['selected_tasks'] or tid in state['task_claimed'] or not self.tasks[tid].get('GroupID'):
                raise UnresolvedEconomy('only current random season tasks can be refreshed')
            index = min(state['refreshes'], len(self.bp['BpTaskRefresh']) - 1)
            self.spend(player, 1237902, self.bp['BpTaskRefresh'][index])
            choices = [i for i, row in self.tasks.items() if row.get('GroupID') == self.tasks[tid]['GroupID']
                       and i != tid and i not in state['task_claimed'] and self.task_available(i)
                       and not state.setdefault('task_stages', {}).get(str(i), 0)]
            if not choices:
                raise UnresolvedEconomy('season task pool has no alternative')
            rng = random.Random(token)
            replacement = rng.choice(choices)
            state['selected_tasks'][state['selected_tasks'].index(tid)] = replacement
            state['tasks'].pop(str(tid), None)
            state['tasks'].pop(str(replacement), None)
            state['refreshes'] += 1
            state['stats']['task_refresh'] = state['stats'].get('task_refresh', 0) + 1
            self.write(player, state)
            return {'code': 10, 'taskId': replacement, 'baseInfo': encode('BattlePassBaseInfo', self.base_info(state))}
        if op in ('BattlePassTalentInfo', 'BattlePassTalentLevel', 'BattlePassTalentReset'):
            if op == 'BattlePassTalentLevel':
                changes = [SEASON_SCHEMAS['TalentLevel'].decode(raw) for raw in req.get('info', [])]
                if not changes or len({r['id'] for r in changes}) != len(changes):
                    raise UnresolvedEconomy('invalid talent change list')
                # TalentLevel.level is the unsaved increment (curPoint), not
                # the resulting level. Native RefreshLevelNum adds it to the
                # module's saved level; OnBtnAddTalentView sends only curPoint.
                total = 0
                for change in changes:
                    tid, added = change['id'], change['level']
                    before = state['talents'].get(str(tid), 0)
                    if (tid not in self.talents or type(added) is not int
                            or added < 0 or before + added > self.talents[tid]['MaxLevel']):
                        raise UnresolvedEconomy('invalid talent increment')
                    total += added
                if total > state['points']:
                    raise UnresolvedEconomy('insufficient talent points')
                for change in changes:
                    key = str(change['id'])
                    state['talents'][key] = state['talents'].get(key, 0) + change['level']
                state['points'] -= total
                if total:
                    state['stats']['talent_add'] = state['stats'].get('talent_add', 0) + 1
                    self.write(player, state)
            elif op == 'BattlePassTalentReset':
                tid = req.get('id')
                level = state['talents'].get(str(tid), 0)
                if tid not in self.talents or not level:
                    raise UnresolvedEconomy('talent not allocated')
                self.spend(player, 1237902, level * self.activities[0]['ActivityParam3'][0])
                state['points'] += level
                state['talents'][str(tid)] = 0
                state['stats']['talent_reset'] = state['stats'].get('talent_reset', 0) + 1
                self.write(player, state)
                return {'code': 10, 'leftPoint': state['points'], 'update': encode('TalentInfo', {'id': tid, 'level': 0})}
            return self.talent_values(player)
        if op == 'BattlepassArtifactOpt':
            return self.artifact.operate(player, req, token)
        if op == 'SeasonRelic':
            return {'code': 10, 'collectedRelic': self.owned_relics(player) or [0]}
        if op.startswith('SeasonAchv'):
            rows = self.achievement_values(player)
            points = sum(row['status'] > 0 for row in rows)
            if op == 'SeasonAchvOverView':
                return {'code': 10, 'achvPoint': points, 'maxAchvPoint': len(rows), 'achvPointRewardList': [2 if i in state['point_claimed'] else 1 if points >= n else 0
                        for i, n in enumerate(self.e.catalog['task_control']['CompleteBpAchievementNumber'])],
                    'achvOverViewData': [encode('SeasonAchvOverViewData', {'achvType': group,
                        'achvProgress': sum(r['status'] > 0 for r in rows if ev(self.achievements[r['achvId']]['AchievementGroup']) == group)})
                        for group in (1, 2, 3)]}
            if op == 'SeasonAchvDetialData':
                group, start, end = req.get('achvType'), req.get('startIndex', 0), req.get('endIndex', 30)
                if group not in (1, 2, 3) or not 0 <= start <= end or end - start > 30:
                    raise UnresolvedEconomy('invalid season achievement page')
                page = [r for r in rows if ev(self.achievements[r['achvId']]['AchievementGroup']) == group][start:end]
                return {'code': 10 if page else 97, 'achvType': group, 'achvDataList': [encode('SeasonAchvData', r) for r in page]}
            if op == 'SeasonAchvReward':
                aid = req.get('achvId')
                achieved = next((r for r in rows if r['achvId'] == aid), None)
                state = self.state(player)
                if not achieved or achieved['status'] != 1:
                    raise UnresolvedEconomy('season achievement unavailable')
                previous = self.achievements[aid].get('LastAchievement')
                if previous and previous not in state['achievements_claimed']:
                    raise UnresolvedEconomy('previous achievement reward not collected')
                state['achievements_claimed'].append(aid)
                self.write(player, state)
                _, reward = self.grant(player, 'achievement', aid, self.achievements[aid]['GiftGroup'])
                return {'code': 10, 'achvId': aid, 'status': 2, 'rewardData': reward}
            if op == 'SeasonAchvPointReward':
                # ``achvPointId`` 是里程碑的「点数阈值」(5/10/20/40/60), 不是下标。
                # BattlePassAchievementModule.RequestPointsReward (0x1809500) 会先取
                # TaskControlManager.GetItem(5)[+0x88] (CompleteBpAchievementNumber), 把
                # get_Item(index) 得到的阈值数值写进 C2L_SeasonAchvPointReward 后才发送;
                # 回包处理 BattlePassAchievementModule.GetPointsReward (0x180C05C) 也把回包
                # 的同一字段与这张阈值表逐项比较。原生 AchievementModule 的同名函数
                # (0x1319DE4) 才是直接发下标 —— 两个模块语义不同, 本协议按阈值数值取值,
                # 同时保留下标写法兼容 (两个集合不相交, 映射唯一)。
                value = req.get('achvPointId', 0)
                state = self.state(player)
                control = self.e.catalog['task_control']
                targets = control['CompleteBpAchievementNumber']
                index = targets.index(value) if type(value) is int and value in targets else value
                if (type(index) is not int or index not in range(len(targets))
                        or points < targets[index] or index in state['point_claimed']):
                    raise UnresolvedEconomy('season achievement-point reward unavailable')
                state['point_claimed'].append(index)
                self.write(player, state)
                _, reward = self.grant(player, 'achievement-point', index,
                    [control['CompleteBpAchievementNumberGiftGroup'][index]])
                return {'code': 10, 'status': 2, 'achvPointId': targets[index], 'rewardData': reward}
            raise UnresolvedEconomy('unknown achievement operation')
        if op == 'BattlePassHistoryInfo':
            return {'code': 10, 'historyInfo': [encode('BattlePassHistoryInfo', {
                'activityId': self.ACTIVITY, 'relicCount': len(state['relics']),
                'taskFinishCount': state['stats'].get('tasks', 0), 'battlePassLv': state['exp'] // self.bp['LevelExp'],
                'finishAchiveId': state['achievements_claimed'] or [0], 'passCount': state['stats'].get('passes', 0),
                'passTotalTime': state['stats'].get('pass_time', 0)})]}
        raise UnresolvedEconomy('season operation lacks a recovered gameplay contract')

    def pushes(self, player):
        if not self.active(player):
            return ()
        with self.e.transaction():
            state = self.state(player)
            task_values = self.task_values(player)
            signature = (tuple(task_values['taskList']), tuple(task_values['boxList']), state.get('weekly_active', 0), state['week'], state['exp'], state['points'], state['sign_day'], state['refreshes'],
                         tuple(sorted(state['levels_claimed'].items())))
            if self.sent_state.get(player) == signature:
                return ()
            previous_ids = self.sent_task_ids.get(player)
            current_ids = tuple(state['selected_tasks'])
            self.sent_task_ids[player] = current_ids
            task_message = (OutboundMessage('L2C_GameTask', task_values)
                            if previous_ids is not None and previous_ids != current_ids else
                            OutboundMessage('L2C_TaskUpdate', {'type': self.TASK_KIND, 'taskList': task_values['taskList']}))
            self.sent_state[player] = signature
            # UpgradeBattlePass is the purchase handler and unconditionally opens
            # the award popup. Refresh the normal query consumer instead.
            return (OutboundMessage('L2C_QueryBattlePassInfo', self.base_values(player)),
                OutboundMessage('L2C_BattlePassTalentUpdate', {'code': 10, 'leftPoint': state['points']}),
                task_message, OutboundMessage('L2C_TreasureBoxUpdate', {'type': self.TASK_KIND, 'boxList': task_values['boxList']}))

    def scene_params(self, player):
        from x2server.messages.activity import encode as activity_encode
        self.require(player)
        cleared = {r[0] for r in self.store.db.execute('SELECT section_id FROM season_runs '
            'WHERE player_id=? AND instance_id=? AND success=1', (player, self.instance))}
        return activity_encode('SceneSectionParam', {'sectionType': 20, 'sectionParam': [
            activity_encode('KeyValuePair_Int32_Int32', {'Key': sid, 'Value': int(sid in cleared)}) for sid in self.sections]})

    def use_item(self, context, packet, req):
        from x2server.messages.economy import ECONOMY_SCHEMAS
        player, item, count = context.session.player_id, req.get('id'), req.get('count', 0)
        result = {'code': 13, 'opt': req.get('opt', 0), 'itemId': item}
        if req.get('opt', 0) != 0 or type(count) is not int or not 1 <= count <= 9999:
            return OutboundMessage('L2C_ItemOpt', result)
        token = hashlib.sha256(f'{context.session.session_id}:{packet.header.request_id}:season-item'.encode() + packet.body).hexdigest()
        try:
            with self.e.transaction():
                self.require(player)
                cached = self.store.db.execute('SELECT response FROM item_opt_receipts WHERE player_id=? AND request_key=?',
                                              (player, token)).fetchone()
                if cached:
                    result = ECONOMY_SCHEMAS['L2C_ItemOpt'].decode(cached[0])
                else:
                    self.spend(player, item, count)
                    rewards = self.e._grant(player, f'season-item:{self.instance}:{token}', {item: count})
                    result.update(code=10, rewardData=self.e.reward_bytes(rewards))
                    self.store.db.execute('INSERT INTO item_opt_receipts VALUES (?,?,?)',
                        (token, player, ECONOMY_SCHEMAS['L2C_ItemOpt'].encode(result)))
        except UnresolvedEconomy:
            pass
        return OutboundMessage('L2C_ItemOpt', result, before_response=self.pushes(player), pushes=self.e.pushes(player))

    async def handle(self, context, packet):
        player = context.session.player_id
        if player is None:
            raise ProtocolError('season request before login')
        name = CORE_MESSAGE_REGISTRY.name_for(packet.message_id)
        req = SEASON_SCHEMAS[name].decode(packet.body)
        response = name.replace('C2L_', 'L2C_', 1)
        token = hashlib.sha256(f'{context.session.session_id}:{packet.header.request_id}:{name}'.encode() + packet.body).hexdigest()
        queries = {'QueryBattlePassInfo', 'BattlePassMissionInfo', 'BattlePassTalentInfo',
                   'SeasonRelic', 'SeasonAchvOverView', 'SeasonAchvDetialData', 'BattlePassHistoryInfo'}
        try:
            with self.e.transaction():
                self.require(player)
                cached = self.store.db.execute('SELECT message,response FROM season_receipts WHERE player_id=? AND instance_id=? AND request_key=?',
                                              (player, self.instance, token)).fetchone()
                if cached and name[4:] not in queries:
                    if cached['message'] != response:
                        raise UnresolvedEconomy('season receipt type mismatch')
                    values = SEASON_SCHEMAS[response].decode(cached['response'])
                else:
                    values = self.operate(player, name[4:], req, token)
                    encoded = encode(response, values)
                    values = SEASON_SCHEMAS[response].decode(encoded)
                    if name[4:] not in queries:
                        self.store.db.execute('INSERT INTO season_receipts VALUES (?,?,?,?,?)',
                                             (player, self.instance, token, response, encoded))
        except (UnresolvedEconomy, ValueError, KeyError, TypeError, IndexError) as exc:
            logging.getLogger('x2.season').info('season rejected player=%s operation=%s reason=%s', player, name, exc)
            values = SEASON_SCHEMAS[response].decode(encode(response, {'code': 13,
                **{k: v for k, v in req.items() if k in {f.name for f in SEASON_SCHEMAS[response].fields}}}))
        if name == 'C2L_BattlepassArtifactOpt' and values.get('code') == 10:
            return OutboundMessage(response, values, before_response=(
                *self.e.pushes(player), self.artifact.hero_message(player), *self.pushes(player)))
        return OutboundMessage(response, values, before_response=self.pushes(player) if name[4:] not in queries else (),
                               pushes=self.e.pushes(player) if values.get('code') == 10 and name[4:] not in queries else ())
