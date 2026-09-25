"""Selected Phase 5 protobuf schemas needed by M1 round-trip tests.

Nested messages remain encoded as protobuf byte strings until their individual
schemas are required by a later milestone. This file defines no handlers.
"""

from x2server.protocol.protobuf import FieldKind, ProtoField, ProtoSchema
from x2server.messages.lobby import LOBBY_SCHEMAS
from x2server.messages.chat import CHAT_SCHEMAS
from x2server.messages.battle import BATTLE_SCHEMAS
from x2server.messages.economy import ECONOMY_SCHEMAS
from x2server.messages.progression import PROGRESSION_SCHEMAS
from x2server.messages.equipment import EQUIPMENT_SCHEMAS
from x2server.messages.wish import WISH_SCHEMAS

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
        C2L_PREPARE_MAIN_MISSION,
        L2C_PREPARE_MAIN_MISSION,
    )
}
CORE_SCHEMAS.update(LOBBY_SCHEMAS)
CORE_SCHEMAS.update(CHAT_SCHEMAS)
CORE_SCHEMAS.update(BATTLE_SCHEMAS)
CORE_SCHEMAS.update(ECONOMY_SCHEMAS)
CORE_SCHEMAS.update(PROGRESSION_SCHEMAS)
CORE_SCHEMAS.update(EQUIPMENT_SCHEMAS)
CORE_SCHEMAS.update(WISH_SCHEMAS)

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
    ProtoField(14, "HeroExp", FieldKind.INT32),
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
))
INT_PAIR = ProtoSchema("KeyValuePair_Int32_Int32", (
    ProtoField(1, "Key", FieldKind.INT32), ProtoField(2, "Value", FieldKind.INT32)))
HERO_GOD_EQUIP = ProtoSchema("HeroGodEquip", (
    ProtoField(1, "id", FieldKind.INT32),
    ProtoField(2, "level", FieldKind.INT32),
    ProtoField(3, "star", FieldKind.INT32),
    ProtoField(4, "jewel", FieldKind.MESSAGE, repeated=True),
    ProtoField(5, "godEquipAttr", FieldKind.MESSAGE),
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

