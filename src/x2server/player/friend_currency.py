"""Friend points: cap grants and repair legacy/imported balances consistently."""
import logging
import uuid

ITEM_ID = 1237917
LIMIT = 5000


def repair(store,player_id=None):
    marker='friend_cap_'+uuid.uuid4().hex
    store.db.execute('SAVEPOINT '+marker)
    try:
        clause=' AND player_id=?' if player_id is not None else ''
        args=(LIMIT,ITEM_ID,LIMIT,player_id) if player_id is not None else (LIMIT,ITEM_ID,LIMIT)
        changed=store.db.execute('UPDATE inventory SET quantity=? WHERE item_id=? AND quantity>?'+clause,args).rowcount
    except BaseException:
        store.db.execute('ROLLBACK TO '+marker)
        store.db.execute('RELEASE '+marker)
        raise
    store.db.execute('RELEASE '+marker)
    if changed:
        logging.getLogger('x2.social').info('friendship point cap repaired player=%s rows=%s',player_id,changed)
    return changed


def capped_rewards(store,player_id,rewards):
    if ITEM_ID not in rewards:
        return rewards
    if type(rewards[ITEM_ID]) is not int or rewards[ITEM_ID]<=0:
        return rewards  # Keep EconomyService's original invalid-reward checks.
    repair(store,player_id)
    row=store.db.execute('SELECT quantity FROM inventory WHERE player_id=? AND item_id=?',(player_id,ITEM_ID)).fetchone()
    owned=row[0] if row else 0
    result=dict(rewards)
    result[ITEM_ID]=min(result[ITEM_ID],max(0,LIMIT-owned))
    if result[ITEM_ID]==0:
        del result[ITEM_ID]
    return result
