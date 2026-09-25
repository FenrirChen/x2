"""Client 2.4 wish pool and draw wire shapes."""
from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema as S

CARD_POOL = S("CardPool", tuple(F(index, name, K.INT32) for index, name in enumerate((
    "poolId", "startTime", "endTime", "jackpotRate", "oneDrawCount",
    "tenDrawCount", "securityNum", "totalDrawCount", "limitValue", "failCount",
    "discountDrawCount", "itemIdSecurity"), 1)))

WISH_SCHEMAS = {s.name: s for s in (
    S("C2L_CardPool", (F(1, "drawPos", K.INT32),)),
    S("L2C_CardPool", (F(1, "code", K.ENUM), F(2, "cardPoolList", K.MESSAGE, repeated=True),
                        F(3, "drawCountID", K.INT32), F(4, "select", K.INT32))),
    S("C2L_LuckDraw", (F(1, "drawnId", K.INT32), F(2, "drawType", K.ENUM))),
    S("L2C_LuckDraw", (F(1, "code", K.ENUM), F(2, "drawnId", K.INT32),
        F(3, "rewardData", K.MESSAGE), F(4, "luckyValue", K.INT32),
        F(5, "oneDrawCount", K.INT32), F(6, "tenDrawCount", K.INT32),
        F(7, "limitValue", K.INT32), F(8, "securityNum", K.INT32),
        F(9, "luckyValueCurrent", K.INT32, repeated=True),
        F(10, "allHeroCardFirstThreeStar", K.BOOL))),
    S("C2L_RequestDrawResult", (F(1, "drawnCountID", K.INT32),)),
    S("L2C_RequestDrawResult", (F(1, "code", K.ENUM), F(2, "drawnId", K.INT32),
        F(3, "rewardData", K.MESSAGE), F(4, "luckyValue", K.INT32),
        F(5, "oneDrawCount", K.INT32), F(6, "tenDrawCount", K.INT32),
        F(7, "limitValue", K.INT32))),
)}
