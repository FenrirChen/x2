import asyncio
import json
from datetime import datetime,timezone,timedelta
from tests.unit.test_economy import env
from tests.unit.test_battle import packet,request
from tests.unit.test_social import social,create,fund,act
from x2server.player.battle import BattleService
from x2server.player.endless import week_start,weekly_values,WEEKLY,PERIOD,NAMESPACE
from x2server.player.login import LoginService
from x2server.messages.core import PLAYER_DATA


def timestamp(date):
    return int(datetime.fromisoformat(date).replace(tzinfo=timezone(timedelta(hours=8))).timestamp())


def enter(store,economy,ctx):
    battle=BattleService(store,economy)
    values=request(); values.update(missionId=2110291,chapter=2060101,sceneId=2210191)
    answer=asyncio.run(battle.enter(ctx,packet(values)))
    assert answer.values['result']==10
    return answer.values['uuid']


def test_light_grants_progress_snapshot_cap_and_replay(env):
    store,economy,ctx=env
    run=enter(store,economy,ctx)
    with economy.transaction():
        assert economy._grant(1,'battle:'+run,{1237913:600})=={1237913:600}
        assert economy._grant(1,'battle:'+run,{1237913:600})=={1237913:600}
    assert weekly_values(store,1,economy.clock())['EndlessWeekVowOfStone']==600
    assert store.db.execute('SELECT progress FROM endless_tasks WHERE task_id=100018').fetchone()[0]==600
    claim=economy.endless.claim(1,100018,'claim')
    assert claim['code']==10
    assert economy.endless.claim(1,100018,'claim')==claim
    wire=PLAYER_DATA.decode(PLAYER_DATA.encode(LoginService.snapshot_push(store.get(1),store,now=economy.clock()).values))
    assert WEEKLY.decode(wire['Weekly'])['EndlessWeekMaxVowOfStone']==10
    with economy.transaction():
        store.db.execute("INSERT INTO economy_runs(uuid,player_id,session_id,section_id) VALUES ('second',1,'test',2110291)")
        assert economy._grant(1,'battle:second',{1237913:600})=={1237913:290}
    assert weekly_values(store,1,economy.clock())['EndlessWeekVowOfStone']==890


def test_weekly_monday_zero_preserves_cap_and_inventory(env):
    store,economy,ctx=env
    stamp=[timestamp('2026-10-18T23:59:59')];economy.clock=lambda:stamp[0]
    run=enter(store,economy,ctx)
    with economy.transaction():
        economy._grant(1,'battle:'+run,{1237913:600})
    assert economy.endless.claim(1,100018,'claim')['code']==10
    quantity=store.db.execute('SELECT quantity FROM inventory WHERE item_id=1237913').fetchone()[0]
    assert week_start(stamp[0])==timestamp('2026-10-12T00:00:00')
    assert economy.endless.refresh_week(1) is None
    stamp[0]+=1
    push=economy.endless.refresh_week(1)
    weekly=WEEKLY.decode(push.values['Weekly'])
    assert weekly['EndlessWeekVowOfStone']==0 and weekly['EndlessWeekMaxVowOfStone']==10
    assert weekly['WeeklyRefreshTime']==timestamp('2026-10-19T00:00:00')
    assert economy.endless.refresh_week(1) is None
    assert store.db.execute('SELECT quantity FROM inventory WHERE item_id=1237913').fetchone()[0]==quantity
    assert not economy.endless.active_run(run,1)
    assert economy.endless.claim(1,100018,'new')['code']==13


def test_historical_light_grants_repaired_without_regrant(env):
    store,economy,ctx=env
    run=enter(store,economy,ctx)
    with economy.transaction():
        # Emulate a pre-fix confirmed reward ledger, not a fabricated profile currency.
        store.db.execute('INSERT INTO economy_grants VALUES (?,?,?,?)',(1,'battle:'+run,json.dumps({'1237913':600}),int(economy.clock())))
        store.db.execute('DELETE FROM activity_state WHERE namespace=?',(NAMESPACE,))
    economy.endless.task_values(1,2060101)
    assert weekly_values(store,1,economy.clock())['EndlessWeekVowOfStone']==600
    assert store.db.execute('SELECT progress FROM endless_tasks WHERE task_id=100018').fetchone()[0]==600
    economy.endless.task_values(1,2060101)
    assert store.db.execute('SELECT progress FROM endless_tasks WHERE task_id=100018').fetchone()[0]==600


def test_club_wish_daily_used_after_claim_and_other_item(social):
    s,ctx,stamp=social
    target=create(s,ctx); fund(s,1237901,100000); fund(s,1201003,1);fund(s,1201004,1)
    answer=act(s,ctx,'ClubWishing',{'itemId':1201003},3)
    assert answer.values['code']==10
    assert next(p for p in answer.pushes if p.message_name=='L2C_ClubWishingCount').values['wishingCount']==1
    assert act(s,ctx,'ClubWishingReceive',{'donateId':target},4).values['code']==10
    assert act(s,ctx,'ClubWishingCount',{},5).values['wishingCount']==1
    assert act(s,ctx,'ClubWishing',{'itemId':1201004},6).values['code']==13
    stamp[0]+=86400
    assert act(s,ctx,'ClubWishingCount',{},7).values['wishingCount']==0
    assert act(s,ctx,'ClubWishing',{'itemId':1201004},8).values['code']==10
