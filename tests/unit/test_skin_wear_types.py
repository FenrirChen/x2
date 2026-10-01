import asyncio

import pytest

from tests.unit.test_battle import packet, request
from tests.unit.test_economy import env  # noqa: F401
from x2server.messages.appearance import HERO_SKIN
from x2server.messages.battle import FIGHT_DATA, FIGHT_HERO
from x2server.player.appearance import AppearanceService
from x2server.player.battle import BattleService


@pytest.mark.parametrize('kind,slots', [(1, {1}), (2, {2}), (3, {1, 2})])
def test_native_apply_types_update_correct_slots_and_wire(env, kind, slots):
    store, economy, ctx = env
    appearance = AppearanceService(store, economy)
    reply = asyncio.run(appearance.handle(ctx, packet(
        {'heroId': 1003, 'skinId': 1220301, 'type': kind}, name='C2L_HeroWearSkin')))
    assert reply.values['code'] == 10 and reply.values['type'] == kind
    assert {r[0] for r in store.db.execute('SELECT type FROM appearance_wear')} == slots
    wire = HERO_SKIN.decode(reply.before_response[0].values['skin'])
    assert wire['battleSkin'] == (1220301 if 1 in slots else 0)
    assert wire['outerSkin'] == (1220301 if 2 in slots else 0)
    entry = asyncio.run(BattleService(store, economy).enter(ctx, packet(request())))
    hero = FIGHT_HERO.decode(FIGHT_DATA.decode(entry.values['data'])['fightHeros'][0])
    assert hero['battleSkinId'] == wire['battleSkin']


def test_legacy_sync_only_skin_recovers_battle_and_outer_idempotently(env):
    store, economy, ctx = env
    AppearanceService(store, economy)
    with store.db:
        store.db.execute('INSERT INTO appearance_wear VALUES (1,1003,3,1220301)')
    appearance = AppearanceService(store, economy)
    rows = [tuple(r) for r in store.db.execute('SELECT * FROM appearance_wear ORDER BY type')]
    assert rows == [(1,1003,1,1220301), (1,1003,2,1220301)]
    assert HERO_SKIN.decode(appearance.skin_values(1)['skinList'][0])['battleSkin'] == 1220301
    AppearanceService(store, economy)
    assert [tuple(r) for r in store.db.execute('SELECT * FROM appearance_wear ORDER BY type')] == rows
    entry = asyncio.run(BattleService(store, economy).enter(ctx, packet(request())))
    assert FIGHT_HERO.decode(FIGHT_DATA.decode(entry.values['data'])['fightHeros'][0])['battleSkinId'] == 1220301


def test_legacy_sync_does_not_overwrite_explicit_battle_choice(env):
    store, economy, ctx = env
    AppearanceService(store, economy)
    with store.db:
        store.db.executemany('INSERT INTO appearance_wear VALUES (1,1003,?,?)',
            [(1,1220303), (3,1220301)])
    AppearanceService(store, economy)
    assert dict(store.db.execute('SELECT type,skin_id FROM appearance_wear')) == {1:1220303,2:1220301}


def test_sync_change_updates_both_atomically_then_outer_change_preserves_battle(env):
    store, economy, ctx = env
    appearance = AppearanceService(store, economy)
    with store.db:
        store.db.execute('INSERT INTO inventory VALUES (1,1220303,1)')
    for kind, skin in [(3,1220303), (2,1220301)]:
        reply = asyncio.run(appearance.handle(ctx, packet(
            {'heroId': 1003, 'skinId': skin, 'type': kind}, name='C2L_HeroWearSkin')))
        assert reply.values['code'] == 10
    assert dict(store.db.execute('SELECT type,skin_id FROM appearance_wear')) == {1:1220303,2:1220301}
    before = '\n'.join(store.db.iterdump())
    reply = asyncio.run(appearance.handle(ctx, packet(
        {'heroId': 1003, 'skinId': 1220304, 'type': 3}, name='C2L_HeroWearSkin')))
    assert reply.values['code'] == 13
    assert '\n'.join(store.db.iterdump()) == before
