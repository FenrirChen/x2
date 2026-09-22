"""Selected Phase 5 protobuf schemas needed by M1 round-trip tests.

Nested messages remain encoded as protobuf byte strings until their individual
schemas are required by a later milestone. This file defines no handlers.
"""

from x2server.protocol.protobuf import FieldKind, ProtoField, ProtoSchema

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

