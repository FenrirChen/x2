"""Evidence-led minimal login; additional snapshot synchronization is separate."""
import logging
import secrets
import time
import json
from functools import lru_cache
from importlib.resources import files
from typing import Any

from x2server.bootstrap.local_identity import LocalIdentityService
from x2server.messages.core import C2L_LOGIN, BASE_INFO, MOBILITY, RECONNECT, STRING_PAIR, INT_PAIR
from x2server.messages.favor import FAVOR, FAVOR_MAP_ENTRY
from .favor import catalog, favor_state
from x2server.network.dispatcher import DispatchContext, OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.types import DecodedPacket
from .store import PlayerStore
from .hero import encode_hero_all
from .server_clock import ServerClock

LOGGER = logging.getLogger("x2.login")


@lru_cache(maxsize=1)
def relic_item_ids():
    rows = json.loads(files("x2server").joinpath(
        "data/reward_items.json").read_text(encoding="utf-8"))
    return frozenset(row["ItemID"] for row in rows
                     if row.get("ItemType", {}).get("value") == 4)

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
        if economy is not None:
            economy.world_boss.identity = identity

    async def login(self, context: DispatchContext, packet: DecodedPacket) -> OutboundMessage:
        values = C2L_LOGIN.decode(packet.body)
        if not self.identity.validates_game_identity(values.get("id", 0), values.get("token", "")):
            raise ProtocolError("local login authentication failed")
        now = self.clock.now()
        player = self.store.login(self.identity.account_for_player(values["id"]), values["id"], now)
        if self.mail:
            self.identity.ensure_welcome_mail(player["id"], now)
            self.identity.ensure_daily_login_mail(player["id"], now)
            self.identity.ensure_hero_choice_mail(player["id"], now)
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
            result["taskChallenge"] = LOBBY_SCHEMAS["L2C_GameTask"].encode(
                self.economy.challenge_values(player["id"]))
        LOGGER.info("authenticated login response prepared player=%s login_count=%s",
                    player["id"], player["login_count"])
        push = self.snapshot_push(player, self.store if self.economy else None, now)
        from x2server.messages.star_chart import STAR_MAP, STAR_PAIR
        star = STAR_MAP.decode(push.values['StarMap'])
        LOGGER.info('login star map player=%s abilities=%s skill_levels=%s AI_points=%s',
            player['id'], [STAR_PAIR.decode(r) for r in star.get('StarAbility', [])],
            [STAR_PAIR.decode(r) for r in star.get('StarSkill', [])], star.get('AIPoint', 0))
        pushes = (push,)
        if self.appearance:
            pushes += (OutboundMessage("L2C_QueryHeroDubbing",
                self.appearance._voice_values(player["id"])),)
        if self.mail:
            pushes += (self.mail.list_message(player["id"]),)
        return OutboundMessage("L2C_Login", result, pushes=pushes)

    @staticmethod
    def snapshot_push(player: dict[str, Any], store: PlayerStore | None = None, now: int | None = None) -> OutboundMessage:
        snapshot = player["snapshot"]
        owned_ids = [hero["id"] for hero in snapshot.get("heroes", []) if hero.get("state") == 2]
        selected = snapshot.get("show")
        show = selected if selected in owned_ids else owned_ids[0] if owned_ids else 0
        from x2server.player.appearance import head_icon_info
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
            "AIPointAutoAdd": int(snapshot.get("star_chart", {}).get("auto_add", False)),
            "QuestIDs": [INT_PAIR.encode({"Key": int(k), "Value": int(v)})
                for k, v in sorted(snapshot.get("guide_groups", {}).items(), key=lambda p: int(p[0]))],
            **currency_balances,
            "IconInfo": head_icon_info(snapshot, {
                int(hero["id"]): hero.get("favor", {})
                for hero in snapshot.get("heroes", [])})})
        initial = {r["HeroID"]: r["InitialLevel"] for r in catalog()["favorabilityhero"]}
        from .star_chart import snapshot_fields
        values = {"BaseInfo": base, "favor": [FAVOR_MAP_ENTRY.encode({"Key": hero["id"],
            "Value": FAVOR.encode(favor_state(hero, initial.get(hero["id"], 1)))})
            for hero in snapshot.get("heroes", []) if hero.get("state") == 2]}
        from .medals import snapshot_value
        values['MedalSystem'] = snapshot_value(store, player['id'], snapshot)
        values.update(snapshot_fields(store, player["id"], snapshot,
                                     int(time.time()) if now is None else now))
        from .world_boss import snapshot_fields as boss_snapshot_fields
        boss_fields, boss_daily = boss_snapshot_fields(store, player['id'],
            int(time.time()) if now is None else now)
        values.update(boss_fields)
        if boss_daily:
            values['Daily'] = values.get('Daily', b'') + boss_daily
        if store is not None:
            relic_ids = relic_item_ids()
            owned_relics = [item_id for item_id, quantity in store.db.execute(
                "SELECT item_id,quantity FROM inventory WHERE player_id=? ORDER BY item_id",
                (player["id"],)) if quantity > 0 and item_id in relic_ids]
            values["RelicPack"] = [INT_PAIR.encode({"Key": index, "Value": item_id})
                                   for index, item_id in enumerate(owned_relics)]
            # f9 EquipPlan (兽主套装预设). 客户端 EquipModule 只在 PlayerData 里认识
            # 预设列表，所以每次带 store 的推送都要带上它（含删除墓碑），否则保存/置顶/
            # 删除之后页面不会刷新。读取自快照自己的 'equip_plans'，与设备无关。
            from .equip_plans import snapshot_value as equip_plan_value
            values["EquipPlan"] = equip_plan_value(snapshot)
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
        now = self.clock.now()
        welcome_created = self.identity.ensure_welcome_mail(player["id"], now) if self.mail else False
        daily_created = self.identity.ensure_daily_login_mail(player["id"], now) if self.mail else False
        choice_created = self.identity.ensure_hero_choice_mail(player["id"], now) if self.mail else False
        daily_granted = self.gift_packages.settle_daily(player["id"]) if self.gift_packages else False
        # Same-process reconnect keeps the authenticated transport session supplied
        # by the client; a fresh login is required after identity-service restart.
        if not context.session.session_id:
            context.session.session_id = secrets.token_urlsafe(24)
        LOGGER.info("authenticated reconnect player=%s", player["id"])
        pushes = self.economy.pushes(player["id"]) if daily_granted and self.economy else ()
        if welcome_created or daily_created or choice_created:
            pushes += (self.mail.list_message(player["id"]),)
        return OutboundMessage("L2C_ReConnect", {"code": 10, "id": player["id"],
            "serverTime": now}, pushes=pushes)

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
