from x2server.player.activity_rotation import ActivityRotation as R


def activity_start(index):
    return R.ANCHOR if index == 0 else R.FIRST_END + (index - 1) * R.SECONDS


def next_activity_cycle(now):
    index=0 if now < R.FIRST_END else 1+(now-R.FIRST_END)//R.SECONDS
    return activity_start(index+7)+(now-activity_start(index))
