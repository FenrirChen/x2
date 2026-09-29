"""Client verified skin, icon, and dubbing message layouts."""
from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema as S

APPEARANCE_IDS = (("Account", 141, 142), ("HeroWearSkin", 529, 530),
    ("BuyCommercialGoods", 525, 526),
    ("SaveHeroDubbing", 688, 689), ("QueryHeroDubbing", 690, 691),
    ("PutOnOrPutOffSeasonIcon", 1002, 1003), ("SeasonIconStatusUp", 1008, 1009))
HERO_SKIN = S("HeroSkin", (F(1, "heroId", K.INT32), F(2, "skinIds", K.INT32, repeated=True),
    F(3, "battleSkin", K.INT32), F(4, "outerSkin", K.INT32)))
SEASON_ICON_DATA = S("SeasonIconData", (F(1, "id", K.INT32), F(2, "rankId", K.INT32)))
HERO_DUBBING_DATA = S("HeroDubbingData", (F(1, "heroId", K.INT32),
    F(2, "dubbingIds", K.INT32, repeated=True)))
PICTURE_ID_ENTRY = S("PictureIDEntry", (F(1, "Key", K.INT32), F(2, "Value", K.INT32)))
ICON_INFO = S("IconInfoProto", (F(1, "IconType", K.INT32), F(2, "IconID", K.INT32),
    F(3, "OrnamentID", K.INT32), F(4, "PictureID", K.MESSAGE, repeated=True)))
COMMERCIAL_GOODS = S("CommercialGoods", (F(1, "goodsId", K.INT32), F(2, "startTime", K.INT32),
    F(3, "endTime", K.INT32), F(4, "originalPrice", K.INT32), F(5, "itemId", K.INT32),
    F(6, "price", K.INT32), F(7, "currencyType", K.ENUM), F(8, "alreadyBuy", K.INT32),
    F(9, "goodsType", K.ENUM), F(10, "preCount", K.INT32), F(11, "rechargeID", K.INT32)))

APPEARANCE_SCHEMAS = {s.name: s for s in (
    HERO_SKIN, SEASON_ICON_DATA, HERO_DUBBING_DATA, PICTURE_ID_ENTRY, ICON_INFO,
    S("C2L_HeroSkinAll", ()),
    S("L2C_HeroSkinAll", (F(1, "skinList", K.MESSAGE, repeated=True),)),
    S("L2C_HeroSkinUpdate", (F(1, "skin", K.MESSAGE),)),
    S("C2L_HeroWearSkin", (F(1, "heroId", K.INT32), F(2, "skinId", K.INT32), F(3, "type", K.INT32))),
    S("L2C_HeroWearSkin", (F(1, "code", K.ENUM), F(2, "heroId", K.INT32),
        F(3, "skinId", K.INT32), F(4, "type", K.INT32))),
    S("C2L_BuyCommercialGoods", (F(1, "goodsId", K.INT32), F(2, "shopType", K.ENUM),
        F(3, "currencyType", K.ENUM))),
    S("L2C_BuyCommercialGoods", (F(1, "code", K.ENUM), F(2, "goodsId", K.INT32),
        F(3, "rewardData", K.MESSAGE), F(4, "shopType", K.ENUM))),
    S("C2L_QueryHeroDubbing", ()),
    S("L2C_QueryHeroDubbing", (F(1, "code", K.ENUM), F(2, "heroDubbingDatas", K.MESSAGE, repeated=True))),
    S("C2L_SaveHeroDubbing", (F(1, "heroId", K.INT32), F(2, "dubbingId", K.INT32))),
    S("L2C_SaveHeroDubbing", (F(1, "code", K.ENUM), F(2, "heroDubbingDatas", K.MESSAGE, repeated=True))),
    S("C2L_PutOnOrPutOffSeasonIcon", (F(1, "type", K.INT32), F(2, "id", K.INT32))),
    S("L2C_PutOnOrPutOffSeasonIcon", (F(1, "code", K.ENUM), F(2, "putOnHeadIcon", K.INT32),
        F(3, "putOnSceneIcon", K.INT32))),
    S("C2L_SeasonIconStatusUp", (F(1, "type", K.INT32), F(2, "id", K.INT32))),
    S("L2C_SeasonIconStatusUp", (F(1, "code", K.ENUM), F(2, "type", K.INT32), F(3, "id", K.INT32))),
    S("C2L_Account", (F(1, "opt", K.ENUM), F(2, "values", K.INT32, repeated=True),
        F(3, "strvals", K.STRING, repeated=True))),
    S("L2C_Account", (F(1, "result", K.ENUM), F(2, "opt", K.ENUM))),
)}
