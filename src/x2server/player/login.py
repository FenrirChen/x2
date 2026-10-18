"""Evidence-led minimal login; additional snapshot synchronization is separate."""
import logging
import secrets
import time
import json
from functools import lru_cache
from importlib.resources import files
from typing import Any

from x2server.bootstrap.local_identity import LocalIdentityService
from x2server.messages.core import (C2L_LOGIN, BASE_INFO, MOBILITY, MODULE_STATUS, RECONNECT,
                                    STRING_PAIR, INT_PAIR, LOGIN_DAILY)
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
    # Item.EffData -> GameAPI.GetCurrencyNum -> BaseInfoProto. Multiple
    # item IDs can name the same official currency (e.g. AoxilisiCoin).
    1237976: "AoxilisiCoin", 1237977: "MemoryPoint",
    1237978: "AoxilisiCoin", 1237979: "MainActivityCoin",
    1237981: "MainActivityCoin", 1237982: "AoxilisiCoin",
    1237984: "NewYearCoin", 1237985: "ShuangHanCoin1",
    1237986: "ShuangHanCoin2", 1237987: "ShuangHanCoin3",
    1237988: "ShuangHanCoin4", 1237989: "ActivityCoin",
    1237980: "BattlepassShopCoin", 1237998: "BattlepassShopCoin",
    1285001: "BattlepassShopCoin",
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
        if self.economy:
            self.economy.extra_activity.repair_course_equipment(player['id'])
        if self.mail:
            self.identity.ensure_welcome_mail(player["id"], now)
            self.identity.ensure_daily_login_mail(player["id"], now)
            self.identity.ensure_hero_choice_mail(player["id"], now)
            self.identity.ensure_ultimate_causality_mail(player["id"], now)
            self.identity.ensure_revival_supply_mail(player["id"], now)
            self.identity.ensure_causality_oct13_mail(player["id"], now)
            self.identity.ensure_journey_supply_mail(player["id"], now)
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
        result["heroAll"] = encode_hero_all(player["snapshot"], season=self.economy.season if self.economy else None, player_id=player["id"])
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
        stamp = int(time.time()) if now is None else int(now)
        currency_balances = {name: 0 for name in SHOP_CURRENCY_FIELDS.values()}
        extra_base: dict[str, Any] = {}
        if store is not None:
            from .friend_currency import repair
            repair(store, player["id"])
            for item_id, quantity in store.db.execute(
                    "SELECT item_id,quantity FROM inventory WHERE player_id=?", (player["id"],)):
                name = SHOP_CURRENCY_FIELDS.get(item_id)
                if name:
                    currency_balances[name] += quantity
            # 活动中心写在 BaseInfoProto 上的计数 (字段 53/54/55 献祭福利, 61 自选三星)。
            # 页签靠 55 非 0 才可点, 53/54 画签到进度。
            from .extra_activity import exchange_count, novice_sign_values
            extra_base = novice_sign_values(store.db, player["id"], stamp, player.get("created_at"))
            extra_base["ForeverExchangeCount"] = exchange_count(store.db, player["id"])
        extra_base['BattlePassWeeklyActive'] = 0
        if store is not None and len(store.db.execute("SELECT name FROM sqlite_master WHERE name IN ('season_state','season_calendar')").fetchall()) == 2:
            from .task_calendar import task_period
            row = store.db.execute('SELECT s.instance_id,s.state_json FROM season_state s JOIN season_calendar c ON s.instance_id=c.instance_id '
                'WHERE s.player_id=? AND c.closed=0 AND c.start_sec<=? AND c.end_sec>? ORDER BY c.start_sec DESC LIMIT 1',
                (player['id'], stamp, stamp)).fetchone()
            if row:
                state = json.loads(row[1])
                if state.get('week') == task_period(2, stamp)[0]:
                    if state.get('weekly_active_period') == state['week']:
                        extra_base['BattlePassWeeklyActive'] = state.get('weekly_active', 0)
                    else:
                        prefix = f"season:{row[0]}:task:{state['week']}:"
                        extra_base['BattlePassWeeklyActive'] = sum(json.loads(r[0]).get('1237999', 0) for r in store.db.execute(
                            'SELECT rewards FROM economy_grants WHERE player_id=? AND substr(source,1,?)=?', (player['id'], len(prefix), prefix)))
        from .naming import nickname_count
        base = BASE_INFO.encode({"Id": player["id"], "NickName": snapshot["nickname"],
            "NickCount": nickname_count(snapshot),
            "Level": snapshot["level"], "Show": show,
            "Gold": snapshot.get("gold", 0), "Crystal": snapshot.get("crystal", 0),
            "Exp": snapshot.get("exp", 0),
            "EquipExp": snapshot.get("equip_exp", 0),
            "HeroExp": snapshot.get("hero_exp", 0),
            "DailyActivity": snapshot.get("daily_activity", 0),
            "WeekActivity": snapshot.get("week_activity", 0),
            "Birthday": snapshot.get("birthday", 0),
            "SignInStartTime": int(player.get("created_at") or 0),
            "MainChapter": snapshot.get("main_chapter", 0),
            "MainSection": snapshot.get("main_section", 0),
            "AIPointAutoAdd": int(snapshot.get("star_chart", {}).get("auto_add", False)),
            "QuestIDs": [INT_PAIR.encode({"Key": int(k), "Value": int(v)})
                for k, v in sorted(snapshot.get("guide_groups", {}).items(), key=lambda p: int(p[0]))],
            **currency_balances,
            **extra_base,
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
        boss_fields, boss_daily = boss_snapshot_fields(store, player["id"],
            int(time.time()) if now is None else now)
        values.update(boss_fields)
        if store is not None:
            from .endless import weekly_values,WEEKLY
            values['Weekly']=WEEKLY.encode(weekly_values(store,player['id'],int(time.time()) if now is None else now))
        if boss_daily:
            values['Daily'] = values.get('Daily', b'') + boss_daily
        if store is not None and store.db.execute("SELECT 1 FROM sqlite_master WHERE name='college_state'").fetchone():
            college_row = store.db.execute('SELECT state_json FROM college_state WHERE player_id=?', (player['id'],)).fetchone()
            if college_row:
                from .college_pray import daily_fields
                values['Daily'] = values.get('Daily', b'') + daily_fields(json.loads(college_row[0]), stamp)
        # 降临纪念 (累计登录): Daily.TotalLoginDays (字段 8)。客户端
        # CumulateLoginModule_RefreshRedPoint 从它判天数够没够, 缺了页面天数恒 0
        # (「时间出错」)。天数按创号时刻算, 与 player/total_login.py 的领取门槛同源。
        from .total_login import login_days
        values["Daily"] = (values.get("Daily") or b"") + LOGIN_DAILY.encode(
            {"TotalLoginDays": login_days(player.get("created_at"), stamp)})
        # REVIVAL_COMPAT 2026-10-02: CollegeModule.IsCollegeEnable (0x1AF9FF8)
        # enables the base entry only when PlayerData.ModuleStatus.GrowthBaseStatus
        # == 1; the official server value is unrecoverable, keep the module open.
        values["ModuleStatus"] = MODULE_STATUS.encode({"GrowthBaseStatus": 1, "ClubStatus": 1})
        if store is not None and store.db.execute("SELECT 1 FROM sqlite_master WHERE name='activity_state'").fetchone():
            from .social import snapshot_value as friend_value
            values["FriendData"] = friend_value(store, player["id"], stamp)
        if store is not None:
            relic_ids = relic_item_ids()
            owned_relics = [item_id for item_id, quantity in store.db.execute(
                "SELECT item_id,quantity FROM inventory WHERE player_id=? ORDER BY item_id",
                (player["id"],)) if quantity > 0 and item_id in relic_ids]
            # Collection unlocks are usable outside the season too.
            if store.db.execute("SELECT 1 FROM sqlite_master WHERE name='season_state'").fetchone():
                for row in store.db.execute('SELECT state_json FROM season_state WHERE player_id=?', (player['id'],)):
                    owned_relics.extend(i for i in json.loads(row[0]).get('relics', []) if i in relic_ids)
                owned_relics = sorted(set(owned_relics))
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
        causality_created = self.identity.ensure_ultimate_causality_mail(player["id"], now) if self.mail else False
        supply_created = self.identity.ensure_revival_supply_mail(player["id"], now) if self.mail else False
        extra_created = self.identity.ensure_causality_oct13_mail(player["id"], now) if self.mail else False
        journey_created = self.identity.ensure_journey_supply_mail(player["id"], now) if self.mail else False
        daily_granted = self.gift_packages.settle_daily(player["id"]) if self.gift_packages else False
        # Same-process reconnect keeps the authenticated transport session supplied
        # by the client; a fresh login is required after identity-service restart.
        if not context.session.session_id:
            context.session.session_id = secrets.token_urlsafe(24)
        LOGGER.info("authenticated reconnect player=%s", player["id"])
        pushes = self.economy.pushes(player["id"]) if daily_granted and self.economy else ()
        if welcome_created or daily_created or choice_created or causality_created or supply_created or extra_created or journey_created:
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
                 STRING_PAIR.encode({"key": "PowerRecover", "val": str(recovery_seconds)}),
                 # Native battle admission defaults to 25*32=800, while the
                 # bag counter displays 1280. Supply the matching capacity.
                 STRING_PAIR.encode({"key": "EquipPageLimit", "val": "40"}),
                 STRING_PAIR.encode({"key": "EquipCellLimit", "val": "32"}),
                 STRING_PAIR.encode({"key": "Energy", "val": "600"})]
        pairs += [STRING_PAIR.encode({'key': 'WishTaskList', 'val': '3'}),
                  STRING_PAIR.encode({'key': 'WishTaskCanTake', 'val': '3'}),
                  STRING_PAIR.encode({'key': 'HeroWishTaskLimit', 'val': '3'})]
        from .moon import PARAMETERS as MOON_PARAMETERS
        pairs += [STRING_PAIR.encode({'key': key, 'val': val}) for key, val in MOON_PARAMETERS.items()]
        from .social import PARAMETERS
        pairs += [STRING_PAIR.encode({'key': key, 'val': val}) for key,val in PARAMETERS.items()]
        LOGGER.info("server configuration response prepared with %s-second power recovery",
                    recovery_seconds)
        return OutboundMessage("L2C_ServerTableConfig", {"code": 10, "keyVal": pairs})
