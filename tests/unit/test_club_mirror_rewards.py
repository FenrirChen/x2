import copy

from tests.unit.test_social import social, create, fund, act
from tests.unit.test_economy import env, rewards
from tests.unit.test_club_mirror_assists import setup_mirror
from x2server.player.battle import BattleService
from x2server.player.social import day
from x2server.messages.battle import BATTLE_SCHEMAS


def finish(s,damage=40,run='reward'):
    with s.economy.transaction():
        s.bind_run(1,2170001,run)
        return s.completed(1,2170001,False,damage,run)


def test_native_stage_chest_is_free_for_participant_and_uses_win_reward(social):
    s,ctx,_=social
    setup_mirror(s,ctx)
    finish(s)
    result=act(s,ctx,'ClubReceiveReward',{'opt':2,'param':2170001},30)
    assert result.values['code']==10
    assert rewards(result.values['rewardData'])==s.economy.gifts([778101])
    assert s.quantity(1,1283201)==0
    assert act(s,ctx,'ClubReceiveReward',{'opt':2,'param':2170001},30).values==result.values
    assert act(s,ctx,'ClubReceiveReward',{'opt':2,'param':2170001},31).values['code']==13
    assert act(s,ctx,'ClubReceiveReward',{'opt':0,'param':2070001},32).values['code']==13
    info=act(s,ctx,'ClubActiMainData',{},33).values
    assert info['receivedLayer']==[2170001]


def test_npc_only_clear_requires_exact_key_and_keeps_atomic_failed_purchase(social):
    s,ctx,_=social
    setup_mirror(s,ctx,members=3)
    finish(s,damage=120)
    assert s.state(1)['mirror']['clears']==[2070001,2070002]
    req={'opt':2,'param':2170002}
    before=copy.deepcopy(s.state(1))
    assert act(s,ctx,'ClubReceiveReward',req,30).values['code']==13
    assert s.state(1)==before
    fund(s,1283201,1)
    result=act(s,ctx,'ClubReceiveReward',req,31)
    assert result.values['code']==10 and s.quantity(1,1283201)==0
    assert rewards(result.values['rewardData'])==s.economy.gifts([778102])
    assert act(s,ctx,'ClubReceiveReward',req,32).values['code']==13


def test_decay_is_90_then_45_then_22_5_then_11_25_percent(social):
    s,ctx,_=social
    setup_mirror(s,ctx,members=4)
    s.mirror_health[2]['maxHP']=20
    result=finish(s,damage=120)
    assert [t['requested'] for t in result['turns']]==[120,54,54,27,13]
    assert [t['applied'] for t in result['turns']]==[100,54,46,20,13]
    assert [t['boss'] for t in result['turns']]==[2070001,2070002,2070002,2070003,2070004]
    assert s.state(1)['today_score']==233


def test_daily_progress_reward_once_and_midnight_reset(social):
    s,ctx,stamp=social
    setup_mirror(s,ctx,members=0,hp=300000000)
    result=finish(s,damage=100000000)
    assert s.state(1)['today_score']==100000000
    assert s.completed(1,2170001,False,100000000,'reward')==result
    assert s.state(1)['today_score']==100000000
    reply=act(s,ctx,'ClubReceiveReward',{'opt':1,'param':0},30)
    assert reply.values['code']==10
    assert rewards(reply.values['rewardData'])=={1237924:160,1237901:17000,1237918:50}
    assert act(s,ctx,'ClubActiMainData',{},31).values['scoreRewardFlag']==1
    assert act(s,ctx,'ClubReceiveReward',{'opt':1,'param':0},32).values['code']==13
    stamp[0]+=86400
    assert s.state(1)['today_score']==0
    assert act(s,ctx,'ClubActiMainData',{},33).values['scoreRewardFlag']==0
    assert act(s,ctx,'ClubReceiveReward',{'opt':1,'param':0},34).values['code']==13
    finish(s,damage=100000000,run='tomorrow')
    assert act(s,ctx,'ClubReceiveReward',{'opt':1,'param':0},35).values['code']==10


def test_only_confirmed_todays_historical_damage_is_backfilled_once(social):
    s,ctx,stamp=social
    create(s,ctx)
    BattleService(s.store,s.economy)
    with s.economy.transaction():
        state=s.state(1)
        state['mirror']['runs']={key:{'done':True,'turns':[{'applied':number}]}
            for key,number in [('today',120000000),('yesterday',500),('unconfirmed',1000)]}
        s.save(1,state)
        for key,t in [('today',stamp[0]),('yesterday',stamp[0]-86400)]:
            s.store.db.execute('INSERT INTO battle_entries(player_id,request_key,uuid,created_at,response) VALUES (1,?,?,?,?)',
                (key,key,t,b''))
            s.store.db.execute('INSERT INTO battle_receipts VALUES (?,?,?,?)',(key,'proof',t,
                BATTLE_SCHEMAS['L2C_CheckoutMainMission'].encode({'result':10,'success':False})))
    state=s.state(1)
    assert state['today_score']==100000000  # UI-safe cap, not int32 overflow.
    assert state['mirror']['runs']['today']['score_day']==day(stamp[0])
    with s.economy.transaction():
        s.save(1,state)
    assert s.state(1)['today_score']==100000000
    meta=s.http('/ClubService.GetClub',{},1)['Club']['Meta']
    assert next(p for p in meta if p['Name']=='clubTodayScore')['Value']['VInt64']==100000000


def test_legacy_claimed_boss_ids_are_normalized_to_stage_ids(social):
    s,ctx,_=social
    create(s,ctx)
    with s.economy.transaction():
        state=s.state(1)
        state['mirror']['clears']=[2070001]
        state['mirror']['claimed']=[2070001]
        s.save(1,state)
    assert act(s,ctx,'ClubActiMainData',{},30).values['receivedLayer']==[2170001]
    assert act(s,ctx,'ClubReceiveReward',{'opt':2,'param':2170001},31).values['code']==13
