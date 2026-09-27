"""Run the local Account bridge and persistent minimal login service."""
import argparse
import asyncio
import os
import logging
from pathlib import Path

from x2server.bootstrap.http_server import BootstrapHTTPServer
from x2server.bootstrap.local_identity import LocalIdentityService
from x2server.bootstrap.models import RecoveredBootstrapContract, RecoveredWebGameConfig, RecoveredServerAddressConfig, ServerAddressEntry
from x2server.config.logging import configure_logging
from x2server.config.settings import Settings
from x2server.network.dispatcher import Dispatcher
from x2server.network.server import X2TCPServer
from x2server.player.store import PlayerStore
from x2server.player.login import LoginService
from x2server.player.lobby import LobbyService
from x2server.player.hero import HeroService
from x2server.player.chat import SilentChatService
from x2server.player.battle import BattleService
from x2server.player.economy import EconomyService
from x2server.player.progression import ProgressionService
from x2server.player.equipment import EquipmentService
from x2server.player.wish import WishService
from x2server.player.shop import ShopService
from x2server.player.server_clock import ServerClock
from x2server.player.birthday import BirthdayService


async def run(database: Path, seconds: float) -> None:
    guest_http = "http://10.0.2.2:18080"
    contract = RecoveredBootstrapContract(
        RecoveredWebGameConfig(service_app_id="x2-local-compat", pbs_server=guest_http,
            login_server=guest_http, account_server=guest_http, esweb_server=guest_http,
            lb_pbs_server=(guest_http,), lb_login_server=(guest_http,), lb_esweb_server=(guest_http,), area_id="local"),
        RecoveredServerAddressConfig((ServerAddressEntry("10.0.2.2", 29000),)))
    identity = LocalIdentityService(contract, account=os.environ["X2_LOCAL_ACCOUNT"], password=os.environ["X2_LOCAL_PASSWORD"])
    store = PlayerStore(database)
    clock = ServerClock()
    economy = EconomyService(store, clock=clock.now)
    equipment = EquipmentService(store, economy)
    wish = WishService(store, economy, clock=clock)
    shop = ShopService(store, economy)
    login = LoginService(identity, store, economy, equipment, wish, clock=clock)
    http = BootstrapHTTPServer("127.0.0.1", 18080, identity)
    tcp = X2TCPServer(Settings(tcp_host="127.0.0.1", tcp_port=29000, read_timeout=120),
        Dispatcher({**LobbyService(clock).handlers(), **BirthdayService(store).handlers(), **economy.handlers(), **shop.handlers(), **equipment.handlers(), **wish.handlers(), **ProgressionService(store, economy).handlers(), **BattleService(store, economy).handlers(), "C2L_HeroAll": HeroService(store).query_all,
                    "C2L_Login": login.login, "C2L_ReConnect": login.reconnect,
                    "C2L_ServerTableConfig": login.server_config}))
    chat = X2TCPServer(Settings(tcp_host="127.0.0.1", tcp_port=29001, read_timeout=120),
                       Dispatcher(SilentChatService().handlers()))
    try:
        await http.start()
        await tcp.start()
        await chat.start()
        logging.getLogger("x2.local").info("local services ready; HTTP 127.0.0.1:18080 TCP 127.0.0.1:29000")
        await asyncio.sleep(seconds)
    finally:
        await chat.stop()
        await tcp.stop()
        await http.stop()
        store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("runtime/player.sqlite3"))
    parser.add_argument("--seconds", type=float, default=3600)
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    if not os.environ.get("X2_LOCAL_ACCOUNT") or not os.environ.get("X2_LOCAL_PASSWORD"):
        parser.error("set X2_LOCAL_ACCOUNT and X2_LOCAL_PASSWORD to dedicated local test values")
    configure_logging("INFO")
    try:
        asyncio.run(run(args.database, args.seconds))
    except KeyboardInterrupt:
        pass
