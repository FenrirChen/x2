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
from x2server.config.deployment import DeploymentEndpoints
from x2server.network.dispatcher import Dispatcher, OutboundMessage
from x2server.network.server import X2TCPServer
from x2server.player.store import PlayerStore
from x2server.player.accounts import AccountStore
from x2server.player.login import LoginService
from x2server.player.lobby import LobbyService
from x2server.player.hero import HeroService
from x2server.player.chat import SilentChatService
from x2server.player.battle import BattleService
from x2server.player.battle_shop import BattleShopService
from x2server.player.economy import EconomyService
from x2server.player.progression import ProgressionService
from x2server.player.equipment import EquipmentService
from x2server.player.wish import WishService
from x2server.player.shop import ShopService
from x2server.player.gift_packages import GiftPackageService
from x2server.player.appearance_shop import AppearanceShopService
from x2server.player.server_clock import ServerClock
from x2server.player.birthday import BirthdayService
from x2server.player.collection import CollectionService
from x2server.player.favor import FavorService
from x2server.player.appearance import AppearanceService
from x2server.player.mail import MailService
from x2server.player.terminal import TerminalService
from x2server.player.college import CollegeStateRepository
from x2server.player.system_mail import daily_welfare_watch, deliver_hero_choice
from x2server.player.tutorial import TutorialService
from x2server.player.star_chart import StarChartService
from x2server.player.equip_plans import EquipPlanService


async def run(database: Path, seconds: float) -> None:
    endpoints = DeploymentEndpoints.from_environment()
    guest_http = f"http://{endpoints.public_host}:{endpoints.http_port}"
    contract = RecoveredBootstrapContract(
        RecoveredWebGameConfig(service_app_id="x2-local-compat", pbs_server=guest_http,
            login_server=guest_http, account_server=guest_http, esweb_server=guest_http,
            lb_pbs_server=(guest_http,), lb_login_server=(guest_http,), lb_esweb_server=(guest_http,), area_id="local"),
        RecoveredServerAddressConfig((ServerAddressEntry(endpoints.public_host, endpoints.game_port),)))
    store = PlayerStore(database)
    logging.getLogger("x2.local").info("active database=%s server_source=%s",
        store.path.resolve(), Path(__file__).resolve())
    accounts = AccountStore(store)
    identity = LocalIdentityService(contract, account=os.environ.get("X2_LOCAL_ACCOUNT"),
        password=os.environ.get("X2_LOCAL_PASSWORD"), accounts=accounts, players=store,
        chat_entry=f"{endpoints.public_host}:{endpoints.chat_port}")
    clock = ServerClock()
    choice_minted, choice_failed = deliver_hero_choice(store, clock.now())
    logging.getLogger("x2.system_mail").info(
        "hero choice mail backfill minted=%s failed=%s", choice_minted, choice_failed)
    college = CollegeStateRepository(store, clock)
    economy = EconomyService(store, clock=clock.now)
    star_chart = StarChartService(store, economy)
    equipment = EquipmentService(store, economy)
    # 兽主套装预设：应用预设要校验部件槽位并推 L2C_EquipUpdate，所以放在 equipment 之后
    # 构造。见 player/equip_plans.py。
    equip_plans = EquipPlanService(store, economy, equipment=equipment, clock=clock)
    wish = WishService(store, economy, clock=clock)
    shop = ShopService(store, economy)
    gift_packages = GiftPackageService(store, economy)
    collection = CollectionService(store, economy)
    favor = FavorService(store, economy, clock=clock.now)
    appearance = AppearanceService(store, economy)
    appearance_shop = AppearanceShopService(store, economy, appearance)
    mail = MailService(store, economy, clock=clock.now)
    terminal = TerminalService(store, economy, clock=clock.now)
    login = LoginService(identity, store, economy, equipment, wish, clock=clock, appearance=appearance,
                         mail=mail, gift_packages=gift_packages, college=college)
    http = BootstrapHTTPServer(endpoints.bind_host, endpoints.http_port, identity)
    tcp = X2TCPServer(Settings(tcp_host=endpoints.bind_host, tcp_port=endpoints.game_port, read_timeout=120),
        Dispatcher({**star_chart.handlers(), **LobbyService(clock, college).handlers(), **TutorialService(store).handlers(), **BirthdayService(store).handlers(), **economy.handlers(), **shop.handlers(), **gift_packages.handlers(), **collection.handlers(), **favor.handlers(), **appearance.handlers(), **appearance_shop.handlers(), **mail.handlers(), **terminal.handlers(), **equipment.handlers(), **equip_plans.handlers(), **wish.handlers(), **ProgressionService(store, economy, appearance).handlers(), **BattleService(store, economy).handlers(), **BattleShopService(store, economy).handlers(), "C2L_HeroAll": HeroService(store).query_all,
                    "C2L_Login": login.login, "C2L_ReConnect": login.reconnect,
                    "C2L_ServerTableConfig": login.server_config}))
    chat = X2TCPServer(Settings(tcp_host=endpoints.bind_host, tcp_port=endpoints.chat_port, read_timeout=120),
                       Dispatcher(SilentChatService().handlers()))
    mail_task = None
    welfare_task = None
    world_boss_task = None

    async def settle_monthcards(day_start):
        """Pay the month-card allowance at the local midnight, even online."""
        for (player_id,) in store.db.execute(
                "SELECT DISTINCT player_id FROM gift_package_claims WHERE package_id=?",
                (gift_packages.MONTHCARD_ID,)):
            if gift_packages.settle_daily(player_id) and player_id in tcp.authenticated_player_ids():
                await tcp.push_to_player(player_id, OutboundMessage("L2C_ItemUpdate",
                    {"code": 10, **economy.inventory_values(player_id)}))

    try:
        await http.start()
        await tcp.start()
        await chat.start()
        mail_task = asyncio.create_task(mail.watch(tcp), name="local-mail-push")
        world_boss_task = asyncio.create_task(economy.world_boss.watch(),name="local-world-boss")
        welfare_task = asyncio.create_task(daily_welfare_watch(store, clock.now,
            on_new_day=settle_monthcards), name="local-daily-welfare")
        logging.getLogger("x2.local").info(
            "services ready; HTTP %s:%s game TCP %s:%s chat TCP %s:%s public=%s",
            endpoints.bind_host, endpoints.http_port, endpoints.bind_host, endpoints.game_port,
            endpoints.bind_host, endpoints.chat_port, endpoints.public_host)
        if seconds == 0:
            await asyncio.Event().wait()
        else:
            await asyncio.sleep(seconds)
    finally:
        for task in (mail_task, welfare_task, world_boss_task):
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        await chat.stop()
        await tcp.stop()
        await http.stop()
        accounts.close()
        store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path,
                        default=Path(os.getenv("X2_DB_PATH", "runtime/player.sqlite3")))
    parser.add_argument("--seconds", type=float, default=3600)
    args = parser.parse_args()
    if args.seconds < 0:
        parser.error("--seconds must be nonnegative (0 runs until stopped)")
    if not os.environ.get("X2_LOCAL_ACCOUNT") or not os.environ.get("X2_LOCAL_PASSWORD"):
        # Optional since the account layer: new players register through the
        # client UI (/register). The passwordless visitor mode needs a
        # collision-safe identity before it can be offered publicly.
        logging.getLogger("x2.local").info(
            "no X2_LOCAL_ACCOUNT/PASSWORD seed; new users register in the client")
    configure_logging("INFO")
    try:
        asyncio.run(run(args.database, args.seconds))
    except KeyboardInterrupt:
        pass
