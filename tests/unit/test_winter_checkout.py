import asyncio
import pytest

from tests.activity_calendar_helpers import activity_start
from tests.unit.test_activity_runtime import runtime
from tests.unit.test_economy import env
from tests.unit.test_battle import packet
from x2server.messages.activity import ACTIVITY_SCHEMAS
from x2server.network.dispatcher import OutboundMessage
from x2server.player.activity_protocol import check_progress
from x2server.player.economy import UnresolvedEconomy


def catalog(rt):
    return [ACTIVITY_SCHEMAS['ActivityData'].decode(raw)
            for raw in rt.a.query_activity(1)['activityData']]


def test_rotation_explicitly_closes_previously_open_modules(runtime):
    _,_,_,rt,now=runtime
    cache={}
    for slot in (3,4,6,1,0,5,2,3,4):
        now[0]=activity_start(slot)+3600
        period=rt.r.at()
        rows=catalog(rt)
        # Native cache merges by activity ID, so omitted rows stay open.
        cache.update({row['actId']:row for row in rows})
        assert {row['activityGroup'] for row in cache.values() if row['state']} == {period.theme['group']}
        assert all(row['endTime'] < now[0] for row in rows if row['activityGroup'] != period.theme['group'])
        if slot==4:
            old_shops=[r for r in rows if r['activityGroup']==13 and r['actType']==43]
            assert old_shops and all(r['state']==0 for r in old_shops)


@pytest.mark.parametrize('slot',range(7))
def test_unsolicited_pass_records_only_go_to_the_osiris_activity(runtime,slot):
    _,_,ctx,rt,now=runtime
    now[0]=activity_start(slot)+3600
    period=rt.r.at()
    updates=rt.progress_messages(1,allow_navigation=False)
    names={p.message_name for p in updates}
    assert ('L2C_ActivityPassRecord' in names) == (period.theme['group']==13)
    if period.theme['group']==7:
        assert 'L2C_QueryShuangHanActivity' in names
    explicit=asyncio.run(rt.handle(ctx,packet({},81001,'C2L_ActivityPassRecord')))
    assert explicit.values['code']==10 and explicit.values['missionPassCount']
    if period.theme['group']!=13:
        with pytest.raises(UnresolvedEconomy):
            check_progress(rt,period,OutboundMessage('L2C_ActivityPassRecord',explicit.values))
