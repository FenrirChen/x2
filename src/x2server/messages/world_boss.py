"""Native WorldBoss (main-screen 时序之门) contracts, client 2.4."""
from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema as S

def schema(name, fields):
    return S(name, tuple(F(i, n, k, repeated=rep) for i, (n, k, rep) in enumerate(fields, 1)))

PLAYER = schema('WorldBossPlayer', [(n,k,False) for n,k in (
    ('name',K.STRING),('damage',K.INT64),('order',K.INT32),('leaderTypeId',K.INT32),
    ('id',K.INT64),('showTypeId',K.INT32),('level',K.INT32),('leaderSkinId',K.INT32),('restPoolDamage',K.INT64))])
_INFO_FIELDS = [
    ('bossId',K.STRING,False),('typeId',K.INT32,False),('group',K.STRING,False),
    ('findTime',K.INT64,False),('state',K.ENUM,False),('stateFinishTime',K.INT64,False),
    ('finderId',K.INT64,False),('finderName',K.STRING,False),('worldBoss',K.BOOL,False),
    ('maxHp',K.INT64,False),('curHp',K.INT64,False),('topPlayers',K.MESSAGE,True),
    ('joinRound',K.INT32,False),('selfPlayer',K.MESSAGE,False),('joinPlayerNum',K.INT32,False),('level',K.INT32,False)]
# Native Serialize 0x18342a4 skips field 12; topPlayers starts at 13.
INFO = S('WorldBossInfo', tuple(F(i if i < 12 else i+1,n,k,repeated=rep)
    for i,(n,k,rep) in enumerate(_INFO_FIELDS,1)))
SLOT = S('WorldBossSlotDesProto',(F(1,'Event',K.INT32),F(2,'Value',K.INT32)))
CONTAINER = S('WorldBossContainer',(F(1,'idx',K.INT32),F(2,'val',K.MESSAGE)))
INT_CONTAINER = S('ContainerIntIntProto',(F(1,'idx',K.INT32),F(2,'val',K.INT32)))
QUESTION = S('WorldBossQuestionProto',(F(1,'Step',K.INT32),F(2,'Question',K.MESSAGE,repeated=True)))
QUESTION_EVENT = S('WorldBossQuestionEventProto',(F(1,'ID',K.INT32),F(2,'Event',K.INT32),F(3,'Value',K.INT32)))
SEARCH = S('WorldBossSearchProto',(F(1,'Slots',K.MESSAGE,repeated=True),
    F(2,'WorldBoss',K.MESSAGE,repeated=True),F(3,'WorldBossQuestion',K.MESSAGE,repeated=True),
    F(4,'WorldBossQuestionEvent',K.MESSAGE,repeated=True)))
BOSS_PLAYER = S('WorldBossPlayerProto',(F(1,'Name',K.STRING),F(2,'Damage',K.INT64),F(3,'Order',K.INT32)))
BOSS = schema('WorldBossProto', [(n,k,rep) for n,k,rep in (
    ('BossID',K.STRING,False),('ID',K.INT32,False),('Group',K.STRING,False),('Start',K.INT64,False),
    ('State',K.INT32,False),('FinderId',K.INT64,False),('FinderName',K.STRING,False),('World',K.INT32,False),
    ('StateFinishTime',K.INT64,False),('MaxHP',K.INT64,False),('CurHP',K.INT64,False),
    ('WorldBossPlayer',K.MESSAGE,True),('SelfPlayer',K.MESSAGE,False),('JoinPlayerNum',K.INT32,False),('Level',K.INT32,False))])
DAILY = S('DailyProto',(F(13,'WorldBossSearchTimes',K.INT32),F(14,'WorldBossChallengeTimes',K.INT32),
    F(15,'NormalBossChallengeTimes',K.INT32)))
