"""社团 (Club) TCP 报文的 protobuf schema。

字段取自客户端自己的声明 ``protocol/commandx2_messages.json`` (字段号=声明顺序),
消息号已登记在 ``protocol/recovered_ids.py`` (742..799 的 club 段)。抓包 logs/packets.jsonl
里用户进社团页时客户端发的是 C2L_RecommandClub(744)/C2L_CreateClub(742), 当时服务端
完全没有实现社团, 所以一律收不到回包 —— 本文件只为给 player/club.py 的 handler 提供
编解码形状。

主坑
----
``list<AppConfig>`` 是命令表生成器把类型解析失败的产物, 真实语义是 ``list<int32>``
(QuickJoinClub.clubIds / L2C_ClubActiMainData.receivedLayer / battledSectionIds),
按 repeated int32 编码即可。证据: 同一命令表里 AppConfig 别处只当整型配置键使用,
且离线参考 x2offline/src/server/pbs_replies.inc 的相关字段都是纯数字数组。
"""
from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema as S

# 实现的 C2L/L2C 消息号 (照 MAIL_IDS 的写法留档; 真正注册走 protocol/recovered_ids.py)。
CLUB_IDS = (("CreateClub", 742, 743), ("RecommandClub", 744, 745),
    ("AppalyJoinClub", 746, 747), ("UpdateClubInfo", 748, 749), ("ClubApproval", 750, 751),
    ("UpdateMemberPrivilege", 752, 753), ("DismissMember", 754, 755), ("QuitClub", 756, 757),
    ("ClubActiMainData", 758, 759), ("ClubWishing", 762, 763), ("ClubWishingCount", 764, 765),
    ("ClubWishingDonate", 766, 767), ("ClubWishingReceive", 768, 769),
    ("QuickJoinClub", 786, 787), ("UpdateClubRecruit", 791, 792), ("JoinClubListner", 795, 796),
    ("ClubReceiveReward", 798, 799))

# SimpleClubData (推荐列表里的一行): 字段照 commandx2_messages.json 的声明序。
SIMPLE_CLUB_DATA = S("SimpleClubData", (
    F(1, "clubId", K.INT32), F(2, "name", K.STRING), F(3, "desc", K.STRING),
    F(4, "memNum", K.INT32), F(5, "memLimit", K.INT32), F(6, "score", K.INT32),
    F(7, "autoLevel", K.INT32), F(8, "applyLevel", K.INT32), F(9, "icon", K.INT32)))

CLUB_SCHEMAS = {s.name: s for s in (
    SIMPLE_CLUB_DATA,
    S("C2L_CreateClub", (F(1, "name", K.STRING), F(2, "desc", K.STRING),
                         F(3, "clubIconId", K.INT32))),
    S("L2C_CreateClub", (F(1, "code", K.ENUM), F(2, "clubId", K.INT32), F(3, "opt", K.INT32))),
    S("C2L_RecommandClub", (F(1, "page", K.INT32), F(2, "pageNum", K.INT32))),
    S("L2C_RecommandClub", (F(1, "code", K.ENUM), F(2, "simpleClubData", K.MESSAGE, True),
                            F(3, "pageTotal", K.INT32))),
    S("C2L_AppalyJoinClub", (F(1, "clubId", K.INT32),)),
    S("L2C_AppalyJoinClub", (F(1, "code", K.ENUM), F(2, "result", K.INT32),
                             F(3, "clubId", K.INT32))),
    S("C2L_QuickJoinClub", (F(1, "clubIds", K.INT32, True),)),
    S("L2C_QuickJoinClub", (F(1, "code", K.ENUM), F(2, "result", K.INT32), F(3, "clubId", K.INT32))),
    S("C2L_UpdateClubInfo", (F(1, "name", K.STRING), F(2, "clubIconId", K.INT32),
                             F(3, "notice", K.STRING), F(4, "opt", K.INT32))),
    S("L2C_UpdateClubInfo", (F(1, "code", K.ENUM), F(2, "opt", K.INT32))),
    S("C2L_UpdateClubRecruit", (F(1, "desc", K.STRING), F(2, "applyAbleLevel", K.INT32),
                                F(3, "applyAbleAutoLevel", K.INT32))),
    S("L2C_UpdateClubRecruit", (F(1, "code", K.ENUM),)),
    S("C2L_JoinClubListner", ()), S("L2C_JoinClubListner", (F(1, "code", K.ENUM),)),
    S("C2L_ClubApproval", (F(1, "applyId", K.INT64), F(2, "opt", K.INT32))),
    S("L2C_ClubApproval", (F(1, "code", K.ENUM),)),
    S("C2L_UpdateMemberPrivilege", (F(1, "optedId", K.INT64), F(2, "opt", K.INT32))),
    S("L2C_UpdateMemberPrivilege", (F(1, "code", K.ENUM),)),
    S("C2L_DismissMember", (F(1, "optedId", K.INT64),)),
    S("L2C_DismissMember", (F(1, "code", K.ENUM),)),
    S("C2L_QuitClub", (F(1, "postId", K.INT32),)),
    S("L2C_QuitClub", (F(1, "postId", K.INT32), F(2, "code", K.ENUM))),
    S("C2L_ClubActiMainData", ()),
    # receivedLayer / battledSectionIds 是 list<AppConfig> -> repeated int32 (见模块 docstring)。
    S("L2C_ClubActiMainData", (F(1, "code", K.ENUM), F(2, "challegeCount", K.INT32),
        F(3, "receivedLayer", K.INT32, True), F(4, "scoreRewardFlag", K.INT32),
        F(5, "battledSectionIds", K.INT32, True))),
    S("C2L_ClubReceiveReward", (F(1, "opt", K.INT32), F(2, "param", K.INT32))),
    S("L2C_ClubReceiveReward", (F(1, "code", K.ENUM), F(2, "rewardData", K.MESSAGE),
                                F(3, "param", K.INT32))),
    S("C2L_ClubWishing", (F(1, "itemId", K.INT32),)),
    S("L2C_ClubWishing", (F(1, "code", K.ENUM), F(2, "itemId", K.INT32))),
    S("C2L_ClubWishingCount", ()),
    S("L2C_ClubWishingCount", (F(1, "code", K.ENUM), F(2, "wishingCount", K.INT32),
        F(3, "guildWishGiveCount", K.INT32), F(4, "guildHelpPowerCount", K.INT32))),
    S("C2L_ClubWishingDonate", (F(1, "wishingId", K.INT64), F(2, "wishingTime", K.INT64))),
    S("L2C_ClubWishingDonate", (F(1, "code", K.ENUM), F(2, "wishingId", K.INT64),
                                F(3, "rewardData", K.MESSAGE))),
    S("C2L_ClubWishingReceive", (F(1, "donateId", K.INT64), F(2, "time", K.INT64))),
    S("L2C_ClubWishingReceive", (F(1, "code", K.ENUM), F(2, "donateId", K.INT64),
                                 F(3, "rewardData", K.MESSAGE))),
)}
