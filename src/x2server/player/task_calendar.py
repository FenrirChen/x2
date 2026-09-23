"""User-defined Revival calendar, not a claim about the official server."""
from datetime import datetime, timedelta, timezone

BEIJING = timezone(timedelta(hours=8))


def task_period(kind: int, now: int) -> tuple[int, int]:
    local = datetime.fromtimestamp(now, BEIJING)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    if kind == 1:
        start, duration = midnight, timedelta(days=1)
    elif kind == 2:
        start = midnight - timedelta(days=local.weekday()) + timedelta(hours=5)
        if local < start:
            start -= timedelta(days=7)
        duration = timedelta(days=7)
    else:
        raise ValueError("unsupported task period")
    return int(start.timestamp()), int((start + duration).timestamp())
