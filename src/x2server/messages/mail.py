"""Mail request and response shapes verified against the 2.4 client."""
from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema as S

MAIL_IDS = (("MailData", 196, 200), ("ReadMail", 204, 205),
    ("ReceiveAttachment", 197, 206), ("ReceiveAllAttachment", 208, 211),
    ("DelMail", 207, 210), ("DelAllMail", 212, 213))
MAIL_ATTACHMENT = S("L2C_MailAttachmentItems", (F(1, "itemID", K.INT32), F(2, "itemNum", K.INT32)))
MAIL_INFO = S("L2C_MailInfo", (F(1, "id", K.INT64), F(2, "from", K.STRING),
    F(3, "title", K.STRING), F(4, "body", K.STRING), F(5, "state", K.INT32),
    F(6, "time", K.INT64), F(7, "GroupID", K.INT32), F(8, "attachments", K.MESSAGE, repeated=True)))
MAIL_SCHEMAS = {s.name: s for s in (MAIL_ATTACHMENT, MAIL_INFO,
    S("C2L_MailData", (F(1, "pageIndex", K.INT32), F(2, "pageSize", K.INT32))),
    S("L2C_MailData", (F(1, "code", K.ENUM), F(2, "total", K.INT32),
        F(3, "mails", K.MESSAGE, repeated=True))),
    S("C2L_ReadMail", (F(1, "mailid", K.INT64),)),
    S("L2C_ReadMail", (F(1, "code", K.ENUM), F(2, "mailid", K.INT64))),
    S("C2L_ReceiveAttachment", (F(1, "mailid", K.INT64),)),
    S("L2C_ReceiveAttachment", (F(1, "code", K.ENUM), F(2, "rewardData", K.MESSAGE),
        F(3, "mailid", K.INT64))),
    S("C2L_ReceiveAllAttachment", (F(1, "mailids", K.INT64, repeated=True),
        F(2, "rewardData", K.MESSAGE))),
    S("L2C_ReceiveAllAttachment", (F(1, "code", K.ENUM), F(2, "rewardData", K.MESSAGE),
        F(3, "mailids", K.INT64, repeated=True))),
    S("C2L_DelMail", (F(1, "mailid", K.INT64),)),
    S("L2C_DelMail", (F(1, "code", K.ENUM), F(2, "mailid", K.INT64))),
    S("C2L_DelAllMail", ()), S("L2C_DelAllMail", (F(1, "code", K.ENUM),)),
)}
