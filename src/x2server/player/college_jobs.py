"""Persisted hero jobs. Costs, occupancy and claims share one savepoint."""
import hashlib
import json
import logging
import uuid

from x2server.network.dispatcher import OutboundMessage
from x2server.messages.lobby import UNLOCK_EXPLORE_RUIN
from .college_upgrade import _catalog
from .progression import catalog as progression_catalog
from .hero import encode_hero_data

# 派遣/培训被拒时把判定用的实际数值打进日志: 客户端只回一个 GameLogicErrCode
# (13/14/38/62~64/186/205/22), 没有上下文时无法区分「星能不够」和「参数/槽位不对」。
LOGGER = logging.getLogger("x2.college")


class CollegeJobsService:
    FLOWS = ('StartTrain', 'CancelTrain', 'FinishTrain',
             'StartExplore', 'CancelExplore', 'FinishExplore', 'ExploreSpeed')

    def __init__(self, repository, economy):
        self.repo, self.economy = repository, economy
        self.store, self.db = repository.store, repository.store.db
        self.explores = {r['ID']: r for r in _catalog()['explores']}
        self.levels = {r['level']: r for r in progression_catalog()['hero_level']}
        with repository.transaction():
            self.db.execute('''CREATE TABLE IF NOT EXISTS college_job_receipts (
                player_id INTEGER NOT NULL, receipt_key TEXT NOT NULL, digest TEXT NOT NULL,
                response TEXT NOT NULL, PRIMARY KEY(player_id,receipt_key))''')

    @staticmethod
    def effects(row, exp, kind):
        # GetExploreLv starts at -1. Each met threshold enables one effect slot.
        values = []
        for index in range(1, min(5, sum(exp >= t for t in row['Exp'])) + 1):
            if row.get(f'ExploreEffect{index}') == kind:
                values.extend(row.get(f'ExploreEffectParam{index}', []))
        return values

    @staticmethod
    def occupied(state):
        result = {}
        for row in state['training']:
            result[row['heroId']] = 3
        for row in state['explore']:
            for hero in row['heroList']:
                result[hero] = 2
        for row in state['pray']:
            if isinstance(row, dict) and row.get('prayHeroID', row.get('heroId')):
                result[row.get('prayHeroID', row.get('heroId'))] = 1
        return result

    def heroes(self, state, snapshot, ids):
        owned = {h['id']: h for h in snapshot.get('heroes', []) if h.get('state') == 2}
        if not ids or len(ids) != len(set(ids)) or any(i not in owned for i in ids):
            return 13, []
        occupied = self.occupied(state)
        for hid in ids:
            status = occupied.get(hid, owned[hid].get('college_status', 0))
            if status:
                return {1: 62, 2: 63, 3: 64}.get(status, 13), []
        return 10, [owned[i] for i in ids]

    def _start_train(self, player_id, state, snapshot, request):
        pos, hid = request.get('trainId', 0), request.get('heroId', 0)
        result = {'code': 13, 'trainId': pos}
        capacity = self.repo.catalog.effect(state, 704, 6, star=True)[0]
        if not 0 <= pos < capacity or any(r['trainingId'] == pos for r in state['training']):
            LOGGER.warning('StartTrain refused: player=%s trainId=%s capacity=%s busy=%s',
                           player_id, pos, capacity, [r['trainingId'] for r in state['training']])
            return result
        code, heroes = self.heroes(state, snapshot, [hid])
        if code != 10:
            LOGGER.warning('StartTrain refused: player=%s heroId=%s hero check code=%s', player_id, hid, code)
            return dict(result, code=code)
        hero = heroes[0]
        level = self.levels.get(hero['level'])
        if not level or not level['next_level'] or hero['level'] >= snapshot['level']:
            LOGGER.warning('StartTrain refused: player=%s heroId=%s heroLevel=%s playerLevel=%s',
                           player_id, hid, hero['level'], snapshot['level'])
            return dict(result, code=14)
        building = self.repo.catalog.state_row(state, 704)
        row = self.repo.catalog.row(704, building['buildingLevel'])
        cost = row['PowerConsume']
        if state['star_energy'] < cost:
            LOGGER.warning('StartTrain refused: player=%s starEnergy=%s < cost=%s', player_id,
                           state['star_energy'], cost)
            return dict(result, code=38)
        duration = self.repo.catalog.effect(state, 704, 7)[0] * 3600
        if duration <= 0:
            LOGGER.warning('StartTrain refused: player=%s duration=%s', player_id, duration)
            return result
        now = self.repo.clock.now()
        # CollegeModule.GetHeroTrainExp (0x1AFC734) reads EffectType2=8,
        # EffectValue2[0] from the training building's CollegeLevel row.
        gain = self.repo.catalog.effect(state, 704, 8)[0]
        if gain <= 0:
            return result
        state['star_energy'] -= cost
        hero['college_status'] = 3
        job_id = uuid.uuid4().hex
        state['training'].append({'trainingId': pos, 'trainingStatus': 2,
            'trainingStartTime': now, 'trainingEndTime': now + duration,
            'trainingTime': duration, 'heroId': hid, 'difficulty': 0, 'buildID': row['BuildID'],
            'paid_energy': cost, 'gain_exp': gain, 'job_id': job_id})
        return dict(result, code=10, heroId=hid, diffdifficulty=0, trainTime=duration,
                    trainEndTime=now + duration, starEnergy=state['star_energy'], buildId=row['BuildID'])

    def _finish_train(self, player_id, state, snapshot, request):
        pos = request.get('trainId', 0)
        result = {'code': 13, 'trainId': pos}
        job = next((r for r in state['training'] if r['trainingId'] == pos), None)
        if not job:
            return result
        if job['trainingEndTime'] > self.repo.clock.now():
            return dict(result, code=205)
        hero = next((h for h in snapshot['heroes'] if h['id'] == job['heroId'] and h['state'] == 2), None)
        if not hero:
            return result
        from .hero_experience import add_hero_exp
        # Correct unfinished legacy jobs using the building row captured at start.
        # Upgrading the building afterwards must not change an existing job's XP.
        started_row = self.repo.catalog.levels.get(job.get('buildID'), {})
        gain = (started_row.get('EffectValue2', [0])[0]
                if started_row.get('EffectType2') == 8 else job['gain_exp'])
        credited = add_hero_exp(hero, gain, snapshot['level'])
        LOGGER.info('training XP player=%s hero=%s build=%s configured=%s credited=%s level=%s exp=%s',
                    player_id, hero['id'], job.get('buildID'), gain, credited, hero['level'], hero.get('exp', 0))
        hero['college_status'] = 0
        state['training'].remove(job)
        # Count once on successful collection, never on start or cancellation.
        self.economy._event(player_id, 'college-train:' + job['job_id'],
            self.economy.TASK_EVENT_HERO_TRAIN, 0, 1)
        self.economy._event(player_id, 'college-train:' + job['job_id'], 69, hero['id'], 1)
        return dict(result, code=10, heroId=hero['id'], heroLevel=hero['level'],
                    heroExp=hero.get('exp', 0), gainExp=credited)

    def _cancel(self, state, snapshot, request, training):
        kind, id_field = ('training', 'trainingId') if training else ('explore', 'exploreId')
        reply_id = 'trainId' if training else 'exploreId'
        pos = request.get(reply_id, 0)
        result = {'code': 13, reply_id: pos}
        job = next((r for r in state[kind] if r[id_field] == pos), None)
        if not job:
            LOGGER.warning('Cancel refused: %s slot=%s has no job (busy=%s)', kind, pos,
                           [r[id_field] for r in state[kind]])
            return result
        # Completed jobs must be claimed, never converted into a free refund.
        if job[kind + 'EndTime'] <= self.repo.clock.now():
            LOGGER.warning('Cancel refused: %s slot=%s already finished, claim it instead', kind, pos)
            return dict(result, code=205)
        ids = [job['heroId']] if training else job['heroList']
        for hero in snapshot['heroes']:
            if hero['id'] in ids:
                hero['college_status'] = 0
        state[kind].remove(job)
        if not training:
            # Existing compatibility proposal: cancel exploration returns its paid energy.
            state['star_energy'] = min(self.repo.catalog.effect(state, 702, 5)[0],
                state['star_energy'] + job['paid_energy'])
        return dict(result, code=10, starEnergy=state['star_energy'])

    def _start_explore(self, player_id, state, snapshot, request):
        from .college_power import hero_power
        pos, difficulty = request.get('exploreId', 0), request.get('diffdifficulty', 0)
        rid, ids = request.get('ruinId', 0), list(request.get('heroIds', []))
        result = {'code': 13}
        capacity = self.repo.catalog.effect(state, 705, 1, star=True)[0]
        ruin = next((r for r in state['ruins'] if r['ruinId'] == rid), None)
        row = self.explores.get(rid)
        if (not 0 <= pos < capacity or not row or not ruin or not 1 <= len(ids) <= 3
                or any(r['exploreId'] == pos for r in state['explore']) or difficulty not in range(3)):
            LOGGER.warning('StartExplore refused: player=%s exploreId=%s capacity=%s ruinId=%s inRuinTable=%s '
                           'inState=%s heroIds=%s busySlots=%s difficulty=%s',
                           player_id, pos, capacity, rid, bool(row), bool(ruin), ids,
                           [r['exploreId'] for r in state['explore']], difficulty)
            return result
        max_difficulty = max([1, *self.effects(row, ruin['exp'], 2)]) - 1
        if difficulty > max_difficulty:
            LOGGER.warning('StartExplore refused: player=%s ruinId=%s ruinExp=%s difficulty=%s > max=%s',
                           player_id, rid, ruin['exp'], difficulty, max_difficulty)
            return result
        code, heroes = self.heroes(state, snapshot, ids)
        if code != 10:
            LOGGER.warning('StartExplore refused: player=%s heroIds=%s hero check code=%s', player_id, ids, code)
            return dict(result, code=code)
        power = sum(hero_power(self.store, player_id, h, self.repo.clock) for h in heroes)
        # CollegeExplorePage ctor 0x1BBDA64 sets MINUAS_POINT=.5 for the
        # Chinese client (1 for Japanese). OnExploreButtonClick 0x1BBD35C
        # accepts TotalFightPoint / Conditon[difficulty] >= MINUAS_POINT.
        # Keep the configured full target separate from the admission minimum.
        target_power = row['Conditon'][difficulty]
        required_power = (target_power + 1) // 2
        if power < required_power:
            LOGGER.warning('StartExplore refused: player=%s ruinId=%s difficulty=%s power=%s < minimum=%s target=%s',
                           player_id, rid, difficulty, power, required_power, target_power)
            return dict(result, code=186)
        if state['star_energy'] < row['PowerConsume']:
            LOGGER.warning('StartExplore refused: player=%s ruinId=%s starEnergy=%s < cost=%s',
                           player_id, rid, state['star_energy'], row['PowerConsume'])
            return dict(result, code=38)
        coefficient = self.repo.catalog.effect(state, 705, 9)[0]
        duration = max(1, (row['WaitTimes'] - sum(self.effects(row, ruin['exp'], 4)))
                       * coefficient // (1000 * len(ids)))
        LOGGER.info('StartExplore accepted: player=%s ruinId=%s difficulty=%s heroIds=%s power=%s minimum=%s target=%s',
                    player_id, rid, difficulty, ids, power, required_power, target_power)
        state['star_energy'] -= row['PowerConsume']
        for hero in heroes:
            hero['college_status'] = 2
        state['explore'].append({'exploreId': pos, 'exploreStatus': 2, 'fightCapacity': power,
            'exploreEndTime': self.repo.clock.now() + duration, 'heroList': ids,
            'difficulty': difficulty, 'ruinId': rid, 'paid_energy': row['PowerConsume'],
            'quantity_bonus': sum(self.effects(row, ruin['exp'], 1)),
            'reward_coefficient': self.repo.catalog.effect(state, 705, 10)[0],
            'job_id': uuid.uuid4().hex})
        return dict(result, code=10)

    def _speed_explore(self, player_id, state, snapshot, request):
        from .college_alchemy import rules
        from .college_upgrade import BuildingUpgradeService
        pos = request.get('exploreId', 0)
        result = {'code': 13, 'exploreId': pos}
        job = next((r for r in state['explore'] if r['exploreId'] == pos), None)
        if not job:
            return result
        now = self.repo.clock.now()
        remaining = job['exploreEndTime'] - now
        if remaining <= 0:
            return dict(result, code=205)
        # CollegeExploreSpeedUp uses AlchemyExploreParam: 902|720|1.
        currency, seconds, units = map(int, rules()['params']['AlchemyExploreParam'].split('|'))
        if currency != 902 or seconds <= 0 or units <= 0:
            return result
        cost = (remaining * units + seconds - 1) // seconds
        code = BuildingUpgradeService._charge(self, player_id, snapshot, {1237902: cost})
        if code != 10:
            return dict(result, code=code)
        job['exploreEndTime'] = now
        # Keep heroes and rewards in the job until the separate claim succeeds.
        return dict(result, code=10, exploreEndTime=now)

    def _finish_explore(self, player_id, state, snapshot, request):
        import secrets
        from collections import Counter
        from .college_alchemy import rules
        pos = request.get('exploreId', 0)
        result = {'code': 13, 'exploreId': pos}
        job = next((r for r in state['explore'] if r['exploreId'] == pos), None)
        if not job:
            return result
        if job['exploreEndTime'] > self.repo.clock.now():
            return dict(result, code=205)
        row = self.explores[job['ruinId']]
        low, high = row[f'Num{job["difficulty"] + 1}']
        bonus, coefficient = job['quantity_bonus'], job['reward_coefficient']
        low, high = (low + bonus) * coefficient // 1000, (high + bonus) * coefficient // 1000
        deferred = Counter()
        rewards = Counter(self.economy.gifts([row['Reward']], deferred=deferred, allow_daily_random=True))
        element_items = {r['ItemID']: r['EffData'][0] for r in rules()['items']}
        # Element gifts belong in College storage, not ordinary inventory.
        # Other unknown destinations must abort the entire claim transaction.
        from .economy import UnresolvedEconomy
        if any(item not in element_items for item in deferred):
            raise UnresolvedEconomy('unrecovered College exploration reward destination')
        rewards.update(deferred)
        rewards[row['ProduceID']] += low + secrets.randbelow(high - low + 1)
        elements = {r['elementId']: r for r in state['alchemy']['elements']}
        caps = self.repo.catalog.effect(state, 706, 12)
        for item, count in rewards.items():
            if item in element_items:
                eid = element_items[item]
                elements[eid]['num'] = min(caps[eid - 991], elements[eid]['num'] + count)
        for hero in snapshot['heroes']:
            if hero['id'] in job['heroList']:
                hero['college_status'] = 0
        # Write hero release before _grant, which saves its own fresh snapshot.
        self.economy.save_snapshot(player_id, snapshot)
        self.economy._grant(player_id, 'college-explore:' + job['job_id'],
            {i: n for i, n in rewards.items() if i not in element_items and n > 0})
        self.economy._event(player_id, 'college-explore:' + job['job_id'],
            self.economy.TASK_EVENT_HERO_ADVENTURE, 0, 1)
        for hid in job['heroList']:
            self.economy._event(player_id, 'college-explore:' + job['job_id'], 67, hid, 1, job['ruinId'])
        state['explore'].remove(job)
        ruin = next(r for r in state['ruins'] if r['ruinId'] == job['ruinId'])
        ruin['exp'] = min(row['Exp'][-1], ruin['exp'] + 1)
        for unlocked in self.effects(row, ruin['exp'], 3):
            if unlocked in self.explores and not any(r['ruinId'] == unlocked for r in state['ruins']):
                state['ruins'].append({'ruinId': unlocked, 'exp': 0, 'queueCount': 0})
        return dict(result, code=10, ruinId=ruin['ruinId'], exp=ruin['exp'],
                    rewardData=self.economy.reward_bytes(rewards).hex())

    def handle(self, context, packet, flow, request):
        pid = context.session.player_id
        key = f'{context.session.session_id}:{packet.header.request_id}:{flow}'
        digest = hashlib.sha256(packet.body).hexdigest()
        with self.repo.transaction():
            self.repo.unlock_ruins(pid)
            state = self.repo.load(pid)
            self.repo.settle(state)
            receipt = self.db.execute('SELECT digest,response FROM college_job_receipts WHERE player_id=? AND receipt_key=?',
                                      (pid, key)).fetchone()
            if receipt:
                values = json.loads(receipt[1]) if receipt[0] == digest else {'code': 13}
            else:
                snapshot = self.store.get(pid)['snapshot']
                if flow.startswith('Cancel'):
                    values = self._cancel(state, snapshot, request, flow == 'CancelTrain')
                else:
                    method = {'StartTrain': self._start_train, 'FinishTrain': self._finish_train,
                              'StartExplore': self._start_explore, 'FinishExplore': self._finish_explore,
                              'ExploreSpeed': self._speed_explore}[flow]
                    values = method(pid, state, snapshot, request)
                if values['code'] == 10:
                    if flow not in ('FinishExplore', 'ExploreSpeed'):
                        self.economy.save_snapshot(pid, snapshot)
                    self.db.execute('INSERT INTO college_job_receipts VALUES (?,?,?,?)',
                                    (pid, key, digest, json.dumps(values)))
            self.repo.save(pid, state)
        if 'rewardData' in values:
            values['rewardData'] = bytes.fromhex(values['rewardData'])
        before = ()
        if values['code'] == 10:
            growth = self.repo.growth_base(pid)
            before = (OutboundMessage('L2C_QueryGrowthBase', growth),
                OutboundMessage('L2C_HeroUpdate', {'code': 10, 'heros': [encode_hero_data(h, season=self.economy.season, player_id=pid)
                    for h in self.store.get(pid)['snapshot']['heroes']]}),
                OutboundMessage('L2C_UnlockExploreRuin', {'code': 10, 'unlockExploreRuin':
                    [UNLOCK_EXPLORE_RUIN.encode(r) for r in self.repo.unlock_ruins(pid)]}),
                *self.economy.pushes(pid))
        return OutboundMessage('L2C_' + flow, values, before_response=before)
