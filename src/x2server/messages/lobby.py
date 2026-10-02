"""Read-only lobby queries recovered from 2.4 ERequestTypes and Serialize methods."""
from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema

# ActivityData.Serialize 0x1dc97c8: client activity-center tab contract.
ACTIVITY_DATA = ProtoSchema("ActivityData", (
    *(F(i, name, K.INT32) for i, name in enumerate(("actId", "state", "activityParentType",
        "actType", "startTime", "endTime", "openLever", "activityShow", "activityGroup", "activityName"), 1)),
    *(F(i, name, K.INT32, repeated=True) for i, name in enumerate(("param1", "param2", "param3", "param4"), 11)),
    F(15, "activityDescription", K.STRING), F(16, "activityReward", K.INT32, repeated=True),
    F(17, "activityDataItems", K.MESSAGE, repeated=True), F(18, "activityTaps", K.STRING),
    F(19, "openType", K.INT32), F(20, "openParam", K.INT32, repeated=True)))

MISSION_PAIR = ProtoSchema("KeyValuePair_Int32_Int32", (F(1, "Key", K.INT32), F(2, "Value", K.INT32)))
MISSION_TYPE = ProtoSchema("MissionTypeData", (F(1, "type", K.INT32),
    F(2, "missionData", K.MESSAGE, repeated=True),
    F(3, "chapterHisMaxScore", K.MESSAGE, repeated=True),
    F(4, "chapterHisMaxScoreSec", K.MESSAGE, repeated=True)))
BUILDING_BASE_INFO = ProtoSchema("BuildingBaseInfo", (F(1, "buildingId", K.INT32),
    F(2, "buildingLevel", K.INT32), F(3, "buildingStar", K.INT32)))
GROWTH_BASE = ProtoSchema("L2C_QueryGrowthBase", (
    F(1, "starEnergy", K.INT32), F(2, "buildingList", K.MESSAGE, repeated=True),
    F(3, "warehouseGold", K.INT32), F(4, "goldGainTime", K.INT32),
    F(5, "starGainTime", K.INT32), F(6, "extraPower", K.INT32),
    F(7, "exploreList", K.MESSAGE, repeated=True),
    F(8, "trainingList", K.MESSAGE, repeated=True),
    F(9, "civilization", K.MESSAGE, repeated=True),
    F(10, "buildQueue", K.MESSAGE), F(11, "wonderQueue", K.MESSAGE),
    F(12, "prayQueue", K.MESSAGE, repeated=True), F(13, "washingCountDay", K.INT32)))


def growth_base_values():
    # Compatibility helper for schema-only callers; production uses CollegeStateRepository.
    from x2server.player.college import initial_state
    state = initial_state()
    return {
        "buildingList": [BUILDING_BASE_INFO.encode(row) for row in state["buildings"]],
        "civilization": [BUILDING_BASE_INFO.encode(row) for row in state["wonders"]]}

LOBBY_IDS = (
    ("QueryTelInfo", 782, 783), ("SeasonIcon", 999, 1001),
    ("QueryItemLimitTime", 715, 716), ("QueryDivination", 576, 578),
    ("QueryNotic", 669, 670), ("NoticPushInfo", 805, 806),
    ("QueryReturnInfo", 776, 777), ("SystemInfo", 432, 433),
    ("GameTask", 351, 354), ("EntryidStatus", 515, 516), ("EquipAll", 539, 538),
    ("QueryMission", 574, 575), ("QueryCollectionAward", 586, 587),
    ("QueryGrowthBase", 579, 584), ("UnlockExploreRuin", 622, 623),
    ("QueryActivity", 615, 616), ("QueryWorldBossOpenTime", 679, 680),
    ("QueryActivityDrawInfo", 697, 699), ("QueryStarPrivilegeReward", 719, 720),
    ("QueryStarPrivilegeInfo", 723, 724), ("QueryIllustrationData", 862, 863),
    ("AccountBuffAutoStop", 885, 886), ("ReceiveGiftRew", 919, 920),
    ("MoonEquip", 964, 965), ("QuerySimpleActivity", 986, 987),
    ("QuerySharedMessage", 653, 654), ("AccountBuffData", 865, 866),
    ("ButtonClick", 376, 377),
    ("CheckFightProfile", 447, 448), ("CommercialShopGoods", 523, 524),
    ("QueryGiftPackage", 531, 532),
    # 星图 -> 剧情回顾 -> 主线. The chapter row's 解锁-button callback calls
    # ChapterModule.QueryUnLockStory(chapterId, chapterType), which sends
    # C2L_UnlockStory (667) and waits for L2C_UnlockStory (668). The client's own
    # ChapterModule.CheckStoryOpen(id) is just `story.Contains(id)`, where `story`
    # is the List<int32> carried on both L2C_QueryMission.story (field 3, declared
    # above) and L2C_UnlockStory.story (field 3). Nothing ever filled that field,
    # so every 剧情回顾 chapter rendered locked with a 解锁 button.
    ("UnlockStory", 667, 668),
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
    "CheckFightProfile": (F(1, "profileType", K.ENUM), F(2, "checkID", K.INT32)),
    "CommercialShopGoods": (F(1, "shopType", K.ENUM),),
    "QueryGiftPackage": (F(1, "playerID", K.INT64),),
    # ChapterInfo.ReviewUnlockRequest / POVChapterInfo.ReviewUnlockRequest hold
    # chapterType, so the request is exactly (chapterId, chapterType).
    "UnlockStory": (F(1, "chapterId", K.INT32), F(2, "chapterType", K.INT32)),
}.items():
    LOBBY_SCHEMAS["C2L_" + name] = ProtoSchema("C2L_" + name, fields)
for name, fields in {
    "QueryGrowthBase": GROWTH_BASE.fields,
    "UnlockExploreRuin": (F(1, "code", K.ENUM), F(2, "unlockExploreRuin", K.MESSAGE, repeated=True)),
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
    "GetCollectiontAward": (F(1, "code", K.ENUM), F(2, "awardID", K.INT32, repeated=True),
                             F(3, "rewardData", K.MESSAGE)),
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
    "CheckFightProfile": (F(1, "code", K.ENUM), F(2, "isProfileExist", K.BOOL),
                          F(3, "sectionId", K.INT32), F(4, "layer", K.INT32),
                          F(5, "heroIds", K.INT32, repeated=True), F(6, "weeklyId", K.INT32),
                          F(7, "currentWeek", K.INT32), F(8, "isProfileValid", K.BOOL)),
    "CommercialShopGoods": (F(1, "code", K.ENUM), F(2, "goods", K.MESSAGE, repeated=True),
                            F(3, "shopType", K.ENUM)),
    "QueryGiftPackage": (F(1, "code", K.ENUM), F(2, "datas", K.MESSAGE, repeated=True)),
    # Field run taken from the client's own type (L2C_UnlockStory { code @0x10,
    # rewardData @0x18, story @0x20 }); the client stores `story` straight into
    # ChapterModule.field_0xF0, the list CheckStoryOpen consults, so 668 is also
    # how the chapter just unlocked becomes replayable without a fresh query.
    "UnlockStory": (F(1, "code", K.ENUM), F(2, "rewardData", K.MESSAGE),
                    F(3, "story", K.INT32, repeated=True)),
}.items():
    LOBBY_SCHEMAS["L2C_" + name] = ProtoSchema("L2C_" + name, fields)

LOBBY_SCHEMAS["C2L_GetCollectionAward"] = ProtoSchema("C2L_GetCollectionAward",
    (F(1, "collectionAwardID", K.INT32),))
