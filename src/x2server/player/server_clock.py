"""One real server clock for client timestamps and Beijing calendar rules."""
from datetime import datetime, timedelta, timezone
import time

BEIJING = timezone(timedelta(hours=8))


def half_month_start(now: int) -> int:
    """Unix seconds of the local half-month block that ``now`` falls in.

    Half-months are the Beijing calendar blocks 1..15 日 and 16 日..月末, cut at
    00:00 like every other account reset. 元素之章 的「可合成次数」按这个周期
    刷新 (client AnswerConfig 281048 answers 15 日), while 每周光能奖励 is weekly.
    """
    moment = datetime.fromtimestamp(int(now), BEIJING)
    start = datetime(moment.year, moment.month, 16 if moment.day >= 16 else 1, tzinfo=BEIJING)
    return int(start.timestamp())


class ServerClock:
    def __init__(self, source=time.time):
        self.source = source

    def now(self) -> int:
        # The client ServerTime base is 1970-01-01. Send Unix seconds, not
        # seconds since 2018 or host-local naive date/time values.
        return int(self.source())

    def beijing(self) -> datetime:
        return datetime.fromtimestamp(self.now(), BEIJING)
