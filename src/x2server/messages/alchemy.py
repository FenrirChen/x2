"""学院炼金 (白夜行星·浮士德的炼金实验室) 的报文契约。

恢复自客户端自己的类型声明 (protocol/commandx2_messages.md L2553-L2681 与
L2796-L2824) 与离线端 x2offline/src/server/router.cpp 的 590 分支:

    炼金 12 对: 590/591 AlchemyMainData, 592/593 SingleCustomerInfo,
                 594/595 MakeItem, 596/597 MakIngSpeed, 598/599 AlchemyFinish,
                 600/601 AlchemyButtonClick, 602/603 AlchemyCollect,
                 604/605 AlchemyBuy, 729/730 QueryAlchemyTrade, 731/732 AlchemyTrade,
                 824/825 AlchemyMakeCancel, 826/827 AlchemyOnekeyCollect
    推送:       617 L2C_QueryGrowthBaseAlchemy (无 C2L 对)

嵌套类型 (Element/CustomerInfo/ProductionBar/AlchemyRecipeBarData/AlchemyTrade/
TradeTableData) 在这里声明, 由各 handler 用 ``.encode(...)`` 编成 bytes 塞进
外层 repeated MESSAGE 字段 —— 与 messages/lobby.py 的 BUILDING_BASE_INFO 同一约定。

present-but-empty: 客户端对空 repeated 字段会解成 null 列表并在
OnReceiveAlchemyMainDataMsg 里抛 NullReferenceException (离线端 router.cpp 590
的注释同样记录了这个坑), 所以未占用的槽位要发**一条空 message** (``b""``),
而不是干脆不发这个字段 (空列表在 protobuf 下等于字段缺失)。
"""
from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema
# recipeIdExp 的元素类型就是 lobby 已经声明过的 KeyValuePair_Int32_Int32 (key/value)。
from x2server.messages.lobby import MISSION_PAIR as KEY_VALUE_PAIR

# Element: 1 elementId, 2 num, 3 lastRecoverTime, 4 buyTimesDay
ELEMENT = ProtoSchema("Element", (
    F(1, "elementId", K.INT32), F(2, "num", K.INT32),
    F(3, "lastRecoverTime", K.INT32), F(4, "buyTimesDay", K.INT32)))

# CustomerInfo 的 tag 顺序**不是**结构体里的字段声明顺序, 以客户端反汇编为准:
# 客户端 CommandX2.CustomerInfo.Deserialize 的 switch 是
#   0x08->+0x10 questId, 0x10->+0x18 itemId, 0x18->+0x28 type,
#   0x20->+0x2C adviseItemId, 0x28->+0x30 param, 0x30->+0x34 result,
#   0x38->+0x20 itemNum
# 也就是说 itemNum 是 tag 7, type 是 tag 3 (不是文档里写的 3=itemNum / 4=type)。
# 之前按文档发, 客户端把 itemNum 的值读进了 type, 于是 type!=2, 顾客头顶显示
# CollegeQuest.Icon (DynamicCollege/LianJin_GanTanHao = 黄色感叹号)。
CUSTOMER_INFO = ProtoSchema("CustomerInfo", (
    F(1, "questId", K.INT32), F(2, "itemId", K.INT32, repeated=True),
    F(3, "type", K.INT32), F(4, "adviseItemId", K.INT32),
    F(5, "param", K.INT32), F(6, "result", K.INT32),
    F(7, "itemNum", K.INT32, repeated=True)))

# ProductionBar: 1 recipeId, 2 endTime, 3 buffId[AppConfig]
PRODUCTION_BAR = ProtoSchema("ProductionBar", (
    F(1, "recipeId", K.INT32), F(2, "endTime", K.INT32),
    F(3, "buffId", K.INT32, repeated=True)))

# AlchemyRecipeBarData: 1 recipeId, 2 expBefore, 3 exp, 4 posIndex[AppConfig]
ALCHEMY_RECIPE_BAR_DATA = ProtoSchema("AlchemyRecipeBarData", (
    F(1, "recipeId", K.INT32), F(2, "expBefore", K.INT32), F(3, "exp", K.INT32),
    F(4, "posIndex", K.INT32, repeated=True)))

# AlchemyTrade: 1 tradeId, 2 tradeNum
ALCHEMY_TRADE = ProtoSchema("AlchemyTrade", (
    F(1, "tradeId", K.INT32), F(2, "tradeNum", K.INT32)))

# TradeTableData: 1 tradeId, 2 tradeNeed[AppConfig], 3 tradeNeedNum[AppConfig],
#                 4 tradeDist, 5 tradeLimitType, 6 tradeLimitNum
TRADE_TABLE_DATA = ProtoSchema("TradeTableData", (
    F(1, "tradeId", K.INT32), F(2, "tradeNeed", K.INT32, repeated=True),
    F(3, "tradeNeedNum", K.INT32, repeated=True), F(4, "tradeDist", K.INT32),
    F(5, "tradeLimitType", K.INT32), F(6, "tradeLimitNum", K.INT32)))

ALCHEMY_IDS = (
    ("AlchemyMainData", 590, 591),
    ("SingleCustomerInfo", 592, 593),
    ("MakeItem", 594, 595),
    ("MakIngSpeed", 596, 597),
    ("AlchemyFinish", 598, 599),
    ("AlchemyButtonClick", 600, 601),
    ("AlchemyCollect", 602, 603),
    ("AlchemyBuy", 604, 605),
    ("QueryAlchemyTrade", 729, 730),
    ("AlchemyTrade", 731, 732),
    ("AlchemyMakeCancel", 824, 825),
    ("AlchemyOnekeyCollect", 826, 827),
)

