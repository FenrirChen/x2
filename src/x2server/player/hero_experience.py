"""Per-hero XP uses the recovered PlayerLevelBonus curve and account level cap."""
from functools import lru_cache


@lru_cache(maxsize=1)
def levels():
    from .progression import catalog
    return {r['level']: r for r in catalog()['hero_level']}


def add_hero_exp(hero, amount, player_level):
    """Return credited XP; carry across levels, without banking new XP at cap.

    Existing surplus from old saves is preserved, including at the level cap.
    The caller owns persistence and the surrounding settlement transaction.
    """
    rows = levels()
    if type(amount) is not int or amount < 0:
        raise ValueError('invalid hero XP')
    cap = min(player_level, max(rows))
    if hero['level'] >= cap or hero['level'] not in rows:
        return 0
    remaining = sum(rows[n]['exp_required'] for n in range(hero['level'], cap))
    credited = min(amount, max(0, remaining - hero.get('exp', 0)))
    hero['exp'] = hero.get('exp', 0) + credited
    while hero['level'] < cap:
        row = rows[hero['level']]
        if not row.get('next_level') or hero['exp'] < row['exp_required']:
            break
        hero['exp'] -= row['exp_required']
        hero['level'] = row['next_level']
    return credited


class BattleHeroExperience:
    # Revival compatibility, not a recovered official per-hero XP formula.
    # Fixed clear XP wins; paid-stamina fallback is only for missing XP rewards.
    XP_PER_STAMINA = 20

    def __init__(self, store, economy):
        self.store, self.economy = store, economy

    def gain_for(self, player_id, run_uuid, section):
        config = self.economy.entry_catalog.sections.get(section, {})
        gain = 0
        for group in config.get('VReward', []):
            for row in self.economy._gift_rows(group):
                if row.get('AwardType', {}).get('value') == 1:
                    gain += sum(n for i, n in zip(row.get('GiftValue', []), row.get('Num', []))
                                if i == 1237907 and type(n) is int and n > 0)
        if not gain:
            cost = self.store.db.execute(
                'SELECT amount FROM battle_costs WHERE uuid=? AND player_id=? AND refunded=0',
                (run_uuid, player_id)).fetchone()
            gain = max(0, cost[0]) * self.XP_PER_STAMINA if cost else 0
        return gain

    def battle(self, player_id, run_uuid, section):
        import json
        import logging
        config = self.economy.entry_catalog.sections.get(section, {})
        bound = self.store.db.execute(
            'SELECT team_json FROM battle_entries WHERE uuid=? AND player_id=?',
            (run_uuid, player_id)).fetchone()
        team = set(json.loads(bound[0])) if bound else set()
        # Same trial exclusions as the existing authoritative favor path.
        trial = config.get('AssistType', {}).get('value') == 1
        if (not team or config.get('Type') == 5 or trial
                or section == 2110607 and len(team) == 1 and team & {1003, 1303}):
            return {}
        gain = self.gain_for(player_id, run_uuid, section)
        if not gain:
            return {}
        snapshot = self.store.get(player_id)['snapshot']
        changes, level_changes = {}, []
        for hero in snapshot.get('heroes', []):
            if hero['id'] in team and hero.get('state') == 2:
                before = hero['level']
                credited = add_hero_exp(hero, gain, snapshot['level'])
                changes[hero['id']] = credited
                count = hero['level'] - before
                if count:
                    level_changes.append((hero['id'], count))
        if changes:
            self.economy.save_snapshot(player_id, snapshot)
            for hid, count in level_changes:
                for kind in (7, self.economy.TASK_EVENT_HERO_LEVEL_UP):
                    self.economy._event(player_id, f'battle-hero-xp:{run_uuid}:{hid}:{kind}',
                                        kind, hid, count)
            logging.getLogger('x2.battle').info(
                'battle hero XP run=%s player=%s section=%s configured=%s credited=%s',
                run_uuid, player_id, section, gain, changes)
        return changes
