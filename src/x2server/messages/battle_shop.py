"""关卡内商店 (in-battle shop) wire contract.

Field order and count come from the client's own IL2CPP metadata, not from a
guess: every generated CommandX2 message declares its ProtoMembers in
declaration order, and the numeric ids and the request bodies already seen on the
wire confirm it (``C2L_RequestInsideBattleShop`` 157 = 08c9b618100418c7e58001
decodes as shopID 400201 / level 4 / sectionId 2110151 in fields 1/2/3).

Recovered runs (tools/il2cpp_type_fields.py, namespace CommandX2):

    C2L_RequestInsideBattleShop  (157) shopID, level, sectionId
    L2C_RequestInsideBattleShop  (160) result, shopID, level, shopItems
    ShopItem                           itemId, _Num, _Price, _Discount,
                                       _MoneyType, _GroupId, _Star
    C2L_BuyInsideBattleShopItems (155) itemID, itemNum, sectionId
    L2C_BuyInsideBattleShopItems (158) result, itemID, itemNum, itemPrice, priceType
    C2L_RecordInsideBattleItems  (156) itemID, itemNum
    L2C_RecordInsideBattleItems  (159) result

``ShopItem`` is nested inside the L2C_RequestInsideBattleShop field run, which is
what fixes its order: the run continues with itemId right after shopItems.
``_MoneyType`` carries a CurrencyType TpyeId (903 = 棱镜), the same numbering the
client's DropCurrencyProto/ProfileCurrency use for in-stage money.
"""

from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema as S

SHOP_ITEM = S("ShopItem", (
    F(1, "itemId", K.INT32),
    F(2, "num", K.INT32),
    F(3, "price", K.INT32),
    F(4, "discount", K.INT32),
    F(5, "moneyType", K.INT32),
    F(6, "groupId", K.INT32),
    F(7, "star", K.INT32),
))

C2L_REQUEST_INSIDE_BATTLE_SHOP = S("C2L_RequestInsideBattleShop", (
    F(1, "shopID", K.INT32), F(2, "level", K.INT32), F(3, "sectionId", K.INT32)))

L2C_REQUEST_INSIDE_BATTLE_SHOP = S("L2C_RequestInsideBattleShop", (
    F(1, "result", K.ENUM), F(2, "shopID", K.INT32), F(3, "level", K.INT32),
    F(4, "shopItems", K.MESSAGE, repeated=True)))

C2L_BUY_INSIDE_BATTLE_SHOP_ITEMS = S("C2L_BuyInsideBattleShopItems", (
    F(1, "itemID", K.INT32), F(2, "itemNum", K.INT32), F(3, "sectionId", K.INT32)))

L2C_BUY_INSIDE_BATTLE_SHOP_ITEMS = S("L2C_BuyInsideBattleShopItems", (
    F(1, "result", K.ENUM), F(2, "itemID", K.INT32), F(3, "itemNum", K.INT32),
    F(4, "itemPrice", K.INT32), F(5, "priceType", K.INT32)))

C2L_RECORD_INSIDE_BATTLE_ITEMS = S("C2L_RecordInsideBattleItems", (
    F(1, "itemID", K.INT32), F(2, "itemNum", K.INT32)))

L2C_RECORD_INSIDE_BATTLE_ITEMS = S("L2C_RecordInsideBattleItems", (F(1, "result", K.ENUM),))

BATTLE_SHOP_SCHEMAS = {schema.name: schema for schema in (
    SHOP_ITEM,
    C2L_REQUEST_INSIDE_BATTLE_SHOP,
    L2C_REQUEST_INSIDE_BATTLE_SHOP,
    C2L_BUY_INSIDE_BATTLE_SHOP_ITEMS,
    L2C_BUY_INSIDE_BATTLE_SHOP_ITEMS,
    C2L_RECORD_INSIDE_BATTLE_ITEMS,
    L2C_RECORD_INSIDE_BATTLE_ITEMS,
)}
