from tests.activity_calendar_helpers import activity_start, next_activity_cycle
import asyncio
from tests.unit.test_activity_runtime import runtime,seed
from tests.unit.test_economy import env
from tests.unit.test_battle import packet
from x2server.messages.activity import ACTIVITY_SCHEMAS
from x2server.player.activity_rotation import ActivityRotation


def test_cafe_query_replay_reads_repaired_store(runtime):
    store,_,ctx,rt,_=runtime
    query=packet({},100,'C2L_CafeStoreInfo')
    before=asyncio.run(rt.handle(ctx,query))
    assert all(ACTIVITY_SCHEMAS['CafeStoreInfo'].decode(q).get('lockState',0)==0 for q in before.values['storeInfo'])
    seed(rt,{1290301:1,1290306:1,1290328:1})
    for kind in (7,8,9):
        assert asyncio.run(rt.handle(ctx,packet({'storeType':kind},100+kind,'C2L_CafeStoreUnLock'))).values['code']==10
    after=asyncio.run(rt.handle(ctx,query))
    assert all(ACTIVITY_SCHEMAS['CafeStoreInfo'].decode(q)['lockState']==1 for q in after.values['storeInfo'])
    assert store.db.execute("SELECT COUNT(*) FROM activity_receipts WHERE message='L2C_CafeStoreInfo'").fetchone()[0]==0


def test_food_difficulty_query_replay_reads_completed_section(runtime):
    _,e,ctx,rt,_=runtime
    query=packet({'activityId':72045},120,'C2L_ActivityMissionData')
    before=asyncio.run(rt.handle(ctx,query))
    assert ACTIVITY_SCHEMAS['ActivityMissionData'].decode(before.values['missionData'][0]).get('lastPastMissionId',0)==0
    with e.transaction():
        rt.r.put(1,rt.a.period(1),'clear',2161191,1)
    after=asyncio.run(rt.handle(ctx,query))
    assert ACTIVITY_SCHEMAS['ActivityMissionData'].decode(after.values['missionData'][0])['lastPastMissionId']==2161191


def test_cafe_same_query_survives_next_occurrence_with_fresh_state(runtime):
    _,_,ctx,rt,now=runtime
    query=packet({},140,'C2L_CafeStoreInfo')
    assert asyncio.run(rt.handle(ctx,query)).values['code']==10
    now[0] = next_activity_cycle(now[0])
    assert asyncio.run(rt.handle(ctx,query)).values['code']==10


def test_repair_mutation_receipt_still_cannot_replay_into_next_occurrence(runtime):
    _,_,ctx,rt,now=runtime
    seed(rt,{1290301:1})
    repair=packet({'storeType':7},150,'C2L_CafeStoreUnLock')
    assert asyncio.run(rt.handle(ctx,repair)).values['code']==10
    now[0] = next_activity_cycle(now[0])
    assert asyncio.run(rt.handle(ctx,repair)).values['code']==13
    assert not rt.cafe.context(1,7)[2]['unlocked']
    assert asyncio.run(rt.handle(ctx,packet({'storeType':7},151,'C2L_CafeStoreUnLock'))).values['code']==10
