"""Native Boss waiting-scene time contract and guaranteed authorized exit."""
import asyncio
import pytest
from tests.unit.test_economy import env
from tests.unit.test_world_boss import call
from tests.unit.test_battle import request,packet
from x2server.player.battle import BattleService
from x2server.player.world_boss import account_state,snapshot_fields
from x2server.messages.world_boss import INFO,SEARCH,CONTAINER,BOSS
from x2server.network.dispatcher import DispatchContext
from x2server.network.session import SessionState

def admit(e,ctx):
    w=e.world_boss
    info=INFO.decode(call(w,ctx,'C2L_QueryWorldBossInfo').values['bossInfos'][0])
    req={'bossid':info['bossId'],'bossGroup':info['group'],'act':1,'typeId':info['typeId']}
    assert call(w,ctx,'C2L_WorldBossAct',req,100).values['code']==10
    sock=DispatchContext('boss-lobby','local',SessionState('boss-lobby',''))
    wire={'bossid':info['bossId'],'act':1,'playerid':1,'value':[1003]}
    joined=call(w,sock,'C2W_WorldBossAct',wire,101)
    assert joined.values['code']==10
    return w,info,sock,wire,joined

def test_single_player_waiting_scene_enters_fight_with_epoch_milliseconds(env):
    store,e,ctx=env
    w,info,sock,wire,joined=admit(e,ctx)
    data=INFO.decode(joined.values['bossInfo'])
    assert data['state']==2 and data['joinPlayerNum']==1
    assert data['stateFinishTime']//1000>w.now()
    assert data['findTime']//1000<=w.now()
    raw=store.db.execute('SELECT created,finish FROM world_boss_runs').fetchone()
    assert (data['findTime'],data['stateFinishTime'])==(raw[0]*1000,raw[1]*1000)
    fields,_=snapshot_fields(store,1,w.now())
    radar=BOSS.decode(CONTAINER.decode(SEARCH.decode(fields['WorldBossSearch'])['WorldBoss'][0])['val'])
    assert radar['StateFinishTime']==data['stateFinishTime']
    assert radar['Start']==data['findTime']
    section=e.entry_catalog.sections[w.bosses[info['typeId']]['StageID']]
    values=dict(request(),missionId=section['SectionID'],chapter=section['ChapterID'],sceneId=section['Maps'][0])
    assert asyncio.run(BattleService(store,e).enter(ctx,packet(values,102))).values['result']==10
    assert account_state(store,1,w.now())['world_challenges']==0

@pytest.mark.parametrize('terminal',[3,4])
def test_leave_after_terminal_state_and_midnight_is_idempotent_without_new_boss(env,terminal):
    store,e,ctx=env
    w,info,sock,wire,_=admit(e,ctx)
    with e.transaction():
        store.db.execute('UPDATE world_boss_runs SET state=?,finish=?',(terminal,w.now()-1))
    old_state=tuple(store.db.execute('SELECT day,state FROM world_boss_accounts').fetchone())
    now=w.now()+86400
    e.clock=lambda:now
    exit_req=dict(wire,act=2)
    # New socket must authenticate its old, expired, player-specific ticket.
    exit_socket=DispatchContext('new-exit','local',SessionState('new-exit',''))
    before=store.db.execute('SELECT count(*) FROM world_boss_runs').fetchone()[0]
    first=call(w,exit_socket,'C2W_WorldBossAct',exit_req,103)
    assert first.values=={'code':10,'bossid':info['bossId'],'act':2}
    assert call(w,exit_socket,'C2W_WorldBossAct',exit_req,103).values==first.values
    assert call(w,exit_socket,'C2W_WorldBossAct',exit_req,104).values==first.values
    main_leave={'bossid':info['bossId'],'bossGroup':info['group'],'act':2}
    assert call(w,ctx,'C2L_WorldBossAct',main_leave,105).values['code']==10
    assert tuple(store.db.execute('SELECT active,charged FROM world_boss_members').fetchone())==(0,0)
    assert store.db.execute('SELECT count(*) FROM world_boss_runs').fetchone()[0]==before
    assert tuple(store.db.execute('SELECT day,state FROM world_boss_accounts').fetchone())==old_state
    # The expired ticket allows cleanup only, never a fresh admission/damage.
    fresh=DispatchContext('bad-join','local',SessionState('bad-join',''))
    assert call(w,fresh,'C2W_WorldBossAct',wire,106).values['code']==13
    assert call(w,exit_socket,'C2W_WorldBossAct',dict(wire,act=3,value=[1]),107).values['code']==13

def test_foreign_player_cannot_leave_owned_boss(env):
    store,e,ctx=env
    w,info,sock,wire,_=admit(e,ctx)
    impostor=DispatchContext('foreign','local',SessionState('foreign',''))
    assert call(w,impostor,'C2W_WorldBossAct',dict(wire,act=2,playerid=2),108).values['code']==13
    assert store.db.execute('SELECT active FROM world_boss_members').fetchone()[0]==1
