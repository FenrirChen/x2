"""Native FriendData and friendship TCP messages (client 2.4)."""
from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema as S

SOCIAL_IDS = (("SendFriendReq",453,454), ("SendFriendCoin",434,435),
              ("ReceiveFriendCoin",436,437), ("UpdateFriends",449,450),
              ("QueryChatFriendsTime",672,671))
INT_LONG = S('ContainerIntInt64Proto', (F(1,'idx',K.INT32),F(2,'val',K.INT64)))
LONG_INT = S('ContainerInt64IntProto', (F(1,'idx',K.INT64),F(2,'val',K.INT32)))
LONG_LONG = S('ContainerInt64Int64Proto', (F(1,'idx',K.INT64),F(2,'val',K.INT64)))
FRIEND_DATA = S('FriendDataProto', (
    F(1,'SendPlayer',K.MESSAGE,True),F(2,'ReceivePlayer',K.MESSAGE,True),
    F(3,'SendCount',K.INT32),F(4,'ReceiveCount',K.INT32),
    F(5,'FriendPos',K.MESSAGE,True),F(6,'FriendPoint',K.MESSAGE,True),
    F(7,'FriendChat',K.MESSAGE,True),F(8,'LastRecommendTime',K.INT32),F(9,'SendReqCount',K.INT32)))
SOCIAL_SCHEMAS = {s.name:s for s in (INT_LONG,LONG_INT,LONG_LONG,FRIEND_DATA)}
ASSIST_DATA = S('AssistData', (
    F(1,'assistPlayerID',K.INT64),F(2,'friendShipLevel',K.INT32),F(3,'playerName',K.STRING),
    F(4,'heroID',K.INT32),F(5,'heroSkinID',K.INT32),F(6,'heroStar',K.INT32),F(7,'heroPower',K.INT64),
    F(8,'assistTimes',K.INT32),F(9,'heroLevel',K.INT32),F(10,'battleData',K.MESSAGE),F(11,'md5',K.STRING)))
SOCIAL_SCHEMAS[ASSIST_DATA.name]=ASSIST_DATA
for name,_,_ in SOCIAL_IDS:
    request = (F(1,'playerid',K.INT64,True),) if name != 'QueryChatFriendsTime' else ()
    if name in ('SendFriendCoin','ReceiveFriendCoin'):
        request += (F(2,'friendPoint',K.INT32,True),)
    response = (F(1,'code',K.ENUM),)
    if name in ('SendFriendReq','SendFriendCoin','ReceiveFriendCoin'):
        response += (F(2,'playerid',K.INT64,True),)
    elif name == 'QueryChatFriendsTime':
        response = (F(1,'chatFriendsTime',K.MESSAGE,True),)
    SOCIAL_SCHEMAS['C2L_'+name] = S('C2L_'+name,request)
    SOCIAL_SCHEMAS['L2C_'+name] = S('L2C_'+name,response)
