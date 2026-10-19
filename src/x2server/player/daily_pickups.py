"""Original daily pickup caps for Sakura letters, enforced at final delivery."""
from functools import lru_cache
from importlib.resources import files
import json

from .task_calendar import task_period


@lru_cache(maxsize=1)
def limits():
    tables = json.loads(files('x2server').joinpath(
        'data/activity_rotation_catalog.json').read_text(encoding='utf8'))['tables']
    result = {}
    for row in tables['Item']:
        if row['ItemID'] not in (1104008, 1104027):
            continue
        index = row['DropLimit'].index(7)  # EItemDropLimit.E_Daily in the original APK.
        result[row['ItemID']] = row['DropLimitParam'][index]['Items'][0]
    assert len(result) == 2
    return result


def capped_pickups(economy, player, source, rewards):
    # DropLimit restricts pickups, not administrator mail or inventory transfers.
    if not source.startswith(('battle:', 'sweep:')) or not any(
            item in rewards for item in (1104008, 1104027)):
        return rewards
    affected = {item: cap for item, cap in limits().items()
                if type(rewards.get(item)) is int and rewards[item] > 0}
    if not affected:
        return rewards
    db = economy.store.db
    start, end = task_period(1, int(economy.clock()))
    raw = db.execute("SELECT value FROM activity_state WHERE player_id=? AND period=0 "
                     "AND namespace='daily-pickups' AND state_key='sakura-letters'", (player,)).fetchone()
    state = json.loads(raw[0]) if raw else {}
    if state.get('day') != start:
        # Bootstrap today's quota from successful grants, including already opened
        # letters, when upgrading an existing account. No startup-wide migration.
        totals = {str(item): 0 for item in limits()}
        for row in db.execute("SELECT rewards FROM economy_grants WHERE player_id=? "
                              "AND created_at>=? AND created_at<? "
                              "AND (source LIKE 'battle:%' OR source LIKE 'sweep:%')",
                              (player, start, end)):
            granted = json.loads(row[0])
            for item in totals:
                totals[item] += granted.get(item, 0)
        state = {'day': start, 'counts': totals}
    rewards = dict(rewards)
    for item, cap in affected.items():
        previous = state['counts'].get(str(item), 0)
        amount = min(rewards[item], max(0, cap - previous))
        state['counts'][str(item)] = previous + amount
        if amount:
            rewards[item] = amount
        else:
            del rewards[item]
    # One bounded account row; counters and inventory share the grant transaction.
    db.execute("INSERT OR REPLACE INTO activity_state VALUES (?,0,'daily-pickups','sakura-letters',?)",
               (player, json.dumps(state, sort_keys=True)))
    return rewards
