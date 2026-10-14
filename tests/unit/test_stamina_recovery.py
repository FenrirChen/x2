"""Time based stamina stays authoritative across requests and cap transitions."""
import asyncio

from tests.unit.test_battle import packet
from tests.unit.test_economy import env  # noqa: F401
from x2server.messages.core import STRING_PAIR
from x2server.player.college import CollegeStateRepository
from x2server.player.economy import EconomyService
from x2server.player.login import LoginService


class _NowClock:
    """ServerClock-shaped adapter so CollegeStateRepository follows the fake clock."""

    def __init__(self, now):
        self._now = now

    def now(self):
        return self._now[0]


def test_recovery_uses_225_seconds_and_keeps_partial_interval(env):
    store, _, _ = env
    now = [1_000_000]
    economy = EconomyService(store, clock=lambda: now[0])
    snapshot = store.get(1)["snapshot"]
    snapshot["mobility"] = {"power": 100}
    economy.save_snapshot(1, snapshot)
    economy.refresh_stamina(1)
    assert store.get(1)["snapshot"]["mobility"] == {
        "power": 100, "recover_anchor": now[0], "shop_power_fetch_time": now[0]}
    now[0] += 224
    economy.refresh_stamina(1)
    assert store.get(1)["snapshot"]["mobility"]["power"] == 100
    now[0] += 1
    economy.refresh_stamina(1)
    assert store.get(1)["snapshot"]["mobility"]["power"] == 101
    now[0] += 450 + 100
    economy.refresh_stamina(1)
    mobility = store.get(1)["snapshot"]["mobility"]
    assert mobility["power"] == 103
    assert mobility["recover_anchor"] == 1_000_000 + 675
    assert mobility["shop_power_fetch_time"] == mobility["recover_anchor"]
    economy.refresh_stamina(1)
    assert store.get(1)["snapshot"]["mobility"] == mobility


def test_recovery_caps_and_restarts_only_after_spending(env):
    store, _, _ = env
    now = [1_000_000]
    economy = EconomyService(store, clock=lambda: now[0])
    snapshot = store.get(1)["snapshot"]
    snapshot["mobility"] = {"power": 148, "recover_anchor": now[0]}
    economy.save_snapshot(1, snapshot)
    now[0] += 900
    economy.refresh_stamina(1)
    assert store.get(1)["snapshot"]["mobility"]["power"] == 149
    now[0] += 900
    economy.charge_battle(1, "run", 2110801, 6)
    assert store.get(1)["snapshot"]["mobility"] == {
        "power": 143, "recover_anchor": now[0], "shop_power_fetch_time": now[0]}
    now[0] += 225
    economy.refresh_stamina(1)
    assert store.get(1)["snapshot"]["mobility"]["power"] == 144


def test_overflow_stamina_is_stored_in_enlightenment_tower(env):
    """体力条填满后剩下的整期按启明之塔 702 星级转化率存进塔, 塔满则封顶丢弃。"""
    store, _, _ = env
    now = [1_000_000]
    economy = EconomyService(store, clock=lambda: now[0])
    repo = CollegeStateRepository(store, _NowClock(now))
    economy.college = repo
    cap = economy.power_caps[60]
    periods = 20
    snapshot = store.get(1)["snapshot"]
    snapshot["mobility"] = {"power": cap,
                            "recover_anchor": now[0] - periods * economy.POWER_RECOVER_SECONDS}
    economy.save_snapshot(1, snapshot)
    economy.refresh_stamina(1)
    # 702 初始 1★ 的转化率是 500 毫因果/期, 体力已满 → 全部 20 期进塔。
    assert int(repo.load(1)["extra_power"]) == periods * 500
    assert store.get(1)["snapshot"]["mobility"]["power"] == cap
    # 塔的存储上限 = storage_cap(702, L1) = 100 因果 = 100000 毫因果; 多出的期数被丢弃。
    now[0] += 400 * economy.POWER_RECOVER_SECONDS
    economy.refresh_stamina(1)
    assert int(repo.load(1)["extra_power"]) == 100 * 1000


def test_client_recovery_config_matches_server(env):
    store, economy, ctx = env
    response = asyncio.run(LoginService(None, store, economy).server_config(
        ctx, packet({}, name="C2L_ServerTableConfig")))
    pairs = {r["key"]: r["val"] for r in map(STRING_PAIR.decode, response.values["keyVal"])}
    assert pairs["PowerRecover"] == str(EconomyService.POWER_RECOVER_SECONDS) == "225"
    capacity = int(pairs['EquipPageLimit']) * int(pairs['EquipCellLimit'])
    assert capacity == 1280
    assert 805 < capacity
