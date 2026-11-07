"""Date choices, covenant settlement and archive boundaries share real services."""
import asyncio
import copy

import pytest

from tests.unit.test_battle import packet
from tests.unit.test_economy import env
from x2server.messages.date import KEY_VALUE, NPC_DATE
from x2server.player.date import DateService, option_values, write_option
from x2server.player.favor import date_rows, FavorService


def call(service, context, name, **values):
    handler = service.handlers()['C2L_' + name]
    return asyncio.run(handler(context, packet(values, name='C2L_' + name)))


def prepare(env, hero_id=1010):
    store, economy, ctx = env
    from x2server.player.appearance import AppearanceService
    economy.appearance = AppearanceService(store, economy)
    service = DateService(store, economy, clock=lambda: 1800000000)
    with economy.transaction():
        snapshot = store.get(1)['snapshot']
        hero = next((h for h in snapshot['heroes'] if h['id'] == hero_id), None)
        if hero is None:
            hero = copy.deepcopy(snapshot['heroes'][0])
            hero['id'] = hero_id
            snapshot['heroes'].append(hero)
        hero.update(state=2, favor={'level': 19, 'exp': 8100}, favor_breaks=[4, 9, 14])
        economy.save_snapshot(1, snapshot)
        store.db.execute('INSERT INTO inventory VALUES (1,1204011,2) '
                         'ON CONFLICT(player_id,item_id) DO UPDATE SET quantity=2')
        for row in date_rows(hero_id):
            for chip in row['chips']:
                write_option(store, 1, hero_id, row['id'], chip, 1, 1800000000)
    return service, ctx


def test_query_refuses_unowned_hero_and_initializes_locked_chip_list(env):
    store, economy, ctx = env
    service = DateService(store, economy)
    assert call(service, ctx, 'QueryHeroDate', heroId=9999).values['code'] == 13
    answer = call(service, ctx, 'QueryHeroDate', heroId=1003)
    assert answer.values['code'] == 10
    for encoded in answer.values['date']:
        row = NPC_DATE.decode(encoded)
        assert row['option']
        assert all(KEY_VALUE.decode(p)['Value'] == 1 for p in row['option'])


def test_choices_must_belong_to_the_requested_date(env):
    service, ctx = prepare(env, 1003)
    row, other = date_rows(1003)
    for option in (999999, other['options'][0], row['chips'][0]):
        answer = call(service, ctx, 'SelcetDateOption', heroId=1003,
                      dateId=row['id'], optionEffectId=option)
        assert answer.values['code'] == 13
    answer = call(service, ctx, 'SelcetDateOption', heroId=1003,
                  dateId=row['id'], optionEffectId=row['options'][0])
    assert answer.values['code'] == 10
    assert len(answer.values['option']) == len(row['chips'])


def test_contract_spends_once_grants_skin_and_advances_to_twenty(env):
    store, economy, _ = env
    service, ctx = prepare(env)
    answer = call(service, ctx, 'OpenContract', heroId=1010)
    assert answer.values['code'] == 10
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1204011').fetchone()[0] == 1
    assert dict(store.db.execute('SELECT item_id,quantity FROM inventory WHERE player_id=1 '
                                'AND item_id IN (1221004,1271004)')) == {1221004: 1, 1271004: 1}
    hero = next(h for h in store.get(1)['snapshot']['heroes'] if h['id'] == 1010)
    assert hero['favor']['level'] == 20 and 19 in hero['favor_breaks']
    assert 'L2C_HeroSkinAll' in [p.message_name for p in answer.pushes]
    assert 'L2C_HeroUpdate' in [p.message_name for p in answer.pushes]
    assert call(service, ctx, 'OpenContract', heroId=1010).values['code'] == 13
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1204011').fetchone()[0] == 1
    assert call(service, ctx, 'QueryHeroDate', heroId=1010).values['skin'] == 1


@pytest.mark.parametrize('missing', ['item', 'chip', 'experience'])
def test_contract_checks_every_gate_without_spending(env, missing):
    store, economy, _ = env
    service, ctx = prepare(env)
    with economy.transaction():
        if missing == 'item':
            store.db.execute('UPDATE inventory SET quantity=0 WHERE player_id=1 AND item_id=1204011')
        elif missing == 'chip':
            row = date_rows(1010)[0]
            store.db.execute('DELETE FROM hero_date_options WHERE player_id=1 AND hero_id=1010 '
                             'AND date_id=? AND option_id=?', (row['id'], row['chips'][0]))
        else:
            snapshot = store.get(1)['snapshot']
            next(h for h in snapshot['heroes'] if h['id'] == 1010)['favor']['exp'] = 8099
            economy.save_snapshot(1, snapshot)
    held = store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1204011').fetchone()[0]
    assert call(service, ctx, 'OpenContract', heroId=1010).values['code'] == 13
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1204011').fetchone()[0] == held
    assert not store.db.execute('SELECT 1 FROM hero_contracts WHERE player_id=1').fetchone()


def test_contract_reward_failure_rolls_back_cost_and_state(env, monkeypatch):
    store, economy, _ = env
    service, ctx = prepare(env)
    def fail(*args, **kwargs):
        raise RuntimeError('reward failure')
    monkeypatch.setattr(economy, '_grant', fail)
    with pytest.raises(RuntimeError, match='reward failure'):
        call(service, ctx, 'OpenContract', heroId=1010)
    assert not store.db.execute('SELECT 1 FROM hero_contracts WHERE player_id=1').fetchone()
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1204011').fetchone()[0] == 2
    assert next(h for h in store.get(1)['snapshot']['heroes'] if h['id'] == 1010)['favor']['level'] == 19


def test_ordinary_break_cannot_bypass_the_covenant(env):
    service, ctx = prepare(env)
    favor = FavorService(service.store, service.economy)
    hero = next(h for h in service.store.get(1)['snapshot']['heroes'] if h['id'] == 1010)
    assert favor._break(1, 1010, hero).values['code'] == 13
    assert option_values(service.store, 1, 1010)
