"""Time based stamina stays authoritative across requests and cap transitions."""
import asyncio

from tests.unit.test_battle import packet
from tests.unit.test_economy import env  # noqa: F401
from x2server.messages.core import STRING_PAIR
from x2server.player.economy import EconomyService
from x2server.player.login import LoginService


def test_recovery_uses_225_seconds_and_keeps_partial_interval(env):
    store, _, _ = env
    now = [1_000_000]
    economy = EconomyService(store, clock=lambda: now[0])
    snapshot = store.get(1)["snapshot"]
    snapshot["mobility"] = {"power": 100}
    economy.save_snapshot(1, snapshot)
    economy.refresh_stamina(1)
    assert store.get(1)["snapshot"]["mobility"] == {"power": 100, "recover_anchor": now[0]}
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
    assert store.get(1)["snapshot"]["mobility"] == {"power": 143, "recover_anchor": now[0]}
    now[0] += 225
    economy.refresh_stamina(1)
    assert store.get(1)["snapshot"]["mobility"]["power"] == 144


def test_client_recovery_config_matches_server(env):
    store, economy, ctx = env
    response = asyncio.run(LoginService(None, store, economy).server_config(
        ctx, packet({}, name="C2L_ServerTableConfig")))
    pairs = {r["key"]: r["val"] for r in map(STRING_PAIR.decode, response.values["keyVal"])}
    assert pairs["PowerRecover"] == str(EconomyService.POWER_RECOVER_SECONDS) == "225"
