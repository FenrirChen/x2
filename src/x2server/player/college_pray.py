"""Persisted wonder prayers, admission, acceleration and exactly-once claims."""
from collections import Counter
import hashlib
import json
import secrets
import uuid

from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.protobuf import ProtoSchema, ProtoField, FieldKind
from .college_power import rules
from .college_jobs import CollegeJobsService
from .hero import encode_hero_data

PRAY_DAILY = ProtoSchema('PrayDaily', (ProtoField(12, 'PrayCount', FieldKind.INT32),))


def prayer_day(now):
    # Language 13101058 explicitly specifies 05:00 China time.
    return (now + 10800) // 86400


def daily_fields(state, now):
    record = state.get('pray_daily', {})
    count = record.get('count', 0) if record.get('day') == prayer_day(now) else 0
    return PRAY_DAILY.encode({'PrayCount': count})


class CollegePrayService:
    FLOWS = ('BuildStartPrayGod', 'BuildCancelPrayGod', 'BuildRewardPrayGod', 'BuildQuickenPrayGod')

    def __init__(self, repository, economy, upgrades):
        self.repo, self.economy, self.upgrades = repository, economy, upgrades
        self.db = repository.store.db
        self.heroes = {hid: r for hid, r in rules()[1].items() if hid < 2000}
        with repository.transaction():
            self.db.execute('''CREATE TABLE IF NOT EXISTS college_pray_receipts (
                player_id INTEGER NOT NULL, receipt_key TEXT NOT NULL, digest TEXT NOT NULL,
                response TEXT NOT NULL, PRIMARY KEY(player_id,receipt_key))''')

    def apply(self, pid, state, snapshot, flow, req):
        bid, now = req.get('buildingId', 0), self.repo.clock.now()
        result = {'code': 13, 'buildingId': bid}
        building = self.repo.catalog.buildings.get(bid)
        saved = self.repo.catalog.state_row(state, bid)
        if not building or building.get('BaseType') != 2 or not building.get('BuildingOpen') or not saved:
            return result
        if snapshot['level'] < 25 or saved.get('buildingStar', 0) < 2:
            return dict(result, code=57)
        job = next((j for j in state['pray'] if j['buildingId'] == bid), None)
        if flow == 'BuildStartPrayGod':
            if job:
                return dict(result, code=55)
            day = prayer_day(now)
            daily = state.get('pray_daily', {})
            count = daily.get('count', 0) if daily.get('day') == day else 0
            if count >= 5:
                return dict(result, code=13)
            hid, sacrifice = req.get('heroId', 0), req.get('itemId', 0)
            # ServerData ctor + OnCheckTabOpen/RefreshPaiQian: prayer=2,
            # guardian=3; RefreshSacrifice requires 4 stars.
            if (hid and saved['buildingStar'] < 3) or (sacrifice and saved['buildingStar'] < 4):
                return dict(result, code=57)
            origin = building['BuildType']
            hero = next((h for h in snapshot.get('heroes', []) if h['id'] == hid and h.get('state') == 2), None)
            if hid:
                code, _ = CollegeJobsService.heroes(self, state, snapshot, [hid])
                if code != 10:
                    return dict(result, code=code)
                if self.heroes.get(hid, {}).get('Origin', {}).get('value') != origin:
                    return result
            # Optional sacrifice selector uses BagModule filter=2 (E_Chip).
            if sacrifice and (self.economy.items.get(sacrifice, {}).get('ItemType', {}).get('value') != 12):
                return result
            costs = Counter(dict(zip(building['PrayItem'], building['PrayItemNum'], strict=True)))
            bonus = self.heroes[hid].get('PrayBouns', 1000) if hid else 1000
            costs = Counter({i: max(1, n * bonus // 1000) for i, n in costs.items()})
            if sacrifice:
                costs[sacrifice] += 1
            candidates = [r for r in self.heroes.values() if r.get('IsOpen') and
                          r.get('Origin', {}).get('value') == origin and r.get('ChipPropID')]
            if not candidates:
                return result
            target = self.heroes[hid] if hid else secrets.choice(candidates)
            code = self.upgrades._charge(pid, snapshot, costs)
            if code != 10:
                return dict(result, code=code)
            duration = building['PrayWaitTimes']
            job_id = uuid.uuid4().hex
            state['pray'].append({'buildingId': bid, 'prayStatus': 1, 'prayStartTime': now,
                'prayEndTime': now + duration, 'prayItemID': sacrifice, 'prayItemNum': int(bool(sacrifice)),
                'prayHeroID': hid, 'paid': dict(costs), 'reward_item': target['ChipPropID'],
                # Language 13102257: one sacrificed chip doubles proceeds.
                'reward_num': 10 if sacrifice else 5, 'job_id': job_id})
            state['pray_daily'] = {'day': day, 'count': count + 1}
            if hero:
                hero['college_status'] = 1
            self.economy.save_snapshot(pid, snapshot)
            # 奇迹祈神计入 E_BaseBless (economy_catalog.json 630006 日 / 630112 周)。
            self.economy._event(pid, 'college-pray:' + job_id,
                self.economy.TASK_EVENT_BASE_BLESS, 0, 1)
            return dict(result, code=10, heroStatus=1 if hid else 0, prayTime=duration, endTime=now + duration)
        if not job:
            return result
        if flow == 'BuildQuickenPrayGod':
            if job['prayEndTime'] <= now:
                return dict(result, code=205)
            card, count = req.get('itemId', 0), req.get('itemNum', 0)
            row = self.upgrades.speed_cards.get(card)
            if not row or count <= 0:
                return result
            seconds = row.get('EffData', [0])[0]
            if seconds <= 0 or count > (job['prayEndTime'] - now + seconds - 1) // seconds:
                return result
            code = self.upgrades._charge(pid, snapshot, {card: count})
            if code != 10:
                return dict(result, code=code)
            job['prayEndTime'] = max(now, job['prayEndTime'] - seconds * count)
            self.repo.settle(state)
            return dict(result, code=10, endTime=job['prayEndTime'])
        if flow == 'BuildRewardPrayGod' and job['prayEndTime'] > now:
            return dict(result, code=205)
        if flow == 'BuildCancelPrayGod' and job['prayEndTime'] <= now:
            return dict(result, code=205)
        # Cancellation text 13102273 promises the prayer symbol back;
        # gold, sacrificed chips and speed cards remain consumed.
        rewards = ({job['reward_item']: job['reward_num']} if flow == 'BuildRewardPrayGod'
                   else {1237840: job['paid'].get('1237840', job['paid'].get(1237840, 0))})
        for hero in snapshot.get('heroes', []):
            if hero['id'] == job['prayHeroID']:
                hero['college_status'] = 0
        self.economy.save_snapshot(pid, snapshot)
        self.economy._grant(pid, 'college-pray:' + flow + ':' + job['job_id'], rewards)
        state['pray'].remove(job)
        if flow == 'BuildRewardPrayGod':
            # 与 BuildStartPrayGod 共用同一 job_id，economy_events 去重，避免重复计数。
            self.economy._event(pid, 'college-pray:' + job['job_id'],
                self.economy.TASK_EVENT_BASE_BLESS, 0, 1)
            result['rewardData'] = self.economy.reward_bytes(rewards).hex()
        return dict(result, code=10)

    occupied = staticmethod(CollegeJobsService.occupied)

    def handle(self, context, packet, flow, req):
        pid = context.session.player_id
        key = f'{context.session.session_id}:{packet.header.request_id}:{flow}'
        digest = hashlib.sha256(packet.body).hexdigest()
        with self.repo.transaction():
            state = self.repo.load(pid)
            self.repo.settle(state)
            receipt = self.db.execute('SELECT digest,response FROM college_pray_receipts WHERE player_id=? AND receipt_key=?', (pid, key)).fetchone()
            if receipt:
                values = json.loads(receipt[1]) if receipt[0] == digest else {'code': 13}
            else:
                values = self.apply(pid, state, self.repo.store.get(pid)['snapshot'], flow, req)
                if values['code'] == 10:
                    self.db.execute('INSERT INTO college_pray_receipts VALUES (?,?,?,?)', (pid, key, digest, json.dumps(values)))
            self.repo.save(pid, state)
        if 'rewardData' in values:
            values['rewardData'] = bytes.fromhex(values['rewardData'])
        before = ()
        if values['code'] == 10:
            before = (OutboundMessage('L2C_QueryGrowthBase', self.repo.growth_base(pid)),
                OutboundMessage('PlayerDataProto', {'Daily': daily_fields(state, self.repo.clock.now())}, data_version=1),
                OutboundMessage('L2C_HeroUpdate', {'code': 10, 'heros': [encode_hero_data(h)
                    for h in self.repo.store.get(pid)['snapshot'].get('heroes', [])]}), *self.economy.pushes(pid))
        return OutboundMessage('L2C_' + flow, values, before_response=before)
