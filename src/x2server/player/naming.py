"""Native BaseInfo.NickCount with compatibility for previously named saves."""


def nickname_count(snapshot):
    count = snapshot.get('nick_count', 0)
    if type(count) is not int or not 0 <= count <= 2**31 - 1:
        count = 0
    # Old exports stored the nickname but predate the explicit native counter.
    return max(count, int(bool(snapshot.get('nickname', '').strip())))
