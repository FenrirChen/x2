"""Recovered activity gameplay; mutations share the economy transaction."""
from collections import Counter
import json
import secrets

from x2server.messages.activity import encode
from x2server.messages.economy import TASK, TREASURE_BOX
from .activity_rotation import ActivityRotation
from .economy import UnresolvedEconomy


def enum(value):
    return value.get('value', 0) if isinstance(value, dict) else value or 0


class ActivityService:
    def __init__(self, economy):
        self.economy, self.store = economy, economy.store
        self.rotation = ActivityRotation(self.store, economy.clock)
        self.tables = self.rotation.catalog['tables']
        self.conditions = {r['TaskConditionID']: r for r in self.tables['TaskCondition']}
        self.tasks = {r['ChallengeTaskID']: r for r in self.tables['ActivityTask']}
        self.food_tasks = {r['ChallengeTaskID']: r for r in self.tables['NewYearFoodTask']}
        self.boxes = {r['BoxID']: r for r in self.tables['ActivityBox']}
        self.box_goods = {r['GoodsGroupID']: r for r in self.tables['ActivityBoxGoods']}
        self.chapters = {r['ID']: r for r in self.tables['ActivityDungeon'] + self.tables['DailyDungeon']}
        self.sections = {r['SectionID']: r for r in self.tables['SectionTable']}

    def period(self, player):
        period = self.rotation.at()
        if period is None or self.store.get(player)['snapshot']['level'] < 17:
            raise UnresolvedEconomy('activity is closed or level is too low')
        return period

    def require(self, player, activity, kind=None):
        period = self.period(player)
        row = self.rotation.activity(activity, period)
        if row is None or kind is not None and enum(row['ActivityType']) != kind:
            raise UnresolvedEconomy('activity is not in the current period')
        return period, row

    def source(self, period, category, key):
        return f'activity:{period.index}:{category}:{key}'

    def obtained(self, player, period, rewards, key):
        if not self.rotation.once(player, period, f'obtained:{key}'):
            return
        for item, count in rewards.items():
            if count > 0:
                previous = self.rotation.get(player, period, 'obtained-item', item, 0)
                self.rotation.put(player, period, 'obtained-item', item, previous + count)
                kind = next((enum(c['CompleteType']) for c in self.conditions.values()
                             if c['CompleteType'].get('enum') == 'E_GetMoney'), None)
                if kind is not None:
                    self.event(player, f'get:{key}:{item}', kind, item, count, period=period)

    def grant(self, player, period, category, key, groups):
        rewards = self.economy.gifts(groups, allow_daily_random=True)
        source = self.source(period, category, key)
        rewards = self.economy._grant(player, source, rewards)
        self.obtained(player, period, rewards, source)
        return rewards

    def yuexi_preview_end(self, period):
        row = self.rotation.of_type(1, period) if period.theme['group'] == 99 else None
        # The client checks the next Beijing day refresh after a claim. A
        # developer review may start mid-day; do not replay that same plot at
        # midnight when only one recovered story exists.
        return min(period.end, ((period.start + 8 * 3600) // 86400
                   + len(row['ActivityParam1'])) * 86400 - 8 * 3600) if row else period.end

    def query_activity(self, player):
        period = self.rotation.at()
        if period is None:
            return {'code': 10}
        rows = []
        for row in period.theme['activities']:
            end = self.yuexi_preview_end(period) if period.theme['group'] == 99 and enum(row['ActivityType']) == 1 else period.end
            values = {'actId': row['ActivityID'], 'state': 1,
                      'activityParentType': enum(row['ActivityParentType']),
                      'actType': enum(row['ActivityType']), 'startTime': period.start,
                      'endTime': end, 'openLever': row['OpenLever'],
                      'activityShow': row.get('ActivityShow', 0),
                      'activityGroup': row['ActivityGroup'], 'activityName': row.get('ActivityName', 0),
                      'activityDescription': row.get('ActivityDescription', ''),
                      'activityTaps': row.get('ActivityTaps', ''),
                      'openType': enum(row.get('OpenType')), 'openParam': row.get('OpenParam', []) or [0],
                      'activityDataItems': [encode('ActivityDataItem', {'index': 0,
                          'itemParams': [encode('ItemData', {'id': 0, 'num': 0})]})]}
            values['state'] = int(self.economy.clock() < end)
            for index in range(1, 5):
                values[f'param{index}'] = row.get(f'ActivityParam{index}', []) or [0]
            values['activityReward'] = row.get('ActivityReward', []) or [0]
            rows.append(encode('ActivityData', values))
        return {'code': 10, 'activityData': rows}

    def task_catalog(self, period, kind, activity=0):
        catalog = self.food_tasks if kind == 20 else self.tasks if kind == 9 else {}
        owned = {a['ActivityID'] for a in period.theme['activities']}
        return {tid: r for tid, r in catalog.items() if r['ActivityID'] in owned
                and (not activity or r['ActivityID'] == activity) and enum(r['IsUse']) == 1}

    def task_namespace(self, task):
        # Food tasks explicitly distinguish once-only and daily tasks.
        if enum(task.get('TaskType')) == 2:
            return f'tasks:day:{(int(self.economy.clock()) + 8 * 3600) // 86400}'
        return 'tasks'

    def event(self, player, key, condition_type, value=0, amount=1, value2=0, period=None):
        if amount <= 0:
            return
        period = period or self.rotation.at()
        if period is None:
            return
        if not self.rotation.once(player, period, f'task:{key}'):
            return
        for kind in (9, 20):
            for tid, task in self.task_catalog(period, kind).items():
                condition = self.conditions[task['TaskConditionID']]
                if enum(condition['CompleteType']) != condition_type:
                    continue
                for column, observed in (('CompleteValue1', value), ('CompleteValue2', value2)):
                    choices = condition.get(column, [])
                    if choices and choices != [0] and observed not in choices:
                        break
                else:
                    namespace = self.task_namespace(task)
                    state = self.rotation.get(player, period, namespace, tid, {'progress': 0, 'claimed': False})
                    state['progress'] = min(condition['CompleteNum'], state['progress'] + amount)
                    self.rotation.put(player, period, namespace, tid, state)

    def task_values(self, player, kind, activity=0):
        period = self.period(player)
        tasks = []
        for tid, task in self.task_catalog(period, kind, activity).items():
            namespace = self.task_namespace(task)
            state = self.rotation.get(player, period, namespace, tid, {'progress': 0, 'claimed': False})
            predecessor = task.get('LastTask')
            unlocked = not predecessor or self.rotation.get(player, period, namespace, predecessor, {}).get('claimed', False)
            status = 4 if state['claimed'] else 3 if unlocked and state['progress'] >= self.conditions[task['TaskConditionID']]['CompleteNum'] else 2 if unlocked else 1
            tasks.append(TASK.encode({'taskId': tid, 'taskStatus': status,
                'taskProgress': state['progress'], 'taskRefreshTime': period.end,
                'activityId': task['ActivityID'], 'stage': task.get('TaskGroupID', 0),
                'finishTimes': int(state['claimed'])}))
        boxes = []
        for box in self.tables['ActivityTaskBox']:
            if self.rotation.activity(box['ActivityID'], period) is None or activity and box['ActivityID'] != activity:
                continue
            key = f"{box['ActivityID']}:{box['BoxID']}"
            boxes.append(TREASURE_BOX.encode({'boxId': box['BoxID'], 'activityId': box['ActivityID'],
                'pickStatus': int(bool(self.rotation.get(player, period, 'task-box', key, False)))}))
        return {'code': 10, 'type': kind, 'activityId': activity,
                'taskList': tasks, 'boxList': boxes}

    def claim_task(self, player, task_id, kind, activity=0):
        period = self.period(player)
        result = {'code': 13, 'taskId': task_id, 'type': kind, 'activityId': activity}
        task = self.task_catalog(period, kind, activity).get(task_id)
        if task is None:
            return result
        namespace = self.task_namespace(task)
        with self.economy.transaction():
            state = self.rotation.get(player, period, namespace, task_id, {'progress': 0, 'claimed': False})
            if state['claimed'] or state['progress'] < self.conditions[task['TaskConditionID']]['CompleteNum']:
                return result
            predecessor = task.get('LastTask')
            if predecessor and not self.rotation.get(player, period, namespace, predecessor, {}).get('claimed'):
                return result
            rewards = self.grant(player, period, 'task', f'{namespace}:{task_id}', [task['GiftGroup']])
            state['claimed'] = True
            self.rotation.put(player, period, namespace, task_id, state)
            result.update(code=10, activityId=task['ActivityID'], rewardData=self.economy.reward_bytes(rewards))
        return result

    def claim_task_box(self, player, activity, box_id):
        period, _ = self.require(player, activity)
        box = next((r for r in self.tables['ActivityTaskBox'] if r['ActivityID'] == activity and r['BoxID'] == box_id), None)
        if box is None or enum(box['CompeteType']) != 1:
            raise UnresolvedEconomy('unknown activity task box')
        with self.economy.transaction():
            key = f'{activity}:{box_id}'
            if self.rotation.get(player, period, 'task-box', key, False):
                raise UnresolvedEconomy('task box already claimed')
            completed = sum(self.rotation.get(player, period, self.task_namespace(t), tid, {}).get('progress', 0)
                >= self.conditions[t['TaskConditionID']]['CompleteNum']
                for tid, t in self.task_catalog(period, 9, activity).items())
            if completed < box['ActivityParam1']:
                raise UnresolvedEconomy('not enough completed tasks')
            rewards = self.grant(player, period, 'task-box', key, [box['GiftID']])
            self.rotation.put(player, period, 'task-box', key, True)
            return rewards

    def admission(self, player, section):
        if section not in self.rotation.section_groups:
            return None
        period = self.period(player)
        if self.rotation.section_groups[section] != period.theme['group']:
            raise UnresolvedEconomy('activity is not open')
        row = self.sections[section]
        chapter = self.chapters.get(row.get('ChapterID'), {})
        previous = self.chapters.get(chapter.get('PreChapter'))
        if previous and not all(self.rotation.get(player, period, 'clear', sid, 0)
                                for sid in previous.get('SectionID', [])):
            raise UnresolvedEconomy('previous activity chapter is not cleared this period')
        if enum(row.get('OpenType')) == 2 and row.get('OpenParam') in self.sections:
            if not self.rotation.get(player, period, 'clear', row['OpenParam'], 0):
                raise UnresolvedEconomy('previous activity section is not cleared this period')
        return period

    def frost_values(self, player):
        period = self.period(player)
        row = self.rotation.of_type(13, period)
        if row is None:
            raise UnresolvedEconomy('winter activity is not open')
        chapters = []
        for cid in row['ActivityParam1']:
            stages = self.chapters[cid].get('SectionID', [])
            passed = [sid for sid in stages if self.rotation.get(player, period, 'clear', sid, 0)]
            chapters.append(encode('ActivityShuangHan', {'chapterId': cid,
                'storyPlayState': bool(self.rotation.get(player, period, 'pv', cid, False)),
                'lastPassMissionId': passed[-1] if passed else 0}))
        return {'code': 10, 'activityInfo': chapters}

    def play_frost_story(self, player, chapter):
        period = self.period(player)
        row = self.rotation.of_type(13, period)
        if row is None or chapter not in row['ActivityParam1']:
            raise UnresolvedEconomy('winter chapter is not open')
        previous = self.chapters.get(self.chapters[chapter].get('PreChapter'))
        if previous and not all(self.rotation.get(player, period, 'clear', sid, 0)
                                for sid in previous.get('SectionID', [])):
            raise UnresolvedEconomy('previous activity chapter is not cleared this period')
        self.rotation.put(player, period, 'pv', chapter, True)
        stages = self.chapters[chapter].get('SectionID', [])
        passed = [sid for sid in stages if self.rotation.get(player, period, 'clear', sid, 0)]
        return {'code': 10, 'activityInfo': encode('ActivityShuangHan', {'chapterId': chapter,
                'storyPlayState': True, 'lastPassMissionId': passed[-1] if passed else 0})}

    def complete(self, player, uuid, section, success):
        period = self.rotation.run_period(player, uuid)
        if period is None:
            return
        row = self.store.db.execute('SELECT section_id,settled FROM activity_runs WHERE uuid=?', (uuid,)).fetchone()
        if row['section_id'] != section or row['settled']:
            raise UnresolvedEconomy('activity run mismatch or replay')
        if success:
            count = self.rotation.get(player, period, 'clear', section, 0)
            self.rotation.put(player, period, 'clear', section, count + 1)
            self.event(player, f'clear:{uuid}', 3, section, 1, period=period)
        self.store.db.execute('UPDATE activity_runs SET settled=1 WHERE uuid=?', (uuid,))

    def pov_chapter_rewards(self, player, section):
        """Called only by successful, validated battle settlement in its transaction."""
        period = self.rotation.at()
        if period is None:
            return {}
        for chapter in self.tables.get('POVChapterInfo', []):
            if (section not in chapter['StageID']
                    or self.rotation.activity(chapter['UnlockActiviyID'], period) is None):
                continue
            self.rotation.put(player, period, 'pov-clear', section, True)
            if (all(self.rotation.get(player, period, 'pov-clear', sid, False)
                    for sid in chapter['StageID'])
                    and self.rotation.once(player, period, f"pov-chapter:{chapter['ChapterID']}")):
                rewards = self.economy.gifts([chapter['ClearReward']], allow_daily_random=True)
                self.obtained(player, period, rewards, f"pov-chapter:{chapter['ChapterID']}")
                return rewards
        return {}

    def mission_values(self, player, activity):
        period, row = self.require(player, activity)
        missions = []
        for chapter in row.get('ActivityParam1', []):
            config = self.chapters.get(chapter)
            if config is None:
                continue
            stages = config.get('SectionID', [])
            passed = [s for s in stages if self.rotation.get(player, period, 'clear', s, 0)]
            challenges = [s for s in config.get('ChallengeLevel', []) if self.rotation.get(player, period, 'clear', s, 0)]
            missions.append(encode('ActivityMissionData', {'chapterId': chapter,
                'lastPastMissionId': passed[-1] if passed else 0, 'pastChallengeId': challenges or [0],
                'playPv': bool(self.rotation.get(player, period, 'pv', chapter, False)), 'passTime': 0}))
        return {'code': 10, 'activityId': activity, 'missionData': missions,
                  # Native OnHandleActivityMissionData sends branch=1 when
                  # branch=0; the wire uses one-based chapter choices.
                  'branch': self.rotation.get(player, period, 'branch', activity,
                      1 if len(row.get('ActivityParam1', [])) == 1 else 0)}

    def unlocked_pools(self, player, period, row):
        """The native pool list contains unlocked stages, not the full catalog."""
        unlocked = []
        for bid in row['ActivityParam1']:
            predecessor = next((self.boxes[previous] for previous in row['ActivityParam1']
                                if self.boxes[previous].get('NextBox') == bid), None)
            if predecessor:
                if predecessor['BoxID'] not in unlocked:
                    continue
                counts = self.rotation.get(player, period, 'pool', predecessor['BoxID'], {})
                if any(counts.get(str(gid), 0) < required for gid, required in
                       zip(predecessor['UnlockGroupID'], predecessor['UnlockGroupTimes'])):
                    continue
            unlocked.append(bid)
        return unlocked

    def pool_values(self, player, activity):
        period, row = self.require(player, activity, 26)
        infos = []
        # RefreshRewardPool populates the client's unlocked-ID list from this
        # response; GetDefalutSelectId selects its last nonempty stage.
        for bid in self.unlocked_pools(player, period, row):
            box = self.boxes[bid]
            counts = self.rotation.get(player, period, 'pool', bid, {})
            pairs = [encode('KeyValuePair_Int32_Int32', {'Key': gid, 'Value': counts.get(str(gid), 0)})
                     for gid in box['GoodsGroupId']]
            infos.append(encode('RewardPoolInfo', {'rewardPoolId': bid, 'goodsIdCountPair': pairs}))
        return {'code': 10, 'activityId': activity, 'rewardPoolInfos': infos}

    def spend(self, player, period, item, amount, key):
        if type(amount) is not int or amount <= 0:
            raise UnresolvedEconomy('invalid activity cost')
        if item in self.economy.CURRENCIES:
            state = self.store.get(player)
            field = self.economy.CURRENCIES[item]
            if state['snapshot'].get(field, 0) < amount:
                raise UnresolvedEconomy('not enough currency')
            state['snapshot'][field] -= amount
            self._save_balance(player, state)
        elif item == 1237900:
            state = self.store.get(player)
            if state['snapshot'].get('mobility', {}).get('power', 0) < amount:
                raise UnresolvedEconomy('not enough power')
            state['snapshot']['mobility']['power'] -= amount
            self._save_balance(player, state)
        else:
            changed = self.store.db.execute('''UPDATE inventory SET quantity=quantity-?
                WHERE player_id=? AND item_id=? AND quantity>=?''', (amount, player, item, amount))
            if not changed.rowcount:
                raise UnresolvedEconomy('not enough activity items')
        # E_ConsumeMaterial is defined in TaskCondition, never a guessed enum.
        condition_type = next((enum(c['CompleteType']) for c in self.conditions.values()
                               if c['CompleteType'].get('enum') == 'E_ConsumeMaterial'), None)
        if condition_type is not None:
            self.event(player, key, condition_type, item, amount, period=period)

    def _save_balance(self, player, state):
        # PlayerStore.save_snapshot commits; never call it inside a purchase.
        from .store import validate_snapshot
        validate_snapshot(state['snapshot'])
        changed = self.store.db.execute('''UPDATE players SET snapshot=?,revision=revision+1
            WHERE id=? AND revision=?''',
            (json.dumps(state['snapshot'], ensure_ascii=False, allow_nan=False), player, state['revision']))
        if not changed.rowcount:
            raise UnresolvedEconomy('player revision conflict')

    def draw_pool(self, player, activity, pool_id, count, key):
        period, row = self.require(player, activity, 26)
        if type(count) is not int or not 1 <= count <= 100 or pool_id not in row['ActivityParam1']:
            raise UnresolvedEconomy('invalid draw count or pool')
        box = self.boxes[pool_id]
        with self.economy.transaction():
            if not self.rotation.once(player, period, f'pool-draw:{key}'):
                raise UnresolvedEconomy('duplicate pool draw')
            if pool_id not in self.unlocked_pools(player, period, row):
                raise UnresolvedEconomy('reward pool is locked')
            counts = self.rotation.get(player, period, 'pool', pool_id, {})
            rewards = Counter()
            for _ in range(count):
                eligible = [(gid, weight) for gid, weight in zip(box['GoodsGroupId'], box['GroupProbability'])
                            if counts.get(str(gid), 0) < self.box_goods[gid]['BuyTimes'] and weight > 0]
                if not eligible:
                    raise UnresolvedEconomy('reward pool exhausted')
                ticket = secrets.randbelow(sum(weight for _, weight in eligible))
                for gid, weight in eligible:
                    ticket -= weight
                    if ticket < 0:
                        break
                counts[str(gid)] = counts.get(str(gid), 0) + 1
                goods = self.box_goods[gid]
                rewards[goods['ItemID']] += goods['ItemNum']
            self.spend(player, period, box['CostID'], box['CostNum'] * count, f'pool-cost:{key}')
            rewards = self.economy._grant(player, self.source(period, 'draw', key), dict(rewards))
            self.obtained(player, period, rewards, self.source(period, 'draw', key))
            self.rotation.put(player, period, 'pool', pool_id, counts)
            return {**self.pool_values(player, activity), 'rewardPoolId': pool_id,
                    'rewardData': self.economy.reward_bytes(rewards)}

    def pre_notice(self, player, activity_type, claim=False):
        period = self.period(player)
        expected = 2 if period.theme['group'] == 7 else 1 if period.theme['group'] == 99 else 3
        if activity_type != expected:
            raise UnresolvedEconomy('incorrect activity family')
        row = next(a for a in period.theme['activities'] if enum(a['ActivityType']) in (1, 15, 24))
        state = self.rotation.get(player, period, 'pre-notice', row['ActivityID'], 0)
        if activity_type == 1:
            state = self.rotation.get(player, period, 'dialogue', 0, state)
        # Native ServerTime.GetRefreshTime (0x3e5227c) returns the next
        # 05:00 UTC boundary (13:00 Beijing) after this timestamp. A completed
        # single intro must remain complete across that boundary throughout
        # its period; acknowledging an old timestamp otherwise replays it.
        now = int(self.economy.clock())
        refresh_start = ((now - 5 * 3600) // 86400) * 86400 + 5 * 3600
        completed_floor = max(period.start, refresh_start)
        if state and state < completed_floor:
            state = completed_floor
            self.rotation.put(player, period, 'pre-notice', row['ActivityID'], state)
            if activity_type == 1:
                self.rotation.put(player, period, 'dialogue', 0, state)
        result = {'code': 10, 'activityType': activity_type, 'lastPreNoticSec': state}
        if claim:
            with self.economy.transaction():
                # This is a completion acknowledgement as well as a reward
                # claim. A repeated acknowledgement must unblock the client.
                if state:
                    return result
                if activity_type == 1 and self.economy.clock() >= self.yuexi_preview_end(period):
                    raise UnresolvedEconomy('preview already claimed')
                groups = row.get('ActivityReward') if activity_type in (1, 2) else row.get('ActivityParam2')
                if not groups:
                    raise UnresolvedEconomy('missing preview gift')
                rewards = self.grant(player, period, 'pre-notice', row['ActivityID'], groups)
                state = int(self.economy.clock())
                self.rotation.put(player, period, 'pre-notice', row['ActivityID'], state)
                if activity_type == 1:
                    self.rotation.put(player, period, 'dialogue', 0, state)
                result.update(lastPreNoticSec=state, rewardData=self.economy.reward_bytes(rewards))
        return result
