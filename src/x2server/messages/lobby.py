"""Read-only lobby queries recovered from 2.4 ERequestTypes and Serialize methods."""
from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema

LOBBY_IDS = (
    ("QueryTelInfo", 782, 783), ("SeasonIcon", 999, 1001),
    ("QueryItemLimitTime", 715, 716), ("QueryDivination", 576, 578),
    ("QueryNotic", 669, 670), ("NoticPushInfo", 805, 806),
    ("QueryReturnInfo", 776, 777), ("SystemInfo", 432, 433),
    ("GameTask", 351, 354), ("EntryidStatus", 515, 516), ("EquipAll", 539, 538),
    ("QueryMission", 574, 575), ("QueryCollectionAward", 586, 587),
    ("QueryActivity", 615, 616), ("QueryWorldBossOpenTime", 679, 680),
    ("QueryActivityDrawInfo", 697, 699), ("QueryStarPrivilegeReward", 719, 720),
    ("QueryStarPrivilegeInfo", 723, 724), ("QueryIllustrationData", 862, 863),
    ("AccountBuffAutoStop", 885, 886), ("ReceiveGiftRew", 919, 920),
    ("MoonEquip", 964, 965), ("QuerySimpleActivity", 986, 987),
    ("QuerySharedMessage", 653, 654), ("AccountBuffData", 865, 866),
    ("ButtonClick", 376, 377),
)
LOBBY_SCHEMAS = {
    "C2L_" + name: ProtoSchema("C2L_" + name,
        (F(1, "version", K.INT32),) if name == "QueryNotic" else ())
    for name, _, _ in LOBBY_IDS
}
for name, fields in {
    "GameTask": (F(1, "type", K.ENUM), F(2, "extraType", K.ENUM), F(3, "chapterId", K.INT32)),
    "ReceiveGiftRew": (F(1, "type", K.INT32),),
    "MoonEquip": (F(1, "moonCampId", K.INT32),),
    "QuerySimpleActivity": (F(1, "id", K.INT32),),
    "AccountBuffData": (F(1, "buffId", K.INT32, repeated=True),),
    "ButtonClick": (F(1, "buttonId", K.INT32),),
}.items():
    LOBBY_SCHEMAS["C2L_" + name] = ProtoSchema("C2L_" + name, fields)
for name, fields in {
    "QueryTelInfo": (F(1, "code", K.ENUM), F(2, "telNumber", K.STRING), F(3, "lastBindTime", K.INT32)),
    "SeasonIcon": (F(1, "code", K.ENUM), F(2, "putOnHeadIcon", K.INT32), F(3, "putOnSceneIcon", K.INT32),
                   F(4, "headIconList", K.MESSAGE, repeated=True), F(5, "sceneIconList", K.MESSAGE, repeated=True)),
    "QueryItemLimitTime": (F(1, "code", K.ENUM), F(2, "itemLimitTimes", K.MESSAGE, repeated=True)),
    "QueryDivination": (F(1, "id", K.INT32), F(2, "blessing", K.MESSAGE), F(3, "checkIn", K.INT32),
                        F(4, "lastDivinationTime", K.INT32), F(5, "validDate", K.INT32)),
    "QueryNotic": (F(1, "code", K.ENUM), F(2, "dataList", K.MESSAGE, repeated=True), F(3, "version", K.INT32)),
    "NoticPushInfo": (F(1, "code", K.ENUM), F(2, "pushInfos", K.MESSAGE, repeated=True)),
    "QueryReturnInfo": (F(1, "code", K.ENUM), F(2, "hasReturn", K.BOOL), F(3, "startTimeSec", K.INT32),
                        F(4, "hasReciveReward", K.BOOL), F(5, "hasDraw", K.BOOL), F(6, "taskPoint", K.INT32),
                        F(7, "confiId", K.INT32), F(8, "endTimeSec", K.INT32), F(9, "loginDays", K.INT32)),
    "SystemInfo": (F(1, "code", K.ENUM), F(2, "serverTime", K.INT32)),
    "ButtonClick": (F(1, "code", K.ENUM),),
    "QuerySharedMessage": (F(1, "code", K.ENUM), F(2, "sharedMessageList", K.MESSAGE, repeated=True)),
    "AccountBuffData": (F(1, "code", K.ENUM), F(2, "buffData", K.MESSAGE, repeated=True), F(3, "buffId", K.INT32, repeated=True)),
    "GameTask": (F(1, "code", K.ENUM), F(2, "type", K.ENUM), F(3, "taskList", K.MESSAGE, repeated=True),
                 F(4, "boxList", K.MESSAGE, repeated=True), F(5, "chapterId", K.INT32),
                 F(6, "chapterTaskPoint", K.INT32), F(7, "chapterTaskTotalPoint", K.INT32), F(8, "activityId", K.INT32)),
    "EntryidStatus": (F(1, "code", K.ENUM), F(2, "entryidStatus", K.MESSAGE, repeated=True)),
    "EquipAll": (F(1, "equip", K.MESSAGE, repeated=True),),
    "QueryMission": (F(1, "OtherChapter", K.MESSAGE, repeated=True), F(2, "mainMission", K.INT32, repeated=True), F(3, "story", K.INT32, repeated=True)),
    "QueryCollectionAward": (F(1, "awardID", K.INT32, repeated=True),),
    "QueryActivity": (F(1, "code", K.ENUM), F(2, "activityData", K.MESSAGE, repeated=True)),
    "QueryWorldBossOpenTime": (F(1, "code", K.ENUM),),
    "QueryActivityDrawInfo": (F(1, "code", K.ENUM), F(2, "drawInfos", K.MESSAGE, repeated=True)),
    "QueryStarPrivilegeReward": (F(1, "code", K.ENUM), F(2, "privilegeRewardList", K.MESSAGE, repeated=True)),
    "QueryStarPrivilegeInfo": (F(1, "code", K.ENUM), F(2, "id", K.INT32), F(3, "buyTime", K.INT32)),
    "QueryIllustrationData": (F(1, "code", K.ENUM), F(2, "jewelBases", K.INT32, repeated=True), F(3, "equipData", K.MESSAGE, repeated=True)),
    "AccountBuffAutoStop": (F(1, "code", K.ENUM), F(2, "buffData", K.MESSAGE, repeated=True)),
    "ReceiveGiftRew": (F(1, "code", K.ENUM), F(2, "type", K.INT32), F(3, "rewardData", K.MESSAGE)),
    "MoonEquip": (F(1, "code", K.ENUM), F(2, "moonEquip", K.MESSAGE, repeated=True), F(3, "moonEquipBarNormal", K.MESSAGE, repeated=True), F(4, "moonEquipBarSpecial", K.MESSAGE, repeated=True)),
    "QuerySimpleActivity": (F(1, "code", K.ENUM), F(2, "totalProgress", K.INT32), F(3, "subProgress", K.MESSAGE, repeated=True), F(4, "mainRewards", K.INT32, repeated=True), F(5, "extraRewards", K.INT32, repeated=True), F(6, "unlockInfo", K.INT32, repeated=True), F(7, "LevelOpenTime", K.INT64)),
}.items():
    LOBBY_SCHEMAS["L2C_" + name] = ProtoSchema("L2C_" + name, fields)
