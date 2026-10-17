import asyncio
import time

import pytest
from tests.unit.test_origin_season import env
from tests.unit.test_battle import packet, request
from x2server.messages.battle import CHECKOUT
from x2server.player.battle import BattleService
from x2server.player.economy import UnresolvedEconomy
from x2server.network.dispatcher import DispatchContext
from x2server.network.session import SessionState


def setup(env, floor=10):
    store, e, s = env
    with e.transaction():
        state = s.state(1)
        state['max_layer'] = floor-1
        state['unlocked_layer'] = floor
        s.write(1,state)
        e._grant(1,'skip-test-tickets',{1202901:20})
    ctx=DispatchContext('test','local',SessionState('test','tower-skip',player_id=1))
    return store,e,s,BattleService(store,e),ctx


def enter(s,b,ctx,floor,rid):
    config=next(r for r in s.configs.values() if r['Level']==floor)
    sid=config['SectionGroup'][0]
    row=s.sections[sid]
    req=request()
    req.update(missionId=sid,chapter=row['ChapterID'],sceneId=row['Maps'][0])
    return asyncio.run(b.enter(ctx,packet(req,rid))),sid,row


def finish(b,ctx,sid,row,seconds,rid,success=True):
    req=packet({'checkout':CHECKOUT.encode({'sectionId':sid,'chapterId':row['ChapterID'],
                'success':success,'fightTime':seconds})},rid,'C2L_CheckoutMainMissionSign')
    return asyncio.run(b.checkout(ctx,req)),req


@pytest.mark.parametrize('seconds,next_floor',[(1,13),(180,13),(299,13),(300,11),(301,12),(599,12),(600,11),(601,11),(3600,11)])
def test_real_checkout_time_boundaries_wire_and_admission(env,seconds,next_floor):
    store,e,s,b,ctx=setup(env)
    started,sid,row=enter(s,b,ctx,10,1)
    assert started.values['result']==10
    response,req=finish(b,ctx,sid,row,seconds,2)
    assert response.values['result']==10
    state=s.state(1)
    assert state['max_layer']==10 and state['unlocked_layer']==next_floor
    assert state['stats']['passes']==1
    mission=next(m for m in response.before_response if m.message_name=='L2C_BattlePassMissionInfo')
    assert mission.values['maxSeasonId']==2090000+next_floor
    assert mission.values['maxPassId']==2090010
    # Only the played floor has a successful run/clear; skipped-floor rewards stay unclaimed.
    cleared={r[0] for r in store.db.execute('SELECT section_id FROM season_runs WHERE player_id=1 AND success=1')}
    assert cleared=={sid}
    for skipped in range(11,next_floor):
        for skipped_sid in s.configs[2090000+skipped]['SectionGroup']:
            assert not store.db.execute('SELECT 1 FROM season_runs WHERE player_id=1 AND section_id=? AND success=1',(skipped_sid,)).fetchone()
    before=store.get(1)
    assert asyncio.run(b.checkout(ctx,req)).values==response.values
    assert store.get(1)==before and s.state(1)==state
    assert finish(b,ctx,sid,row,seconds+1 if seconds<3600 else 1,3)[0].values['result']==13
    assert s.state(1)==state
    next_sid=s.configs[2090000+next_floor]['SectionGroup'][0]
    s.admission(1,next_sid)
    with pytest.raises(UnresolvedEconomy):
        s.admission(1,s.configs[2090001+next_floor]['SectionGroup'][0])
    assert enter(s,b,ctx,next_floor,4)[0].values['result']==10


def test_failed_run_and_lower_floor_replays_do_not_accumulate_unlocks(env):
    store,e,s,b,ctx=setup(env)
    first,sid,row=enter(s,b,ctx,10,1)
    assert first.values['result']==10
    assert finish(b,ctx,sid,row,60,2,False)[0].values['result']==10
    assert s.state(1)['max_layer']==9 and s.state(1)['unlocked_layer']==10
    assert enter(s,b,ctx,10,3)[0].values['result']==10
    assert finish(b,ctx,sid,row,100,4)[0].values['result']==10
    assert s.state(1)['unlocked_layer']==13
    for rid in (5,7):
        _,lower,lower_row=enter(s,b,ctx,1,rid)
        assert finish(b,ctx,lower,lower_row,100,rid+1)[0].values['result']==10
        assert s.state(1)['unlocked_layer']==13
    # A skipped floor may still be played and get its own first clear.
    _,middle,middle_row=enter(s,b,ctx,11,9)
    assert finish(b,ctx,middle,middle_row,600,10)[0].values['result']==10
    assert store.db.execute('SELECT 1 FROM season_runs WHERE player_id=1 AND section_id=? AND success=1',(middle,)).fetchone()
    assert s.state(1)['max_layer']==11 and s.state(1)['unlocked_layer']==13


@pytest.mark.parametrize('floor',[98,99,100])
def test_last_floor_is_capped_without_marking_unplayed_floors_cleared(env,floor):
    _,_,s,b,ctx=setup(env,floor)
    _,sid,row=enter(s,b,ctx,floor,1)
    assert finish(b,ctx,sid,row,100,2)[0].values['result']==10
    assert s.state(1)['max_layer']==floor and s.state(1)['unlocked_layer']==100
    assert s.mission_values(1)['maxSeasonId']==2090100
    assert s.mission_values(1)['maxPassId']==2090000+floor


def test_zero_client_time_uses_existing_server_elapsed_fallback(env):
    store,_,s,b,ctx=setup(env)
    started,sid,row=enter(s,b,ctx,10,1)
    with store.db:
        store.db.execute('UPDATE battle_entries SET created_at=? WHERE uuid=?',
                         (int(time.time())-600,started.values['uuid']))
    response,_=finish(b,ctx,sid,row,0,2)
    assert response.values['result']==10 and response.values['fightTimeLength']>=600
    assert s.state(1)['unlocked_layer']==11


def test_legacy_progress_save_roundtrip_restart_and_season_isolation(env,tmp_path):
    from tests.unit.test_save_manager import build_full_schema
    from x2server.player.save_manager import SaveManager
    from x2server.player.season import SeasonService
    store,e,s,b,ctx=setup(env)
    with e.transaction():
        state=s.state(1)
        state.pop('unlocked_layer')
        s.write(1,state)
    assert s.state(1)['unlocked_layer']==10
    _,sid,row=enter(s,b,ctx,10,1)
    assert finish(b,ctx,sid,row,120,2)[0].values['result']==10
    build_full_schema(store)
    manager=SaveManager(store,backup_root=tmp_path/'skip-backups')
    try:
        archive=manager.export_save(1)
        with e.transaction():
            state=s.state(1)
            state.update(unlocked_layer=11)
            s.write(1,state)
        manager.import_save(1,archive)
        rebuilt=SeasonService(e,enabled=True,instance=s.base_instance)
        assert rebuilt.state(1)['max_layer']==10
        assert rebuilt.mission_values(1)['maxSeasonId']==2090013
        assert SeasonService(e,enabled=True,instance='other-tower').mission_values(1)['maxSeasonId']==2090001
    finally:
        manager.close()
