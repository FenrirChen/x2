"""All client AppearanceShop goods, with durable currency charges and ownership."""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files

from x2server.messages.appearance import APPEARANCE_SCHEMAS, COMMERCIAL_GOODS
from x2server.messages.lobby import LOBBY_SCHEMAS
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError

from .economy import UnresolvedEconomy


class AppearanceShopService:
    SHOP_TYPE = 1
    CURRENCIES = {902: 1237902, 923: 1237923}

    def __init__(self, store, economy, appearance):
        self.store, self.economy, self.appearance = store, economy, appearance
        catalog = json.loads(files("x2server").joinpath("data/appearance_shop_catalog.json").read_text(encoding="utf-8"))
        self.goods = {row["goodsId"]: row for row in catalog["goods"]}
        if len(self.goods) != 27 or len({row["itemId"] for row in self.goods.values()}) != len(self.goods) or any(
                row["itemId"] not in economy.items for row in self.goods.values()):
            raise ValueError("appearance shop catalog changed")
        with store.db:
            store.db.execute("""CREATE TABLE IF NOT EXISTS appearance_shop_purchases (
                player_id INTEGER NOT NULL, item_id INTEGER NOT NULL, goods_id INTEGER NOT NULL,
                purchased_at INTEGER NOT NULL, PRIMARY KEY(player_id,item_id))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS appearance_shop_receipts (
                request_key TEXT PRIMARY KEY, player_id INTEGER NOT NULL, response BLOB NOT NULL)""")

    def handlers(self):
        return {"C2L_CommercialShopGoods": self.query, "C2L_BuyCommercialGoods": self.buy}

    def listing(self, player_id):
        bought = {row[0] for row in self.store.db.execute(
            "SELECT item_id FROM appearance_shop_purchases WHERE player_id=?", (player_id,))}
        return [COMMERCIAL_GOODS.encode({"goodsId": row["goodsId"], "itemId": row["itemId"],
            "startTime": 0, "endTime": 2147483647, "originalPrice": row["price"],
            "price": row["price"], "currencyType": row["currencyType"],
            "alreadyBuy": int(row["itemId"] in bought), "goodsType": row["goodsType"],
            "preCount": 0, "rechargeID": 0})
            for row in sorted(self.goods.values(), key=lambda r: (r["sort"], r["goodsId"]))]

    async def query(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("appearance shop queried before login")
        request = LOBBY_SCHEMAS["C2L_CommercialShopGoods"].decode(packet.body)
        shop_type = request.get("shopType", 0)
        if shop_type != self.SHOP_TYPE:
            return OutboundMessage("L2C_CommercialShopGoods", {"code": 13, "shopType": shop_type})
        return OutboundMessage("L2C_CommercialShopGoods", {"code": 10, "shopType": shop_type,
            "goods": self.listing(player_id)})

    async def buy(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("appearance shop bought before login")
        request = APPEARANCE_SCHEMAS["C2L_BuyCommercialGoods"].decode(packet.body)
        goods_id, shop_type = request.get("goodsId", 0), request.get("shopType", 0)
        row = self.goods.get(goods_id)
        reject = OutboundMessage("L2C_BuyCommercialGoods", {"code": 13,
            "goodsId": goods_id, "shopType": shop_type})
        if not row or shop_type != self.SHOP_TYPE or request.get("currencyType") != row["currencyType"]:
            return reject
        key = hashlib.sha256(f"appearance:{player_id}:{context.session.session_id}:{packet.header.request_id}".encode()
                             + packet.body).hexdigest()
        schema = APPEARANCE_SCHEMAS["L2C_BuyCommercialGoods"]
        cached = self.store.db.execute("SELECT response FROM appearance_shop_receipts WHERE request_key=? AND player_id=?",
                                       (key, player_id)).fetchone()
        if cached:
            return OutboundMessage("L2C_BuyCommercialGoods", schema.decode(cached[0]),
                pushes=self.economy.pushes(player_id))
        try:
            with self.economy.transaction():
                inserted = self.store.db.execute("INSERT OR IGNORE INTO appearance_shop_purchases VALUES (?,?,?,?)",
                    (player_id, row["itemId"], goods_id, int(self.economy.clock())))
                if not inserted.rowcount:
                    return reject
                currency = self.CURRENCIES[row["currencyType"]]
                if currency == 1237902:
                    snapshot = self.store.get(player_id)["snapshot"]
                    if snapshot.get("crystal", 0) < row["price"]:
                        raise UnresolvedEconomy("insufficient crystal")
                    snapshot["crystal"] -= row["price"]
                    self.economy.save_snapshot(player_id, snapshot)
                else:
                    spent = self.store.db.execute("""UPDATE inventory SET quantity=quantity-?
                        WHERE player_id=? AND item_id=? AND quantity>=?""",
                        (row["price"], player_id, currency, row["price"]))
                    if not spent.rowcount:
                        raise UnresolvedEconomy("insufficient appearance coupons")
                reward = self.economy._grant(player_id, f"appearance-shop:{row['itemId']}",
                                             {row["itemId"]: 1})
                result = {"code": 10, "goodsId": goods_id, "shopType": shop_type,
                          "rewardData": self.economy.reward_bytes(reward)}
                self.store.db.execute("INSERT INTO appearance_shop_receipts VALUES (?,?,?)",
                    (key, player_id, schema.encode(result)))
        except UnresolvedEconomy:
            return reject
        return OutboundMessage("L2C_BuyCommercialGoods", result, pushes=(
            OutboundMessage("L2C_CommercialShopGoods", {"code": 10, "shopType": shop_type,
                "goods": self.listing(player_id)}),
            OutboundMessage("L2C_HeroSkinAll", self.appearance.skin_values(player_id)),
            *self.economy.pushes(player_id)))
