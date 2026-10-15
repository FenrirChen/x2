import asyncio
from datetime import datetime, timezone, timedelta

import pytest

from tests.unit.test_social import social, create, fund, act
from tests.unit.test_economy import env


class Sink:
    def __init__(self, fail=None):
        self.messages=[]
        self.fail=fail

    async def push_to_player(self,pid,message):
        if message.message_name==self.fail:
            return 0
        self.messages.append(message)
        return 1


def at(day,hour,minute=0):
    return int(datetime(2026,10,day,hour,minute,tzinfo=timezone(timedelta(hours=8))).timestamp())


def wish_and_claim(s,ctx):
    member=create(s,ctx)
    fund(s,1237901,100000)
    fund(s,1201003,1)
    assert act(s,ctx,'ClubWishing',{'itemId':1201003},3).values['code']==10
    assert act(s,ctx,'ClubWishingReceive',{'donateId':member},4).values['code']==10


def count(sink):
    return next(m.values['wishingCount'] for m in reversed(sink.messages)
                if m.message_name=='L2C_ClubWishingCount')


def test_http_before_midnight_watcher_cannot_swallow_wish_reset(social):
    s,ctx,stamp=social
    stamp[0]=at(14,23,59)
    wish_and_claim(s,ctx)
    sink=Sink()
    assert asyncio.run(s.refresh_online_daily(1,sink))
    assert count(sink)==1
    stamp[0]=at(15,0)
    # This HTTP route persists the rollover before the periodic task executes.
    s.http('/ClubService.GetWishingPage',{},1)
    assert s.state(1)['wish_counts']=={}
    assert s.refresh_friends(1) is None  # Reproduces the old watcher's lost trigger.
    assert asyncio.run(s.refresh_online_daily(1,sink))
    assert count(sink)==0
    before=len(sink.messages)
    assert not asyncio.run(s.refresh_online_daily(1,sink))
    assert len(sink.messages)==before
    # Reset still permits only one new wish, including after collection.
    assert act(s,ctx,'ClubWishing',{'itemId':1201003},5).values['code']==10
    assert act(s,ctx,'ClubWishing',{'itemId':1201003},6).values['code']==13


@pytest.mark.parametrize('failure',['PlayerDataProto','L2C_ClubWishingCount'])
def test_failed_notification_is_retried_even_after_state_was_saved(social,failure):
    s,ctx,stamp=social
    stamp[0]=at(14,23)
    wish_and_claim(s,ctx)
    sink=Sink()
    assert asyncio.run(s.refresh_online_daily(1,sink))
    stamp[0]=at(15,0)
    sink.fail=failure
    assert not asyncio.run(s.refresh_online_daily(1,sink))
    sink.fail=None
    assert asyncio.run(s.refresh_online_daily(1,sink))
    assert count(sink)==0
    assert not asyncio.run(s.refresh_online_daily(1,sink))


def test_first_online_sync_preserves_already_used_today_and_unclaimed_donation(social):
    s,ctx,stamp=social
    stamp[0]=at(14,23)
    member=create(s,ctx)
    fund(s,1237901,100000)
    fund(s,1201003,1)
    assert act(s,ctx,'ClubWishing',{'itemId':1201003},3).values['code']==10
    sink=Sink()
    assert asyncio.run(s.refresh_online_daily(1,sink))
    assert count(sink)==1
    stamp[0]=at(16,0)  # Offline for more than one game day.
    s.http('/ClubService.GetWishingPage',{},1)
    assert asyncio.run(s.refresh_online_daily(1,sink))
    assert count(sink)==0
    assert any(w['owner']=='self' and w['got']<w['num'] for w in s.state(1)['wishes'])
    assert act(s,ctx,'ClubWishingReceive',{'donateId':member},4).values['code']==10
    assert act(s,ctx,'ClubWishing',{'itemId':1201003},5).values['code']==10
