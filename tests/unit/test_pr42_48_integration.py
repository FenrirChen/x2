import asyncio,json
import pytest
from tests.unit.test_economy import env
from tests.unit.test_social import social,act
from tests.unit.test_college_upgrade import game
from tests.unit.test_battle import packet
from x2server.player.shop import ShopService
from x2server.player.college_jobs import CollegeJobsService


def test_new_shop_union_all_goods_purchase_and_weekly_refresh(env):
    store,economy,ctx=env;shop=ShopService(store,economy)
    assert not ({802,807,810}&shop.retired_shop_ids)
    for (sid,gid),row in shop.compat_offers.items():
        if sid not in (802,807,810):continue
        with store.db:
            store.db.execute('INSERT INTO inventory VALUES (?,?,?) ON CONFLICT(player_id,item_id) DO UPDATE SET quantity=excluded.quantity',
                (1,row['currencyItemId'],4000 if sid==802 else 100000))
        answer=asyncio.run(shop.handle(ctx,packet({'shopId':sid,'goodsId':gid,'buyNum':1},request_id=gid,name='C2L_BuyGoods')))
        assert answer.values['code']==10,(sid,gid)
    from datetime import datetime,timezone,timedelta
    now=int(datetime(2026,10,18,23,59,59,tzinfo=timezone(timedelta(hours=8))).timestamp())
    economy.clock=lambda:now
    assert shop._next_refresh(807)==now+1==shop._next_refresh(810)


def test_actual_friend_gains_daily_gifts_cap_and_replay(social):
    s,ctx,stamp=social;uid=next(iter(s.characters))
    assert act(s,ctx,'ReceiveFriendCoin',{'playerid':[uid]},1).values['code']==10
    s.economy.ensure_periods(1)
    assert s.store.db.execute('SELECT progress FROM economy_tasks WHERE task_id=630023').fetchone()[0]==0
    sent=act(s,ctx,'SendFriendCoin',{'playerid':[uid]},2)
    assert sent.values['code']==10
    assert any(p.message_name=='L2C_TaskUpdate' and p.values['type']==1 for p in sent.pushes)
    assert any(p.message_name=='L2C_AchvUpdate' for p in sent.pushes)
    assert act(s,ctx,'SendFriendCoin',{'playerid':[uid]},2).values['code']==10
    assert s.economy.achievements.states(1)[660010][0]==40
    with s.store.db:
        s.store.db.execute('UPDATE inventory SET quantity=5000 WHERE item_id=1237917')
    stamp[0]+=86400
    assert act(s,ctx,'SendFriendCoin',{'playerid':[uid]},3).values['code']==10
    assert s.store.db.execute('SELECT progress FROM economy_tasks WHERE task_id=630023').fetchone()[0]==1
    assert s.economy.achievements.states(1)[660010][0]==40


def test_legacy_achievement_sources_backfill_once_without_rewards(env):
    store,e,ctx=env
    with e.transaction():
        e._grant(1,'college-trade:legacy',{1237901:1234})
        e._grant(1,'social:legacy',{1237917:20})
        e._grant(1,'terminal-wish:123:1700001',{1237901:20})
        store.db.execute('DELETE FROM achievement_events')
    before=dict(store.db.execute('SELECT item_id,quantity FROM inventory'))
    counts=store.db.execute('SELECT COUNT(*) FROM economy_grants').fetchone()[0]
    states=e.achievements.states(1)
    assert states[662300][0]==1234
    assert states[660010][0]==20
    assert states[660280][0]==1
    assert e.achievements.states(1)==states
    assert dict(store.db.execute('SELECT item_id,quantity FROM inventory'))==before
    assert store.db.execute('SELECT COUNT(*) FROM economy_grants').fetchone()[0]==counts
    with e.transaction():e._grant(1,'social:new',{1237917:20})
    assert e.achievements.states(1)[660010][0]==40


def test_ruin_experience_chain_and_six_queue_rows(game):
    _,_,repo,college,_=game
    assert [r['ruinId'] for r in repo.unlock_ruins(1)]==[34001]
    state=repo.load(1)
    assert college.jobs.effects(college.jobs.explores[34001],0,3)==[]
    assert college.jobs.effects(college.jobs.explores[34001],1,3)==[34002]
    assert college.jobs.effects(college.jobs.explores[34002],5,3)==[]
    assert college.jobs.effects(college.jobs.explores[34002],6,3)==[34003]
    growth=repo.growth_base(1)
    from x2server.messages.lobby import TRAINING_DATA,EXPLORE_DATA
    train=[TRAINING_DATA.decode(r) for r in growth['trainingList']]
    explore=[EXPLORE_DATA.decode(r) for r in growth['exploreList']]
    assert len(train)==len(explore)==6
    assert [r['trainingStatus'] for r in train]==[1,0,0,0,0,0]
