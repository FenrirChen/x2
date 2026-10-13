"""Approved 35-day season calendar. Unimplemented seasons remain closed."""
from datetime import datetime, timedelta, timezone

ANCHOR = int(datetime(2026,10,13,tzinfo=timezone(timedelta(hours=8))).timestamp())
DURATION = 35 * 86400
# Same order as BattlePassModule.GetBattlePassSeason's native groups 16/23/34.
SEASONS = (
    {'key':'origin','name':'起源悖论','activity':74001,'ticket':1202901,'implemented':True},
    {'key':'moon','name':'月相明暗','ticket':1202902,'implemented':False},
    {'key':'leisure','name':'暇裕时光','ticket':1202903,'implemented':False},
)


def current_season(now):
    if now < ANCHOR:
        return None
    index = (int(now)-ANCHOR)//DURATION
    result=dict(SEASONS[index % len(SEASONS)])
    result.update(index=index, cycle=index//len(SEASONS), start=ANCHOR+index*DURATION,
                  end=ANCHOR+(index+1)*DURATION)
    return result
