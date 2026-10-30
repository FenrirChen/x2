"""Run the local Account bridge and persistent minimal login service."""
import argparse
import asyncio
import os
import logging
import time
from pathlib import Path

from x2server.bootstrap.http_server import BootstrapHTTPServer
from x2server.bootstrap.local_identity import LocalIdentityService
from x2server.bootstrap.save_manager_api import SaveManagerAPI
from x2server.bootstrap.models import RecoveredBootstrapContract, RecoveredWebGameConfig, RecoveredServerAddressConfig, ServerAddressEntry
from x2server.config.logging import configure_logging
from x2server.config.settings import Settings
from x2server.config.deployment import DeploymentEndpoints
from x2server.network.dispatcher import Dispatcher, OutboundMessage
from x2server.network.server import X2TCPServer
from x2server.player.store import PlayerStore
from x2server.player.accounts import AccountStore
from x2server.player.save_manager import SaveManager
from x2server.player.login import LoginService
from x2server.player.lobby import LobbyService
from x2server.player.hero import HeroService
from x2server.player.chat import SilentChatService
from x2server.player.battle import BattleService
from x2server.player.battle_shop import BattleShopService
from x2server.player.economy import EconomyService
from x2server.player.activity import ActivityService
from x2server.player.activity_runtime import ActivityRuntime
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
from x2server.player.college import CollegeService, CollegeStateRepository
from x2server.player.system_mail import daily_welfare_watch, deliver_hero_choice, deliver_ultimate_causality, deliver_revival_supply, deliver_player_gift
from x2server.player.tutorial import TutorialService
from x2server.player.star_chart import StarChartService
from x2server.player.equip_plans import EquipPlanService
from x2server.player.divination import DivinationService
from x2server.player.social import SocialService
from x2server.bootstrap.social_api import SocialAPI


def _online_player_ids(loop: asyncio.AbstractEventLoop, tcp: "X2TCPServer") -> set[int]:
    """Thread-safe snapshot of live authenticated game players.

    The bootstrap HTTP service answers from worker threads while the TCP server
    lives on the asyncio loop; scheduling the snapshot onto the loop removes
    the race that a raw dict read would have.
    """
    import concurrent.futures

    async def snapshot() -> set[int]:
        return tcp.authenticated_player_ids()

    future = asyncio.run_coroutine_threadsafe(snapshot(), loop)
    try:
        return future.result(timeout=2.0)
    except concurrent.futures.TimeoutError:
        logging.getLogger("x2.local").error("online player snapshot timed out")
        future.cancel()
        raise RuntimeError("online player snapshot timed out")


