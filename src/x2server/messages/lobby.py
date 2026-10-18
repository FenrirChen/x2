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
# 星之特权 (特别课程) 一条档位的领取状态, 嵌在 L2C_QueryStarPrivilegeReward /
# L2C_ReciveStarPrivilegeReward 的 privilegeRewardList 里。字段序 = 客户端自己的类型
# (protocol/commandx2_messages.md 的 StarPrivilegeReward):
# level / reciveFreeReward / recivePrivilegeReward, 全 int32。
STAR_PRIVILEGE_REWARD = ProtoSchema("StarPrivilegeReward", (
    F(1, "level", K.INT32),
    F(2, "reciveFreeReward", K.INT32),
    F(3, "recivePrivilegeReward", K.INT32),
))
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
# Nested College wire types; field numbers follow dump.cs declaration order like
# GROWTH_BASE. UnlockExploreRuin: queueCount/exp/ruinId (0x10/0x14/0x18).
UNLOCK_EXPLORE_RUIN = ProtoSchema("UnlockExploreRuin", (F(1, "queueCount", K.INT32),
    F(2, "exp", K.INT32), F(3, "ruinId", K.INT32)))
# CustomerInfo/ProductionBar/Element per L2C_AlchemyMainData (591) consumers.
# Queue/slot row types used by the GrowthBase snapshot. The client's generated
# deserializer (SilentOrbit) leaves absent repeated/singular fields NULL, so the
# snapshot always carries zero-filled entries for every list the UI derefs.
EXPLORE_DATA = ProtoSchema("ExploreData", (F(1, "exploreId", K.INT32),
    F(2, "exploreStatus", K.INT32), F(3, "fightCapacity", K.INT64),
    F(4, "exploreEndTime", K.INT32), F(5, "heroList", K.INT32, repeated=True),
    F(6, "difficulty", K.INT32), F(7, "ruinId", K.INT32)))
TRAINING_DATA = ProtoSchema("TrainingData", (F(1, "trainingId", K.INT32),
    F(2, "trainingStatus", K.INT32), F(3, "trainingStartTime", K.INT32),
    F(4, "trainingEndTime", K.INT32), F(5, "heroId", K.INT32),
    F(6, "difficulty", K.INT32), F(7, "trainingTime", K.INT32),
    F(8, "buildID", K.INT32)))
PRAY_QUEUE = ProtoSchema("PrayQueue", (F(1, "buildingId", K.INT32),
    F(2, "prayStatus", K.INT32), F(3, "prayStartTime", K.INT32),
    F(4, "prayEndTime", K.INT32), F(5, "prayItemID", K.INT32),
    F(6, "prayItemNum", K.INT32), F(7, "prayHeroID", K.INT32)))
BUILD_QUEUE = ProtoSchema("BuildQueue", (F(1, "buildingId", K.INT32),
    F(2, "upgradeStatus", K.INT32), F(3, "upgradeStartTime", K.INT32),
    F(4, "upgradeEndTime", K.INT32)))
WONDER_QUEUE = ProtoSchema("WonderQueue", (F(1, "buildingId", K.INT32),
    F(2, "upgradeStatus", K.INT32), F(3, "upgradeStartTime", K.INT32),
    F(4, "upgradeEndTime", K.INT32)))

def zero_queue_row(schema):
    """One all-default element so an absent field never decodes to null."""
    return schema.encode({})
# Native Serialize 0x38f05a8 writes type at tag 0x18 and itemNum at
# tag 0x38. Declaration order differs: using itemNum as field 3 made the
# overhead UI read quantity 1 as the quest type and select its empty icon.
CUSTOMER_INFO = ProtoSchema("CustomerInfo", (F(1, "questId", K.INT32),
    F(2, "itemId", K.INT32, repeated=True), F(7, "itemNum", K.INT32, repeated=True),
    F(3, "type", K.ENUM), F(4, "adviseItemId", K.INT32), F(5, "param", K.INT32),
    F(6, "result", K.INT32)))
PRODUCTION_BAR = ProtoSchema("ProductionBar", (F(1, "recipeId", K.INT32),
    F(2, "endTime", K.INT32), F(3, "buffId", K.INT32, repeated=True)))
ELEMENT = ProtoSchema("Element", (F(1, "elementId", K.INT32), F(2, "num", K.INT32),
    F(3, "lastRecoverTime", K.INT32), F(4, "buyTimesDay", K.INT32)))
ALCHEMY_MAIN = ProtoSchema("L2C_AlchemyMainData", (F(1, "code", K.ENUM),
    F(2, "recipeIdExp", K.MESSAGE, repeated=True), F(3, "customeres", K.MESSAGE, repeated=True),
    F(4, "productionBars", K.MESSAGE, repeated=True), F(5, "elements", K.MESSAGE, repeated=True),
    F(6, "buffType", K.INT32), F(7, "buffCount", K.INT32)))


