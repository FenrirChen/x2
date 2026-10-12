"""Original Nian maze-currency report converts independently of victory."""
import asyncio
import json
import pytest

from tests.unit.test_activity_runtime import runtime
from tests.unit.test_economy import env, rewards
from tests.unit.test_battle import packet, request
from x2server.player.activity_rotation import ActivityRotation
from x2server.player.battle import BattleService
from x2server.messages.battle import CHECKOUT, BATTLE_SCHEMAS, OUTSIDE_ITEM
from x2server.messages.lobby import MISSION_PAIR
from x2server.messages.economy import ITEM


def game(runtime, theme=0):
    store, economy, context, rt, now = runtime
    now[0] = ActivityRotation.ANCHOR + theme * ActivityRotation.SECONDS + 3600
    economy.activity = rt.a
    return store, economy, context, rt, now, BattleService(store, economy), 2161190 if theme == 0 else 2160400


def finish(game, score, sequence, success=False, raw=None, outside=()):
    store, economy, context, rt, now, battle, sid = game
    row = battle.catalog.sections[sid]
    values = request()
    values.update(missionId=sid, chapter=row['ChapterID'], sceneId=row['Maps'][0])
    entry = asyncio.run(battle.enter(context, packet(values, sequence)))
    assert entry.values['result'] == 10
    done = packet({'checkout': CHECKOUT.encode({'sectionId': sid, 'chapterId': row['ChapterID'],
        'success': success, 'fightTime': 60, 'outsideItems': list(outside), 'extraData': raw if raw is not None else [
            MISSION_PAIR.encode({'Key': 1237903, 'Value': score})]})}, sequence + 1, 'C2L_CheckoutMainMissionSign')
    return asyncio.run(battle.checkout(context, done)), done, entry.values['uuid']


@pytest.mark.parametrize('theme', [0, 5])
@pytest.mark.parametrize('success', [False, True])
def test_nian_actual_840_prism_report_awards_packet_once(runtime, theme, success):
    g = game(runtime, theme)
    result, done, run = finish(g, 840, 601, success)
    assert result.values['result'] == 10
    assert rewards(result.values['rewardData'])[1203021] == 1
    store, economy, context, rt, _, battle, sid = g
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1203021').fetchone()[0] == 1
    assert rt.r.get(1, rt.r.at(), 'clear', sid, 0) == int(success)
    assert rt.r.get(1, rt.r.at(), 'obtained-item', 1203021) == 1
    replay = asyncio.run(battle.checkout(context, done))
    schema = BATTLE_SCHEMAS['L2C_CheckoutMainMission']
    assert schema.encode(replay.values) == schema.encode(result.values)
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1203021').fetchone()[0] == 1
    sources = json.loads(store.db.execute('SELECT sources FROM reward_settlement_audit WHERE run_id=?', (run,)).fetchone()[0])
    assert len(sources['ACTIVITY_GAMEPLAY']) == 1
    assert next(ITEM.decode(raw)['dayGet'] for raw in economy.inventory_values(1)['items'] if ITEM.decode(raw)['id'] == 1203021) == 1


def test_nian_threshold_daily_cap_consumed_gift_and_next_cycle(runtime):
    g = game(runtime)
    store, economy, context, rt, now, battle, sid = g
    result, _, _ = finish(g, 519, 701)
    assert not rewards(result.values['rewardData'])
    result, _, _ = finish(g, 520, 703)
    assert rewards(result.values['rewardData'])[1203021] == 1
    result, _, _ = finish(g, 1040, 705)
    assert rewards(result.values['rewardData'])[1203021] == 2
    result, _, _ = finish(g, 10000, 707)
    assert not rewards(result.values['rewardData'])
    with economy.transaction():
        store.db.execute('UPDATE inventory SET quantity=0 WHERE player_id=1 AND item_id=1203021')
    item = next(ITEM.decode(raw) for raw in economy.inventory_values(1)['items'] if ITEM.decode(raw)['id'] == 1203021)
    assert item['num'] == 0 and item['dayGet'] == 3
    assert not any(1203021 in m.values['ids'] for m in economy.pushes(1) if m.message_name == 'L2C_ItemRemove')
    now[0] += 86400
    result, _, _ = finish(g, 520, 709)
    assert rewards(result.values['rewardData'])[1203021] == 1
    now[0] += 35 * 86400
    result, _, _ = finish(g, 1560, 711)
    assert rewards(result.values['rewardData'])[1203021] == 3


@pytest.mark.parametrize('amount', [-1, 10**7 + 1])
def test_invalid_nian_reports_rollback(runtime, amount):
    g = game(runtime)
    response, _, _ = finish(g, amount, 801)
    assert response.values['result'] == 13
    assert g[3].a.gameplay_day_counts(1)[1203021] == 0


def test_native_extra_currency_tag_is_independent_of_schema():
    # Captured checkout field11: Key1237903 / Value840.
    values = CHECKOUT.decode(bytes.fromhex('5a07088fc74b10c806'))
    assert MISSION_PAIR.decode(values['extraData'][0]) == {'Key': 1237903, 'Value': 840}


def test_duplicate_nian_currency_is_rejected_without_consuming_daily_limit(runtime):
    g = game(runtime)
    raw = MISSION_PAIR.encode({'Key': 1237903, 'Value': 840})
    response, _, _ = finish(g, 0, 901, raw=[raw, raw])
    assert response.values['result'] == 13
    assert g[3].a.gameplay_day_counts(1)[1203021] == 0


def test_normal_failed_battle_never_converts_nian_currency(runtime):
    store, economy, context, rt, _, = runtime
    economy.activity = rt.a
    battle = BattleService(store, economy)
    assert asyncio.run(battle.enter(context, packet(request(), 951))).values['result'] == 10
    done = packet({'checkout': CHECKOUT.encode({'sectionId': 2110801, 'chapterId': 2010100,
        'success': False, 'fightTime': 60, 'extraData': [MISSION_PAIR.encode({'Key': 1237903, 'Value': 5200})]})},
        952, 'C2L_CheckoutMainMissionSign')
    response = asyncio.run(battle.checkout(context, done))
    assert response.values['result'] == 10 and not rewards(response.values['rewardData'])
    assert not store.db.execute('SELECT 1 FROM inventory WHERE player_id=1 AND item_id=1203021').fetchone()


def test_client_outside_packet_cannot_duplicate_server_exchange(runtime):
    g = game(runtime)
    response, _, _ = finish(g, 840, 981, success=True,
        outside=[OUTSIDE_ITEM.encode({'id': 1203021, 'num': 100, 'quality': 4, 'eNum': 0})])
    assert response.values['result'] == 10
    assert rewards(response.values['rewardData'])[1203021] == 1
    assert g[3].a.gameplay_day_counts(1)[1203021] == 1
