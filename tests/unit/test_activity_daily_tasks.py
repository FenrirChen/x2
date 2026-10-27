import asyncio
import pytest
from tests.unit.test_economy import env
from tests.unit.test_activity_runtime import runtime
from tests.activity_calendar_helpers import activity_start
from tests.unit.test_battle import packet
from x2server.messages.economy import TASK
from x2server.messages.battle import CHECKOUT, PROFILE_HERO
from x2server.player.battle import BattleService
from x2server.player.economy import UnresolvedEconomy
from x2server.player.task_calendar import task_period


def prepare(runtime):
    store,e,ctx,rt,now=runtime
    now[0]=activity_start(6)+3600
    e.activity=rt.a
    battle=BattleService(store,e)
    p=store.get(1)
    store.save_snapshot(1,{**p['snapshot'],'mobility':{'power':100000}},p['revision'])
    e.ensure_periods(1)
    return store,e,ctx,rt,now,battle


def tasks(e):
    return {r['taskId']:r for r in map(TASK.decode,e.task_values(1,1)['taskList'])}


def test_only_live_activity_tasks_are_visible_and_claimable(runtime):
    store,e,ctx,rt,now,battle=prepare(runtime)
    assert {i for i in tasks(e) if i in (630025,630026,630040,630041)}=={630040,630041}
    with e.transaction():store.db.execute('UPDATE economy_tasks SET progress=99 WHERE player_id=1 AND task_id IN (630025,630026)')
    assert e.claim(1,630025,1)['code']==13
    assert e.claim(1,630026,1)['code']==13
    now[0]=activity_start(1)+3600
    assert not {630025,630026,630040,630041}&tasks(e).keys()


def test_real_activity_clears_finish_daily_task_and_reward_once(runtime):
    store,e,ctx,rt,now,battle=prepare(runtime)
    tasks(e)  # Initial query before doing anything must not prevent future counts.
    for index,sid in enumerate(range(2160111,2160114)):
        row=battle.catalog.sections[sid]
        reply=asyncio.run(battle.enter(ctx,packet({'missionId':sid,'chapter':row['ChapterID'],
            'sceneId':row['Maps'][0],'heros':[PROFILE_HERO.encode({'heroId':1003,'leader':1})]},100+index)))
        assert reply.values['result']==10
        request=packet({'checkout':CHECKOUT.encode({'chapterId':row['ChapterID'],
            'sectionId':sid,'success':True,'fightTime':200})},200+index,name='C2L_CheckoutMainMissionSign')
        result=asyncio.run(battle.checkout(ctx,request))
        assert result.values['result']==10
        assert asyncio.run(battle.checkout(ctx,request)).values==result.values
    assert tasks(e)[630040]['taskProgress']==3
    first=e.claim(1,630040,1)
    assert first['code']==10
    snapshot=store.get(1)
    assert e.claim(1,630040,1)==first
    assert store.get(1)==snapshot


def test_exchange_updates_daily_task_once_and_old_progress_recovers(runtime):
    store,e,ctx,rt,now,battle=prepare(runtime)
    assert tasks(e)[630041]['taskProgress']==0
    shop=rt.exchange.shops[887];offer=shop['goods'][0]
    with pytest.raises(UnresolvedEconomy):rt.exchange.buy(1,887,offer['goodsId'],1,'failed')
    assert tasks(e)[630041]['taskProgress']==0
    with e.transaction():e._grant(1,'test:shop-currency',{offer['currencyItemId']:100000})
    first=rt.exchange.buy(1,887,offer['goodsId'],1,'purchase')
    assert rt.exchange.buy(1,887,offer['goodsId'],1,'purchase')==first
    assert tasks(e)[630041]['taskProgress']==1
    # Model yesterday's server bug: paid receipt exists, daily progress was lost.
    with e.transaction():
        # Grant audit uses wall time; align this synthetic receipt to the fixture day.
        store.db.execute("UPDATE economy_grants SET created_at=? WHERE player_id=1 AND source=?",
                         (now[0], f'activity:{rt.r.at().index}:shop:purchase'))
        store.db.execute('UPDATE economy_tasks SET progress=0 WHERE player_id=1 AND task_id=630041')
        store.db.execute("DELETE FROM economy_events WHERE player_id=1 AND event_key LIKE 'activity-daily-repair-v1:%'")
    assert tasks(e)[630041]['taskProgress']==1
    assert tasks(e)[630041]['taskProgress']==1
    assert e.claim(1,630041,1)['code']==10
    now[0]+=86400
    assert tasks(e)[630041]['taskProgress']==0


def test_recovery_uses_successful_today_runs_only_and_never_regresses_claim(runtime):
    store,e,ctx,rt,now,battle=prepare(runtime)
    period=rt.r.at();start,end=task_period(1,now[0])
    for i,(sid,success,stamp) in enumerate([(2160111,True,now[0]),(2160112,True,now[0]),
            (2160113,False,now[0]),(2160111,False,now[0]),(2160111,True,start-1)]):
        uuid=f'old-{i}'
        with e.transaction():
            rt.r.bind_run(1,sid,uuid)
            store.db.execute('UPDATE activity_runs SET settled=1 WHERE uuid=?',(uuid,))
            store.db.execute('INSERT INTO battle_checkout_wire VALUES (?,?,?)',
                             (uuid,CHECKOUT.encode({'success':success}),'[]'))
            store.db.execute('INSERT INTO reward_settlement_audit VALUES (?,?,?,?,?,?)',
                             (uuid,1,sid,'{}','[]',stamp))
    assert tasks(e)[630040]['taskProgress']==2
    assert e.claim(1,630040,1)['code']==13
    with e.transaction():
        rt.r.bind_run(1,2160113,'old-third-success')
        store.db.execute("UPDATE activity_runs SET settled=1 WHERE uuid='old-third-success'")
        store.db.execute('INSERT INTO battle_checkout_wire VALUES (?,?,?)',
                         ('old-third-success',CHECKOUT.encode({'success':True}),'[]'))
        store.db.execute('INSERT INTO reward_settlement_audit VALUES (?,?,?,?,?,?)',
                         ('old-third-success',1,2160113,'{}','[]',now[0]))
        store.db.execute("DELETE FROM economy_events WHERE event_key LIKE 'activity-daily-repair-v1:%'")
    assert tasks(e)[630040]['taskProgress']==3
    assert e.claim(1,630040,1)['code']==10
    with e.transaction():store.db.execute("DELETE FROM economy_events WHERE event_key LIKE 'activity-daily-repair-v1:%'")
    assert tasks(e)[630040]['taskStatus']==4
    now[0]+=86400
    assert tasks(e)[630040]['taskProgress']==0
