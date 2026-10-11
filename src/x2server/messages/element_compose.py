"""元素合成 (element compose) wire contract.

Field order and count come from the client's own IL2CPP metadata (namespace
CommandX2, ProtoMember declaration order), matching the recovered methods in
ElementComposeModule:

    C2L_ElementCompose (495) elementID, missionID, layer, count
    L2C_ElementCompose (496) code, composeItem (KeyValuePair<Int32,Int32>), count

``ElementComposeModule_CanCompose(int32_t formulaID)`` and
``GetElementListByOrder(int32_t formulaID)`` show the request's ``elementID`` is
an ElementSynthesis formula id (420501..420564), not one raw element item:
``GetOrderByItemList`` maps a three-element pick to that id and
``GetElementListByOrder`` maps it back. ``composeItem`` echoes the produced
(itemId, num) pairs, which is what ``OnElementCompose`` opens BagGotItemWnd with.
"""

from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema as S

C2L_ELEMENT_COMPOSE = S("C2L_ElementCompose", (
    F(1, "elementID", K.INT32), F(2, "missionID", K.INT32),
    F(3, "layer", K.INT32), F(4, "count", K.INT32)))

L2C_ELEMENT_COMPOSE = S("L2C_ElementCompose", (
    F(1, "code", K.ENUM), F(2, "composeItem", K.MESSAGE, repeated=True),
    F(3, "count", K.INT32)))

ELEMENT_COMPOSE_SCHEMAS = {schema.name: schema for schema in (
    C2L_ELEMENT_COMPOSE,
    L2C_ELEMENT_COMPOSE,
)}