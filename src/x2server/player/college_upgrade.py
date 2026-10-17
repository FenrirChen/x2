"""Official CollegeBuilding/Level/StarLevel progression; no invented pricing."""
from collections import Counter
from functools import lru_cache
from importlib.resources import files
import asyncio
import hashlib
import json
import logging

from x2server.network.dispatcher import OutboundMessage


@lru_cache(maxsize=1)
def _catalog():
    return json.loads(files('x2server').joinpath('data/college_upgrade_catalog.json').read_text(encoding='utf8'))


class UpgradeCatalog:
    def __init__(self):
        data = _catalog()
        self.buildings = {r['ID']: r for r in data['buildings']}
        self.levels = {r['BuildID']: r for r in data['levels']}
        self.stars = {r['BuildID']: r for r in data['stars']}

    def row(self, building_id, number, star=False):
        building = self.buildings[building_id]
        ids = building['StarID' if star else 'LevelID']
        if not 1 <= number <= len(ids):
            return None
        return (self.stars if star else self.levels)[ids[number - 1]]

    @staticmethod
    def state_row(state, building_id):
        return next((r for r in state['buildings'] + state['wonders'] if r['buildingId'] == building_id), None)

    def effect(self, state, building_id, effect_type, star=False):
        building = self.state_row(state, building_id)
        row = self.row(building_id, building.get('buildingStar', 0) if star else building['buildingLevel'], star)
        prefix = 'StarEffect' if star else 'Effect'
        for index in (1, 2):
            if row and row.get(f'{prefix}Type{index}') == effect_type:
                return list(row[f'{prefix}Value{index}'])
        return [0]


