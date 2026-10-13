import pytest
from datetime import datetime, timezone, timedelta
from tests.unit.test_origin_season import env
from x2server.player.economy import UnresolvedEconomy
from x2server.messages.season import SEASON_SCHEMAS


def stamp(hour, day=13):
    return int(datetime(2026,10,day,hour,tzinfo=timezone(timedelta(hours=8))).timestamp())


@pytest.mark.parametrize('hour', [0,4,5,8,12,13,19,23])
def test_claim_once_and_native_display_date(env,hour):
    store,e,s=env
    store.db.execute("UPDATE season_calendar SET start_sec=0")
    e.clock=lambda:stamp(hour)
    assert s.base_info(s.state(1))['lastBattlePassSign']==0
    with e.transaction():
        result=s.operate(1,'SignBattlePass',{},'first')
    assert SEASON_SCHEMAS['BattlePassBaseInfo'].decode(result['baseInfo'])['lastBattlePassSign']==stamp(hour)
    with pytest.raises(UnresolvedEconomy),e.transaction():
        s.operate(1,'SignBattlePass',{},'repeat')
    assert s.state(1)['exp']==680


def test_legacy_midnight_marker_and_midnight_reset(env):
    store,e,s=env
    store.db.execute("UPDATE season_calendar SET start_sec=0")
    e.clock=lambda:stamp(1)
    with e.transaction():s.operate(1,'SignBattlePass',{},'first')
    day=s.state(1)['sign_day']
    e.clock=lambda:stamp(19)
    assert s.base_info(s.state(1))['lastBattlePassSign']==stamp(19)
    assert s.state(1)['sign_day']==day
    e.clock=lambda:stamp(0,14)
    assert s.base_info(s.state(1))['lastBattlePassSign']==0
    with e.transaction():s.operate(1,'SignBattlePass',{},'next-day')
    assert s.state(1)['exp']==1360
