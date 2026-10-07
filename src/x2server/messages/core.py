"""Selected Phase 5 protobuf schemas needed by M1 round-trip tests.

Nested messages remain encoded as protobuf byte strings until their individual
schemas are required by a later milestone. This file defines no handlers.
"""

from x2server.protocol.protobuf import FieldKind, ProtoField, ProtoSchema
from x2server.messages.lobby import LOBBY_SCHEMAS
from x2server.messages.achievements import ACHIEVEMENT_SCHEMAS
from x2server.messages.chat import CHAT_SCHEMAS
from x2server.messages.battle import BATTLE_SCHEMAS
from x2server.messages.economy import ECONOMY_SCHEMAS
from x2server.messages.progression import PROGRESSION_SCHEMAS
from x2server.messages.equipment import EQUIPMENT_SCHEMAS
from x2server.messages.wish import WISH_SCHEMAS
from x2server.messages.favor import FAVOR_SCHEMAS
from x2server.messages.appearance import APPEARANCE_SCHEMAS
from x2server.messages.mail import MAIL_SCHEMAS
from x2server.messages.terminal import TERMINAL_SCHEMAS
from x2server.messages.battle_shop import BATTLE_SHOP_SCHEMAS
from x2server.messages.star_chart import STAR_CHART_SCHEMAS
from x2server.messages.medals import MEDAL_SCHEMAS
from x2server.messages.world_boss import WORLD_BOSS_SCHEMAS
from x2server.messages.equip_plan import EQUIP_PLAN_SCHEMAS

C2L_LOGIN = ProtoSchema(
    "C2L_Login",
    (
        ProtoField(1, "id", FieldKind.INT64),
        ProtoField(2, "token", FieldKind.STRING),
        ProtoField(3, "deviceid", FieldKind.STRING),
        ProtoField(4, "connectType", FieldKind.ENUM),
        ProtoField(5, "submitInfo", FieldKind.MESSAGE),
        ProtoField(6, "submitInfo163", FieldKind.MESSAGE),
    ),
)

L2C_LOGIN = ProtoSchema(
    "L2C_Login",
    (
        ProtoField(1, "code", FieldKind.ENUM),
        ProtoField(2, "id", FieldKind.INT64),
        ProtoField(3, "loginCount", FieldKind.INT32),
        ProtoField(4, "fightDataProfile", FieldKind.MESSAGE),
        ProtoField(5, "startDataVersion", FieldKind.INT32),
        ProtoField(6, "serverTime", FieldKind.INT32),
        ProtoField(7, "isCreateRole", FieldKind.BOOL),
        ProtoField(8, "logicCode", FieldKind.INT32),
        ProtoField(9, "heroAll", FieldKind.MESSAGE),
        ProtoField(10, "itemAll", FieldKind.MESSAGE),
        ProtoField(11, "noticeAll", FieldKind.MESSAGE),
        ProtoField(12, "cardPool", FieldKind.MESSAGE),
        ProtoField(13, "heroSkinAll", FieldKind.MESSAGE),
        ProtoField(14, "growthBase", FieldKind.MESSAGE),
        ProtoField(15, "rechargeNoticeAll", FieldKind.MESSAGE),
        ProtoField(16, "equipAll", FieldKind.MESSAGE),
        ProtoField(17, "taskDaily", FieldKind.MESSAGE),
        ProtoField(18, "taskWeekly", FieldKind.MESSAGE),
        ProtoField(19, "taskChallenge", FieldKind.MESSAGE),
        ProtoField(20, "limitTaskChallenge", FieldKind.MESSAGE),
        ProtoField(21, "sgroupId", FieldKind.STRING),
    ),
)

C2L_GUIDE_STEP = ProtoSchema(
    "C2L_GuideStep",
    (
        ProtoField(1, "stepId", FieldKind.INT32),
        ProtoField(2, "stepState", FieldKind.INT32),
    ),
)

L2C_GUIDE_STEP = ProtoSchema(
    "L2C_GuideStep",
    (ProtoField(1, "code", FieldKind.ENUM),),
)

C2L_FILL_BIRTHDAY = ProtoSchema("C2L_FillBirthday", (
    ProtoField(1, "month", FieldKind.INT32),
    ProtoField(2, "day", FieldKind.INT32),
))
L2C_FILL_BIRTHDAY = ProtoSchema("L2C_FillBirthday", (
    ProtoField(1, "code", FieldKind.ENUM),
))

C2L_PREPARE_MAIN_MISSION = ProtoSchema(
    "C2L_PrepareMainMission",
    (
        ProtoField(1, "chapter", FieldKind.INT32),
        ProtoField(2, "level", FieldKind.INT32),
    ),
)

L2C_PREPARE_MAIN_MISSION = ProtoSchema(
    "L2C_PrepareMainMission",
    (ProtoField(1, "result", FieldKind.ENUM),),
)