class BuildingUpgradeService:
    def __init__(self, repository, economy):
        self.repo = repository
        self.economy = economy
        self.catalog = repository.catalog
        self.db = repository.store.db
        from .college_alchemy import rules
        self.speed_cards = {r['ItemID']: r for r in rules()['speed_cards']}
        with repository.transaction():
            self.db.execute('''CREATE TABLE IF NOT EXISTS college_upgrade_receipts (
                player_id INTEGER NOT NULL, receipt_key TEXT NOT NULL, digest TEXT NOT NULL,
                response TEXT NOT NULL, PRIMARY KEY(player_id,receipt_key))''')

    def _charge(self, player_id, snapshot, costs):
        # Validate the entire cost vector first, then debit in the same savepoint
        # as the queue/star and receipt. Zero inventory rows are tombstones.
        for item, quantity in costs.items():
            if quantity <= 0:
                return 29
            currency = self.economy.CURRENCIES.get(item)
            if currency:
                if snapshot.get(currency, 0) < quantity:
                    return 35 if currency == 'gold' else 36 if currency == 'crystal' else 26
            else:
                row = self.db.execute('SELECT quantity FROM inventory WHERE player_id=? AND item_id=?',
                                      (player_id, item)).fetchone()
                if not row or row[0] < quantity:
                    return 22
        changed = False
        for item, quantity in costs.items():
            currency = self.economy.CURRENCIES.get(item)
            if currency:
                snapshot[currency] -= quantity
                changed = True
            else:
                self.db.execute('UPDATE inventory SET quantity=quantity-? WHERE player_id=? AND item_id=?',
                                (quantity, player_id, item))
        if changed:
            self.economy.save_snapshot(player_id, snapshot)
        return 10

    @staticmethod
    def costs(row):
        ids, quantities = row.get('Consume', []), row.get('ConsumeNum', [])
        if len(ids) != len(quantities):
            raise ValueError('mismatched official cost vector')
        result = Counter()
        for item, quantity in zip(ids, quantities):
            result[item] += quantity
        return result

    @staticmethod
    def wonder_condition(target, snapshot):
        from .battle_bonuses import catalog as bonus_catalog
        from .progression import catalog as progression_catalog
        condition = target.get('PreconditionType', 0)
        needed = target.get('PreconditionValue', 0)
        if condition not in range(1, 15):
            return False
        origin = (condition + 1) // 2
        identities = bonus_catalog()['heroes']
        heroes = {h['id']: h for h in snapshot.get('heroes', [])
                  if h.get('state') == 2 and identities.get(str(h['id']), {}).get('origin') == origin}
        if condition % 2:
            return len(heroes) >= needed
        # CheckHeroHelper sums PlayerStage.BigStarNum, not raw stage IDs and
        # not the number of heroes above a threshold.
        stars = {r['star']: r['big_star'] for r in progression_catalog()['hero_star']}
        return sum(stars.get(h.get('star', 0), 0) for h in heroes.values()) >= needed

    def _apply(self, player_id, flow, request, state):
        building_id, kind = request.get('buildingId', 0), request.get('type', 0)
        values = {'code': 13, 'buildingId': building_id, 'type': kind}
        building = self.catalog.buildings.get(building_id)
        current = self.catalog.state_row(state, building_id)
        if not building or not current or building.get('BuildingOpen') != 1 or kind != building['BaseType']:
            return values
        queue_key = 'build_queue' if kind == 1 else 'wonder_queue'
        queue = state.get(queue_key)
        snapshot = self.repo.store.get(player_id)['snapshot']
        if kind == 2 and snapshot['level'] < 25:
            return dict(values, code=37)
        now = self.repo.clock.now()
        if flow == 'BuildCrystalFinish':
            if not queue or queue['buildingId'] != building_id:
                return values
            # ServerData.SpeedUpTimes default=5 minutes (ctor q0 @4187a90);
            # InitData multiplies by 60. GetFastNeedCurrency returns
            # max(0, CeilToInt(remaining/300, .0001)-1): last five minutes free.
            remaining = queue['upgradeEndTime'] - now
            cost = max(0, (remaining + 299) // 300 - 1)
            if cost:
                values['code'] = self._charge(player_id, snapshot, {1237902: cost})
                if values['code'] != 10:
                    return values
            queue['upgradeEndTime'] = now
            self.repo.settle(state)
            return dict(values, code=10, buildStatus=1, crystal=snapshot.get('crystal', 0))
        if flow == 'BuildSpeedUP':
            if not queue or queue['buildingId'] != building_id:
                return values
            item, quantity = request.get('itemId', 0), request.get('itemNum', 0)
            item_row = self.speed_cards.get(item)
            if quantity <= 0 or not item_row or item_row.get('FunctionEff', {}).get('value') != 8:
                return values
            seconds = item_row.get('EffData', [0])[0]
            if seconds <= 0:
                return values
            # Refuse a forged excess quantity rather than burning unneeded items.
            remaining = queue['upgradeEndTime'] - now
            if quantity > (remaining + seconds - 1) // seconds:
                return values
            values['code'] = self._charge(player_id, snapshot, {item: quantity})
            if values['code'] != 10:
                return values
            queue['upgradeEndTime'] = max(now, queue['upgradeEndTime'] - seconds * quantity)
            end = queue['upgradeEndTime']
            self.repo.settle(state)
            values.update(endTime=end, buildTime=max(0, end - queue['upgradeStartTime']),
                          itemId=item, itemNum=quantity, buildStatus=1 if not state.get(queue_key) else 0)
            return values
        if queue:
            values['code'] = 55
            return values
        is_star = flow == 'BuildStarUP'
        number = current.get('buildingStar', 0) if is_star else current['buildingLevel']
        limit = building['StarLimited' if is_star else 'LevelLimited']
        if number >= limit:
            values['code'] = 14
            return values
        target = self.catalog.row(building_id, number + 1, is_star)
        if not target:
            values['code'] = 29
            return values
        if is_star:
            if kind == 2:
                if not self.wonder_condition(target, snapshot):
                    return dict(values, code=68)
            previous = self.catalog.row(building_id, number, True)
            if previous and current['buildingLevel'] < previous['LimitLevel']:
                values['code'] = 56
                return values
        else:
            if kind == 2 and current.get('buildingStar', 0) == 0:
                return dict(values, code=57)
            star = self.catalog.row(building_id, current.get('buildingStar', 0), True)
            if star and current['buildingLevel'] >= star['LimitLevel']:
                values['code'] = 57
                return values
            condition, needed = target.get('PreconditionType', 0), target.get('PreconditionValue', 0)
            if condition == 1 and snapshot['level'] < needed:
                values['code'] = 37
                return values
            if condition == 2 and self.catalog.state_row(state, 701)['buildingLevel'] < needed:
                return values
            if condition not in (0, 1, 2):
                values['code'] = 29
                return values
        values['code'] = self._charge(player_id, snapshot, self.costs(target))
        if values['code'] != 10:
            return values
        if is_star:
            current['buildingStar'] = number + 1
            values['star'] = number + 1
        else:
            duration = target.get('WaitTimes', 0)
            state[queue_key] = {'buildingId': building_id, 'upgradeStatus': 1,
                'upgradeStartTime': now, 'upgradeEndTime': now + duration, 'target_level': number + 1}
            values.update(endTime=now + duration, buildTime=duration)
            self.repo.settle(state)
        return values

    def handle(self, context, packet, flow, request):
        player_id = context.session.player_id
        receipt_key = f'{context.session.session_id}:{packet.header.request_id}:{flow}'
        digest = hashlib.sha256(packet.body).hexdigest()
        with self.repo.transaction():
            state = self.repo.load(player_id)
            self.repo.settle(state)
            receipt = self.db.execute('SELECT digest,response FROM college_upgrade_receipts WHERE player_id=? AND receipt_key=?',
                                      (player_id, receipt_key)).fetchone()
            if receipt:
                values = json.loads(receipt[1]) if receipt[0] == digest else {'code': 13}
            else:
                values = self._apply(player_id, flow, request, state)
                if values['code'] == 10:
                    self.db.execute('INSERT INTO college_upgrade_receipts VALUES (?,?,?,?)',
                                    (player_id, receipt_key, digest, json.dumps(values)))
            self.repo.save(player_id, state)
        before = ()
        if values['code'] == 10:
            # 244/246 handlers fire UI refresh events; authoritative 584 must be
            # installed first so they use the new queue, star and effects.
            before = (OutboundMessage('L2C_QueryGrowthBase', self.repo.growth_base(player_id)),
                      *self.economy.pushes(player_id))
        return OutboundMessage('L2C_' + flow, values, before_response=before)

    def complete_due(self, player_id):
        from .college_pray import prayer_day, daily_fields
        with self.repo.transaction():
            state = self.repo.load(player_id)
            self.repo.settle(state)
            daily_reset = bool(state.get('pray_daily') and
                state['pray_daily'].get('day') != prayer_day(self.repo.clock.now()))
            if daily_reset:
                state['pray_daily'] = {'day': prayer_day(self.repo.clock.now()), 'count': 0}
            completed = state.pop('upgrade_notifications', [])
            training = [r for r in state['training'] if r['trainingEndTime'] <= self.repo.clock.now()
                        and not r.get('completion_notified')]
            for row in training:
                row['completion_notified'] = True
            prayers = [r for r in state['pray'] if r['prayEndTime'] <= self.repo.clock.now()
                       and not r.get('completion_notified')]
            for row in prayers:
                row['completion_notified'] = True
            if completed or training or prayers or daily_reset:
                self.repo.save(player_id, state)
        daily_push = ((OutboundMessage('PlayerDataProto',
            {'Daily': daily_fields(state, self.repo.clock.now())}, data_version=1),) if daily_reset else ())
        if not completed and not training and not prayers:
            return daily_push
        growth = self.repo.growth_base(player_id)
        return (OutboundMessage('L2C_QueryGrowthBase', growth),
                *(OutboundMessage('L2C_UpLevelBuildingId', {'buildingId': bid}) for bid in completed),
                *(OutboundMessage('L2C_PrayEnd', {'buildingId': r['buildingId']}) for r in prayers),
                *((OutboundMessage('L2C_TrainingUpdate', {'trainList': growth['trainingList']}),)
                  if training else ()), *daily_push)

    async def watch(self, tcp):
        while True:
            await self.repo.store.wait_for_import()
            for player_id in tcp.authenticated_player_ids():
                await self.repo.store.wait_for_import()
                try:
                    for message in self.complete_due(player_id):
                        await tcp.push_to_player(player_id, message)
                except Exception:
                    logging.getLogger('x2.college').exception('building completion player=%s', player_id)
            await asyncio.sleep(1)
