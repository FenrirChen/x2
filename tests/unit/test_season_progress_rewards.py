import asyncio
import json
import pytest
from tests.unit.test_origin_season import env
from tests.unit.test_season_protocol_tasks import ctx
from tests.unit.test_battle import packet
from x2server.messages.economy import TREASURE_BOX, REWARD, REWARD_ITEM, TASK
from x2server.messages.core import BASE_INFO
from x2server.player.login import LoginService
from x2server.player.season_schedule import ANCHOR
from x2server.player.task_calendar import task_period


def call(s, op, req, rid):
    return asyncio.run(s.handle(ctx(), packet(req,rid,'C2L_'+op)))


def boxes(e, index, rid=20):
    return asyncio.run(e.handle(ctx(),packet({'type':15,'boxId':index},rid,'C2L_PickTreasureBox')))


def test_achievement_five_original_point_rewards_and_replay(env):
    store,e,s=env
    overview=call(s,'SeasonAchvOverView',{},1)
    assert overview.values['achvPointRewardList']==[0]*5
    assert call(s,'SeasonAchvPointReward',{'achvPointId':5},2).values['code']==13
    assert call(s,'SeasonAchvPointReward',{'achvPointId':0},2).values['code']==13
    with e.transaction():
        state=s.state(1)
        state.update(max_layer=100,exp=60000,relics=list(range(100)),hero_growth={'1003':{'level':80,'star':46,'artifact':6}},
            equip_growth={str(i):15 for i in range(12)},equip_obtained={str(i):6 for i in range(12)},
            items_obtained={'1270306':1,'1221203':1,'1270407':1},timed_layers={'80':200},
            chapter_layers={c:90 for c in ['群星跃迁之时','寂灭之墟','饕餮盛宴','黑暗金字塔','火剑之路','云中电玩城']})
        state['stats'].update(passes=500,talent_add=1,talent_reset=1,shop_spent=50,tasks=1,signs=1,task_refresh=1)
        s.write(1,state)
    overview=call(s,'SeasonAchvOverView',{},3)
    assert overview.values['achvPoint']>=60
    assert overview.values['achvPointRewardList']==[1]*5
    targets=s.e.catalog['task_control']['CompleteBpAchievementNumber']
    assert targets==[5,10,20,40,60]
    # 客户端 C2L_SeasonAchvPointReward.achvPointId 发的是里程碑阈值本身 (5/10/20/40/60),
    # 不是下标 —— 见 season.py 该分支的说明; 下标写法作为兼容路径另行保留。
    for i,n in enumerate(targets):
        result=call(s,'SeasonAchvPointReward',{'achvPointId':n},10+i)
        assert result.values['code']==10 and result.values['status']==2
        assert result.values['achvPointId']==n
        rewards={r['itemId']:r['itemNum'] for r in map(REWARD_ITEM.decode, REWARD.decode(result.values['rewardData'])['rewardItem'])}
        assert rewards=={1237840:i+1,1237925:1}
        before=[tuple(r) for r in store.db.execute('SELECT * FROM inventory')]
        assert call(s,'SeasonAchvPointReward',{'achvPointId':n},10+i).values==result.values
        assert [tuple(r) for r in store.db.execute('SELECT * FROM inventory')]==before
        assert call(s,'SeasonAchvPointReward',{'achvPointId':n},100+i).values['code']==13
    for i in range(5):
        assert call(s,'SeasonAchvPointReward',{'achvPointId':i},300+i).values['code']==13
    assert call(s,'SeasonAchvOverView',{},200).values['achvPointRewardList']==[2]*5


def test_real_week_task_claim_adds_active_currency_and_updates_wire(env):
    store,e,s=env
    with e.transaction():
        for i in range(5):s.event(1,f'test-pass:{i}',97,20)
        result=s.claim_task_response(1,6007001,'task-claim')
    assert result['code']==10 and s.state(1)['weekly_active']==50
    assert TASK.decode(result['nextTask'])['taskStatus']==4
    assert s.claim_task_response(1,6007001,'task-claim')==result
    assert s.state(1)['weekly_active']==50
    push=LoginService.snapshot_push(store.get(1),store,int(e.clock()))
    assert BASE_INFO.decode(push.values['BaseInfo'])['BattlePassWeeklyActive']==50
    assert BASE_INFO.encode({'BattlePassWeeklyActive':50})[:2]==bytes([0x98,0x04])
    statuses=[TREASURE_BOX.decode(r)['pickStatus'] for r in s.task_values(1)['boxList']]
    assert statuses==[1,0,0,0,0]
    updates=s.pushes(1)
    assert any(r.message_name=='L2C_TreasureBoxUpdate' and r.values['type']==15 for r in updates)
    assert boxes(e,1).values['code']==13
    result=boxes(e,0,21)
    assert result.values['code']==10 and REWARD.decode(result.values['rewardData'])['rewardItem']
    assert boxes(e,0,21).values==result.values
    assert boxes(e,0,22).values['code']==13


def test_all_week_boxes_once_then_reset_at_monday_and_backfill_old_ledger(env):
    store,e,s=env
    e.clock=lambda:ANCHOR+3600
    with e.transaction():
        state=s.state(1);week=state['week']
        store.db.execute('INSERT INTO economy_grants VALUES (?,?,?,?)',(1,f'season:{s.instance}:task:{week}:old:0',json.dumps({'1237999':150}),int(e.clock())))
        state.pop('weekly_active_period',None);s.write(1,state)
    push=LoginService.snapshot_push(store.get(1),store,int(e.clock()))
    assert BASE_INFO.decode(push.values['BaseInfo'])['BattlePassWeeklyActive']==150
    assert s.state(1)['weekly_active']==150
    assert s.state(1)['weekly_active']==150
    for i in range(5):assert boxes(e,i,30+i).values['code']==10
    assert [TREASURE_BOX.decode(r)['pickStatus'] for r in s.task_values(1)['boxList']]==[2]*5
    end=task_period(2,int(e.clock()))[1]
    e.clock=lambda:end
    assert s.state(1)['weekly_active']==0
    assert [TREASURE_BOX.decode(r)['pickStatus'] for r in s.task_values(1)['boxList']]==[0]*5
    with e.transaction():e._grant(1,'new-week-test',{1237999:150})
    for i in range(5):assert boxes(e,i,50+i).values['code']==10