CORE_SCHEMAS = {
    schema.name: schema
    for schema in (
        C2L_LOGIN,
        L2C_LOGIN,
        C2L_GUIDE_STEP,
        L2C_GUIDE_STEP,
        C2L_FILL_BIRTHDAY,
        L2C_FILL_BIRTHDAY,
        C2L_PREPARE_MAIN_MISSION,
        L2C_PREPARE_MAIN_MISSION,
    )
}
CORE_SCHEMAS.update(LOBBY_SCHEMAS)
CORE_SCHEMAS.update(ACHIEVEMENT_SCHEMAS)
CORE_SCHEMAS.update(MEDAL_SCHEMAS)
CORE_SCHEMAS.update(WORLD_BOSS_SCHEMAS)
CORE_SCHEMAS.update(CHAT_SCHEMAS)
CORE_SCHEMAS.update(BATTLE_SCHEMAS)
CORE_SCHEMAS.update(ECONOMY_SCHEMAS)
CORE_SCHEMAS.update(PROGRESSION_SCHEMAS)
CORE_SCHEMAS.update(EQUIPMENT_SCHEMAS)
CORE_SCHEMAS.update(WISH_SCHEMAS)
CORE_SCHEMAS.update(FAVOR_SCHEMAS)
CORE_SCHEMAS.update(APPEARANCE_SCHEMAS)
CORE_SCHEMAS.update(MAIL_SCHEMAS)
CORE_SCHEMAS.update(TERMINAL_SCHEMAS)
CORE_SCHEMAS.update(BATTLE_SHOP_SCHEMAS)
CORE_SCHEMAS.update(STAR_CHART_SCHEMAS)
# 兽主套装预设 (EquipPlan, 423-430 四对). PlayerDataProto 的第 9 号成员由本表之外的
# EquipPlanProto 形状下发，见 messages/equip_plan.py。没有这些 schema 和下面的
# handler，客户端每次保存/置顶/删除/应用预设都收不到回包，功能等于没有。
CORE_SCHEMAS.update(EQUIP_PLAN_SCHEMAS)

# CONFIRMED: MessageReflector registers PlayerDataProto as 1000, independently
# of its generated get_PID() returning 0. BaseInfo Serialize RVA 0x30A1348.
BASE_INFO = ProtoSchema("BaseInfoProto", (
    ProtoField(1, "Id", FieldKind.INT64),
    ProtoField(2, "NickName", FieldKind.STRING),
    ProtoField(3, "Level", FieldKind.INT32),
    ProtoField(4, "Crystal", FieldKind.INT32),
    ProtoField(5, "Gold", FieldKind.INT32),
    ProtoField(6, "Exp", FieldKind.INT32),
    ProtoField(7, "EquipExp", FieldKind.INT32),
    ProtoField(8, "Show", FieldKind.INT32),
    ProtoField(9, "IconInfo", FieldKind.MESSAGE),
    ProtoField(10, "JewelChip", FieldKind.INT32),
    ProtoField(11, "SeniorJewelChip", FieldKind.INT32),
    ProtoField(22, "ChallengeCoin", FieldKind.INT32),
    ProtoField(23, "PowerOfLight", FieldKind.INT32),
    ProtoField(28, "WishCrystal", FieldKind.INT32),
    ProtoField(29, "StarSkillPoint", FieldKind.INT32),
    ProtoField(30, "FriendCoin", FieldKind.INT32),
    ProtoField(31, "BossCoin", FieldKind.INT32),
    ProtoField(35, "VowOfCoin", FieldKind.INT32),
    ProtoField(37, "EquipSeniorChip", FieldKind.INT32),
    ProtoField(42, "RechargeExp", FieldKind.INT32),
    ProtoField(43, "AICoin", FieldKind.INT32),
    ProtoField(44, "AIPointAutoAdd", FieldKind.INT32),
    ProtoField(47, "SkinCoupon", FieldKind.INT32),
    ProtoField(56, "GuildScore", FieldKind.INT32),
    ProtoField(59, "RMBCrystal", FieldKind.INT32),
    ProtoField(60, "JewelCoin", FieldKind.INT32),
    ProtoField(66, "FragmentMoney", FieldKind.INT32),
    ProtoField(32, "Birthday", FieldKind.INT32),
    ProtoField(14, "HeroExp", FieldKind.INT32),
    ProtoField(15, "QuestIDs", FieldKind.MESSAGE, repeated=True),
    ProtoField(20, "DailyActivity", FieldKind.INT32),
    ProtoField(21, "WeekActivity", FieldKind.INT32),
    ProtoField(33, "MainChapter", FieldKind.INT32),
    ProtoField(34, "MainSection", FieldKind.INT32),
))
MOBILITY = ProtoSchema("MobilityProto", (
    ProtoField(1, "Power", FieldKind.INT32),
    ProtoField(2, "ShopPowerFetchTime", FieldKind.INT32),
    ProtoField(3, "SectionPowerFetchTime", FieldKind.INT32),
    ProtoField(4, "DBPNextRefreshTime", FieldKind.INT32),
))
PLAYER_DATA = ProtoSchema("PlayerDataProto", (
    ProtoField(1, "BaseInfo", FieldKind.MESSAGE),
    ProtoField(2, "Mobility", FieldKind.MESSAGE),
    ProtoField(3, "Daily", FieldKind.MESSAGE),
    ProtoField(5, "WorldBossSearch", FieldKind.MESSAGE),
    ProtoField(7, "MedalSystem", FieldKind.MESSAGE),
    ProtoField(8, "StarMap", FieldKind.MESSAGE),
    # Field 9 = EquipPlan (EquipPlanProto, 兽主套装预设). 客户端 EquipModule 只在登录
    # 收到的 PlayerData 里初始化预设列表，此后每次保存/置顶/删除/应用都靠服务端再推
    # 一份 PlayerData 来刷新；这个成员缺席时预设页永远是空的，保存也拿不到回包。形状见
    # messages/equip_plan.py，值由 player/equip_plans.snapshot_value 生成。
    ProtoField(9, "EquipPlan", FieldKind.MESSAGE),
    ProtoField(11, "RelicPack", FieldKind.MESSAGE, repeated=True),
    ProtoField(15, "favor", FieldKind.MESSAGE, repeated=True),
))
HERO_DATA = ProtoSchema("HeroData", (
    ProtoField(1, "id", FieldKind.INT32),
    ProtoField(2, "state", FieldKind.INT32),
    ProtoField(3, "level", FieldKind.INT32),
    ProtoField(4, "star", FieldKind.INT32),
    ProtoField(5, "godEquip", FieldKind.MESSAGE),
    ProtoField(6, "equips", FieldKind.MESSAGE, repeated=True),
    ProtoField(7, "exp", FieldKind.INT32),
    ProtoField(8, "heroSkills", FieldKind.MESSAGE, repeated=True),
    ProtoField(9, "Enjoy", FieldKind.INT32),
    ProtoField(10, "Status", FieldKind.INT32),
    ProtoField(11, "name", FieldKind.STRING),
    ProtoField(12, "fetters", FieldKind.MESSAGE, repeated=True),
    ProtoField(13, "getTime", FieldKind.INT64),
    ProtoField(14, "archives", FieldKind.MESSAGE, repeated=True),
    ProtoField(15, "tiredStatus", FieldKind.INT32),
    ProtoField(16, "seasonEquips", FieldKind.MESSAGE, repeated=True),
))
INT_PAIR = ProtoSchema("KeyValuePair_Int32_Int32", (
    ProtoField(1, "Key", FieldKind.INT32), ProtoField(2, "Value", FieldKind.INT32)))
