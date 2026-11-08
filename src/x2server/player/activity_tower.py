"""Period-owned Full-view Rift tower growth and explicit first-clear rewards."""
from collections import Counter
from x2server.messages.activity import encode, ACTIVITY_SCHEMAS
from .economy import UnresolvedEconomy


class ActivityTower:
    OPERATIONS = {'QueryActivityTower', 'ActivityTowerLevelUp',
                  'QueryTowerReward', 'ReceiveTowerReward'}

    def __init__(self, activity):
        self.a, self.e, self.r = activity, activity.economy, activity.rotation
        self.rows = {row['ID']: row for row in activity.tables['Tower']}
        self.ranks = {row['ID']: row for row in activity.tables['TowerRank']}
        self.base = {row['Type']: row['ID'] for row in self.rows.values() if row['Level'] == 1}
        if len(self.base) != 6:
            raise ValueError('tower catalog must contain six level-one tower types')
        self.currency = next(iter(self.rows.values()))['CostItem']

    def owns(self, section):
        return section in self.ranks

    def balance(self, player):
        row = self.a.store.db.execute('SELECT quantity FROM inventory WHERE player_id=? AND item_id=?',
                                      (player, self.currency)).fetchone()
        return int(row[0]) if row else 0

    def owned(self, player, period):
        result = {}
        saved = self.r.get(player, period, 'tower', 'owned')
        if saved is None:
            saved = [row['ID'] for row in self.rows.values() if
                     self.r.get(player, period, 'obtained-item', row['TowerItem'], 0)]
        for tid in saved:
            row = self.rows.get(tid)
            if row and (row['Type'] not in result or
                        row['Level'] > self.rows[result[row['Type']]]['Level']):
                result[row['Type']] = tid
        return result

    def legacy_pending(self, player, period, section):
        rows = self.a.store.db.execute('''SELECT p.item_id,SUM(p.quantity)
            FROM pending_rewards p JOIN activity_runs a
            ON p.player_id=a.player_id AND p.source='battle:' || a.uuid
            WHERE a.player_id=? AND a.period=? AND a.section_id=? AND a.settled=1
            GROUP BY p.item_id''', (player, period.index, section))
        items = {row['TowerItem'] for row in self.rows.values()}
        return {item: count for item, count in rows if item in items and count > 0}

    def received(self, player, period):
        # Old servers paid FirVReward at checkout. Never pay those clears again;
        # only new settlements explicitly mark a reward as pending manual claim.
        return sorted(sid for sid in self.ranks if
            self.r.get(player, period, 'tower-reward-claimed', sid, False) or
            (self.r.get(player, period, 'clear', sid, 0) and not
             self.r.get(player, period, 'tower-reward-pending', sid, False) and not
             self.legacy_pending(player, period, sid)))

    def entry(self, player, section, requested):
        """Echo native Tower IDs, resolving stale saved levels to current ownership."""
        period = self.a.period(player)
        owned = self.owned(player, period)
        rank = self.ranks[section]
        limit = rank.get('TowerNumber', 0)
        selected, kinds = [], set()
        # The first two lessons use behavior-script-provided towers (limit=0).
        if limit:
            for tid in requested:
                row = self.rows.get(tid)
                if (not row or row['Type'] not in owned or row['Type'] in kinds
                        or row['Type'] not in rank['Tower']):
                    raise UnresolvedEconomy('invalid or locked defense tower selection')
                kinds.add(row['Type'])
                selected.append(owned[row['Type']])
            if not 1 <= len(selected) <= limit:
                raise UnresolvedEconomy('invalid defense tower team size')
        reply = self.a.runtime.operate(player, 'ActivityTowerPassive', {}, 'entry')
        passive = next(ACTIVITY_SCHEMAS['ActivityTowerPassive'].decode(raw)
                       for raw in reply['passives']
                       if ACTIVITY_SCHEMAS['ActivityTowerPassive'].decode(raw)['sectionId'] == section)
        return {'selectedTowerList': selected,
                'towerPlayerPassiveList': passive['heroPassiveIds'],
                'towerMonsterPassiveList': passive['monsterPassiveIds']}

    def handle(self, player, op, req, token):
        period = self.a.period(player)
        if self.r.of_type(50, period) is None:
            raise UnresolvedEconomy('tower defense is not open')
        owned = self.owned(player, period)
        if op == 'QueryActivityTower':
            return {'code': 10, 'towerInfo': [encode('ActivityTowerInfo', {'id': owned[k]})
                                             for k in sorted(owned)] or [encode('ActivityTowerInfo', {})],
                    'towerPoint': self.balance(player)}
        if op == 'ActivityTowerLevelUp':
            kind, action = req.get('type'), req.get('opt', 0)
            if kind not in owned or action not in (0, 1):
                raise UnresolvedEconomy('invalid tower type or operation')
            current = self.rows[owned[kind]]
            if action == 0:
                target = next((row for row in self.rows.values() if row['Type'] == kind
                               and row['Level'] == current['Level'] + 1), None)
                if target is None:
                    raise UnresolvedEconomy('tower is already at maximum level')
                self.a.spend(player, period, self.currency, current['Cost'], 'tower-up:' + token)
            else:
                if current['Level'] == 1:
                    raise UnresolvedEconomy('tower is already reset')
                refund = sum(row.get('Cost', 0) for row in self.rows.values()
                             if row['Type'] == kind and row['Level'] < current['Level'])
                self.e._grant(player, self.a.source(period, 'tower-reset', token), {self.currency: refund})
                target = self.rows[self.base[kind]]
            owned[kind] = target['ID']
            self.r.put(player, period, 'tower', 'owned', [owned[k] for k in sorted(owned)])
            return {'code': 10, 'towerInfo': encode('ActivityTowerInfo', {'id': target['ID']}),
                    'towerPoint': self.balance(player)}
        received = self.received(player, period)
        if op == 'QueryTowerReward':
            return {'code': 10, 'received': received or [0]}
        section = req.get('sectionId', 0)
        if (section not in self.ranks or section not in period.theme['section_ids'] or
                section in received or not self.r.get(player, period, 'clear', section, 0)):
            raise UnresolvedEconomy('tower reward is locked or already received')
        legacy = self.legacy_pending(player, period, section)
        if legacy and not self.r.get(player, period, 'tower-reward-pending', section, False):
            rewards = legacy  # Currency was already delivered; only repair parked towers.
        else:
            deferred = Counter()
            rewards = self.e.gifts(self.a.sections[section]['FirVReward'], deferred=deferred)
            valid = {row['TowerItem'] for row in self.rows.values()}
            if set(deferred) - valid:
                raise UnresolvedEconomy('unknown tower reward destination')
            rewards = dict(Counter(rewards) + deferred)
        rewards = self.e._grant(player, self.a.source(period, 'tower-first-clear', section),
                                rewards, stackable_types=(8,))
        self.a.obtained(player, period, rewards, f'tower-first-clear:{section}')
        for row in self.rows.values():
            if rewards.get(row['TowerItem'], 0) and (row['Type'] not in owned or
                    row['Level'] > self.rows[owned[row['Type']]]['Level']):
                owned[row['Type']] = row['ID']
        self.r.put(player, period, 'tower', 'owned', [owned[k] for k in sorted(owned)])
        for item in legacy:
            self.a.store.db.execute('''DELETE FROM pending_rewards WHERE player_id=? AND item_id=?
                AND source IN (SELECT 'battle:' || uuid FROM activity_runs
                WHERE player_id=? AND period=? AND section_id=? AND settled=1)''',
                (player, item, player, period.index, section))
        self.r.put(player, period, 'tower-reward-claimed', section, True)
        return {'code': 10, 'received': sorted(received + [section]),
                'rewardData': self.e.reward_bytes(rewards)}
