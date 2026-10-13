import json
from datetime import datetime, timedelta, timezone
from tests.unit.test_origin_season import env
from tests.integration.test_local_registration import AccountFlow
from x2server.player.system_mail import deliver_daily_welfare, deliver_player_gift
from x2server.player.season_schedule import ANCHOR,DURATION,current_season
from x2server.player.activity_rotation import ActivityRotation


def test_daily_ticket_offline_old_player_restart_and_claim_history(env, monkeypatch):
    store,e,s=env
    now=ANCHOR+12*3600
    # An unbound legacy save is eligible; deployment sweep does not need login.
    assert deliver_daily_welfare(store,now)[1]==[]
    assert deliver_daily_welfare(store,now)[0]==0
    rows=store.db.execute("SELECT * FROM player_mail WHERE source_key LIKE 'daily_season_ticket:%'").fetchall()
    assert len(rows)==1 and json.loads(rows[0]['attachments'])=={'1202901':10}
    from x2server.player.mail import MailService
    mail=MailService(store,e)
    with e.transaction():
        assert mail._claim(1,[rows[0]['id']])=={1202901:10}
    deliver_daily_welfare(store,now)
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1202901').fetchone()[0]==10
    deliver_daily_welfare(store,now+86400)
    assert store.db.execute("SELECT count(*) FROM player_mail WHERE source_key LIKE 'daily_season_ticket:%'").fetchone()[0]==2
    deliver_daily_welfare(store,ANCHOR+DURATION)
    assert store.db.execute("SELECT count(*) FROM player_mail WHERE source_key LIKE 'daily_season_ticket:%'").fetchone()[0]==2


def test_remote_deployment_gift_backfills_offline_and_never_duplicates(env):
    store,e,s=env
    assert deliver_player_gift(store,ANCHOR,'causality_oct13')==(1,[])
    row=store.db.execute("SELECT * FROM player_mail WHERE source_key LIKE 'causality_gift_20261013_50:%'").fetchone()
    assert json.loads(row['attachments'])=={'1202014':50}
    assert deliver_player_gift(store,ANCHOR+1,'causality_oct13')==(0,[])
    store.db.execute('UPDATE player_mail SET deleted=1,state=3 WHERE id=?',(row['id'],));store.db.commit()
    assert deliver_player_gift(store,ANCHOR+86400,'causality_oct13')==(0,[])


def test_season_35_days_and_return_keeps_ticket_inventory(env):
    store,e,s=env
    e.clock=lambda:ANCHOR+100
    with e.transaction():e._grant(1,'tickets',{1202901:27})
    first=s.instance
    state=s.state(1);state['exp']=3000
    with e.transaction():s.write(1,state)
    assert s.active(1)
    assert s.calendar()['start_sec']==ANCHOR and s.calendar()['end_sec']==ANCHOR+DURATION
    e.clock=lambda:ANCHOR+DURATION
    assert current_season(e.clock())['key']=='moon' and not s.active(1)
    e.clock=lambda:ANCHOR+3*DURATION
    assert s.active(1) and s.instance!=first
    assert s.state(1)['exp']==0
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1202901').fetchone()[0]==27


def test_weekly_calendar_first_extension_and_all_boundaries(env):
    store,e,_=env
    r=ActivityRotation(store,e.clock)
    assert r.at(ANCHOR).index==0
    assert r.at(r.FIRST_END-1).index==0
    for i in range(1,16):
        start,end=r.bounds(i)
        period=r.at(start)
        assert end-start==7*86400
        assert datetime.fromtimestamp(start,timezone(timedelta(hours=8))).weekday()==0
        assert period.start==start and period.end==end and period.index>=1_000_000
        assert r.at(end-1)==period and r.at(end)!=period


def test_markread_http_updates_only_owned_mail(tmp_path):
    flow=AccountFlow(tmp_path)
    try:
        flow.register('alpha','password')
        _,game=flow.game_session('alpha','password')
        player=game['playerID']
        ids=[r[0] for r in flow.store.db.execute('SELECT id FROM player_mail WHERE player_id=? LIMIT 2',(player,))]
        args={'appid':flow.identity.contract.web_config.service_app_id,'userid':str(player),'ids':ids}
        def req(values):return flow.identity.respond('POST','/MailService.MarkRead',json.dumps(values).encode(),authorization='Bearer '+game['token'])
        response=req(args)
        assert response.status==200 and json.loads(response.body)['code']==0
        assert all(r[0]==1 for r in flow.store.db.execute('SELECT state FROM player_mail WHERE id IN (?,?)',ids))
        assert req(dict(args,ids=[ids[0],999999])).status==404
        assert req(dict(args,userid='999999')).status==403
        assert req(dict(args,ids=[-1])).status==400
        assert req(args).status==200
    finally:flow.accounts.close();flow.store.close()


def test_daily_watch_survives_normal_callback_and_issues_next_day(env):
    import asyncio
    from x2server.player.system_mail import daily_welfare_watch
    store,e,s=env
    now=[ANCHOR+3600]
    async def scenario():
        async def rollover(day):
            return None
        task=asyncio.create_task(daily_welfare_watch(store,lambda:now[0],poll=0.01,on_new_day=rollover))
        try:
            await asyncio.sleep(0.03)
            assert not task.done()
            now[0]+=86400
            await asyncio.sleep(0.03)
            assert not task.done()
            assert store.db.execute("SELECT count(*) FROM player_mail WHERE source_key LIKE 'daily_season_ticket:%'").fetchone()[0]==2
        finally:
            task.cancel()
            try:await task
            except asyncio.CancelledError:pass
    asyncio.run(scenario())
