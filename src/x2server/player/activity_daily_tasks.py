"""Match event daily tasks to the live theme; recover today's proven actions."""
from .task_calendar import task_period
from x2server.messages.battle import CHECKOUT
from x2server.messages.economy import ECONOMY_SCHEMAS

TASK_IDS = frozenset((630025, 630026, 630040, 630041))


def task_open(economy, task_id):
    if task_id not in TASK_IDS:
        return True
    activity = getattr(economy, 'activity', None)
    period = activity.rotation.at() if activity else None
    if period is None:
        return False
    condition = economy.catalog['task_conditions'][str(task_id)]
    kind = condition['CompleteType']['value']
    if kind == 3:
        required = set(condition.get('CompleteValue1', [])) - {0}
        return bool(required) and required <= set(period.theme['section_ids'])
    if kind == 24:
        aids = {row['ActivityID'] for row in period.theme['activities']}
        shops = {row['ShopID'] for row in activity.tables['ShopConfig']
                 if row.get('ShopParam1') in aids}
        required = set(condition.get('CompleteValue2', [])) - {0}
        return bool(required) and required <= shops
    return False


def repair(economy, player):
    activity = getattr(economy, 'activity', None)
    period = activity.rotation.at() if activity else None
    if period is None:
        return
    level = economy.store.get(player)['snapshot']['level']
    ids = [tid for tid in TASK_IDS if task_open(economy, tid)
           and economy.tasks[tid]['AcceptLevel'] <= level]
    if not ids:
        return
    db = economy.store.db
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='battle_checkout_wire'").fetchone():
        return  # Do not finish recovery during partial service construction.
    start, end = task_period(1, int(economy.clock()))
    key = f'activity-daily-repair-v1:{start}:{period.index}'
    with economy.transaction():
        if db.execute('SELECT 1 FROM economy_events WHERE player_id=? AND event_key=?', (player,key)).fetchone():
            return
        clears = []
        for sid, wire in db.execute("""SELECT a.section_id,w.checkout
                FROM activity_runs r JOIN reward_settlement_audit a ON a.run_id=r.uuid
                JOIN battle_checkout_wire w ON w.uuid=r.uuid
                WHERE r.player_id=? AND r.period=? AND r.settled=1
                  AND a.created_at>=? AND a.created_at<?""", (player,period.index,start,end)):
            if CHECKOUT.decode(wire).get('success'):
                clears.append(sid)
        purchases = []
        for wire, in db.execute("""SELECT r.response FROM activity_receipts r
                JOIN economy_grants g ON g.player_id=r.player_id
                  AND g.source='activity:' || r.period || ':shop:' || r.request_key
                WHERE r.player_id=? AND r.period=? AND r.message='L2C_BuyGoods'
                  AND g.created_at>=? AND g.created_at<?""", (player,period.index,start,end)):
            reply = ECONOMY_SCHEMAS['L2C_BuyGoods'].decode(wire)
            if reply.get('code') == 10:
                purchases.append(reply)
        for tid in ids:
            condition = economy.catalog['task_conditions'][str(tid)]
            if condition['CompleteType']['value'] == 3:
                choices = set(condition['CompleteValue1'])
                count = sum(sid in choices for sid in clears)
            else:
                choices = set(condition['CompleteValue2'])
                count = sum(row.get('buyNum',0) for row in purchases if row.get('shopId') in choices)
            db.execute('UPDATE economy_tasks SET progress=MAX(progress,?) WHERE player_id=? AND task_id=?',
                       (min(count,condition['CompleteNum']),player,tid))
        # Adopt progress instead of replaying actions into every task consumer.
        db.execute('INSERT INTO economy_events VALUES (?,?)', (player,key))