def growth_base_values():
    # Compatibility helper for schema-only callers; production uses CollegeStateRepository.
    from x2server.player.college import initial_state
    state = initial_state()
    return {
        "buildingList": [BUILDING_BASE_INFO.encode(row) for row in state["buildings"]],
        "civilization": [BUILDING_BASE_INFO.encode(row) for row in state["wonders"]],
        "exploreList": [zero_queue_row(EXPLORE_DATA)],
        "trainingList": [zero_queue_row(TRAINING_DATA)],
        "prayQueue": [zero_queue_row(PRAY_QUEUE)],
        "buildQueue": zero_queue_row(BUILD_QUEUE),
        "wonderQueue": zero_queue_row(WONDER_QUEUE)}

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
    ("QuerySimpleActivity", 986, 987),
    ("QuerySharedMessage", 653, 654), ("AccountBuffData", 865, 866),
    ("ButtonClick", 376, 377), ("Logout", 405, 406),
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
    # 活动中心 (星相屋 / 首充 / 特别课程 / 积分活动 / 献祭福利 / 降临纪念 / 自选三星) 的
    # 读写消息。这些之前只有消息号没有 schema/handler, 客户端点「领取」收不到回包 ->
    # 一直等到超时再重连。它们都由 player/lobby.py 的 DELEGATED 转给真实现:
    #   362/363 星相屋每日占卜      -> player/divination.py
    #   721/722, 988/989, 1013/1014, 774/775, 890/891, 986/987
    #                                -> player/extra_activity.py
    #   816/817 降临纪念 (累计登录) -> player/total_login.py
    #   635/636 首充领取              -> EconomyService (player/economy.py)
    # (633/634 QueryFirstReCharge 已在 COLLEGE_IDS 里登记, 不在这里重复, 否则
    #  registry 会因同名 id 冲突而拒绝加载。)
    ("Divination", 362, 363), ("ReciveStarPrivilegeReward", 721, 722),
    ("SimpleActivityOpt", 988, 989), ("SimpleActivityNotice", 1013, 1014),
    ("TotalLoginReward", 816, 817), ("ReciveNoviceSign", 774, 775),
    ("ExchangeItemActivity", 890, 891), ("ReciveFirstReCharge", 635, 636),
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
    # 活动中心领取请求体。字段序 = 客户端自己的类型:
    #   C2L_ReciveStarPrivilegeReward = reciveLevelList(list<int32>, 线上是裸 varint)
    #   C2L_SimpleActivityOpt = id, opt(0 UNLOCK_FUN / 1 REWARD_MAIN / 2 REWARD_EXTRA), param
    #   C2L_SimpleActivityNotice = id
    #   C2L_TotalLoginReward = daysIndex (0-based 下标或 36/81 这个天数, 两种都认)
    #   C2L_ReciveNoviceSign = SignCount
    # C2L_Divination / C2L_ExchangeItemActivity / C2L_ReciveFirstReCharge 都是空结构,
    # 走 LOBBY_IDS 默认的空 schema (C2L_QueryFirstReCharge 同理, 但它的编号在
    # COLLEGE_IDS 里, schema 由 messages/college.py 提供)。
    "ReciveStarPrivilegeReward": (F(1, "reciveLevelList", K.INT32, repeated=True),),
    "SimpleActivityOpt": (F(1, "id", K.INT32), F(2, "opt", K.ENUM), F(3, "param", K.INT32)),
    "SimpleActivityNotice": (F(1, "id", K.INT32),),
    "TotalLoginReward": (F(1, "daysIndex", K.INT32),),
    "ReciveNoviceSign": (F(1, "SignCount", K.INT32),),
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
    "Logout": (F(1, "code", K.ENUM),),
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
    # 活动中心回包。字段序都取自离线端 x2offline/src/server/router.cpp 与客户端
    # il2cpp-types.h 的声明序:
    #   363 Divination = code + rewardData
    #   817 TotalLoginReward = code + daysIndex(回显) + rewardData
    #   775 ReciveNoviceSign = code + SignCount(新的已签到天数) + rewardData
    #   891 ExchangeItemActivity = code + rewardData (必须带 rewardData, 否则换不了)
    #   722 ReciveStarPrivilegeReward = code + privilegeRewardList + rewardData
    #   989 SimpleActivityOpt = code + mainRewards + extraRewards + unlockInfo + rewardData
    #   1014 SimpleActivityNotice = code + id + totalProgress + subProgress +
    #        mainRewards + extraRewards + unlockInfo
    #   634 QueryFirstReCharge = code + state; 636 ReciveFirstReCharge = code + rewardData
    "Divination": (F(1, "code", K.ENUM), F(2, "rewardData", K.MESSAGE)),
    "TotalLoginReward": (F(1, "code", K.ENUM), F(2, "daysIndex", K.INT32),
                         F(3, "rewardData", K.MESSAGE)),
    "ReciveNoviceSign": (F(1, "code", K.ENUM), F(2, "SignCount", K.INT32),
                         F(3, "rewardData", K.MESSAGE)),
    "ExchangeItemActivity": (F(1, "code", K.ENUM), F(2, "rewardData", K.MESSAGE)),
    "ReciveStarPrivilegeReward": (F(1, "code", K.ENUM),
                                  F(2, "privilegeRewardList", K.MESSAGE, repeated=True),
                                  F(3, "rewardData", K.MESSAGE)),
    "SimpleActivityOpt": (F(1, "code", K.ENUM), F(2, "mainRewards", K.INT32, repeated=True),
                          F(3, "extraRewards", K.INT32, repeated=True),
                          F(4, "unlockInfo", K.INT32, repeated=True),
                          F(5, "rewardData", K.MESSAGE)),
    "SimpleActivityNotice": (F(1, "code", K.ENUM), F(2, "id", K.INT32),
                             F(3, "totalProgress", K.INT32),
                             F(4, "subProgress", K.MESSAGE, repeated=True),
                             F(5, "mainRewards", K.INT32, repeated=True),
                             F(6, "extraRewards", K.INT32, repeated=True),
                             F(7, "unlockInfo", K.INT32, repeated=True)),
    "QueryFirstReCharge": (F(1, "code", K.ENUM), F(2, "state", K.INT32)),
    "ReciveFirstReCharge": (F(1, "code", K.ENUM), F(2, "rewardData", K.MESSAGE)),
}.items():
    LOBBY_SCHEMAS["L2C_" + name] = ProtoSchema("L2C_" + name, fields)

LOBBY_SCHEMAS["C2L_GetCollectionAward"] = ProtoSchema("C2L_GetCollectionAward",
    (F(1, "collectionAwardID", K.INT32),))
