"""Local silent chat contract (2.4 ChatJoin/ChatAway serializers)."""
from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema

CHAT_IDS = (("ChatJoin", 521, 522), ("ChatAway", 527, 528))
CHAT_SCHEMAS = {
    "C2L_ChatJoin": ProtoSchema("C2L_ChatJoin", (
        F(1, "PlayerID", K.INT64), F(2, "name", K.STRING),
        F(3, "iconID", K.INT32), F(6, "channelId", K.INT32))),
    "C2L_ChatAway": ProtoSchema("C2L_ChatAway", (F(1, "isAway", K.BOOL),)),
    **{f"L2C_{name}": ProtoSchema(f"L2C_{name}", (F(1, "code", K.ENUM),))
       for name in ("ChatJoin", "ChatAway")},
}
