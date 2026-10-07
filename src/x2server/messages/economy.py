"""2.4 economy messages. Evidence and deliberate gaps: docs/phase19_economy.md."""
from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema as S


def ints(name, fields):
    return S(name, tuple(F(n, field, K.INT32) for n, field in enumerate(fields.split(), 1)))


ITEM = S("ItemData", (F(1, "id", K.INT32), F(2, "num", K.INT32),
    F(3, "locked", K.BOOL), F(4, "dayGet", K.INT32)))
REWARD_ITEM = S("RewardItem", (F(1, "itemId", K.INT32), F(2, "itemNum", K.INT32), F(3, "transform", K.BOOL)))
REWARD = S("RewardData", (F(1, "rewardItem", K.MESSAGE, repeated=True),
    F(2, "rewardEquip", K.MESSAGE, repeated=True), F(3, "transformHero", K.MESSAGE, repeated=True)))
GOODS = S("L2C_Goods", (F(1, "goodsId", K.INT32), F(2, "originalPrice", K.INT32),
    F(3, "itemId", K.INT32), F(4, "num", K.INT32), F(5, "price", K.INT32),
    F(6, "currencyType", K.INT32), F(7, "canBuyTimes", K.INT32),
    F(8, "hasBuyTimes", K.INT32), F(9, "startTime", K.INT32),
    F(10, "endTime", K.INT32), F(11, "goodsTag", K.INT32), F(12, "limited", K.INT32)))
GIFT_PACKAGE_DATA = S("GiftPackageData", (F(1, "id", K.INT32), F(2, "state", K.ENUM),
    F(3, "pushID", K.INT32), F(4, "pushDeadline", K.INT64), F(5, "leftTime", K.INT32),
    F(6, "PurchaseTime", K.INT32), F(7, "unShelves", K.INT64)))
TASK = ints("TaskData", "taskId taskStatus taskProgress taskRefreshTime finishTimes stage activityId difficulty")
TREASURE_BOX = ints("TreasureBoxData", "boxId pickStatus activityId")
FINISH_REQUEST = ints("ReqFinishTaskData", "taskId type activityId")
FINISH_RESULT = S("RspFinishTaskData", (F(1, "code", K.ENUM), F(2, "taskId", K.INT32),
    F(3, "rewardData", K.MESSAGE), F(4, "type", K.ENUM), F(5, "nextTask", K.MESSAGE), F(6, "activityId", K.INT32)))
ECONOMY_IDS = (("FetchMobilityPower", 134, 137), ("ShopGoods", 221, 225), ("RefreshShop", 220, 224),
    ("JewelCompose", 144, 147), ("GodEqupJewelCompose", 215, 216), ("GodEquipJewelDot", 725, 726),
    ("ItemOpt", 111, 112),
    ("BuyGoods", 219, 222), ("QueryGoodsInfo", 301, 302),
    ("QueryReCommendShop", 693, 694), ("PaymentStore", 451, 452),
    ("RechargeInfo", 822, 823),
    ("FinishGameTask", 350, 353), ("FinishGameTaskAsync", 814, 815), ("PickTreasureBox", 310, 314),
    # 好感日常任务 (心愿任务) 的接取, 由许愿页签的「选择页」确认键发出. 客户端自己声明的是
    # C2L_AcceptFavorTask(list<int> taskIds, GameTaskType type) -> L2C_AcceptFavorTask(code).
    ("AcceptFavorTask", 459, 460))
