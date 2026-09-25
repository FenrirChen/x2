"""One real server clock for client timestamps and Beijing calendar rules."""
from datetime import datetime, timedelta, timezone
import time

BEIJING = timezone(timedelta(hours=8))


class ServerClock:
    def __init__(self, source=time.time):
        self.source = source

    def now(self) -> int:
        # The client ServerTime base is 1970-01-01. Send Unix seconds, not
        # seconds since 2018 or host-local naive date/time values.
        return int(self.source())

    def beijing(self) -> datetime:
        return datetime.fromtimestamp(self.now(), BEIJING)
