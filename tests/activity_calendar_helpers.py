from x2server.player.activity_rotation import ActivityRotation as R


def activity_start(index):
    # Callers use catalog theme slots; convert them to actual calendar weeks.
    cycle, slot = divmod(index, len(R.CYCLE_ORDER))
    calendar_index = cycle * len(R.CYCLE_ORDER) + R.CYCLE_ORDER.index(slot)
    return R.ANCHOR if calendar_index == 0 else R.FIRST_END + (calendar_index - 1) * R.SECONDS


def next_activity_cycle(now):
    index = 0 if now < R.FIRST_END else 1 + (now - R.FIRST_END) // R.SECONDS
    start = R.ANCHOR if index == 0 else R.FIRST_END + (index - 1) * R.SECONDS
    next_start = R.FIRST_END + (index + len(R.CYCLE_ORDER) - 1) * R.SECONDS
    return next_start + (now - start)