ECONOMY_SCHEMAS = {s.name: s for s in (
    S("C2L_GodEqupJewelCompose", (F(1, "HeroID", K.INT32), F(2, "HoleIsID", K.INT32), F(3, "RecipeID", K.INT32))),
    S("L2C_GodEqupJewelCompose", (F(1, "result", K.ENUM), F(2, "ID", K.INT32))),
    S("C2L_JewelCompose", (F(1, "RecipeID", K.INT32), F(2, "composeCount", K.INT32))),
    S("L2C_JewelCompose", (F(1, "result", K.ENUM), F(2, "rewardData", K.MESSAGE), F(3, "recipeID", K.INT32))),
    S("C2L_GodEquipJewelDot", (F(1, "heroId", K.INT32),)),
    S("L2C_GodEquipJewelDot", (F(1, "code", K.ENUM),)),
    S("C2L_ItemOpt", (F(1, "id", K.INT32), F(2, "opt", K.ENUM),
        F(3, "count", K.INT32), F(4, "selectedItemIndexList", K.INT32, repeated=True))),
    S("L2C_ItemOpt", (F(1, "code", K.ENUM), F(2, "opt", K.ENUM),
        F(3, "rewardData", K.MESSAGE), F(4, "itemId", K.INT32))),
    S("C2L_FetchMobilityPower", (F(1, "itemId", K.INT32),)),
    S("L2C_FetchMobilityPower", (F(1, "result", K.ENUM), F(2, "rewardData", K.MESSAGE))),
    S("C2L_ItemAll", ()),
    S("L2C_ItemAll", (F(1, "items", K.MESSAGE, repeated=True),)),
    S("L2C_ItemUpdate", (F(1, "code", K.ENUM), F(2, "items", K.MESSAGE, repeated=True))),
    S("L2C_ItemRemove", (F(1, "ids", K.INT32, repeated=True),)),
    ints("C2L_ShopGoods", "shopId"), ints("C2L_RefreshShop", "shopId"),
    ints("C2L_BuyGoods", "shopId goodsId buyNum"), ints("C2L_QueryGoodsInfo", "goodsId"),
    S("C2L_QueryReCommendShop", ()),
    S("L2C_QueryReCommendShop", (F(1, "code", K.ENUM), F(2, "recommendTag", K.MESSAGE, repeated=True))),
    S("C2L_PaymentStore", ()),
    S("L2C_PaymentStore", (F(1, "code", K.ENUM), F(2, "product", K.MESSAGE, repeated=True))),
    ints("C2L_RechargeInfo", "extra"),
    ints("C2L_BuyGiftPackage", "giftPackageID num"),
    S("L2C_BuyGiftPackage", (F(1, "code", K.ENUM), F(2, "rewardData", K.MESSAGE),
        F(3, "datas", K.MESSAGE, repeated=True))),
    ints("C2L_RechargeGoodsInfo", "rechargeID"),
    S("L2C_RechargeGoodsInfo", (F(1, "code", K.ENUM),)),
    S("L2C_RechargeInfo", (F(1, "code", K.ENUM), F(2, "totalRMB", K.INT32),
        F(3, "orders", K.MESSAGE, repeated=True))),
    ints("L2C_QueryGoodsInfo", "code shopId goodsId price originalPrice hasBuyTimes canBuyTimes itemNum currencyType"),
    S("L2C_BuyGoods", (F(1, "code", K.ENUM), F(2, "itemId", K.INT32), F(3, "itemNum", K.INT32),
        F(4, "goodsId", K.INT32), F(5, "price", K.INT32), F(6, "originalPrice", K.INT32),
        F(7, "hasBuyTimes", K.INT32), F(8, "rewardData", K.MESSAGE), F(9, "buyNum", K.INT32),
        F(10, "changeItemID", K.INT32), F(11, "shopId", K.INT32))),
    ints("C2L_DailyAndWeekTask", "type"),
    # 心愿任务的第二步. 回包只有 code, 没有任务清单: 客户端拿到 10 之后自己把页面切到
    # 「我的任务」并重查 C2L_GameTask(type=6, extraType=0), 所以那一份列表走
    # L2C_GameTask 推回去, 而不是这个回包 (FavorWishModule 只注册了 L2C_GameTask 的
    # 处理器). 元数据把 repeated int32 的元素名写成 AppConfig, 与其它扁平清单同一占位。
    S("C2L_AcceptFavorTask", (F(1, "taskIds", K.INT32, repeated=True), F(2, "type", K.ENUM))),
    S("L2C_AcceptFavorTask", (F(1, "code", K.ENUM),)),
    S("C2L_FinishGameTask", (F(1, "data", K.MESSAGE, repeated=True),)),
    S("L2C_FinishGameTask", (F(1, "data", K.MESSAGE, repeated=True),)),
    ints("C2L_FinishGameTaskAsync", "taskId type"),
    S("L2C_FinishGameTaskAsync", (F(1, "data", K.MESSAGE),)),
    S("L2C_TaskUpdate", (F(1, "type", K.ENUM), F(2, "taskList", K.MESSAGE, repeated=True))),
    S("L2C_TreasureBoxUpdate", (F(1, "type", K.ENUM), F(2, "boxList", K.MESSAGE, repeated=True))),
    ints("C2L_PickTreasureBox", "boxId type param activityId"),
    S("L2C_PickTreasureBox", (F(1, "code", K.ENUM), F(2, "boxId", K.INT32), F(3, "type", K.ENUM),
        F(4, "rewardData", K.MESSAGE), F(5, "param", K.INT32), F(6, "activityId", K.INT32))),
)}
for name in ("L2C_ShopGoods", "L2C_RefreshShop"):
    ECONOMY_SCHEMAS[name] = S(name, (F(1, "code", K.ENUM), F(2, "shopId", K.INT32),
        F(3, "NextRefreshTime", K.INT64), F(4, "RefreshTimes", K.INT32),
        F(5, "RefreshPrice", K.INT32), F(6, "goods", K.MESSAGE, repeated=True)))
