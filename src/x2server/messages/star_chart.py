"""StarMapProto and star chart requests recovered from the 2.4 client."""
from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema as S

STAR_PAIR = S('ContainerIntIntProto', (F(1, 'Key', K.INT32), F(2, 'Value', K.INT32)))
STAR_MAP = S('StarMapProto', (F(1, 'StarAbility', K.MESSAGE, repeated=True),
    F(2, 'StarSkill', K.MESSAGE, repeated=True), F(3, 'AIPoint', K.INT32)))
STAR_DAILY = S('DailyProto', (F(18, 'AddAIPointCount', K.INT32),))
STAR_CHART_SCHEMAS = {
    'C2L_StarSkillUp': S('C2L_StarSkillUp', (F(1, 'skillID', K.INT32), F(2, 'targetLevel', K.INT32))),
    'L2C_StarSkillUp': S('L2C_StarSkillUp', (F(1, 'code', K.ENUM),
        F(2, 'skillID', K.INT32), F(3, 'targetLevel', K.INT32))),
    'C2L_AutoAddAIPoint': S('C2L_AutoAddAIPoint', (F(1, 'open', K.BOOL),)),
    'L2C_AutoAddAIPoint': S('L2C_AutoAddAIPoint', (F(1, 'code', K.ENUM),)),
    'C2L_AddAIPoint': S('C2L_AddAIPoint', ()),
    'L2C_AddAIPoint': S('L2C_AddAIPoint', (F(1, 'code', K.ENUM),
        F(2, 'AIPoint', K.INT32), F(3, 'AddAIPointCount', K.INT32))),
}
STAR_CHART_IDS = tuple(zip(STAR_CHART_SCHEMAS, (413, 414, 661, 662, 663, 664)))
