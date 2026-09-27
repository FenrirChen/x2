"""Favor protocol fields recovered from the client message declarations."""
from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema as S

FAVOR_IDS = (("AddFavor", 274, 277), ("UpgradeFetters", 498, 499),
    ("UnlockHeroArchives", 500, 501), ("QueryHeroArchives", 502, 503),
    ("FavorBreak", 651, 652), ("QueryHeroJournal", 657, 658))

HERO_FETTER = S("HeroFetter", (F(1, "posId", K.INT32), F(2, "level", K.INT32)))
HERO_ARCHIVE = S("HeroArchive", (F(1, "fileId", K.INT32), F(2, "status", K.INT32)))
FAVOR = S("Favor", (F(1, "level", K.INT32), F(2, "exp", K.INT32)))
FAVOR_MAP_ENTRY = S("FavorMapEntry", (F(1, "Key", K.INT32), F(2, "Value", K.MESSAGE)))
FAVOR_CHANGE_INFO = S("FavorChangeInfo", (F(1, "beforeLevel", K.INT32),
    F(2, "beforeExp", K.INT32), F(3, "afterLevel", K.INT32),
    F(4, "afterExp", K.INT32), F(5, "heroID", K.INT32), F(6, "type", K.ENUM)))

FAVOR_SCHEMAS = {
    "C2L_AddFavor": S("C2L_AddFavor", (F(1, "opt", K.INT32), F(2, "optionId", K.INT32),
        F(3, "heroId", K.INT32), F(4, "num", K.INT32))),
    "L2C_AddFavor": S("L2C_AddFavor", (F(1, "code", K.ENUM), F(2, "opt", K.INT32),
        F(3, "optionId", K.INT32), F(4, "heroId", K.INT32), F(5, "exp", K.INT32),
        F(6, "level", K.INT32), F(7, "newExp", K.INT32), F(8, "newLevel", K.INT32),
        F(9, "giftsTimes", K.INT32))),
    "C2L_UpgradeFetters": S("C2L_UpgradeFetters", (F(1, "mainHeroId", K.INT32), F(2, "positionId", K.INT32))),
    "L2C_UpgradeFetters": S("L2C_UpgradeFetters", (F(1, "code", K.ENUM), F(2, "mainHeroId", K.INT32), F(3, "positionId", K.INT32))),
    "C2L_UnlockHeroArchives": S("C2L_UnlockHeroArchives", (F(1, "heroID", K.INT32), F(2, "archivesID", K.INT32))),
    "L2C_UnlockHeroArchives": S("L2C_UnlockHeroArchives", (F(1, "code", K.ENUM), F(2, "heroID", K.INT32), F(3, "archivesID", K.INT32))),
    "C2L_QueryHeroArchives": S("C2L_QueryHeroArchives", (F(1, "heroID", K.INT32),)),
    "L2C_QueryHeroArchives": S("L2C_QueryHeroArchives", (F(1, "code", K.ENUM), F(2, "needRefresh", K.BOOL))),
    "C2L_FavorBreak": S("C2L_FavorBreak", (F(1, "heroId", K.INT32),)),
    "L2C_FavorBreak": S("L2C_FavorBreak", (F(1, "code", K.ENUM), F(2, "heroId", K.INT32))),
    "C2L_QueryHeroJournal": S("C2L_QueryHeroJournal", (F(1, "heroId", K.INT32),)),
    "L2C_QueryHeroJournal": S("L2C_QueryHeroJournal", (F(1, "code", K.ENUM),
        F(2, "heroId", K.INT32), F(3, "journal", K.INT32, repeated=True))),
    "L2C_FavorChangeInfo": S("L2C_FavorChangeInfo", (F(1, "data", K.MESSAGE, repeated=True),)),
}
