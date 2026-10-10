"""One real server clock for client timestamps and Beijing calendar rules."""
from datetime import datetime, timedelta, timezone
import time

BEIJING = timezone(timedelta(hours=8))

# The one day boundary the whole server shares. Everything counted "per day"
# buckets time through the helpers below rather than through ``now // 86400``:
# the bare epoch division rolls over at UTC midnight, which is 08:00 here and not
# the midnight the client's own refresh timers count down to.
DAY_SECONDS = 86400
BEIJING_OFFSET = 8 * 3600


def day_index(now: int) -> int:
    """Which local day ``now`` falls in, as an integer key."""
    return (int(now) + BEIJING_OFFSET) // DAY_SECONDS


def day_period(now: int) -> tuple[int, int]:
    """``(start, end)`` as Unix seconds for the local day containing ``now``."""
    start = day_index(now) * DAY_SECONDS - BEIJING_OFFSET
    return start, start + DAY_SECONDS


def week_period(now: int) -> tuple[int, int]:
    """``(start, end)`` for the local week containing ``now``; weeks start Monday 00:00."""
    day = day_index(now)
    # 1970-01-01 (day 0) was a Thursday, so this week's Monday is 3 days earlier.
    monday = day - (day + 3) % 7
    start = monday * DAY_SECONDS - BEIJING_OFFSET
    return start, start + 7 * DAY_SECONDS


class ServerClock:
    def __init__(self, source=time.time):
        self.source = source

    def now(self) -> int:
        # The client ServerTime base is 1970-01-01. Send Unix seconds, not
        # seconds since 2018 or host-local naive date/time values.
        return int(self.source())

    def beijing(self) -> datetime:
        return datetime.fromtimestamp(self.now(), BEIJING)
