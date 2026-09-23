"""2.4 first-battle wire contract; nested serializers verified against IL2CPP."""
from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema as S

PROFILE_HERO = S("ProfileHero", (F(1, "heroId", K.INT32), F(2, "leader", K.INT32), F(3, "state", K.INT32)))
HERO_SKILL = S("HeroSkill", (F(1, "id", K.INT32), F(2, "level", K.INT32)))
HERO_ATTR = S("HeroAttrCount", tuple(F(n, name, K.INT64) for n, name in enumerate(("atk", "def", "hp", "sp"), 1)))
HERO_ATTR_ADD = S("HeroAttrAdd", (F(1, "attrId", K.INT32), F(2, "attrValue", K.INT64)))
FIGHT_HERO = S("FightHero", (
    F(1, "id", K.INT32), F(2, "state", K.INT32), F(3, "level", K.INT32), F(4, "star", K.INT32),
    F(5, "heroGodEquip", K.MESSAGE), F(7, "exp", K.INT32), F(8, "heroSkill", K.MESSAGE, repeated=True),
    F(9, "attrAdd", K.MESSAGE, repeated=True), F(12, "heroAttrCount", K.MESSAGE)))
# FightData deliberately starts at field 2 (Serialize 0x350E1C0).
FIGHT_DATA = S("FightData", (F(2, "fightHeros", K.MESSAGE, repeated=True), F(3, "missionId", K.INT32),
    F(4, "dropData", K.MESSAGE), F(7, "CRIDmg", K.INT32)))
DROP_DATA = S("FightDropData", (F(1, "dropValues", K.INT32, repeated=True), F(2, "missionId", K.INT32)))
FIGHT_PROFILE = S("FightDataProfile", (F(1, "missionId", K.INT32), F(2, "layer", K.INT32),
    F(7, "chapterId", K.INT32), F(10, "randomSeed", K.INT32), F(13, "sceneId", K.INT32),
    F(20, "isProfileValid", K.BOOL)))
CHECKOUT = S("C2L_CheckoutMainMission", (F(1, "chapterId", K.INT32), F(2, "sectionId", K.INT32),
    F(4, "success", K.BOOL), F(6, "expertMode", K.BOOL), F(8, "checkGm", K.BOOL),
    F(9, "fightTime", K.INT32), F(10, "heros", K.MESSAGE, repeated=True)))
BATTLE_SCHEMAS = {
    "C2L_CheckoutMainMission": CHECKOUT,
    "C2L_CheckoutMainMissionSign": S("C2L_CheckoutMainMissionSign", (
        F(1, "checkout", K.MESSAGE), F(2, "battleFileBytes", K.BYTES),
        F(3, "battleFileString", K.STRING), F(4, "sendTag", K.BOOL))),
    "L2C_CheckoutMainMission": S("L2C_CheckoutMainMission", (
        F(1, "result", K.ENUM), F(2, "success", K.BOOL), F(3, "rewardData", K.MESSAGE),
        *(F(i, name, K.INT32, repeated=True) for i, name in (
            (4, "heroIDList"), (5, "heroLevel"), (6, "heroExp"), (7, "heroUpLevelNum"),
            (11, "heroFavorExp"), (12, "heroAddFavorExp"), (13, "heroFavorLevel"))),
        F(8, "roleLevel", K.INT32), F(9, "UpLevelNum", K.INT32), F(10, "roleExp", K.INT32),
        F(14, "heroFullLevel", K.BOOL, repeated=True), F(15, "favorFullLevel", K.BOOL, repeated=True),
        F(16, "playerFullLevel", K.BOOL), F(18, "fightTimeLength", K.INT32))),
    "C2L_FightKillInfo": S("C2L_FightKillInfo", (F(1, "sectionId", K.INT32),)),
    "L2C_FightKillInfo": S("L2C_FightKillInfo", (F(1, "code", K.ENUM),)),
    "C2L_FightDropData": S("C2L_FightDropData", (F(1, "missionId", K.INT32),
        F(2, "chapterId", K.INT32), F(3, "layer", K.INT32), F(10, "expertMode", K.BOOL),
        F(14, "sceneId", K.INT32))),
    "L2C_FightDropData": S("L2C_FightDropData", (F(1, "result", K.ENUM), F(2, "uuid", K.STRING),
        F(3, "sign", K.BYTES), F(4, "data", K.BYTES))),
    "C2L_DelFightProfile": S("C2L_DelFightProfile", (F(1, "sectionID", K.INT32), F(2, "checkout", K.BOOL))),
    "L2C_DelFightProfile": S("L2C_DelFightProfile", (F(1, "code", K.ENUM), F(2, "sectionID", K.INT32))),
    "C2L_FightData": S("C2L_FightData", (F(1, "heros", K.MESSAGE, repeated=True), F(2, "missionId", K.INT32),
        F(3, "chapter", K.INT32), F(4, "expertMode", K.BOOL), F(5, "checkGm", K.BOOL),
        F(6, "isFromProfile", K.BOOL), F(11, "randomSeed", K.INT32), F(13, "sceneId", K.INT32))),
    "L2C_FightData": S("L2C_FightData", (F(1, "result", K.ENUM), F(2, "uuid", K.STRING),
        F(3, "sign", K.BYTES), F(4, "data", K.BYTES), F(5, "fightDataProfile", K.MESSAGE),
        F(19, "playerLevel", K.INT32))),
}
