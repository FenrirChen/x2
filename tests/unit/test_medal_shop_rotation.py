"""Medal shelf rotation, quota migration and permanent character-fragment stock."""
import asyncio
from datetime import datetime, timedelta, timezone
import pytest
from tests.unit.test_economy import env
from tests.unit.test_battle import packet
from tests.unit.test_restored_shops_favor import listing, buy, fund
from x2server.player.shop import ShopService

TZ = timezone(timedelta(hours=8))
def stamp(y,m,d,h=0,minute=0):
    return int(datetime(y,m,d,h,minute,tzinfo=TZ).timestamp())

def test_medal_shelf_rotates_at_monday_and_across_iso_year(env):
    store,e,ctx=env
    now=[stamp(2026,10,18,23,59)]
    e.clock=lambda:now[0]
    service=ShopService(store,e)
    slots=[1909401,1909402,1909403]
    def shelf():
        return [g['goodsId'] for g in listing(service,ctx,803) if g['goodsId'] in slots]
    assert shelf()==[1909401]
    now[0]=stamp(2026,10,19)
    assert shelf()==[1909402]
    for date,gid in [((2026,12,28),1909403),((2027,1,4),1909401),
                     ((2027,1,11),1909402),((2027,1,18),1909403)]:
        now[0]=stamp(*date)
        assert shelf()==[gid]
        result=asyncio.run(service.handle(ctx,packet({'shopId':803},name='C2L_ShopGoods')))
        assert result.values['NextRefreshTime']==now[0]+7*86400
        hidden=next(g for g in slots if g!=gid)
        assert asyncio.run(service.handle(ctx,packet({'goodsId':hidden},name='C2L_QueryGoodsInfo'))).values['code']==13
        assert buy(service,ctx,803,hidden,rid=hidden).values['code']==13

def test_medal_old_wish_coin_and_rotating_shelf_share_current_week_quota(env):
    store,e,ctx=env
    now=[stamp(2026,10,19)]
    e.clock=lambda:now[0]
    service=ShopService(store,e)
    fund(store,1237918,10000)
    with store.db:
        store.db.execute('INSERT INTO shop_compat_counts VALUES (1,803,1909401,?,2)',(service._period(2),))
    good=next(g for g in listing(service,ctx,803) if g['goodsId']==1909402)
    assert good['hasBuyTimes']==2
    assert buy(service,ctx,803,1909402,2,rid=1).values['code']==13
    first=buy(service,ctx,803,1909402,rid=2)
    assert first.values['code']==10 and first.values['hasBuyTimes']==3
    assert first.values['itemId']==1237920
    assert buy(service,ctx,803,1909402,rid=2).values==first.values
    assert buy(service,ctx,803,1909402,rid=3).values['code']==13
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237918').fetchone()[0]==9500
    now[0]=stamp(2026,10,26)
    assert next(g for g in listing(service,ctx,803) if g['goodsId']==1909403)['hasBuyTimes']==0

@pytest.mark.parametrize('gid,item,limit,price,weekly',[
    (1908101,1201016,20,300,True),(1909501,1206003,5,4800,False)])
def test_medal_new_fragments_delivered_with_weekly_or_lifetime_limits(env,gid,item,limit,price,weekly):
    store,e,ctx=env
    now=[stamp(2026,10,14)]
    e.clock=lambda:now[0]
    service=ShopService(store,e)
    fund(store,1237918,100000)
    result=buy(service,ctx,803,gid,limit,rid=10)
    assert result.values['code']==10
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?',(item,)).fetchone()[0]==limit
    assert buy(service,ctx,803,gid,rid=11).values['code']==13
    assert buy(service,ctx,803,gid,limit,rid=10).values==result.values
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237918').fetchone()[0]==100000-limit*price
    now[0]=stamp(2026,10,19)
    good=next(g for g in listing(service,ctx,803) if g['goodsId']==gid)
    assert good['hasBuyTimes']==(0 if weekly else limit)
    assert buy(service,ctx,803,gid,rid=12).values['code']==(10 if weekly else 13)