# 729/731 (炼金交易活动) 不在 messages/college.py 的 COLLEGE_IDS 里, 单列一份给
# protocol/registry.py 注册 —— 注册表按名字去重, 若把整个 ALCHEMY_IDS 都塞进去会和
# COLLEGE_IDS 里的 590..605/824..826 重名报 "duplicate message name"。
ALCHEMY_TRADE_IDS = (
    ("QueryAlchemyTrade", 729, 730),
    ("AlchemyTrade", 731, 732),
)

ALCHEMY_SCHEMAS: dict[str, ProtoSchema] = {}

_C2L = {
    # (590 空结构, 只靠 message id 区分请求)
    "AlchemyMainData": (),
    "SingleCustomerInfo": (F(1, "posIndex", K.INT32),),
    "MakeItem": (F(1, "posIndex", K.INT32), F(2, "recipeId", K.INT32)),
    "MakIngSpeed": (F(1, "posIndex", K.INT32), F(2, "type", K.INT32)),
    "AlchemyFinish": (F(1, "type", K.INT32), F(2, "posIndex", K.INT32),
                      F(3, "plusPrice", K.BOOL), F(4, "discountPrice", K.BOOL)),
    "AlchemyButtonClick": (F(1, "type", K.INT32), F(2, "posIndex", K.INT32)),
    "AlchemyCollect": (F(1, "posIndex", K.INT32),),
    "AlchemyBuy": (F(1, "type", K.INT32), F(2, "typeId", K.INT32)),
    "QueryAlchemyTrade": (F(1, "activityId", K.INT32),),
    "AlchemyTrade": (F(1, "activityId", K.INT32), F(2, "tradeId", K.INT32)),
    "AlchemyMakeCancel": (F(1, "posIndex", K.INT32),),
    "AlchemyOnekeyCollect": (F(1, "posIndex", K.INT32, repeated=True),),
}
_L2C = {
    "AlchemyMainData": (F(1, "code", K.ENUM),
                        F(2, "recipeIdExp", K.MESSAGE, repeated=True),
                        F(3, "customeres", K.MESSAGE, repeated=True),
                        F(4, "productionBars", K.MESSAGE, repeated=True),
                        F(5, "elements", K.MESSAGE, repeated=True),
                        F(6, "buffType", K.INT32), F(7, "buffCount", K.INT32)),
    "SingleCustomerInfo": (F(1, "code", K.ENUM), F(2, "posIndex", K.INT32),
                           F(3, "customere", K.MESSAGE),
                           F(4, "transactionNum", K.INT32),
                           F(5, "transactionLastRecoverTime", K.INT32)),
    "MakeItem": (F(1, "code", K.ENUM), F(2, "posIndex", K.INT32),
                 F(3, "productionBar", K.MESSAGE)),
    "MakIngSpeed": (F(1, "code", K.ENUM), F(2, "posIndex", K.INT32)),
    "AlchemyFinish": (F(1, "code", K.ENUM), F(2, "type", K.INT32),
                      F(3, "posIndex", K.INT32), F(4, "rewardData", K.MESSAGE),
                      F(5, "alchemyType", K.INT32)),
    "AlchemyButtonClick": (F(1, "code", K.ENUM), F(2, "type", K.INT32),
                           F(3, "posIndex", K.INT32), F(4, "result", K.INT32),
                           F(5, "param", K.INT32)),
    "AlchemyCollect": (F(1, "code", K.ENUM), F(2, "rewardData", K.MESSAGE),
                       F(3, "recipeId", K.INT32), F(4, "exp", K.INT32),
                       F(5, "posIndex", K.INT32)),
    "AlchemyBuy": (F(1, "code", K.ENUM),),
    "QueryAlchemyTrade": (F(1, "code", K.ENUM), F(2, "activityId", K.INT32),
                          F(3, "alchemyTrades", K.MESSAGE, repeated=True),
                          F(4, "tradeTableData", K.MESSAGE, repeated=True)),
    "AlchemyTrade": (F(1, "code", K.ENUM),
                     F(2, "alchemyTrades", K.MESSAGE, repeated=True),
                     F(3, "rewardData", K.MESSAGE)),
    "AlchemyMakeCancel": (F(1, "code", K.ENUM), F(2, "rewardData", K.MESSAGE),
                          F(3, "posIndex", K.INT32)),
    "AlchemyOnekeyCollect": (F(1, "code", K.ENUM), F(2, "rewardData", K.MESSAGE),
                             F(3, "barData", K.MESSAGE, repeated=True)),
}
for _name, _c2l, _l2c in ALCHEMY_IDS:
    ALCHEMY_SCHEMAS["C2L_" + _name] = ProtoSchema("C2L_" + _name, _C2L[_name])
    ALCHEMY_SCHEMAS["L2C_" + _name] = ProtoSchema("L2C_" + _name, _L2C[_name])

# 617 是服务器主动推送 (无 C2L 对), 名字就是客户端自己的类型名。
ALCHEMY_SCHEMAS["L2C_QueryGrowthBaseAlchemy"] = ProtoSchema("L2C_QueryGrowthBaseAlchemy", (
    F(1, "code", K.ENUM),
    F(2, "elements", K.MESSAGE, repeated=True),
    F(3, "starEnergy", K.INT32), F(4, "starGainTime", K.INT32),
    F(5, "buffType", K.INT32), F(6, "buffCount", K.INT32)))