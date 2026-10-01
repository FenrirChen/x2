"""Deliver previously deferred battle rewards whose destinations are now supported."""
import hashlib
import logging
from x2server.player.equipment_factory import materialize_instances


def recover(economy, player_id):
    store = economy.store
    with economy.transaction():
        store.db.execute('''CREATE TABLE IF NOT EXISTS pending_reward_deliveries (
            player_id INTEGER NOT NULL, source TEXT NOT NULL, item_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL, PRIMARY KEY(player_id,source,item_id))''')
        rows = store.db.execute('''SELECT p.source,p.item_id,p.quantity FROM pending_rewards p
            LEFT JOIN pending_reward_deliveries d ON d.player_id=p.player_id
                AND d.source=p.source AND d.item_id=p.item_id
            WHERE p.player_id=? AND d.source IS NULL AND p.source LIKE 'battle:%' ''', (player_id,)).fetchall()
        for source, item, count in rows:
            run_id = source.removeprefix('battle:')
            run = store.db.execute('SELECT player_id,settled FROM economy_runs WHERE uuid=?', (run_id,)).fetchone()
            if not run or run['player_id'] != player_id or not run['settled'] or count <= 0:
                continue
            # A parked row is authoritative only alongside the committed grant
            # ledger. Do not deliver an item already present in that grant.
            original = store.db.execute('SELECT rewards FROM economy_grants WHERE player_id=? AND source=?',
                                        (player_id, source)).fetchone()
            if not original:
                continue
            import json
            if str(item) in json.loads(original[0]):
                continue
            kind = economy.items.get(item, {}).get('ItemType', {}).get('value')
            token = hashlib.sha256(f'{player_id}:{source}:{item}'.encode()).hexdigest()
            if kind == 10 and str(item) in economy.equipment_factory.data['equib_base']:
                # Old fixed Gift equipment was parked without quality. Preserve
                # today's fixed Gift rule (one-star); never reroll a runtime drop.
                materialize_instances(store.db, player_id, item, 1, count,
                                      'pending:' + token, economy.equipment_factory, 0)
            elif (kind in economy.STACKABLE_REWARD_TYPES or item in economy.CURRENCIES
                  or kind == 16 and economy.items[item].get('ItemUseScence', {}).get('value') == 1):
                economy._grant(player_id, 'pending-delivery:' + token, {item: count})
            else:
                continue
            store.db.execute('INSERT INTO pending_reward_deliveries VALUES (?,?,?,?)',
                             (player_id, source, item, count))
            logging.getLogger('x2.rewards').info('pending battle reward delivered player=%s source=%s item=%s count=%s',
                                               player_id, source, item, count)
