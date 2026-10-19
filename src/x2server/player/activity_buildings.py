"""Sakura buildings: original level costs and period-owned extra-drop effects."""
from x2server.messages.activity import encode
from .economy import UnresolvedEconomy


class ActivityBuildings:
    def __init__(self, activity):
        self.a, self.r, self.e = activity, activity.rotation, activity.economy
        self.rows = {(r['BuildingID'], r['BuildingLevel']): r
                     for r in activity.tables['ActivityBuilding']}

    def rows_for(self, period):
        owned = {a['ActivityID'] for a in period.theme['activities']}
        return {key: row for key, row in self.rows.items() if row['ActivityID'] in owned}

    def level(self, player, period, building):
        return self.r.get(player, period, 'building', building, 0)

    def values(self, player, period):
        ids = sorted({key[0] for key in self.rows_for(period)})
        if not ids:
            raise UnresolvedEconomy('current activity has no buildings')
        return {'code': 10, 'buildings': [encode('ActivityBuilding',
            {'id': bid, 'lv': self.level(player, period, bid)}) for bid in ids]}

    def upgrade(self, player, period, building, token):
        if type(building) is not int:
            raise UnresolvedEconomy('invalid activity building')
        level = self.level(player, period, building)
        row = self.rows_for(period).get((building, level + 1))
        if row is None:
            raise UnresolvedEconomy('unknown building or maximum level')
        # RefreshView @1551ef4 looks up (id, current+1), then reads the
        # target row's UnlockItem and LevelUpNum at 1552600..155261c.
        self.a.spend(player, period, row['UnlockItem'], row['LevelUpNum'],
                     f'building:{token}')
        self.r.put(player, period, 'building', building, level + 1)
        return {'code': 10, 'id': building, 'lv': level + 1}

    def effects(self, player, period):
        result = set()
        for bid in {key[0] for key in self.rows_for(period)}:
            row = self.rows.get((bid, self.level(player, period, bid)))
            if row:
                result.update(row['BuildingEffect'])
        return result
