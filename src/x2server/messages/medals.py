"""Native MedalOpt 411/412 and PlayerDataProto.MedalSystem (field 7)."""
from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema as S

MEDAL_PACK = S('MedalPackProto', (F(1, 'Medal', K.MESSAGE, repeated=True),))
MEDAL_SHOW = S('MedalShowProto', (F(1, 'Position', K.MESSAGE, repeated=True),))
MEDAL_SYSTEM = S('MedalSystemProto', (F(1, 'MedalPack', K.MESSAGE), F(2, 'MedalShow', K.MESSAGE)))
MEDAL_SCHEMAS = {
    'C2L_MedalOpt': S('C2L_MedalOpt', (F(1, 'pos', K.MESSAGE, repeated=True),)),
    'L2C_MedalOpt': S('L2C_MedalOpt', (F(1, 'code', K.INT32),)),
}
