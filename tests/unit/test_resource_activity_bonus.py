import asyncio
import pytest
from tests.unit.test_economy import env, rewards
from tests.unit.test_section_reward_system import enter, checkout
from tests.unit.test_battle import packet
from x2server.player.activity import ActivityService
from x2server.player.activity_runtime import ActivityRuntime
from x2server.player.extra_drop import ExtraDropService, beijing_day
from x2server.player.battle import BattleService
from x2server.messages.activity import ACTIVITY_SCHEMAS


def enable(e):
    now = [1791936000]
    e.clock = lambda: now[0]
    e.activity = ActivityService(e)
    e.extra_drop = ExtraDropService(e, enabled=True)
    runtime = ActivityRuntime(e.activity, None)
    return now, runtime


def test_activity_controls_bonus_group_quota_midnight_and_query(env):
    store,e,_ = env
    now,runtime = enable(e)
    rows = [ACTIVITY_SCHEMAS['ActivityData'].decode(r) for r in e.activity.query_activity(1)['activityData']]
    row = next(r for r in rows if r['actId']==71004)
    assert row['state']==1 and row['param1']==[100002,100003,100004,100005]
    for i in range(201):
        with e.transaction():
            bonus = e.extra_drop.rewards(1,2130101 if i%2 else 2130105,{1237901:100,1237914:1})
        assert bonus==({1237901:100} if i<200 else {})
    data=runtime.operate(1,'ExtraDropData',{},'query')['data']
    counts={r['Key']:r['Value'] for r in map(ACTIVITY_SCHEMAS['KeyValuePair_Int32_Int32'].decode,data)}
    assert counts[100002]==200
    # Material dungeons use their own official row, difficulty shares its quota.
    with e.transaction():
        assert e.extra_drop.rewards(1,2130201,{1238100:2})=={1238100:2}
    now[0]=(beijing_day(now[0])+1)*86400-28800
    assert e.extra_drop.used(1,100002)==0
    e.extra_drop.config['enabled']=False
    assert not e.extra_drop.rewards(1,2130101,{1237901:100})
    row=ACTIVITY_SCHEMAS['ActivityData'].decode(e.extra_drop.activity_values(1)[0])
    assert row['state']==0
    e.extra_drop.config['enabled']=True
    now[0]=e.extra_drop.config['end']
    assert not e.extra_drop.active(1)


def test_real_battle_and_sweep_share_quota_and_replay(env):
    store,e,context=env
    now,_=enable(e)
    s=BattleService(store,e)
    enter(s,context,2130101,2030100,2230101)
    result=checkout(s,context,2130101,2030100,outside=({'id':1101076,'num':10},))
    assert result.values['result']==10
    assert rewards(result.values['rewardData'])[1237901]==560
    assert e.extra_drop.used(1,100002)==1
    assert checkout(s,context,2130101,2030100,outside=({'id':1101076,'num':10},)).values==result.values
    assert e.extra_drop.used(1,100002)==1
    req=packet({'sectionId':2130101,'sweepCount':10},911,'C2L_SecSweep')
    result=asyncio.run(s.sweep(context,req))
    assert result.values['code']==10
    assert rewards(result.values['rewardData'])[1237901]==2078*20
    assert e.extra_drop.used(1,100002)==11
    assert asyncio.run(s.sweep(context,req)).values==result.values
    assert e.extra_drop.used(1,100002)==11


def test_quota_rolls_back_and_belongs_to_complete_save(env):
    store,e,_=env
    enable(e)
    with pytest.raises(RuntimeError),e.transaction():
        e.extra_drop.rewards(1,2130101,{1237901:1})
        raise RuntimeError('grant failed')
    assert e.extra_drop.used(1,100002)==0
    from tests.unit.test_save_manager import build_full_schema
    from x2server.player.save_manager import SaveManager
    build_full_schema(store)
    with e.transaction():
        e.extra_drop.rewards(1,2130101,{1237901:1})
    manager=SaveManager(store)
    data=manager.export_save(1)
    with store.db:
        store.db.execute('DELETE FROM activity_state WHERE period=?',(e.extra_drop.PERIOD,))
    manager.import_save(1,data)
    assert e.extra_drop.used(1,100002)==1


@pytest.mark.parametrize('limit',[0,1,3])
def test_resource_bonus_limit_is_configurable_without_changing_base_drops(env,monkeypatch,limit):
    _,e,_=env
    from x2server.player import extra_drop
    original=extra_drop.config
    monkeypatch.setattr(extra_drop,'config',lambda:dict(original(),limit=limit))
    enable(e)
    assert e.extra_drop.limit==limit
    for n in range(limit+1):
        with e.transaction():
            assert e.extra_drop.rewards(1,2130101,{1237901:5})==({1237901:5} if n<limit else {})
    assert e.extra_drop.used(1,100002)==limit


@pytest.mark.parametrize('limit',[-1,True,'200',1.5,2147483648])
def test_resource_bonus_rejects_invalid_config(env,monkeypatch,limit):
    _,e,_=env
    from x2server.player import extra_drop
    original=extra_drop.config
    monkeypatch.setattr(extra_drop,'config',lambda:dict(original(),limit=limit))
    with pytest.raises(ValueError,match='limit'):
        ExtraDropService(e,enabled=True)