async def loop_health_watch(interval=1):
    while True:
        started = time.monotonic()
        await asyncio.sleep(interval)
        lag = time.monotonic() - started - interval
        if lag > .5:
            memory = {}
            status = Path('/proc/self/status')
            if status.exists():
                for line in status.read_text().splitlines():
                    key, _, value = line.partition(':')
                    if key in ('VmRSS', 'VmSwap'):
                        memory[key] = value.strip()
            logging.getLogger('x2.local').warning('event loop stalled lag=%.3fs memory=%s', lag, memory)


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
    # Approved 35-day Origin season is on by default in actual deployments.
    # Administrators may explicitly disable it with X2_ORIGIN_SEASON_ENABLED=0.
    os.environ.setdefault('X2_ORIGIN_SEASON_ENABLED', '1')
    accounts = AccountStore(store)
    save_manager = SaveManager(store)
    removed_backups = save_manager.prune_import_backups()
    logging.getLogger("x2.local").info("import backup retention removed=%s keep_per_player=1", removed_backups)
    save_api = SaveManagerAPI(save_manager, accounts,
        online_player_ids=lambda: _online_player_ids(main_loop, tcp),
        isolated_jobs=True)  # No time cooldown; concurrent heavy jobs are still bounded.
    identity = LocalIdentityService(contract, account=os.environ.get("X2_LOCAL_ACCOUNT"),
        password=os.environ.get("X2_LOCAL_PASSWORD"), accounts=accounts, players=store,
        chat_entry=f"{endpoints.public_host}:{endpoints.chat_port}",
        save_manager_api=save_api)
    main_loop = asyncio.get_running_loop()
    clock = ServerClock()
    choice_minted, choice_failed = deliver_hero_choice(store, clock.now())
    logging.getLogger("x2.system_mail").info(
        "hero choice mail backfill minted=%s failed=%s", choice_minted, choice_failed)
    causality_minted, causality_failed = deliver_ultimate_causality(store, clock.now())
    logging.getLogger("x2.system_mail").info(
        "ultimate causality mail backfill minted=%s failed=%s", causality_minted, causality_failed)
    college = CollegeStateRepository(store, clock)
    supply_minted, supply_failed = deliver_revival_supply(store, clock.now())
    logging.getLogger("x2.system_mail").info(
        "revival supply mail backfill minted=%s failed=%s", supply_minted, supply_failed)
    extra_minted, extra_failed = deliver_player_gift(store, clock.now(), "causality_oct13")
    logging.getLogger("x2.system_mail").info("October causality gift minted=%s failed=%s", extra_minted, extra_failed)
    oct25_minted, oct25_failed = deliver_player_gift(store, clock.now(), "oct25_supply_80_200")
    logging.getLogger("x2.system_mail").info("October 25 supply backfill minted=%s failed=%s", oct25_minted, oct25_failed)
    journey_minted, journey_failed = deliver_player_gift(store, clock.now(), "journey_supply_120_100")
    logging.getLogger("x2.system_mail").info("journey supply mail backfill minted=%s failed=%s", journey_minted, journey_failed)
    from x2server.player.extra_drop import resource_drop_enabled
    economy = EconomyService(store, clock=clock.now, resource_double_drop=resource_drop_enabled())
    economy.college = college
    social = SocialService(store, economy, college)
    economy.social = social
    identity.social_api = SocialAPI(identity, social, main_loop)
    # 星相屋/每日占卜 (362/363): 读写自己的签到状态并真发货, 见 player/divination.py。
    divination = DivinationService(store, economy)
    college_flows = CollegeService(college, economy=economy)
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
    lobby = LobbyService(clock, college)
    # ActivityRuntime answers C2L_QueryActivity, so hand the lobby in: otherwise
    # the recovered sweep entry disappears from the rebuilt roster directory.
    activity = ActivityService(economy, lobby=lobby)
    economy.activity = activity
    activity_runtime = ActivityRuntime(activity, mail, appearance)
    terminal = TerminalService(store, economy, clock=clock.now)
    login = LoginService(identity, store, economy, equipment, wish, clock=clock, appearance=appearance,
                         mail=mail, gift_packages=gift_packages, college=college)
    http = BootstrapHTTPServer(endpoints.bind_host, endpoints.http_port, identity)
    tcp = X2TCPServer(Settings(tcp_host=endpoints.bind_host, tcp_port=endpoints.game_port, read_timeout=120),
        Dispatcher({**star_chart.handlers(), **lobby.handlers(), **college_flows.handlers(), **TutorialService(store).handlers(), **BirthdayService(store).handlers(), **economy.handlers(), **divination.handlers(), **shop.handlers(), **gift_packages.handlers(), **collection.handlers(), **favor.handlers(), **appearance.handlers(), **appearance_shop.handlers(), **mail.handlers(), **terminal.handlers(), **equipment.handlers(), **equip_plans.handlers(), **wish.handlers(), **ProgressionService(store, economy, appearance).handlers(), **BattleService(store, economy).handlers(), **BattleShopService(store, economy).handlers(), "C2L_HeroAll": HeroService(store, economy).query_all,
                    **activity_runtime.handlers(), **social.handlers(), "C2L_Login": login.login, "C2L_ReConnect": login.reconnect,
                    "C2L_ServerTableConfig": login.server_config}, wait_for_database=store.wait_for_import))
    chat = X2TCPServer(Settings(tcp_host=endpoints.bind_host, tcp_port=endpoints.chat_port, read_timeout=120),
                       Dispatcher(SilentChatService().handlers()))
    mail_task = None
    welfare_task = None
    world_boss_task = None
    college_task = None
    activity_task = None
    social_task = None
    checkpoint_task = None
    health_task = None
    retention_task = None

    async def settle_monthcards(day_start):
        """Settle month cards and expire terminal wishes at server midnight."""
        for (player_id,) in store.db.execute('SELECT player_id FROM favor_wish_state WHERE day<>?', (day_start,)).fetchall():
            await store.wait_for_import()
            update = economy.terminal_wish.expire_day(player_id)
            if update and player_id in tcp.authenticated_player_ids():
                await tcp.push_to_player(player_id, update)
        for player_id in tcp.authenticated_player_ids():
            await store.wait_for_import()
            for update in economy.moon.expire_day(player_id):
                await tcp.push_to_player(player_id, update)
        for (player_id,) in store.db.execute(
                "SELECT DISTINCT player_id FROM gift_package_claims WHERE package_id=?",
                (gift_packages.MONTHCARD_ID,)).fetchall():
            await store.wait_for_import()
            if gift_packages.settle_daily(player_id) and player_id in tcp.authenticated_player_ids():
                await tcp.push_to_player(player_id, OutboundMessage("L2C_ItemUpdate",
                    {"code": 10, **economy.inventory_values(player_id)}))

    try:
        save_manager.prepare_indexes()
        health_task = asyncio.create_task(loop_health_watch(), name="local-loop-health")
        checkpoint_task = asyncio.create_task(store.checkpoint_watch(), name="local-db-checkpoint")
        from x2server.player.diagnostic_retention import DiagnosticRetention
        retention_task = asyncio.create_task(DiagnosticRetention(store).watch(), name="local-diagnostic-retention")
        await http.start()
        await tcp.start()
        await chat.start()
        social_task = asyncio.create_task(social.watch(tcp), name="local-friend-midnight-refresh")
        mail_task = asyncio.create_task(mail.watch(tcp), name="local-mail-push")
        activity_task = asyncio.create_task(activity_runtime.watch(tcp), name='local-activity-rotation')
        world_boss_task = asyncio.create_task(economy.world_boss.watch(),name="local-world-boss")
        college_task = asyncio.create_task(college_flows.upgrades.watch(tcp), name="local-college-upgrades")
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
        for task in (mail_task, welfare_task, world_boss_task, college_task, activity_task, social_task, retention_task, checkpoint_task, health_task):
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        await chat.stop()
        await tcp.stop()
        await http.stop()
        await asyncio.to_thread(save_api.close)
        accounts.close()
        save_manager.close()
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