GOD_SLOT_LOCK_INFO = ProtoSchema("GodSlotLockInfo", (
    ProtoField(1, "slot", FieldKind.INT32), ProtoField(2, "state", FieldKind.INT32)))
HERO_GOD_EQUIP = ProtoSchema("HeroGodEquip", (
    ProtoField(1, "id", FieldKind.INT32),
    ProtoField(2, "level", FieldKind.INT32),
    ProtoField(3, "star", FieldKind.INT32),
    ProtoField(4, "jewel", FieldKind.MESSAGE, repeated=True),
    ProtoField(5, "godEquipAttr", FieldKind.MESSAGE),
    ProtoField(8, "godSlotLockInfo", FieldKind.MESSAGE, repeated=True),
))
HERO_ALL = ProtoSchema("L2C_HeroAll", (ProtoField(1, "heros", FieldKind.MESSAGE, repeated=True),))
STRING_PAIR = ProtoSchema("KeyValuePair_String_String", (
    ProtoField(1, "key", FieldKind.STRING), ProtoField(2, "val", FieldKind.STRING)))
CORE_SCHEMAS[PLAYER_DATA.name] = PLAYER_DATA
CORE_SCHEMAS[HERO_ALL.name] = HERO_ALL
CORE_SCHEMAS["C2L_HeroAll"] = ProtoSchema("C2L_HeroAll", ())
RECONNECT = ProtoSchema("C2L_ReConnect", (
    ProtoField(1, "id", FieldKind.INT64), ProtoField(2, "token", FieldKind.STRING),
    ProtoField(3, "deviceid", FieldKind.STRING), ProtoField(4, "submitInfo", FieldKind.MESSAGE),
    ProtoField(5, "submitInfo163", FieldKind.MESSAGE)))
for schema in (
    RECONNECT,
    ProtoSchema("L2C_ReConnect", (ProtoField(1, "code", FieldKind.ENUM),
        ProtoField(2, "id", FieldKind.INT64), ProtoField(3, "fightDataProfile", FieldKind.MESSAGE),
        ProtoField(4, "serverTime", FieldKind.INT32))),
    ProtoSchema("C2L_ServerTableConfig", ()),
    ProtoSchema("L2C_ServerTableConfig", (ProtoField(1, "code", FieldKind.ENUM),
        ProtoField(2, "keyVal", FieldKind.MESSAGE, repeated=True))),
):
    CORE_SCHEMAS[schema.name] = schema

