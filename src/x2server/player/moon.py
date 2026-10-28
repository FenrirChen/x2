"""Moon Garden: original camps, missions, equipment and NPC friendship.

State is account-owned activity_state data, included in save export/import.
Scene quest completion is reported by the original client (974); item/reward
identities, prerequisites, quantities and one-time receipts stay server-owned.
"""
from collections import Counter
from functools import lru_cache
from importlib.resources import files
import hashlib
import json
import logging
import random

from x2server.messages.moon import MOON_IDS, MOON_SCHEMAS as S
from x2server.messages.economy import TASK, REWARD
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY
from .task_calendar import task_period

LOGGER = logging.getLogger('x2.moon')


@lru_cache(maxsize=1)
def catalog():
    return json.loads(files('x2server').joinpath('data/moon_catalog.json').read_text(encoding='utf8'))


PARAMETERS = catalog()['parameters']


def enc(name, values):
    return S[name].encode(values)


class MoonService:
    KINDS = (16, 17, 18, 19)
    SECTIONS = (2111001, 2111051)

    def __init__(self, economy):
        self.e, self.store, self.db = economy, economy.store, economy.store.db
        data = catalog()
        self.camps = {r['CampID']: r for r in data['mooncamp']}
        self.npcs = {r['NPCID']: r for r in data['moonnpc']}
        self.equips = {r['EquipID']: r for r in data['moonequip']}
        self.missions = {r['QuestGroupID']: r for r in data['missiontable']}
        self.predecessors = {r['PredecessorID']: r for r in data['missionpredecessor']}
        self.rng = random.SystemRandom()
        self.e.items.update({r['ItemID']: r for r in data['items']})
        groups = {r['GiftGroup'] for r in data['gifts']}
        self.e.catalog['gifts'] = [r for r in self.e.catalog['gifts'] if r['GiftGroup'] not in groups] + data['gifts']

    def handlers(self):
        return {'C2L_' + n: self.handle for n, _, _ in MOON_IDS}

    def quantity(self, pid, item):
        row = self.db.execute('SELECT quantity FROM inventory WHERE player_id=? AND item_id=?', (pid, item)).fetchone()
        return row[0] if row else 0

    def spend(self, pid, item, num):
        if num <= 0 or self.db.execute('UPDATE inventory SET quantity=quantity-? WHERE player_id=? AND item_id=? AND quantity>=?',
                                      (num, pid, item, num)).rowcount != 1:
            raise ValueError('insufficient Moon material')

    def load(self, pid):
        day, _ = task_period(1, int(self.e.clock()))
        row = self.db.execute("SELECT value FROM activity_state WHERE player_id=? AND period=0 AND namespace='moon' AND state_key='state'", (pid,)).fetchone()
        state = json.loads(row[0]) if row else {'tasks': {}, 'claimed': {}, 'npc': {}, 'levels': {}, 'slots': {}, 'receipts': {}}
        if state.get('day') != day:
            # Accepted unfinished repeat missions remain resumable across midnight.
            state.update(day=day, flowers=0, chips=0, given=0, accepted=0, refreshed=0, offers=[])
            state['tasks'] = {k: v for k, v in state['tasks'].items()
                              if self.kind(int(k)) != 18 or v['status'] in (2, 3)}
            state['receipts'] = {}
        for mid, row in self.missions.items():
            if self.kind(mid) == 19:
                state['tasks'].setdefault(str(mid), self.task(row, 2))
        return state

    def save(self, pid, state):
        self.db.execute("INSERT OR REPLACE INTO activity_state VALUES (?,0,'moon','state',?)", (pid, json.dumps(state, sort_keys=True)))

    def kind(self, mid):
        return {1: 17, 2: 18, 3: 19}[self.missions[mid]['QuestType']['value']]

    def task(self, row, status=1, difficulty=1):
        return {'status': status, 'children': {str(i): 2 for i in row['QuestID']}, 'difficulty': difficulty}

    def camp_open(self, state, cid):
        return state['tasks'].get(str(self.camps[cid]['CampTask']), {}).get('status') == 4

    def available(self, pid, state, row):
        for pre in row.get('Predecessors', []):
            rule = self.predecessors[pre]
            values = rule['Param']
            if rule['PredecessorType']['value'] == 1:
                if not all(state['tasks'].get(str(i), {}).get('status') == 4 for i in values):
                    return False
            elif rule['PredecessorType']['value'] == 2:
                if self.quantity(pid, values[0]) < values[1]:
                    return False
            else:
                return False
        return True

    def children(self, task):
        return [enc('ChildrenMission', {'childrenMissionId': int(i), 'childrenMissionStatus': v}) for i, v in task['children'].items()]

    def group(self, mid, task):
        return enc('MoonMissionGroup', {'missionGroupId': mid, 'moonChildrenMission': self.children(task)})

    def task_wire(self, mid, task):
        return enc('TaskData', {'taskId': mid, 'taskStatus': task['status'],
            'taskProgress': sum(v >= 3 for v in task['children'].values()),
            'taskRefreshTime': task_period(1, int(self.e.clock()))[1] if self.kind(mid) == 18 else 0,
            'finishTimes': int(task['status'] == 4), 'difficulty': task['difficulty'],
            'childrenMission': self.children(task)})

    def task_values(self, pid, kind):
        with self.e.transaction():
            state = self.load(pid)
            for mid, row in self.missions.items():
                if self.kind(mid) == 17 and self.available(pid, state, row):
                    state['tasks'].setdefault(str(mid), self.task(row))
            self.save(pid, state)
            return {'code': 10, 'type': kind,
                'taskList': [self.task_wire(int(mid), task) for mid, task in state['tasks'].items()
                             if kind == 16 or self.kind(int(mid)) == kind]}

    def daily_limit(self, pid, name):
        base = int(PARAMETERS[name])
        if name == 'MoonFlowerGetLimit':
            base += self.quantity(pid, 1120013)
        if name == 'MoonFlowerGiveLimit':
            base += self.quantity(pid, 1120014) * 2
        return base

    def unlock_values(self, pid, state):
        from x2server.messages.core import STRING_PAIR
        return {'code': 10, 'moonCampUnlock': [enc('MoonCampUnlock', {
            'moonCampId': cid, 'moonCampStatus': 2 if self.camp_open(state, cid) else 1}) for cid in self.camps],
            # 959 uses the limit names to carry TODAY'S CONSUMPTION, not maxima.
            'keyVal': [STRING_PAIR.encode({'key': k, 'val': str(state[v])}) for k, v in
                [('MoonFlowerGiveLimit', 'given'), ('MoonFlowerGetLimit', 'flowers'), ('MoonEquipExpGetLimit', 'chips'),
                 ('MoonTaskRefreshLimit', 'refreshed'), ('MoonTaskReceiveLimit', 'accepted')]]}

    def prestige_values(self, pid, state):
        return {'code': 10, 'moonCampPrestige': [enc('MoonCampPrestige', {'moonCampId': cid,
            'moonCampPrestige': self.quantity(pid, row['CampPrestigeItem']),
            'moonCampReward': state['claimed'].get('camp:' + str(cid), [])}) for cid, row in self.camps.items()]}

    def npc_values(self, pid, state, cid=0):
        return {'code': 10, 'moonCampId': cid, 'moonNPCFavorability': [enc('MoonNPCFavorability', {
            'moonNPCId': nid, 'favorability': state['npc'].get(str(nid), 0),
            'moonRewardIds': state['claimed'].get('npc:' + str(nid), [])})
            for nid, row in self.npcs.items() if not cid or cid == row['CampID']]}

    def equip_level(self, pid, state, eid):
        return state['levels'].get(str(eid), 1) if self.quantity(pid, self.equips[eid]['EquipItemID']) else 0

    def slot_values(self, pid, state):
        # Original maximum is 4 normal + 1 special; prestige grants extra normal
        # slot unlock items: one normal-slot reward from each of the four camps.
        normal = min(int(PARAMETERS['MoonNormalEquipLimit']), self.quantity(pid, 1120007))
        special = int(PARAMETERS['MoonSpecialEquipLimit'])
        return normal, special

    def equip_values(self, pid, state):
        normal, special = self.slot_values(pid, state)
        def slots(kind, count, opened):
            return [enc('MoonEquipBarInfo', {'moonSlotIndex': i,
                'moonEquipId': state['slots'].get(f'{kind}:{i}', 0) if i < opened else -1}) for i in range(count)]
        return {'code': 10, 'moonEquip': [enc('MoonEquipData', {'moonEquipId': eid,
            'moonEquipLevel': self.equip_level(pid, state, eid)}) for eid in self.equips if self.equip_level(pid, state, eid)],
            'moonEquipBarNormal': slots('normal', int(PARAMETERS['MoonNormalEquipLimit']), normal),
            'moonEquipBarSpecial': slots('special', special, special)}

    def pushes(self, pid, state):
        return (OutboundMessage('L2C_MoonCampUnlock', self.unlock_values(pid, state)),
            OutboundMessage('L2C_MoonCampPrestige', self.prestige_values(pid, state)),
            OutboundMessage('L2C_MoonEquip', self.equip_values(pid, state)),
            OutboundMessage('L2C_MoonNPCFavorability', self.npc_values(pid, state)))

    def grant(self, pid, state, key, groups, equipment_star=None):
        # _grant's ledger protects retries independently of the transport session.
        source = 'moon:' + key
        existing = self.db.execute('SELECT rewards FROM economy_grants WHERE player_id=? AND source=?', (pid, source)).fetchone()
        pending = Counter()
        rewards = ({int(i): n for i, n in json.loads(existing[0]).items()} if existing else
                   self.e.gifts(groups, deferred=pending, allow_daily_random=True) if groups else {})
        specs = []
        for item, count in pending.items():
            if self.e.items[item].get('ItemType', {}).get('value') == 11:
                rewards[item] = rewards.get(item, 0) + count
                continue
            if not self.e.equipment_factory.is_drop_equipment(item):
                raise ValueError(f'unrecovered Moon reward destination {item}, groups={groups}')
            star = self.e.items[item]['ItemQuality']['value']
            if star == 7:
                if equipment_star is None:
                    raise ValueError('Moon equipment identification missing')
                star = equipment_star
            specs.append({'item_id': item, 'quantity': count, 'star': star})
        equipment = self.e.materialize_equipment(pid, source, specs) if specs else []
        self.e._grant(pid, source, rewards, stackable_types=(11,))
        return self.e.reward_bytes(rewards, equipment)

    def claim_task(self, pid, mid, kind):
        result = {'code': 13, 'taskId': mid, 'type': kind}
        if mid not in self.missions or kind not in (16, self.kind(mid)):
            return result
        with self.e.transaction():
            state = self.load(pid)
            task = state['tasks'].get(str(mid))
            if not task or task['status'] != 3:
                return result
            result['rewardData'] = self.finish(pid, state, mid)
            result['code'] = 10
            self.save(pid, state)
        return result

    def finish(self, pid, state, mid):
        task, row = state['tasks'][str(mid)], self.missions[mid]
        groups = list(row.get('Award', []))
        repeat = self.kind(mid) == 18
        if repeat and row.get('RandomAward'):
            # Difficulty n selects the original n-th reward group.
            groups.append(row['RandomAward'][min(task['difficulty'] - 1, len(row['RandomAward']) - 1)])
        if repeat:
            token, group = self.camps[row['CampID']]['MoonRepeatTaskExtraReward']
            if self.quantity(pid, token):
                groups.append(group)
        key = f'task:{mid}' + (f':{state["day"]}' if repeat else '')
        # USER_DECISION 2026-10-18: original Gift has E_Unsure quality;
        # identify repeat rewards by difficulty (1-2/3-4/5-7/8-9 -> 3/4/5/6).
        difficulty = task['difficulty']
        equipment_star = 3 if difficulty <= 2 else 4 if difficulty <= 4 else 5 if difficulty <= 7 else 6
        reward = self.grant(pid, state, key, groups, equipment_star if repeat else None)
        if row.get('NPCID'):
            from x2server.messages.economy import REWARD_ITEM
            for item in map(REWARD_ITEM.decode, REWARD.decode(reward).get('rewardItem', [])):
                if item.get('itemId') == 1120008:
                    nid = row['NPCID']
                    state['npc'][str(nid)] = min(self.npcs[nid]['NPCFavorability'][-1],
                        state['npc'].get(str(nid), 0) + item['itemNum'] * 5)
        task['status'] = 4
        return reward

    def offers(self, pid, state, refresh=False):
        if refresh:
            # Native RefreshCount displays GlobalParamString limit minus one;
            # the initial board is the first of six, leaving five manual refreshes.
            if state['refreshed'] >= int(PARAMETERS['MoonTaskRefreshLimit']) - 1:
                raise ValueError('daily Moon refresh limit')
            state['refreshed'] += 1
        if refresh or not state['offers']:
            pool = [mid for mid, row in self.missions.items() if self.kind(mid) == 18
                    and self.available(pid, state, row) and str(mid) not in state['tasks']]
            state['offers'] = self.rng.sample(pool, min(int(PARAMETERS['MoonTaskRefreshNum']), len(pool)))
            level = self.store.get(pid)['snapshot']['level']
            rank = max((r for r in catalog()['moontaskrank'] if r['Level'] <= level), key=lambda r: r['Level'])
            state['offer_difficulty'] = {str(mid): self.rng.choices(rank['Difficulty'], rank['DifficultyPower'])[0]
                                         for mid in state['offers']}
        rows = [self.task_wire(mid, self.task(self.missions[mid], 1, state['offer_difficulty'][str(mid)])) for mid in state['offers']]
        rows += [self.task_wire(int(mid), task) for mid, task in state['tasks'].items() if self.kind(int(mid)) == 18 and task['status'] in (2, 3)]
        return {'code': 10, 'repeatTaskData': rows, 'taskRepeatRefreshCountDay': state['refreshed']}

    def sync(self, pid, state, raw_groups):
        if not 0 < len(raw_groups) <= 193:
            raise ValueError('invalid Moon group count')
        groups, rewards = [], Counter()
        for raw in raw_groups:
            group = S['MoonMissionGroup'].decode(raw)
            mid = group.get('missionGroupId', 0)
            task = state['tasks'].get(str(mid))
            if mid not in self.missions or not task or task['status'] not in (2, 3, 4):
                raise ValueError('Moon mission was not accepted')
            reported = group.get('moonChildrenMission', [])
            if len(reported) > len(task['children']):
                raise ValueError('too many Moon children')
            seen = set()
            for blob in reported:
                child = S['ChildrenMission'].decode(blob)
                qid, status = str(child.get('childrenMissionId', 0)), child.get('childrenMissionStatus', 0)
                if qid not in task['children'] or qid in seen or status not in (2, 3, 4):
                    raise ValueError('invalid Moon child identity/status')
                seen.add(qid)
                task['children'][qid] = max(task['children'][qid], status)
            if task['status'] == 2 and all(v >= 3 for v in task['children'].values()):
                task['status'] = 3
                if self.kind(mid) != 18:
                    data = REWARD.decode(self.finish(pid, state, mid))
                    from x2server.messages.economy import REWARD_ITEM
                    for item in map(REWARD_ITEM.decode, data.get('rewardItem', [])):
                        rewards[item['itemId']] += item['itemNum']
            groups.append(self.group(mid, task))
        return {'code': 10, 'moonMissionGroup': groups, 'rewardData': self.e.reward_bytes(dict(rewards))}

    def mutate(self, pid, state, name, request):
        if name in ('MoonCampPrestigeReward', 'MoonNPCFavorabilityReward'):
            camp = name == 'MoonCampPrestigeReward'
            ident = request.get('moonCampId' if camp else 'moonNPCId', 0)
            rows = self.camps if camp else self.npcs
            index = request.get('rewardIndex', -1)
            if ident not in rows:
                raise ValueError('unknown Moon reward owner')
            row = rows[ident]
            thresholds = row['CampPrestigeStage' if camp else 'NPCFavorability']
            gift_ids = row['CampPrestigeGift' if camp else 'NPCGift']
            value = self.quantity(pid, row['CampPrestigeItem']) if camp else state['npc'].get(str(ident), 0)
            key = ('camp:' if camp else 'npc:') + str(ident)
            if not 0 <= index < len(thresholds) or value < thresholds[index] or index in state['claimed'].get(key, []):
                raise ValueError('Moon reward not claimable')
            if camp and not self.camp_open(state, ident):
                raise ValueError('Moon camp is locked')
            if not camp and not self.camp_open(state, row['CampID']):
                raise ValueError('Moon NPC camp is locked')
            reward = self.grant(pid, state, key + ':' + str(index), [gift_ids[index]] if gift_ids[index] else [])
            state['claimed'].setdefault(key, []).append(index)
            return {'code': 10, **request, 'rewardData': reward}
        if name == 'MoonFlowerGive':
            nid, num = request.get('moonNPCId', 0), request.get('moonFlowerNumber', 0)
            if nid not in self.npcs or not self.camp_open(state, self.npcs[nid]['CampID']):
                raise ValueError('Moon NPC is locked')
            favor = state['npc'].get(str(nid), 0)
            per_flower = self.e.items[1120002]['EffData'][0]
            if not 0 < num <= self.daily_limit(pid, 'MoonFlowerGiveLimit') - state['given'] or favor >= self.npcs[nid]['NPCFavorability'][-1]:
                raise ValueError('Moon gift limit reached')
            num = min(num, (self.npcs[nid]['NPCFavorability'][-1] - favor + per_flower - 1) // per_flower)
            self.spend(pid, 1120002, num)
            state['given'] += num
            state['npc'][str(nid)] = min(self.npcs[nid]['NPCFavorability'][-1], favor + num * per_flower)
            return {'code': 10, 'moonNPCId': nid, 'favorability': state['npc'][str(nid)], 'realNum': num}
        if name == 'MoonEquipUpLevel':
            eid = request.get('moonEquipId', 0)
            if eid not in self.equips:
                raise ValueError('unknown Moon equipment')
            level = self.equip_level(pid, state, eid)
            costs = self.equips[eid].get('EquipExp', [])
            if not 1 <= level < len(costs):
                raise ValueError('Moon equipment unowned or maximum level')
            self.spend(pid, 1120001, costs[level])
            state['levels'][str(eid)] = level + 1
            return {'code': 10, 'moonEquip': enc('MoonEquipData', {'moonEquipId': eid, 'moonEquipLevel': level + 1})}
        if name == 'MoonEquipPutOnOrOff':
            eid, index, operate = request.get('moonEquipId', 0), request.get('slotIndex', -1), request.get('operate', -1)
            if eid not in self.equips or not self.equip_level(pid, state, eid):
                raise ValueError('Moon equipment unowned')
            special = self.equips[eid].get('EquipType', {}).get('value', 0) == 0
            slot_kind = 'special' if special else 'normal'
            if operate not in (1, 2) or not 0 <= index < self.slot_values(pid, state)[int(special)]:
                raise ValueError('Moon equipment slot locked/invalid operation')
            key = f'{slot_kind}:{index}'
            if operate == 1:
                for k, item in list(state['slots'].items()):
                    if item == eid:
                        del state['slots'][k]
                state['slots'][key] = eid
            else:
                if state['slots'].get(key) != eid:
                    raise ValueError('Moon equipment not in slot')
                del state['slots'][key]
            return {'code': 10, 'slotType': int(special), 'moonEquipId': eid if operate == 1 else 0, 'slotIndex': index}
        if name == 'MoonAcceptableRepeatTask':
            opt = request.get('opt', 0)
            if opt not in (0, 1, 2):
                raise ValueError('invalid Moon refresh operation')
            # MoonTaskPage.OnOpen sends 1; OnRefresh_BtnClick sends 2.
            return self.offers(pid, state, opt == 2)
        if name == 'MoonMissionGroupAcceptedSync':
            group = S['MoonMissionGroup'].decode(request.get('moonMissionGroup', b''))
            mid = group.get('missionGroupId', 0)
            if mid not in self.missions or not self.available(pid, state, self.missions[mid]):
                raise ValueError('Moon mission prerequisite not met')
            old = state['tasks'].get(str(mid))
            if old and (old['status'] in (2, 3) or
                        (old['status'] == 4 and self.kind(mid) != 18)):
                # A reconnect or delayed NPC interaction may resend acceptance
                # after a permanent story has completed. Return saved children;
                # never reopen the story or grant its rewards again. Completed
                # daily commissions still require the next day's offer.
                task = old
            else:
                repeat = self.kind(mid) == 18
                if old and old['status'] == 4:
                    raise ValueError('Moon mission already finished')
                if repeat and (mid not in state['offers'] or state['accepted'] >= int(PARAMETERS['MoonTaskReceiveLimit'])):
                    raise ValueError('Moon repeat unavailable/daily limit')
                task = self.task(self.missions[mid], 2, state.get('offer_difficulty', {}).get(str(mid), 1))
                if repeat:
                    state['accepted'] += 1
                    state['offers'].remove(mid)
                state['tasks'][str(mid)] = task
            return {'code': 10, 'moonMissionGroup': self.group(mid, task),
                'taskRepeatReceiveCountDay': state['accepted'], 'taskRefreshTime': task_period(1, int(self.e.clock()))[1]}
        if name == 'MoonMissionGroupSync':
            return self.sync(pid, state, request.get('moonMissionGroup', []))
        raise ValueError('unsupported Moon operation')

    def accept_reward(self, pid, source, rewards):
        """Apply original daily pickup caps to actual settlement, once per run.

        Quest/letter rewards are not monster pickups and do not consume quotas.
        The enclosing economy grant and Moon counters commit or roll back together.
        """
        if not source.startswith('battle:'):
            return rewards
        run = self.db.execute('SELECT section_type FROM economy_runs WHERE player_id=? AND uuid=?',
                              (pid, source[7:])).fetchone()
        if not run or run[0] != 21:
            return rewards
        state, rewards = self.load(pid), dict(rewards)
        for item, field, limit in ((1120001, 'chips', 'MoonEquipExpGetLimit'), (1120002, 'flowers', 'MoonFlowerGetLimit')):
            if item in rewards:
                amount = min(rewards[item], max(0, self.daily_limit(pid, limit) - state[field]))
                state[field] += amount
                if amount:
                    rewards[item] = amount
                else:
                    del rewards[item]
        self.save(pid, state)
        return rewards

    def claim_pushes(self, results):
        from x2server.messages.economy import FINISH_RESULT
        equips = []
        for raw in results:
            row = FINISH_RESULT.decode(raw)
            if row.get('type') in self.KINDS and row.get('code') == 10:
                equips.extend(REWARD.decode(row.get('rewardData', b'')).get('rewardEquip', []))
        return (OutboundMessage('L2C_EquipUpdate', {'code': 10, 'equip': equips}),) if equips else ()

    def battle_skill(self, pid):
        """Map the equipped Moon items to the original team-caster payload."""
        from x2server.messages.battle import FIGHT_GROUP_SKILL
        state = self.load(pid)
        eid = state['slots'].get('special:0', 0)
        if eid not in self.equips or not self.equip_level(pid, state, eid):
            return b''
        row, variant, passives = self.equips[eid], 1, []
        for key, normal_id in state['slots'].items():
            if not key.startswith('normal:') or normal_id not in self.equips or not self.equip_level(pid, state, normal_id):
                continue
            normal = self.equips[normal_id]
            for skill in normal.get('EquipSkill', []):
                if skill['Items'][0] == eid:
                    variant += skill['Items'][1]
            if not normal.get('EquipIDInfo') or eid in normal['EquipIDInfo']:
                passives.extend(normal.get('EquipEffect', []))
        skills = {r['Items'][0]: r['Items'][1] for r in row['EquipSkill']}
        active = skills[max(k for k in skills if k <= variant)]
        return FIGHT_GROUP_SKILL.encode({'activeSkillId': active,
            'activeSkillLevel': self.equip_level(pid, state, eid), 'unitId': row['UnitID'],
            'passiveIds': sorted(set(passives))})

    def expire_day(self, pid):
        with self.e.transaction():
            row = self.db.execute("SELECT value FROM activity_state WHERE player_id=? AND period=0 AND namespace='moon' AND state_key='state'", (pid,)).fetchone()
            if not row or json.loads(row[0]).get('day') == task_period(1, int(self.e.clock()))[0]:
                return ()
            state = self.load(pid)
            self.save(pid, state)
            return (OutboundMessage('L2C_MoonCampUnlock', self.unlock_values(pid, state)),
                    OutboundMessage('L2C_GameTask', self.task_values(pid, 16)))

    async def handle(self, context, packet):
        pid = context.session.player_id
        if pid is None:
            raise ProtocolError('Moon operation before login')
        full_name = CORE_MESSAGE_REGISTRY.name_for(packet.message_id)
        name = full_name[4:]
        request = S[full_name].decode(packet.body)
        response = 'L2C_' + name
        try:
            with self.e.transaction():
                state = self.load(pid)
                cid = request.get('moonCampId', 0)
                if cid and cid not in self.camps:
                    raise ValueError('unknown Moon camp')
                if name == 'MoonCampUnlock':
                    values = self.unlock_values(pid, state)
                elif name == 'MoonCampPrestige':
                    values = self.prestige_values(pid, state)
                elif name == 'MoonNPCFavorability':
                    values = self.npc_values(pid, state, cid)
                elif name == 'MoonEquip':
                    values = self.equip_values(pid, state)
                else:
                    key = context.session.session_id + ':' + str(packet.header.request_id)
                    digest = hashlib.sha256(packet.body + full_name.encode()).hexdigest()
                    previous = state['receipts'].get(key)
                    if previous:
                        if previous['digest'] != digest:
                            raise ValueError('Moon request id reused with different body')
                        values = S[response].decode(bytes.fromhex(previous['wire']))
                    else:
                        values = self.mutate(pid, state, name, request)
                        state['receipts'][key] = {'digest': digest, 'wire': S[response].encode(values).hex()}
                        while len(state['receipts']) > 256:
                            del state['receipts'][next(iter(state['receipts']))]
                self.save(pid, state)
            before = self.e.pushes(pid) if name not in ('MoonCampUnlock', 'MoonCampPrestige', 'MoonEquip', 'MoonNPCFavorability', 'MoonAcceptableRepeatTask') else ()
            if name in ('MoonCampUnlock', 'MoonMissionGroupSync'):
                before += (OutboundMessage('L2C_GameTask', self.task_values(pid, 16)),)
            if name in ('MoonMissionGroupSync', 'MoonCampPrestigeReward'):
                before += self.pushes(pid, state)
            elif name in ('MoonAcceptableRepeatTask', 'MoonMissionGroupAcceptedSync', 'MoonFlowerGive'):
                before += (OutboundMessage('L2C_MoonCampUnlock', self.unlock_values(pid, state)),)
            return OutboundMessage(response, values, before_response=before)
        except (ValueError, KeyError) as exc:
            LOGGER.info('Moon operation denied player=%s request=%s reason=%s', pid, name, exc)
            return OutboundMessage(response, {'code': 13})
