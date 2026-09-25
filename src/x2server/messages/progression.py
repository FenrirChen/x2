"""2.4 HeroOpt / UpHeroSkill / HeroUpdate serializers; see phase20 report."""
from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema as S

PROGRESSION_SCHEMAS = {s.name: s for s in (
    S("C2L_HeroOpt", (F(1,"id",K.INT32), F(2,"opt",K.ENUM), F(3,"upstarConsumeItemId",K.INT32), F(4,"heroName",K.STRING))),
    S("L2C_HeroOpt", (F(1,"code",K.ENUM), F(2,"id",K.INT64), F(3,"opt",K.ENUM), F(4,"rewardData",K.MESSAGE), F(5,"upstarConsumeItemId",K.INT32))),
    S("C2L_UpHeroSkill", (F(1,"heroId",K.INT32), F(2,"skillId",K.INT32), F(3,"uplevel",K.INT32))),
    S("L2C_UpHeroSkill", (F(1,"code",K.ENUM), F(2,"heroId",K.INT32), F(3,"skillId",K.INT32), F(4,"uplevel",K.INT32))),
    S("L2C_HeroUpdate", (F(1,"code",K.ENUM), F(2,"heros",K.MESSAGE,repeated=True))),
    S("C2L_Artifact", (F(1,"opt",K.ENUM), F(2,"heroId",K.INT32), F(3,"jewelId",K.INT32), F(4,"holeId",K.INT32))),
    S("L2C_Artifact", (F(1,"code",K.ENUM), F(2,"opt",K.ENUM), F(3,"heroId",K.INT32), F(4,"jewelId",K.INT32), F(5,"holeId",K.INT32))),
    S("L2C_UpdatePlayerLevel", (F(1,"beforeLevel",K.INT32), F(2,"afterLevel",K.INT32))),
)}
