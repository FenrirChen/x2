"""降临纪念 Daily.f22 (TotalLoginIndex) 回归测试。

客户端 CumulateLoginItem 靠 Daily.TotalLoginIndex 把档位画成「已领取」,
CumulateLoginModule_RefreshRedPoint 也靠它清红点; 该字段缺席时客户端列表为
null, List.Contains 会抛 NRE。这里锁住两条: 已领档位必须下发、无档位时发哨兵。
"""

from tests.unit.test_economy import env
from x2server.messages.core import INT_PAIR, LOGIN_DAILY
from x2server.player.login import LoginService
from x2server.player.total_login import _EMPTY_INDEX, ensure_schema


def _claimed_index(push):
    daily = LOGIN_DAILY.decode(push.values["Daily"])
    return [INT_PAIR.decode(raw)["Key"] for raw in daily["TotalLoginIndex"]]


def test_claimed_slots_are_pushed_in_daily(env):
    store, economy, _ = env
    ensure_schema(store.db)
    with store.db:
        store.db.execute("INSERT OR IGNORE INTO player_total_login_claimed VALUES (1,0)")
        store.db.execute("INSERT OR IGNORE INTO player_total_login_claimed VALUES (1,2)")
    push = LoginService.snapshot_push(store.get(1), store, int(economy.clock()))
    assert _claimed_index(push) == [0, 2]
    assert set(LOGIN_DAILY.decode(push.values["Daily"])) == {
        "TotalLoginDays", "TotalLoginIndex"}


def test_no_claim_pushes_sentinel_instead_of_null(env):
    store, economy, _ = env
    push = LoginService.snapshot_push(store.get(1), store, int(economy.clock()))
    assert _claimed_index(push) == [_EMPTY_INDEX]
