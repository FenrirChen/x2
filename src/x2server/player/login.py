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

# CurrencyType.ItemID -> BaseInfoProto field. The client reads shop balances
# through BaseInfoProto, while ItemAll is the separate item-bag ledger.
SHOP_CURRENCY_FIELDS = {
    1237904: "JewelChip", 1237905: "SeniorJewelChip",
    1237912: "ChallengeCoin", 1237913: "PowerOfLight",
    1237914: "VowOfCoin", 1237915: "WishCrystal",
    1237916: "StarSkillPoint", 1237917: "FriendCoin",
    1237918: "BossCoin", 1237920: "EquipSeniorChip",
    1237921: "RechargeExp", 1237922: "AICoin",
    1237923: "SkinCoupon", 1237924: "GuildScore",
    1237925: "JewelCoin", 1237926: "RMBCrystal",
    1237927: "FragmentMoney", 1237928: "FragmentMoney",
}


class LoginService:
    def __init__(self, identity: LocalIdentityService, store: PlayerStore, economy=None, equipment=None, wish=None, clock=None, appearance=None, mail=None, gift_packages=None, college=None) -> None:
        self.identity = identity
        self.store = store
        self.economy = economy
        self.equipment = equipment
        self.wish = wish
        self.appearance = appearance
        self.mail = mail
        self.gift_packages = gift_packages
        self.college = college
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
        for name in ("itemAll", "noticeAll", "cardPool", "heroSkinAll",
                     "rechargeNoticeAll", "equipAll", "taskDaily", "taskWeekly", "taskChallenge", "limitTaskChallenge"):
            result[name] = b""
        from x2server.messages.lobby import GROWTH_BASE, growth_base_values
        result["growthBase"] = GROWTH_BASE.encode(self.college.growth_base(player["id"])
                                                  if self.college else growth_base_values())
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
            if self.gift_packages:
                self.gift_packages.settle_daily(player["id"])
            player = self.store.get(player["id"])
            result["itemAll"] = ECONOMY_SCHEMAS["L2C_ItemAll"].encode(self.economy.inventory_values(player["id"]))
            for name, kind in (("taskDaily", 1), ("taskWeekly", 2)):
                result[name] = LOBBY_SCHEMAS["L2C_GameTask"].encode(self.economy.task_values(player["id"], kind))
        LOGGER.info("authenticated login response prepared player=%s login_count=%s",
                    player["id"], player["login_count"])
        push = self.snapshot_push(player, self.store if self.economy else None)
        pushes = (push,)
        if self.appearance:
            pushes += (OutboundMessage("L2C_QueryHeroDubbing",
                self.appearance._voice_values(player["id"])),)
        if self.mail:
            pushes += (self.mail.list_message(player["id"]),)
        return OutboundMessage("L2C_Login", result, pushes=pushes)

    @staticmethod
    def snapshot_push(player: dict[str, Any], store: PlayerStore | None = None) -> OutboundMessage:
        snapshot = player["snapshot"]
        owned_ids = [hero["id"] for hero in snapshot.get("heroes", []) if hero.get("state") == 2]
        selected = snapshot.get("show")
        show = selected if selected in owned_ids else owned_ids[0] if owned_ids else 0
        from x2server.messages.appearance import ICON_INFO
        currency_balances = {name: 0 for name in SHOP_CURRENCY_FIELDS.values()}
        if store is not None:
            for item_id, quantity in store.db.execute(
                    "SELECT item_id,quantity FROM inventory WHERE player_id=?", (player["id"],)):
                name = SHOP_CURRENCY_FIELDS.get(item_id)
                if name:
                    currency_balances[name] += quantity
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
            **currency_balances,
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
        daily_granted = self.gift_packages.settle_daily(player["id"]) if self.gift_packages else False
        # Same-process reconnect keeps the authenticated transport session supplied
        # by the client; a fresh login is required after identity-service restart.
        if not context.session.session_id:
            context.session.session_id = secrets.token_urlsafe(24)
        LOGGER.info("authenticated reconnect player=%s", player["id"])
        return OutboundMessage("L2C_ReConnect", {"code": 10, "id": player["id"],
            "serverTime": self.clock.now()},
            pushes=self.economy.pushes(player["id"]) if daily_granted and self.economy else ())

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
