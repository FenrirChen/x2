"""Persistent earned medals and three native display slots."""
import json
from functools import lru_cache
from importlib.resources import files
from x2server.messages.core import INT_PAIR
from x2server.messages.medals import MEDAL_PACK, MEDAL_SHOW, MEDAL_SYSTEM, MEDAL_SCHEMAS
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError


@lru_cache(maxsize=1)
def catalog():
    return {r['MedalItem']: r for r in json.loads(files('x2server').joinpath(
        'data/medals.json').read_text(encoding='utf-8'))['medals']}


def owned(store, player_id, snapshot):
    earned = snapshot.get('medal_earned', {})
    if store is None:
        return {}
    # Old genuine grants already reside in inventory; unlike avatar-frame
    # compatibility projections, querying the ledger never invents ownership.
    return {catalog()[item]['MedalID']: earned.get(str(item), 1)
            for item, count in store.db.execute(
                'SELECT item_id,quantity FROM inventory WHERE player_id=? AND quantity>0', (player_id,))
            if item in catalog()}


def snapshot_value(store, player_id, snapshot):
    medals = owned(store, player_id, snapshot)
    positions = snapshot.get('medal_positions', {})
    return MEDAL_SYSTEM.encode({'MedalPack': MEDAL_PACK.encode({'Medal': [
        INT_PAIR.encode({'Key': key, 'Value': value}) for key, value in sorted(medals.items())]}),
        'MedalShow': MEDAL_SHOW.encode({'Position': [INT_PAIR.encode({'Key': i,
            'Value': positions.get(str(i), 0) if positions.get(str(i), 0) in medals else 0})
            for i in range(3)]})})


class MedalService:
    def __init__(self, economy):
        self.economy, self.store = economy, economy.store

    def handlers(self):
        return {'C2L_MedalOpt': self.handle}

    async def handle(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError('medal wearing before login')
        entries = [INT_PAIR.decode(raw) for raw in MEDAL_SCHEMAS['C2L_MedalOpt'].decode(packet.body).get('pos', [])]
        reject = OutboundMessage('L2C_MedalOpt', {'code': 13})
        if not 1 <= len(entries) <= 3 or len({e.get('Key') for e in entries}) != len(entries):
            return reject
        with self.economy.transaction():
            snapshot = self.store.get(player_id)['snapshot']
            medals = owned(self.store, player_id, snapshot)
            positions = dict(snapshot.get('medal_positions', {}))
            for entry in entries:
                slot, medal = entry.get('Key'), entry.get('Value', 0)
                if slot not in range(3) or medal != 0 and medal not in medals:
                    return reject
                positions[str(slot)] = medal
            nonzero = [v for v in positions.values() if v]
            if len(set(nonzero)) != len(nonzero):
                return reject
            snapshot['medal_positions'] = positions
            self.economy.save_snapshot(player_id, snapshot)
        return OutboundMessage('L2C_MedalOpt', {'code': 10},
            before_response=(self.economy.pushes(player_id)[0],))
