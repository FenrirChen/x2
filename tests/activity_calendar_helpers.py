from x2server.player.activity_rotation import ActivityRotation as R


def activity_start(index):
    index = R.FIRST_CYCLE_SWAP.get(index, index)
    return R.ANCHOR if index == 0 else R.FIRST_END + (index - 1) * R.SECONDS


def next_activity_cycle(now):
    index=0 if now < R.FIRST_END else 1+(now-R.FIRST_END)//R.SECONDS
    semantic = R.FIRST_CYCLE_SWAP.get(index, index)
    return activity_start(semantic+7)+(now-activity_start(semantic))
