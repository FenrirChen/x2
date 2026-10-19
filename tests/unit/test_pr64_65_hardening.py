import asyncio
from copy import deepcopy
import pytest
from tests.unit.test_economy import env
from tests.unit.test_battle import packet
from x2server.player.favor import FavorService, interaction_data, touch_gain
from x2server.player.appearance import AppearanceService, dubbing_unlocked
from x2server.messages.appearance import HERO_DUBBING_DATA


def send(service, ctx, option=46004, sequence=1, hero=0, opt=1):
    return asyncio.run(service.handle(ctx, packet({'opt': opt, 'optionId': option, 'heroId': hero},
                                                   sequence, name='C2L_AddFavor')))


def test_touch_retry_invalid_animation_and_rollback(env, monkeypatch):
    store, e, ctx = env
    service = FavorService(store, e)
    assert touch_gain(46001) == 0 and touch_gain(46004) == 3
    assert send(service, ctx, 46001).values['code'] == 13
    assert send(service, ctx, 999999).values['code'] == 13
    assert send(service, ctx, 46004, opt=0).values['code'] == 13
    assert send(service, ctx, 48707).values['code'] == 13  # God not owned.
    result = send(service, ctx)
    assert result.values['code'] == 10
    assert send(service, ctx).values == result.values
    assert store.get(1)['snapshot']['heroes'][0]['favor']['exp'] == 3
    assert store.db.execute('SELECT sum(count) FROM favor_touch_log').fetchone()[0] == 1
    def fail(*args):
        raise RuntimeError('fail favor snapshot')
    monkeypatch.setattr(e, 'save_snapshot', fail)
    with pytest.raises(RuntimeError, match='fail favor snapshot'):
        send(service, ctx, sequence=2)
    assert store.db.execute('SELECT sum(count) FROM favor_touch_log').fetchone()[0] == 1


def test_touch_account_limit_midnight_and_maximum_exp(env):
    store, e, ctx = env
    now = [1800028799]  # A mutable clock; advance to the next Beijing midnight below.
    e.clock = lambda: now[0]
    service = FavorService(store, e, clock=e.clock)
    player = store.get(1)
    template = player['snapshot']['heroes'][0]
    ids = [1003, 1004, 1005, 1006]
    heroes = []
    for hid in ids:
        h = deepcopy(template); h['id'] = hid; heroes.append(h)
    store.save_snapshot(1, {**player['snapshot'], 'heroes': heroes}, player['revision'])
    data = interaction_data()
    options = {hid: next(int(k) for k,v in data['by_interaction'].items()
                         if v == hid and touch_gain(int(k)) > 0) for hid in ids}
    for index, hid in enumerate(ids[:3]):
        for n in range(5):
            assert send(service, ctx, options[hid], sequence=100 + index * 10 + n).values['code'] == 10
    assert send(service, ctx, options[1006], sequence=200).values['code'] == 72
    from x2server.player.task_calendar import task_period
    now[0] = task_period(1, now[0])[1]
    assert send(service, ctx, options[1006], sequence=201).values['code'] == 10
    player = store.get(1)
    h = player['snapshot']['heroes'][0]
    maximum = service.levels[service.heroes[1003]['LevelLimit']]['Exp']
    h['favor'] = {'level': service.heroes[1003]['LevelLimit'], 'exp': maximum}
    store.save_snapshot(1, player['snapshot'], player['revision'])
    assert send(service, ctx, sequence=202).values['newExp'] == maximum


def test_voice_gift_requires_success_and_breaks_are_unique(env):
    store, e, ctx = env
    service = FavorService(store, e)
    voices = AppearanceService(store, e)
    gift_voice = next(i for i,r in voices.voices.items() if r['hero_id'] == 1003 and r['unlock_condition'] == 1350111)
    def save():
        return asyncio.run(voices.handle(ctx, packet({'heroId': 1003, 'dubbingId': gift_voice},
                                                     name='C2L_SaveHeroDubbing')))
    assert save().values['code'] == 13
    favorite = next(iter(service.favorites[1003]))
    assert asyncio.run(service.handle(ctx, packet({'opt': 2, 'heroId': 1003,
        'optionId': favorite, 'num': 1}, name='C2L_AddFavor'))).values['code'] == 13
    assert save().values['code'] == 13
    with store.db:
        store.db.execute('INSERT INTO inventory VALUES (1,?,1)', (favorite,))
    assert asyncio.run(service.handle(ctx, packet({'opt': 2, 'heroId': 1003,
        'optionId': favorite, 'num': 1}, name='C2L_AddFavor'))).values['code'] == 10
    assert save().values['code'] == 10
    raw = AppearanceService(store, e)._voice_values(1)['heroDubbingDatas'][0]
    assert gift_voice in HERO_DUBBING_DATA.decode(raw)['dubbingIds']
    assert not dubbing_unlocked(1350104, {'favor_breaks': [4, 4, 4]}, set(), 1)
    assert not dubbing_unlocked(99999, {}, {1}, 1)
