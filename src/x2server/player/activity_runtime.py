"""Authenticated activity routes and durable, atomic request receipts."""
import asyncio
import hashlib
import json
import logging
import secrets
from collections import Counter

from x2server.messages.activity import ACTIVITY_SCHEMAS, encode
from x2server.messages.lobby import LOBBY_SCHEMAS, MISSION_PAIR
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY
from .activity import enum
from .activity_cafe import ActivityCafe
from .activity_exchange import ActivityExchange
from .economy import UnresolvedEconomy


class ActivityRuntime:
    def __init__(self, activity, mail):
        self.a, self.e, self.r, self.mail = activity, activity.economy, activity.rotation, mail
        activity.runtime = self
        self.cafe, self.exchange = ActivityCafe(activity), ActivityExchange(activity)
        self.buff_rows = {r['AccountBuffID']: r for r in activity.tables['AccountBuff']}

    def handlers(self):
        return {name: self.handle for name in ACTIVITY_SCHEMAS if name.startswith('C2L_')} | {
            'C2L_EntryidStatus': self.handle, 'C2L_AccountBuffData': self.handle,
            'C2L_AccountBuffAutoStop': self.handle}

    def count(self, player, period, item):
        return self.r.get(player, period, 'obtained-item', item, 0)

    def lantern(self, player, op, req, token):
        aid = req.get('activityId', 0)
        period, row = self.a.require(player, aid, 31 if op == 'LanternShowPaper' else 30)
        result = {'code': 10, 'activityId': aid}
        state = self.r.get(player, period, 'lantern', aid, {'boxes': [], 'question': 0})
        if op == 'LanternShowQueryData':
            result.update(receivedBoxs=state['boxes'] or [-1],
                newYearCardCount=self.count(player, period, row['ActivityParam1'][1]),
                newYearPaperCount=self.count(player, period, 1290335))
        elif op == 'LanternShowQuestion':
            if not state['question']:
                self.a.spend(player, period, row['ActivityParam1'][0], 1, f'question:{token}')
                choices = [q['QaID'] for q in self.a.tables['AnswerConfig'] if q['QaType'] == row['ActivityReward'][0]]
                if not choices:
                    raise UnresolvedEconomy('missing questions')
                state['question'] = secrets.choice(choices)
            result['questionId'] = state['question']
        elif op == 'LanternShowAnswerQuestion':
            q = next((q for q in self.a.tables['AnswerConfig'] if q['QaID'] == req.get('questionId')), None)
            idx = req.get('answerIndex', -1)
            if (q is None or not state['question'] or q['QaID'] != state['question']
                    or type(idx) is not int or not 0 <= idx < len(q['AnswerName'])):
                raise UnresolvedEconomy('invalid or already answered question')
            rewards = Counter()
            for _ in range(q['RewardNum'][idx]):
                rewards.update(self.e.gifts([q['AnswerReward'][idx]], allow_daily_random=True))
            right = idx + 1 == q['RightAnswer']  # UI shuffles zero-based content indices.
            if right:
                rewards.update(self.e.gifts(row['ActivityParam2'], allow_daily_random=True))
            rewards = self.e._grant(player, self.a.source(period, 'answer', token), dict(rewards))
            self.a.obtained(player, period, rewards, self.a.source(period, 'answer', token))
            state['question'] = 0
            result.update(questionId=q['QaID'], answerIndex=idx, right=right,
                          rewardData=self.e.reward_bytes(rewards))
        elif op == 'LanternShowRecBox':
            idx = req.get('boxIndex', -1)
            if (type(idx) is not int or not 0 <= idx < len(row['ActivityParam3']) or idx in state['boxes']
                    or self.count(player, period, row['ActivityParam1'][1]) < row['ActivityParam3'][idx]):
                raise UnresolvedEconomy('lantern box is locked or claimed')
            rewards = self.a.grant(player, period, 'lantern-box', f'{aid}:{idx}', [row['ActivityParam4'][idx]])
            state['boxes'].append(idx)
            result.update(boxIndex=idx, receivedBoxs=sorted(state['boxes']), rewardData=self.e.reward_bytes(rewards))
        elif op == 'LanternShowPaper':
            self.a.spend(player, period, row['ActivityParam1'][0], row['ActivityParam1'][1], f'paper:{token}')
            item = secrets.choice(row['ActivityParam2'])
            buff = next(b for b in self.buff_rows.values() if b['AccountItem'] == item)
            # The original server's duration is absent. Compatibility: countdown
            # lasts to this period's end; use-count buffs affect the next fight.
            value = {'buffId': buff['AccountBuffID'], 'buffType': enum(buff['AccountUseType']),
                     'buffEnd': period.end if enum(buff['AccountUseType']) == 1 else 1, 'buffStop': 0}
            self.r.put(player, period, 'buff', value['buffId'], value)
            result['buffData'] = encode('AccountBuffData', value)
        else:
            raise UnresolvedEconomy('unknown lantern operation')
        self.r.put(player, period, 'lantern', aid, state)
        return result

    def buffs(self, player, period, section):
        result = []
        for bid, row in self.buff_rows.items():
            state = self.r.get(player, period, 'buff', bid)
            if (state and not state['buffStop'] and section in row.get('AccountEffectValue3', [])
                    and state['buffEnd'] > (int(self.e.clock()) if state['buffType'] == 1 else 0)):
                result.append((row, state))
        return result

    def prepare_buffs(self, player, section, uuid, cost):
        period = self.r.run_period(player, uuid)
        if period is None:
            return cost
        rows = self.buffs(player, period, section)
        self.r.put(player, period, 'run-buffs', uuid, [r['AccountBuffID'] for r, _ in rows])
        for row, state in rows:
            if state['buffType'] == 2:
                state['buffEnd'] -= 1
                self.r.put(player, period, 'buff', row['AccountBuffID'], state)
        reduction = max((r['AccountEffectValue1'] for r, _ in rows if enum(r['AccountBuffEffect']) == 6), default=0)
        return max(0, (cost * (1000 - reduction) + 999) // 1000)

    def extra_rewards(self, player, uuid, section, base):
        period = self.r.run_period(player, uuid)
        if period is None:
            return {}
        rewards = Counter()
        day = (int(self.e.clock()) + 8 * 3600) // 86400
        extra_ids = {i for a in period.theme['activities'] if enum(a['ActivityType']) == 23 for i in a['ActivityParam1']}
        for row in self.a.tables['ExtraDroop']:
            if row['ID'] not in extra_ids or section not in row['SectionGroup'] or enum(row['DroopType']) != 1:
                continue
            namespace = f'extra:{day}' if row['RefreshCycle'] == 1 else 'extra'
            count = self.r.get(player, period, namespace, row['ID'], 0)
            if count < row['NumLimit']:
                rewards.update(self.e.gifts(row['ExtraGiftID'], allow_daily_random=True))
                self.r.put(player, period, namespace, row['ID'], count + 1)
        for bid in self.r.get(player, period, 'run-buffs', uuid, []):
            row = self.buff_rows[bid]
            kind, ratio = enum(row['AccountBuffEffect']), row['AccountEffectValue1']
            if kind in (7, 9):
                items = [1237908] if kind == 7 else row.get('AccountEffectValue4', [])
                for item in items:
                    rewards[item] += base.get(item, 0) * ratio // 1000
            elif kind == 8 and secrets.randbelow(1000) < ratio:
                rewards.update(self.e.gifts(row['AccountEffectValue4'], allow_daily_random=True))
        return {i: n for i, n in rewards.items() if n}

    def records(self, player, period):
        records, passes = [], []
        for sid in period.theme['section_ids']:
            value = self.r.get(player, period, 'record', sid, 0)
            records.append(encode('ActivityMissionRecordData', {'missionId': sid, 'recordValue': value}))
            passes.append(encode('KeyValuePair_Int32_Int32', {'Key': sid, 'Value': self.r.get(player, period, 'clear', sid, 0)}))
        return {'code': 10, 'missionRecordData': records, 'previousRecord': 0, 'missionPassCount': passes}

    def operate(self, player, op, req, token):
        if op == 'QueryActivity':
            return self.a.query_activity(player)
        if op == 'EntryidStatus':
            return {'code': 10, 'entryidStatus': [MISSION_PAIR.encode({'Key': 19, 'Value': 1})]}
        period = self.a.period(player)
        if op == 'QueryShuangHanActivity':
            return self.a.frost_values(player)
        if op == 'PlayShuangHanPV':
            return self.a.play_frost_story(player, req.get('chapterId', 0))
        if op == 'SceneGlobalParam':
            # CheckSceneSectionParam matches SectionTable.Type and then the
            # prerequisite section ID/count from ActivityDungeon. Preserve
            # actual progress; receiving this reply also ends the login wait.
            groups = {}
            for sid in period.theme['section_ids']:
                section_type = enum(self.a.sections[sid]['Type'])
                groups.setdefault(section_type, []).append(encode('KeyValuePair_Int32_Int32',
                    {'Key': sid, 'Value': self.r.get(player, period, 'clear', sid, 0)}))
            return {'code': 10, 'sceneSectionParam': [encode('SceneSectionParam',
                {'sectionType': kind, 'sectionParam': rows}) for kind, rows in sorted(groups.items())]
                or [encode('SceneSectionParam', {'sectionType': 0,
                    'sectionParam': [encode('KeyValuePair_Int32_Int32', {})]})]}
        if op.startswith('CafeStore'):
            return self.cafe.handle(player, op, req, token)
        if op.startswith('LanternShow'):
            return self.lantern(player, op, req, token)
        if op in ('QueryActivityTower', 'ActivityTowerPassive'):
            if self.r.of_type(50, period) is None:
                raise UnresolvedEconomy('tower defense is not open')
            if op == 'QueryActivityTower':
                towers = self.a.tables['Tower']
                owned = self.r.get(player, period, 'tower', 'owned', [])
                balance = self.a.store.db.execute('SELECT quantity FROM inventory '
                    'WHERE player_id=? AND item_id=?', (player, towers[0]['CostItem'])).fetchone()
                # Native 0x13424D4 dereferences the list; TowerManager.GetItem(0)
                # is checked and skipped at 0x134256C. Represent no owned towers
                # without granting the six paid level-one towers for free.
                return {'code': 10, 'towerInfo': [encode('ActivityTowerInfo', {'id': tid})
                        for tid in owned] or [encode('ActivityTowerInfo', {})],
                        'towerPoint': balance['quantity'] if balance else 0}
            # Full-view Rift chooses its passives once per section and period.
            passives = []
            for rank in self.a.tables['TowerRank']:
                if rank['ID'] not in period.theme['section_ids']:
                    continue
                state = self.r.get(player, period, 'tower-passive', rank['ID'])
                if state is None:
                    def choose(groups, weights):
                        ticket = secrets.randbelow(sum(weights))
                        for group, weight in zip(groups, weights):
                            ticket -= weight
                            if ticket < 0:
                                return group['Items']
                    state = {'sectionId': rank['ID'],
                             'heroPassiveIds': choose(rank['PlayerPassive'], rank['PlayerPassiveRandom']),
                             'monsterPassiveIds': choose(rank['MonsterPassive'], rank['MonsterPassiveNumber'])}
                    self.r.put(player, period, 'tower-passive', rank['ID'], state)
                passives.append(encode('ActivityTowerPassive', state))
            return {'code': 10, 'passives': passives}
        if op in ('ActivityPreNotic', 'ActivityPreNoticInfo'):
            return self.a.pre_notice(player, req.get('activityType', 0), op == 'ActivityPreNotic')
        if op == 'ActivityRewardPoolInfo':
            return self.a.pool_values(player, req.get('activityId', 0))
        if op == 'ActivityRewardPoolDraw':
            return self.a.draw_pool(player, req.get('activityId', 0), req.get('rewardPoolId', 0), req.get('drawCount', 0), token)
        if op == 'ActivityMissionData':
            return self.a.mission_values(player, req.get('activityId', 0))
        if op == 'ActivityMissionSelBranch':
            aid, branch = req.get('activityId', 0), req.get('branch', 0)
            _, row = self.a.require(player, aid)
            if not 1 <= branch <= len(row.get('ActivityParam1', [])):
                raise UnresolvedEconomy('invalid branch')
            self.r.put(player, period, 'branch', aid, branch)
            return {'code': 10, 'activityId': aid, 'branch': branch}
        if op in ('QueryActivityMissionRecord', 'ActivityPassRecord'):
            result = self.records(player, period)
            return {'code': 10, 'missionPassCount': result['missionPassCount']} if op == 'ActivityPassRecord' else result
        if op == 'ExtraDropData':
            day = (int(self.e.clock()) + 28800) // 86400
            ids = {i for a in period.theme['activities'] if enum(a['ActivityType']) == 23 for i in a['ActivityParam1']}
            return {'data': [encode('KeyValuePair_Int32_Int32', {'Key': row['ID'],
                'Value': self.r.get(player, period, f'extra:{day}' if row['RefreshCycle'] == 1 else 'extra', row['ID'], 0)})
                for row in self.a.tables['ExtraDroop'] if row['ID'] in ids] or [encode('KeyValuePair_Int32_Int32', {})]}
        if op == 'ActivityMissionRecordSave':
            sid, score = req.get('missionId', 0), req.get('recordVal', -1)
            row = self.a.sections.get(sid)
            if (row is None or sid not in period.theme['section_ids'] or not 0 <= score <= 10**7
                    or not self.r.get(player, period, 'clear', sid, 0)):
                raise UnresolvedEconomy('record without a completed activity run')
            # One accepted record per successful run; replays cannot accumulate.
            clear = self.r.get(player, period, 'clear', sid, 0)
            if not self.r.once(player, period, f'record:{sid}:{clear}'):
                raise UnresolvedEconomy('record already saved')
            old = self.r.get(player, period, 'record', sid, 0)
            self.r.put(player, period, 'record', sid, max(score, old))
            return {'code': 10, 'missionId': sid, 'recordVal': max(score, old)}
        if op in ('QueryFoodMissionReward', 'ReceiveFoodMissionReward'):
            aid = req.get('activityId', 0)
            _, row = self.a.require(player, aid, 29)
            received = self.r.get(player, period, 'score-box', aid, [])
            result = {'code': 10, 'activityId': aid, 'receivedList': received or [0]}
            if op == 'ReceiveFoodMissionReward':
                threshold = req.get('scoreCount', 0)
                score = sum(self.r.get(player, period, 'record', sid, 0)
                    for cid in row['ActivityParam1'] for sid in self.a.chapters[cid]['SectionID'])
                if threshold not in row['ActivityParam4'] or threshold in received or score < threshold:
                    raise UnresolvedEconomy('food score reward not available')
                idx = row['ActivityParam4'].index(threshold)
                rewards = self.a.grant(player, period, 'score-box', f'{aid}:{threshold}', [row['ActivityReward'][idx]])
                received.append(threshold)
                self.r.put(player, period, 'score-box', aid, received)
                result.update(receivedList=sorted(received), scoreCount=threshold, rewardData=self.e.reward_bytes(rewards))
            return result
        if op == 'ActivityShop':
            return self.exchange.activity_listing(player, req.get('activityType', 0))
        if op in ('ActivityDialogReciveInfo', 'ActivityDialogue'):
            # YueXiModule.ShowStory selects Param1 by elapsed event day and
            # OnPLotEnd sends 628 (including when the plot is skipped).
            row = self.r.of_type(1, period) if period.theme['group'] == 99 else None
            if row is None:
                if op == 'ActivityDialogReciveInfo' and self.r.of_type(27, period):
                    return {'code': 10, 'lastReciveTimeSec': 0}
                raise UnresolvedEconomy('no recovered dialogue reward configuration')
            last = self.r.get(player, period, 'dialogue', 0,
                              self.r.get(player, period, 'pre-notice', row['ActivityID'], 0))
            result = {'code': 10, 'lastReciveTimeSec': last}
            if op == 'ActivityDialogue':
                now = int(self.e.clock())
                day = (now - period.start) // 86400
                groups = row.get('ActivityParam2', [])
                if (now >= self.a.yuexi_preview_end(period)
                        or not 0 <= day < len(row['ActivityParam1']) or day >= len(groups)
                        or last and (last - period.start) // 86400 == day):
                    raise UnresolvedEconomy('dialogue is closed or already claimed')
                reward = self.a.grant(player, period, 'dialogue', day, [groups[day]])
                self.r.put(player, period, 'dialogue', 0, now)
                self.r.put(player, period, 'pre-notice', row['ActivityID'], now)
                result.update(lastReciveTimeSec=now, rewardData=self.e.reward_bytes(reward))
            return result
        if op == 'ActivityReissueState':
            return {'code': 10, 'activityType': req.get('activityType', 0), 'reciveCount': 0}
        if op in ('AccountBuffData', 'AccountBuffAutoStop'):
            rows = []
            for bid in self.buff_rows:
                value = self.r.get(player, period, 'buff', bid)
                if value and value['buffEnd'] > (int(self.e.clock()) if value['buffType'] == 1 else 0):
                    rows.append(encode('AccountBuffData', value))
            # GodSoonModule.OnAccountBuffData @0x13e3074 explicitly handles
            # a missing list. BuffInfo requires a real AccountBuffID: ID 0 is
            # not an idle placeholder and crashes ContentID/icon rendering.
            return {'code': 10, 'buffData': rows}
        raise UnresolvedEconomy('activity operation is not available in this theme')

    async def handle(self, context, packet):
        player = context.session.player_id
        if player is None:
            raise ProtocolError('activity requested before login')
        name = CORE_MESSAGE_REGISTRY.name_for(packet.message_id)
        schema = ACTIVITY_SCHEMAS.get(name) or LOBBY_SCHEMAS[name]
        req = schema.decode(packet.body)
        response = name.replace('C2L_', 'L2C_', 1)
        response_schema = ACTIVITY_SCHEMAS.get(response) or LOBBY_SCHEMAS[response]
        token = hashlib.sha256(f'{context.session.session_id}:{packet.header.request_id}:{name}'.encode() + packet.body).hexdigest()
        try:
            with self.e.transaction():
                cached = self.a.store.db.execute('SELECT period,message,response FROM activity_receipts WHERE player_id=? AND request_key=?', (player, token)).fetchone()
                if cached:
                    if cached['period'] % self.r.state_cycle_size not in self.r.state_slots:
                        raise UnresolvedEconomy('activity is closed')
                    if cached['message'] != response:
                        raise UnresolvedEconomy('receipt mismatch')
                    values = response_schema.decode(cached['response'])
                else:
                    values = self.operate(player, name[4:], req, token)
                    self.a.store.db.execute('INSERT INTO activity_receipts VALUES (?,?,?,?,?)',
                        (player, token, self.r.at().index if self.r.at() else -1, response, response_schema.encode(values)))
        except (UnresolvedEconomy, ValueError, KeyError, TypeError) as exc:
            # Encoding remains inside the transaction: an incompatible payload
            # must roll back and answer the request, never disconnect/retry it.
            if isinstance(exc, (KeyError, TypeError)):
                logging.getLogger('x2.activity').exception('activity protocol rejected %s player=%s', name, player)
            logging.getLogger('x2.activity').info('activity denied %s player=%s reason=%s', name, player, exc)
            fields = {f.name for f in response_schema.fields}
            values = {key: value for key, value in req.items() if key in fields}
            if 'code' in fields:
                values['code'] = 13
            if name == 'C2L_ExtraDropData':
                values = {'data': [encode('KeyValuePair_Int32_Int32', {})]}
            return OutboundMessage(response, values)
        queries = {'QueryActivity', 'EntryidStatus', 'ActivityPassRecord', 'ExtraDropData',
                   'SceneGlobalParam',
                   'QueryActivityMissionRecord', 'ActivityMissionData', 'ActivityRewardPoolInfo',
                   'CafeStoreInfo', 'CafeStoreUpdate', 'LanternShowQueryData',
                   'QueryFoodMissionReward', 'ActivityPreNoticInfo', 'ActivityReissueState',
                   'QueryActivityTower', 'ActivityTowerPassive',
                   'QueryShuangHanActivity', 'PlayShuangHanPV',
                   'ActivityDialogReciveInfo', 'ActivityShop', 'AccountBuffData', 'AccountBuffAutoStop'}
        queries.add('ActivityMissionSelBranch')  # Only branch state changes, no inventory/player snapshot.
        return OutboundMessage(response, values,
            before_response=self.e.pushes(player) if name[4:] not in queries else ())

    def progress_messages(self, player):
        period = self.r.at()
        if period is None:
            return ()
        messages = [OutboundMessage('L2C_SceneGlobalParam',
                    self.operate(player, 'SceneGlobalParam', {}, 'progress')),
                    OutboundMessage('L2C_ActivityPassRecord',
                    {'code': 10, 'missionPassCount': self.records(player, period)['missionPassCount']})]
        for row in period.theme['activities']:
            if enum(row['ActivityType']) == 13:
                messages.append(OutboundMessage('L2C_QueryShuangHanActivity', self.a.frost_values(player)))
            elif any(cid in self.a.chapters for cid in row.get('ActivityParam1', [])):
                messages.append(OutboundMessage('L2C_ActivityMissionData',
                                self.a.mission_values(player, row['ActivityID'])))
        return tuple(messages)

    def deliver_daily_mail(self, player):
        period = self.r.at()
        if period is None or self.a.store.get(player)['snapshot']['level'] < 15:
            return
        row = self.r.of_type(33, period)
        if row is None:
            return
        day = (int(self.e.clock()) - period.start) // 86400
        # Ten original daily letters are delivered as two per day in a five-day period.
        for mid in row['ActivityParam1'][2 * day:2 * day + 2]:
            template = next(t for t in self.a.tables['MailInfo'] if t['id'] == mid)
            source = self.a.source(period, 'daily-mail', mid)
            with self.e.transaction():
                if not self.r.once(player, period, source):
                    continue
                mail_id = self.mail.send(player, template['title'], template['body'], self.e.gifts([template['gift']], allow_daily_random=True))
                self.a.store.db.execute('UPDATE player_mail SET source_key=? WHERE id=?', (source, mail_id))

    async def watch(self, server):
        previous = None
        while True:
            period = self.r.at()
            current = (period.index, self.a.yuexi_preview_end(period) > int(self.e.clock())) if period else None
            for player in server.authenticated_player_ids():
                self.deliver_daily_mail(player)
                if previous != current:
                    await server.push_to_player(player, OutboundMessage('L2C_QueryActivity', self.a.query_activity(player)))
            previous = current if server.authenticated_player_ids() else None
            await asyncio.sleep(5)
