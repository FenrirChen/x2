from tests.activity_calendar_helpers import activity_start, next_activity_cycle
import asyncio
import pytest
from tests.unit.test_activity_runtime import runtime, seed
from tests.unit.test_economy import env
from tests.unit.test_battle import packet
from x2server.messages.economy import TREASURE_BOX, ECONOMY_SCHEMAS
from x2server.messages.activity import ACTIVITY_SCHEMAS
from x2server.player.activity_rotation import ActivityRotation


def claim_tasks(rt, aid, count):
    period = rt.a.period(1)
    for tid, task in list(rt.a.task_catalog(period, 9, aid).items())[:count]:
        rt.r.put(1, period, rt.a.task_namespace(task), tid, {'progress': 999999, 'claimed': True})


@pytest.mark.parametrize('theme', range(7))
def test_box_static_query_ids_native_claim_index_and_open_state(runtime, theme):
    store, e, ctx, rt, now = runtime
    e.activity = rt.a
    now[0] = activity_start(theme) + 3600
    period = rt.a.period(1)
    boxes = [r for r in rt.a.tables['ActivityTaskBox'] if rt.r.activity(r['ActivityID'], period)]
    if not boxes:
        return
    for box in boxes:
        aid = box['ActivityID']
        with e.transaction():
            claim_tasks(rt, aid, box['ActivityParam1'])
        values = rt.a.task_values(1, 9, aid)
        queried = list(map(TREASURE_BOX.decode, values['boxList']))
        index = next(i for i, q in enumerate(queried) if q['boxId'] == box['BoxID'])
        assert queried[index]['pickStatus'] == 1
        p = packet({'type': 9, 'activityId': aid, 'boxId': index}, 500 + box['BoxID'], 'C2L_PickTreasureBox')
        response = asyncio.run(e.handle(ctx, p))
        assert response.values['code'] == 10
        assert response.values['boxId'] == index
        ECONOMY_SCHEMAS['L2C_PickTreasureBox'].encode(response.values)
        grant_count = store.db.execute('SELECT COUNT(*) FROM economy_grants').fetchone()[0]
        assert asyncio.run(e.handle(ctx, p)).values == response.values
        assert store.db.execute('SELECT COUNT(*) FROM economy_grants').fetchone()[0] == grant_count
        assert TREASURE_BOX.decode(rt.a.task_values(1, 9, aid)['boxList'][index])['pickStatus'] == 2
        assert asyncio.run(e.handle(ctx, packet({'type': 9, 'activityId': aid, 'boxId': index},
            1000 + box['BoxID'], 'C2L_PickTreasureBox'))).values['code'] == 13
    now[0] = next_activity_cycle(now[0])
    assert all(TREASURE_BOX.decode(q).get('pickStatus', 0) == 0 for q in rt.a.task_values(1, 9)['boxList'])


def test_box_unclaimed_progress_cannot_pay_and_preserves_previous_static_claim(runtime):
    store, e, ctx, rt, _ = runtime
    e.activity = rt.a
    period = rt.a.period(1)
    aid = 72041
    with e.transaction():
        for tid, task in rt.a.task_catalog(period, 9, aid).items():
            rt.r.put(1, period, rt.a.task_namespace(task), tid, {'progress': 999999, 'claimed': False})
    assert all(TREASURE_BOX.decode(q).get('pickStatus', 0) == 0 for q in rt.a.task_values(1, 9, aid)['boxList'])
    for index in (-1, 0, 5, 41):
        assert asyncio.run(e.handle(ctx, packet({'type': 9, 'activityId': aid, 'boxId': index},
            600 + index, 'C2L_PickTreasureBox'))).values['code'] == 13
    with e.transaction():
        rt.r.put(1, period, 'task-box', '72041:41', True)
    assert TREASURE_BOX.decode(rt.a.task_values(1, 9, aid)['boxList'][0])['pickStatus'] == 2
    assert not store.db.execute("SELECT 1 FROM economy_grants WHERE source LIKE '%task-box%'").fetchone()


@pytest.mark.parametrize('theme', [0, 5])
def test_each_native_cafe_repair_request_requires_recipe_and_reloads_unlocked(runtime, theme):
    store, e, ctx, rt, now = runtime
    now[0] = activity_start(theme) + 3600
    period = rt.a.period(1)
    food = rt.r.of_type(27, period)
    assert food is not None
    for kind in food['ActivityParam1']:
        recipe = rt.cafe.levels[kind, 1]['CafeUnlockCon'][0]
        p = packet({'storeType': kind}, 700 + kind, 'C2L_CafeStoreUnLock')
        assert asyncio.run(rt.handle(ctx, p)).values['code'] == 13
        seed(rt, {recipe: 1}, key=f'recipe-{kind}')
        response = asyncio.run(rt.handle(ctx, p))
        assert response.values == {'code': 10, 'storeType': kind, 'lockState': 1}
        ACTIVITY_SCHEMAS['L2C_CafeStoreUnLock'].encode(response.values)
        assert asyncio.run(rt.handle(ctx, p)).values == response.values
        info = asyncio.run(rt.handle(ctx, packet({}, 800 + kind, 'C2L_CafeStoreInfo')))
        cafe = [ACTIVITY_SCHEMAS['CafeStoreInfo'].decode(q) for q in info.values['storeInfo']]
        assert next(q for q in cafe if q['type'] == kind)['lockState'] == 1
        assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?', (recipe,)).fetchone()[0] == 1
