"""Resource bonus drops governed by the same ActivityData shown to the client."""
import json
from importlib.resources import files
from x2server.messages.activity import encode


def config():
    return json.loads(files('x2server').joinpath('data/resource_drop_activity.json').read_text('utf8'))


def resource_drop_enabled():
    return bool(config()['enabled'])


def beijing_day(now):
    return (int(now) + 28800) // 86400


class ExtraDropService:
    # A separate namespace in the existing exported activity_state avoids adding
    # player data outside the complete save boundary. Quotas survive theme rotation.
    PERIOD = -71004

    def __init__(self, economy, enabled=False):
        self.e = economy
        self.store, self.clock = economy.store, economy.clock
        self.enabled = bool(enabled)
        self.config = config()
        self.by_section = {}
        self.rows = {}
        data = json.loads(files('x2server').joinpath('data/activity_rotation_catalog.json').read_text('utf8'))
        wanted = set(self.config['activity']['param1'])
        for row in data['tables']['ExtraDroop']:
            if row['ID'] not in wanted:
                continue
            ratios = row.get('DroopUPParam') or []
            sections = row.get('SectionGroup') or []
            if len(ratios) != 1 or ratios[0] != 100:
                raise ValueError('resource activity requires verified +100% rows')
            self.rows[row['ID']] = row
            for section in sections:
                if section in economy.daily_sections:
                    self.by_section[section] = row
        if set(self.rows) != wanted:
            raise ValueError('resource activity drop configuration incomplete')

    def active(self, player):
        return (self.enabled and self.config['enabled']
                and self.config['start'] <= int(self.clock()) < self.config['end']
                and getattr(self.e, 'activity', None) is not None
                and self.store.get(player)['snapshot']['level'] >= self.config['activity']['openLever'])

    def activity_values(self, player):
        if not self.enabled:
            return []
        row = dict(self.config['activity'], state=int(self.active(player)),
            startTime=self.config['start'], endTime=self.config['end'],
            activityShow=0, openType=0, openParam=[0], param4=[0], activityReward=[0],
            activityDataItems=[encode('ActivityDataItem', {'index':0,
                'itemParams':[encode('ItemData', {'id':0,'num':0})]})])
        return [encode('ActivityData', row)]

    def used(self, player, row_id):
        namespace = 'resource-double:' + str(beijing_day(self.clock()))
        row = self.store.db.execute('SELECT value FROM activity_state WHERE player_id=? '
            'AND period=? AND namespace=? AND state_key=?',
            (player,self.PERIOD,namespace,str(row_id))).fetchone()
        return int(json.loads(row[0])) if row else 0

    def values(self, player):
        if not self.active(player):
            return []
        return [encode('KeyValuePair_Int32_Int32', {'Key':rid,'Value':self.used(player,rid)})
                for rid in sorted(self.rows)]

    def rewards(self, player, section, base):
        row = self.by_section.get(section)
        if row is None or not self.active(player):
            return {}
        used = self.used(player, row['ID'])
        if used >= min(10, row['NumLimit']):
            return {}
        # Only the official ExtraParam1 resources receive a bonus. First-clear
        # hero rewards, currencies and unrelated drops must not also be doubled.
        rewards = {item:int(base.get(item,0)) for item in row['ExtraParam1'] if base.get(item,0)>0}
        if not rewards:
            return {}
        namespace = 'resource-double:' + str(beijing_day(self.clock()))
        self.store.db.execute('INSERT INTO activity_state VALUES (?,?,?,?,?) '
            'ON CONFLICT(player_id,period,namespace,state_key) DO UPDATE SET value=excluded.value',
            (player,self.PERIOD,namespace,str(row['ID']),json.dumps(used+1)))
        return rewards