WORLD_BOSS_SCHEMAS = {
    'C2L_WorldBossSearch':S('C2L_WorldBossSearch',()),
    'L2C_WorldBossSearch':schema('L2C_WorldBossSearch',[(n,k,False) for n,k in (
        ('code',K.ENUM),('bossEvent',K.INT32),('eventVal',K.INT32),('slotIdx',K.INT32),
        ('rewardData',K.MESSAGE),('bossId',K.STRING),('bossGroup',K.STRING))]),
    'C2L_WorldBossOpenSearchChest':S('C2L_WorldBossOpenSearchChest',(F(1,'slotId',K.INT32),)),
    'L2C_WorldBossOpenSearchChest':S('L2C_WorldBossOpenSearchChest',(F(1,'code',K.ENUM),F(2,'slotId',K.INT32),F(3,'rewardData',K.MESSAGE))),
    'C2L_QueryWorldBossInfo':S('C2L_QueryWorldBossInfo',(F(1,'bossId',K.STRING),F(2,'bossGroup',K.STRING))),
    'L2C_QueryWorldBossInfo':S('L2C_QueryWorldBossInfo',(F(1,'code',K.ENUM),F(2,'bossInfos',K.MESSAGE,repeated=True),F(3,'bossId',K.STRING),F(4,'entry',K.STRING))),
    'C2L_WorldBossAct':S('C2L_WorldBossAct',(F(1,'typeId',K.INT32),F(2,'bossid',K.STRING),F(3,'act',K.ENUM),F(4,'value',K.INT64,repeated=True),F(5,'bossGroup',K.STRING))),
    'L2C_WorldBossAct':S('L2C_WorldBossAct',(F(1,'code',K.ENUM),F(2,'bossid',K.STRING),F(3,'act',K.ENUM),F(4,'value',K.INT64,repeated=True))),
    'C2L_WorldBossLetter':S('C2L_WorldBossLetter',(F(1,'slotIdx',K.INT32),F(2,'questIdx',K.INT32),F(3,'answerIdx',K.INT32))),
    'L2C_WorldBossLetter':S('L2C_WorldBossLetter',(F(1,'code',K.ENUM),F(2,'slotIdx',K.INT32),F(3,'questIdx',K.INT32),F(4,'answerIdx',K.INT32),F(5,'rewardData',K.MESSAGE))),
    'C2W_WorldBossAct':S('C2W_WorldBossAct',(F(1,'token',K.STRING),F(2,'bossid',K.STRING),F(3,'act',K.ENUM),F(4,'value',K.INT64,repeated=True),F(5,'playerid',K.INT64),F(6,'skinIds',K.INT64,repeated=True),F(7,'sgsw',K.STRING))),
    'W2C_WorldBossAct':S('W2C_WorldBossAct',(F(1,'code',K.ENUM),F(2,'bossid',K.STRING),F(3,'act',K.ENUM),F(4,'bossInfo',K.MESSAGE))),
    'C2L_WorldBossQuestSelect':S('C2L_WorldBossQuestSelect',(F(1,'slotIdx',K.INT32),F(2,'aOrb',K.INT32))),
    'L2C_WorldBossQuestSelect':S('L2C_WorldBossQuestSelect',(F(1,'code',K.ENUM),F(2,'slotIdx',K.INT32),F(3,'rewardData',K.MESSAGE))),
    'WorldBossInfo':INFO,
    'C2L_WorldBossSelectHero':S('C2L_WorldBossSelectHero',(F(1,'bossId',K.STRING),F(2,'bossGroup',K.STRING),F(3,'heroList',K.INT32,repeated=True))),
    'L2C_WorldBossSelectHero':S('L2C_WorldBossSelectHero',(F(1,'code',K.ENUM),F(2,'bossId',K.STRING),F(3,'bossGroup',K.STRING))),
    'W2C_WorldBossPlayerAct':S('W2C_WorldBossPlayerAct',(F(1,'player',K.MESSAGE),F(2,'bossid',K.STRING),F(3,'act',K.ENUM),F(4,'clubId',K.INT32),F(5,'clubMemberNum',K.INT32))),
}
WORLD_BOSS_IDS = tuple(zip(WORLD_BOSS_SCHEMAS,(407,408,409,410,415,416,417,418,419,420,421,422,471,472,431,701,702,494)))
