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
                    item_row = next((r for r in self.tables['Item'] if r['ItemID'] == item), {})
                    currency = item_row.get('EffData', []) if enum(item_row.get('ItemType')) == 16 else []
                    if len(currency) == 1:
                        self.event(player, f'get:{key}:{item}', kind, currency[0], count, period=period)

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
        season_rows = (self.economy.season.activity_values()
                       + self.economy.extra_drop.activity_values(player))
        if period is None:
            return {"code": 10, "activityData": season_rows}
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
        return {'code': 10, 'activityData': rows + season_rows}

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

    def battle_kills(self, player, run, units, period=None):
        period = period or self.rotation.run_period(player, run) or self.rotation.at()
        if period is None:
            return
        for unit, count in units.items():
            key = f'kill-unit:{run}:{unit}'
            old = self.rotation.get(player, period, 'event-progress', key, 0)
            if count > old:
                self.event(player, f'{key}:{count}', 1, unit, count - old, period=period)
                self.rotation.put(player, period, 'event-progress', key, count)

    def task_values(self, player, kind, activity=0):
        period = self.period(player)
        self.repair_tasks(player, period)
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
        completed = {}
        for box in self.tables['ActivityTaskBox']:
            if self.rotation.activity(box['ActivityID'], period) is None or activity and box['ActivityID'] != activity:
                continue
            aid = box['ActivityID']
            if not self.task_catalog(period, kind, aid):
                continue
            completed.setdefault(aid, self.completed_task_count(player, period, kind, aid))
            key = f"{box['ActivityID']}:{box['BoxID']}"
            boxes.append(TREASURE_BOX.encode({'boxId': box['BoxID'], 'activityId': box['ActivityID'],
                # RefreshData looks up the static BoxID; claiming instead sends
                # the zero-based index within this activity's box list.
                'pickStatus': 2 if self.rotation.get(player, period, 'task-box', key, False)
                    else int(completed[aid] >= box['ActivityParam1'])}))
        return {'code': 10, 'type': kind, 'activityId': activity,
                'taskList': tasks, 'boxList': boxes}

    def repair_tasks(self, player, period):
        """Recover provable missed currency/kill/survival progress in this period."""
        from x2server.messages.battle import BATTLE_SCHEMAS, CHECKOUT, PROFILE_HERO
        from x2server.messages.core import INT_PAIR
        from .endless import KILLS
        with self.economy.transaction():
            if self.rotation.once(player, period, 'bag-obtained-repair-v1'):
                # The old bag path paid currencies but never notified activity
                # progress. Receipt + committed grant prove a successful use.
                for key, raw in self.store.db.execute('''SELECT r.request_key,g.rewards
                    FROM item_opt_receipts r JOIN economy_grants g
                    ON g.player_id=r.player_id AND g.source='item-opt:' || r.request_key
                    WHERE r.player_id=? AND g.created_at>=? AND g.created_at<?''',
                    (player, period.start, period.end)).fetchall():
                    rewards = {int(i): n for i, n in json.loads(raw).items()
                               if n > 0 and enum(self.economy.items.get(int(i), {}).get('ItemType')) == 16}
                    self.obtained(player, period, rewards, f'bag-use:{key}')
            if not self.rotation.once(player, period, 'task-repair-v1'):
                return
            currencies = Counter()
            for row in self.tables['Item']:
                eff = row.get('EffData', [])
                if enum(row.get('ItemType')) == 16 and len(eff) == 1:
                    currencies[eff[0]] += self.rotation.get(player, period, 'obtained-item', row['ItemID'], 0)
            for tid, task in self.task_catalog(period, 9).items():
                condition = self.conditions[task['TaskConditionID']]
                if enum(condition['CompleteType']) != 38:
                    continue
                value = sum(currencies[c] for c in condition.get('CompleteValue1', []))
                state = self.rotation.get(player, period, 'tasks', tid, {'progress': 0, 'claimed': False})
                state['progress'] = max(state['progress'], min(value, condition['CompleteNum']))
                self.rotation.put(player, period, 'tasks', tid, state)
            if self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='fight_drop_observations'").fetchone():
                for run, raw in self.store.db.execute('''SELECT o.uuid,o.body FROM fight_drop_observations o
                    JOIN activity_runs a ON a.uuid=o.uuid AND a.player_id=o.player_id
                    WHERE a.player_id=? AND a.period=?''', (player, period.index)).fetchall():
                    report = BATTLE_SCHEMAS['C2L_FightDropData'].decode(raw)
                    units = Counter()
                    for raw_detail in KILLS.decode(report.get('killMonster', b'')).get('killDetail', [])[:512]:
                        detail = INT_PAIR.decode(raw_detail)
                        if 0 < detail.get('Value', 0) <= 10000:
                            units[detail.get('Key', 0)] += detail['Value']
                    if sum(units.values()) <= 100000:
                        self.battle_kills(player, run, units, period)
            if self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='battle_checkout_wire'").fetchone():
                for run, section, team, raw, reply in self.store.db.execute('''
                    SELECT a.uuid,a.section_id,e.team_json,w.checkout,r.response FROM activity_runs a
                    JOIN battle_entries e ON e.uuid=a.uuid JOIN battle_checkout_wire w ON w.uuid=a.uuid
                    JOIN battle_receipts r ON r.uuid=a.uuid WHERE a.player_id=? AND a.period=?''',
                    (player, period.index)).fetchall():
                    result = BATTLE_SCHEMAS['L2C_CheckoutMainMission'].decode(reply)
                    if result.get('result') == 10:
                        request = CHECKOUT.decode(raw)
                        units = Counter()
                        for raw_detail in KILLS.decode(request.get('killMonster', b'')).get('killDetail', [])[:512]:
                            detail = INT_PAIR.decode(raw_detail)
                            if 0 < detail.get('Value', 0) <= 10000:
                                units[detail.get('Key', 0)] += detail['Value']
                        if sum(units.values()) <= 100000:
                            self.battle_kills(player, run, units, period)
                        if result.get('success'):
                            alive = {h.get('heroId') for h in map(PROFILE_HERO.decode, request.get('heros', []))
                                     if h.get('state', 0) == 0} & set(json.loads(team))
                            self.event(player, f'three-hero:{run}', 63, section, 1, len(alive), period)

    def claim_task(self, player, task_id, kind, activity=0):
        period = self.period(player)
        self.repair_tasks(player, period)
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

    def completed_task_count(self, player, period, kind, activity):
        # Native NewYear2TaskView.Refresh counts TaskStatus == 4, i.e. tasks
        # whose rewards have been claimed, not hidden successor progress.
        return sum(bool(self.rotation.get(player, period, self.task_namespace(task), tid, {}).get('claimed'))
                   for tid, task in self.task_catalog(period, kind, activity).items())

    def claim_task_box(self, player, activity, box_id, kind=9):
        period, _ = self.require(player, activity)
        boxes = [r for r in self.tables['ActivityTaskBox'] if r['ActivityID'] == activity]
        if (kind not in (9, 20) or not self.task_catalog(period, kind, activity)
                or not 0 <= box_id < len(boxes)):
            raise UnresolvedEconomy('unknown activity task box')
        box = boxes[box_id]
        if enum(box['CompeteType']) != 1:
            raise UnresolvedEconomy('unknown activity task box condition')
        with self.economy.transaction():
            self.repair_tasks(player, period)
            # Preserve the historical durable key so already-paid boxes cannot
            # be paid again after changing the wire index interpretation.
            key = f"{activity}:{box['BoxID']}"
            if self.rotation.get(player, period, 'task-box', key, False):
                raise UnresolvedEconomy('task box already claimed')
            completed = self.completed_task_count(player, period, kind, activity)
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
        # Entry-only building snapshots are no longer needed after the receipt commits.
        self.store.db.execute("DELETE FROM activity_state WHERE player_id=? AND period=? "
                              "AND namespace='run-buildings' AND state_key=?",
                              (player, period.index, uuid))

    def gameplay_day_counts(self, player, period=None):
        period = period or self.rotation.at()
        if period is None:
            return {}
        day = (int(self.economy.clock()) + 8 * 3600) // 86400
        return {item: self.rotation.get(player, period, f'gameplay-day:{day}', item, 0)
                for row in period.theme['activities'] if enum(row['ActivityType']) == 28
                for item in row.get('ActivityParam4', [])}

    def gameplay_rewards(self, player, period, section, extra_data):
        """ActivityGamePlay1 converts reported maze currency even on defeat.

        Its activity row owns the currency, exchange ratio, output and daily cap;
        these rewards do not mark a failed ordinary battle as cleared.
        """
        from x2server.messages.lobby import MISSION_PAIR
        config = self.sections.get(section, {})
        row = next((r for r in period.theme['activities'] if enum(r['ActivityType']) == 28
                    and config.get('ChapterID') in r.get('ActivityParam1', [])), None)
        if row is None:
            return {}
        currencies, ratios, items = (row.get('ActivityParam2', []), row.get('ActivityParam3', []),
                                    row.get('ActivityParam4', []))
        if not len(currencies) == len(ratios) == len(items) or any(r <= 0 for r in ratios):
            raise UnresolvedEconomy('invalid gameplay exchange configuration')
        if len(extra_data) > 64:
            raise UnresolvedEconomy('too many gameplay currency entries')
        reported = {}
        for raw in extra_data:
            pair = MISSION_PAIR.decode(raw)
            currency, amount = pair.get('Key', 0), pair.get('Value', 0)
            if currency not in currencies:
                continue
            if currency in reported or not 0 <= amount <= 10**7:
                raise UnresolvedEconomy('invalid/duplicate gameplay currency')
            reported[currency] = amount
        day = (int(self.economy.clock()) + 8 * 3600) // 86400
        rewards = {}
        limits = row.get('ActivityReward', [])
        if limits and (len(limits) != len(items) or any(limit < 0 for limit in limits)):
            raise UnresolvedEconomy('invalid gameplay daily limit')
        for index, (currency, ratio, item) in enumerate(zip(currencies, ratios, items, strict=True)):
            quantity = reported.get(currency, 0) // ratio
            previous = self.rotation.get(player, period, f'gameplay-day:{day}', item, 0)
            if limits:
                quantity = min(quantity, max(0, limits[index] - previous))
            if quantity:
                rewards[item] = quantity
                self.rotation.put(player, period, f'gameplay-day:{day}', item, previous + quantity)
        return rewards

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
