"""Recovered terminal communication and moments wire contracts."""

from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema as S

TERMINAL_IDS = (("QueryPrivateLetter", 476, 477),
                ("UpdatePrivateLetter", 478, 479),
                ("AddBlackNpc", 480, 481),
                ("ReplyLetter", 482, 483),
                ("QueryNpcBlog", 484, 485),
                ("ReplyNpcBlog", 486, 487),
                ("LikeNpcBlog", 488, 489))

PAIR = S("KeyValuePair_Int32_Int32", (F(1, "Key", K.INT32), F(2, "Value", K.INT32)))
LETTER_DATA = S("NpcLetterData", (F(1, "letterID", K.INT32),
                                  F(2, "replyID", K.INT32), F(3, "index", K.INT32)))
LETTER_GROUP = S("NpcLetterGroup", (F(1, "startTime", K.INT32),
                                    F(2, "letterData", K.MESSAGE, True), F(3, "status", K.INT32)))
LETTER_BOX = S("NpcLetterBox", (F(1, "heroID", K.INT32),
                                F(2, "groups", K.MESSAGE, True), F(3, "lastReplyTime", K.INT32)))
SYSTEM_LETTER = S("SystemLetter", (F(1, "letterID", K.INT32),
                                    F(2, "startTime", K.INT32), F(3, "heroID", K.INT32)))
CHAT_GROUP = S("NpcChatGroup", (F(1, "chatGroupID", K.INT32), F(2, "chat", K.MESSAGE, True)))
BLOG_GROUP = S("NpcBlogGroup", (F(1, "groupID", K.INT32), F(2, "startTime", K.INT32),
                                F(3, "likeTime", K.INT32), F(4, "chatGroup", K.MESSAGE, True)))
BLOG_BOX = S("NpcBlogBox", (F(1, "heroID", K.INT32), F(2, "blogGroup", K.MESSAGE, True)))

TERMINAL_SCHEMAS = {s.name: s for s in (
    PAIR, LETTER_DATA, LETTER_GROUP, LETTER_BOX, SYSTEM_LETTER, CHAT_GROUP, BLOG_GROUP, BLOG_BOX,
    S("C2L_QueryPrivateLetter", (F(1, "type", K.ENUM),)),
    S("L2C_QueryPrivateLetter", (F(1, "code", K.ENUM), F(2, "letterBoxs", K.MESSAGE, True),
                                  F(3, "systemLetters", K.MESSAGE, True), F(4, "blcakHeros", K.MESSAGE, True))),
    S("C2L_UpdatePrivateLetter", (F(1, "heroID", K.INT32), F(2, "letterID", K.INT32), F(3, "isEnd", K.BOOL))),
    S("L2C_UpdatePrivateLetter", (F(1, "code", K.ENUM), F(2, "letterBox", K.MESSAGE),
                                   F(3, "blcakHeros", K.MESSAGE, True))),
    S("C2L_AddBlackNpc", (F(1, "heroID", K.INT32),)),
    S("L2C_AddBlackNpc", (F(1, "code", K.ENUM), F(2, "blcakHeros", K.MESSAGE, True))),
    S("C2L_ReplyLetter", (F(1, "heroID", K.INT32), F(2, "groupID", K.INT32),
                           F(3, "letterID", K.INT32), F(4, "replyID", K.INT32))),
    S("L2C_ReplyLetter", (F(1, "code", K.ENUM), F(2, "letterBox", K.MESSAGE),
                           F(3, "blcakHeros", K.MESSAGE, True), F(4, "heroID", K.INT32),
                           F(5, "groupID", K.INT32), F(6, "letterID", K.INT32), F(7, "replyID", K.INT32))),
    S("C2L_QueryNpcBlog", ()),
    S("L2C_QueryNpcBlog", (F(1, "code", K.ENUM), F(2, "blogBox", K.MESSAGE, True),
                            F(3, "blcakHeros", K.MESSAGE, True))),
    S("C2L_ReplyNpcBlog", (F(1, "heroID", K.INT32), F(2, "groupID", K.INT32),
                            F(3, "chatGroupID", K.INT32), F(4, "replyID", K.INT32))),
    S("L2C_ReplyNpcBlog", (F(1, "code", K.ENUM), F(2, "blogBox", K.MESSAGE),
                            F(3, "blcakHeros", K.MESSAGE, True))),
    S("C2L_LikeNpcBlog", (F(1, "heroID", K.INT32), F(2, "groupID", K.INT32))),
    S("L2C_LikeNpcBlog", (F(1, "code", K.ENUM), F(2, "blogBox", K.MESSAGE),
                           F(3, "blcakHeros", K.MESSAGE, True))),
)}
