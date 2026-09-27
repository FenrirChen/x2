"""Evidence-led minimal login; additional snapshot synchronization is separate."""
import logging
import secrets
import time
from typing import Any

from x2server.bootstrap.local_identity import LocalIdentityService
from x2server.messages.core import C2L_LOGIN, BASE_INFO, MOBILITY, RECONNECT, STRING_PAIR
from x2server.messages.favor import FAVOR, FAVOR_MAP_ENTRY
from .favor import catalog, favor_state
from x2server.network.dispatcher import DispatchContext, OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.types import DecodedPacket
from .store import PlayerStore
from .hero import encode_hero_all
from .server_clock import ServerClock

LOGGER = logging.getLogger("x2.login")


class LoginService:
    def __init__(self, identity: LocalIdentityService, store: PlayerStore, economy=None, equipment=None, wish=None, clock=None, appearance=None) -> None:
        self.identity = identity
        self.store = store
        self.economy = economy
        self.equipment = equipment
        self.wish = wish
        self.appearance = appearance
        self.clock = clock or ServerClock()

    async def login(self, context: DispatchContext, packet: DecodedPacket) -> OutboundMessage:
        values = C2L_LOGIN.decode(packet.body)
        if not self.identity.validates_game_identity(values.get("id", 0), values.get("token", "")):
            raise ProtocolError("local login authentication failed")
        now = self.clock.now()
        player = self.store.login(self.identity.account, values["id"], now)
        context.session.session_id = secrets.token_urlsafe(24)
        context.session.player_id = player["id"]
        result: dict[str, Any] = {"code": 10, "id": player["id"], "loginCount": player["login_count"],
                  "startDataVersion": 0, "serverTime": now, "isCreateRole": player["login_count"] == 1,
                  "logicCode": 0, "sgroupId": "1"}
        # Explicit empty collections for the first controlled compatibility probe.
        for name in ("itemAll", "noticeAll", "cardPool", "heroSkinAll", "growthBase",
                     "rechargeNoticeAll", "equipAll", "taskDaily", "taskWeekly", "taskChallenge", "limitTaskChallenge"):
            result[name] = b""
        result["heroAll"] = encode_hero_all(player["snapshot"])
        if self.equipment:
            from x2server.messages.lobby import LOBBY_SCHEMAS
            result["equipAll"] = LOBBY_SCHEMAS["L2C_EquipAll"].encode(self.equipment.values(player["id"]))
        if self.wish:
            from x2server.messages.wish import WISH_SCHEMAS
            result["cardPool"] = WISH_SCHEMAS["L2C_CardPool"].encode(self.wish.values(player["id"]))
        if self.appearance:
            from x2server.messages.appearance import APPEARANCE_SCHEMAS
            result["heroSkinAll"] = APPEARANCE_SCHEMAS["L2C_HeroSkinAll"].encode(
                self.appearance.skin_values(player["id"]))
        if self.economy:
            from x2server.messages.economy import ECONOMY_SCHEMAS
            from x2server.messages.lobby import LOBBY_SCHEMAS
            self.economy.login_event(player["id"])
            player = self.store.get(player["id"])
            result["itemAll"] = ECONOMY_SCHEMAS["L2C_ItemAll"].encode(self.economy.inventory_values(player["id"]))
            for name, kind in (("taskDaily", 1), ("taskWeekly", 2)):
                result[name] = LOBBY_SCHEMAS["L2C_GameTask"].encode(self.economy.task_values(player["id"], kind))
        LOGGER.info("authenticated login response prepared player=%s login_count=%s",
                    player["id"], player["login_count"])
        fragment_money = self.store.db.execute(
            "SELECT quantity FROM inventory WHERE player_id=? AND item_id=1237927", (player["id"],)).fetchone() if self.economy else None
        push = self.snapshot_push(player, fragment_money[0] if fragment_money else 0)
        pushes = (push,)
        if self.appearance:
            pushes += (OutboundMessage("L2C_QueryHeroDubbing",
                self.appearance._voice_values(player["id"])),)
        return OutboundMessage("L2C_Login", result, pushes=pushes)

    @staticmethod
    def snapshot_push(player: dict[str, Any], fragment_money: int = 0) -> OutboundMessage:
        snapshot = player["snapshot"]
        owned_ids = [hero["id"] for hero in snapshot.get("heroes", []) if hero.get("state") == 2]
        selected = snapshot.get("show")
        show = selected if selected in owned_ids else owned_ids[0] if owned_ids else 0
        from x2server.messages.appearance import ICON_INFO
        base = BASE_INFO.encode({"Id": player["id"], "NickName": snapshot["nickname"],
            "Level": snapshot["level"], "Show": show,
            "Gold": snapshot.get("gold", 0), "Crystal": snapshot.get("crystal", 0),
            "Exp": snapshot.get("exp", 0),
            "EquipExp": snapshot.get("equip_exp", 0),
            "HeroExp": snapshot.get("hero_exp", 0),
            "DailyActivity": snapshot.get("daily_activity", 0),
            "WeekActivity": snapshot.get("week_activity", 0),
            "Birthday": snapshot.get("birthday", 0),
            "MainChapter": snapshot.get("main_chapter", 0),
            "MainSection": snapshot.get("main_section", 0),
            "FragmentMoney": fragment_money,
            "IconInfo": ICON_INFO.encode({"IconType": 1,
                "IconID": snapshot.get("head_icon", 1000001)})})
        initial = {r["HeroID"]: r["InitialLevel"] for r in catalog()["favorabilityhero"]}
        values = {"BaseInfo": base, "favor": [FAVOR_MAP_ENTRY.encode({"Key": hero["id"],
            "Value": FAVOR.encode(favor_state(hero, initial.get(hero["id"], 1)))})
            for hero in snapshot.get("heroes", []) if hero.get("state") == 2]}
        if "mobility" in snapshot:
            mobility = snapshot["mobility"]
            values["Mobility"] = MOBILITY.encode({
                "Power": mobility["power"],
                "ShopPowerFetchTime": mobility.get("shop_power_fetch_time", 0),
                "SectionPowerFetchTime": mobility.get("section_power_fetch_time", 0),
                "DBPNextRefreshTime": mobility.get("dbp_next_refresh_time", 0),
            })
        return OutboundMessage("PlayerDataProto", values, data_version=1)

    async def reconnect(self, context: DispatchContext, packet: DecodedPacket) -> OutboundMessage:
        values = RECONNECT.decode(packet.body)
        if not self.identity.validates_game_identity(values.get("id", 0), values.get("token", "")):
            return OutboundMessage("L2C_ReConnect", {"code": 0})
        try:
            player = self.store.get(values["id"])
        except KeyError:
            return OutboundMessage("L2C_ReConnect", {"code": 0})
        context.session.player_id = player["id"]
        # Same-process reconnect keeps the authenticated transport session supplied
        # by the client; a fresh login is required after identity-service restart.
        if not context.session.session_id:
            context.session.session_id = secrets.token_urlsafe(24)
        LOGGER.info("authenticated reconnect player=%s", player["id"])
        return OutboundMessage("L2C_ReConnect", {"code": 10, "id": player["id"],
            "serverTime": self.clock.now()})

    async def server_config(self, context: DispatchContext, packet: DecodedPacket) -> OutboundMessage:
        if context.session.player_id is None:
            raise ProtocolError("configuration requested before login")
        # An absent repeated field becomes null in this generated C# decoder.
        # The client default is 300 seconds; Revival recovers power 25% faster.
        from .economy import EconomyService
        recovery_seconds = (self.economy.POWER_RECOVER_SECONDS if self.economy is not None
                            else EconomyService.POWER_RECOVER_SECONDS)
        pairs = [STRING_PAIR.encode({"key": "PowerBuyNum", "val": "120"}),
                 STRING_PAIR.encode({"key": "PowerRecover", "val": str(recovery_seconds)})]
        LOGGER.info("server configuration response prepared with %s-second power recovery",
                    recovery_seconds)
        return OutboundMessage("L2C_ServerTableConfig", {"code": 10, "keyVal": pairs})
