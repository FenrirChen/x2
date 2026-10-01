"""Native 2.4 Achv* protocol; static Serialize tags verified from libil2cpp."""
from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema as S

ACHIEVEMENT_IDS = (('AchvDetialData', 344, 347), ('AchvOverView', 345, 348),
                   ('AchvReward', 346, 349), ('AchvPointReward', 358, 359), ('ReCountAchv', 811, 812))
ACHV = S('AchvData', tuple(F(i, n, K.INT32) for i, n in enumerate(
    ('achvProgress', 'status', 'achvId', 'stage'), 1)))
OVERVIEW = S('AchvOverViewData', (F(1, 'achvType', K.INT32), F(2, 'achvProgress', K.INT32)))
ACHIEVEMENT_SCHEMAS = {
    'C2L_ReCountAchv': S('C2L_ReCountAchv', (F(1, 'conditions', K.MESSAGE, repeated=True),
        F(2, 'extras', K.INT32, repeated=True), F(3, 'extra', K.INT32))),
    'L2C_ReCountAchv': S('L2C_ReCountAchv', (F(1, 'code', K.INT32),)),
    'C2L_AchvOverView': S('C2L_AchvOverView', ()),
    'L2C_AchvOverView': S('L2C_AchvOverView', (F(1, 'code', K.INT32),
        F(2, 'achvOverViewData', K.MESSAGE, repeated=True), F(3, 'achvPoint', K.INT32),
        F(4, 'achvPointMax', K.INT32), F(5, 'achvPointRewardList', K.INT32, repeated=True))),
    'C2L_AchvDetialData': S('C2L_AchvDetialData', (F(1, 'achvType', K.INT32),
        F(2, 'startIndex', K.INT32), F(3, 'endIndex', K.INT32))),
    'L2C_AchvDetialData': S('L2C_AchvDetialData', (F(1, 'code', K.INT32),
        F(2, 'achvDataList', K.MESSAGE, repeated=True), F(3, 'achvType', K.INT32))),
    'L2C_AchvUpdate': S('L2C_AchvUpdate', (F(1, 'achvDataList', K.MESSAGE, repeated=True),
                                         F(2, 'achvPoint', K.INT32))),
}
for name, field in [('AchvReward', 'achvId'), ('AchvPointReward', 'achvPointId')]:
    ACHIEVEMENT_SCHEMAS['C2L_' + name] = S('C2L_' + name, (F(1, field, K.INT32),))
    ACHIEVEMENT_SCHEMAS['L2C_' + name] = S('L2C_' + name, (F(1, 'code', K.INT32),
        F(2, 'status', K.INT32), F(3, field, K.INT32), F(4, 'rewardData', K.MESSAGE)))
