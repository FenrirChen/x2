"""Evidence-bounded shop listings and purchases for the recovered 809 goods."""

from __future__ import annotations

import hashlib
import logging
import json
from datetime import datetime, timedelta, timezone
from importlib.resources import files

from x2server.messages.economy import ECONOMY_SCHEMAS, GOODS
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY

from .economy import UnresolvedEconomy


LOGGER = logging.getLogger("x2.shop")


class ShopService:
    """Serve only goods whose static GoodsID-to-ItemID link is explicit."""

    SHOP_ID = 809
    CURRENCY_TYPE = 902
    CURRENCY_ITEM = 1237902
    COMPAT_STOCK = 999999

    def __init__(self, store, economy):
        self.store = store
        self.economy = economy
        shop = economy.shops[self.SHOP_ID]
        groups = set(shop["GoodsGroupId"])
        by_quick_buy = {item["QuickBuyID"]: item["ItemID"] for item in economy.items.values()
                        if item.get("QuickBuyID")}
        self.offers = {}
        for row in economy.catalog["goods"]:
            if row["GroupID"] not in groups:
                continue
            item_id = by_quick_buy.get(row["GoodsID"])
            if (item_id is None or row.get("ShopResourceType", {}).get("value") != self.CURRENCY_TYPE
                    or type(row.get("ItemPrice")) is not int or row["ItemPrice"] <= 0
                    or row.get("Limited") is not None):
                continue
            self.offers[row["GoodsID"]] = (item_id, row["ItemPrice"], row.get("GoodsTag", {}).get("value", 0))
        if len(self.offers) != 15:
            raise ValueError("shop 809 static goods evidence changed")
        # Restore only the requested random shop. Other speculative community
        # shop catalogs stay retired; shop 809 keeps its separate static route.
        random_shop = json.loads(files("x2server").joinpath(
            "data/random_shop_801.json").read_text(encoding="utf-8"))
        compat = {"shops": {"801": random_shop["goods"]}}
        self.retired_shop_ids = set(range(801, 812)) - {self.SHOP_ID, 801}
        self.compat_offers = {}
        self.compat_disabled = []
        for shop_id, rows in compat["shops"].items():
            for row in rows:
                item_id = row["itemId"]
                item = economy.items.get(item_id, {})
                kind = item.get("ItemType", {}).get("value")
                deliverable = (item_id in economy.CURRENCIES or item_id == 1237900 or
                    kind in economy.STACKABLE_REWARD_TYPES or
                    kind == 16 and item.get("ItemUseScence", {}).get("value") == 1)
                if (not deliverable or type(row.get("num")) is not int or row["num"] <= 0 or
                        type(row.get("price")) is not int or row["price"] <= 0):
                    self.compat_disabled.append((int(shop_id), row["goodsId"]))
                    continue
                if row.get("randomPool"):
                    pool = random_shop["pools"].get(row["randomPool"], [])
                    if not pool or any(economy.items.get(i, {}).get("ItemType", {}).get("value") != 12
                                       for i in pool):
                        self.compat_disabled.append((int(shop_id), row["goodsId"]))
                        continue
                    row["poolItems"] = pool
                self.compat_offers[(int(shop_id), row["goodsId"])] = row
        with store.db:
            store.db.execute("""CREATE TABLE IF NOT EXISTS shop_purchase_counts (
                player_id INTEGER NOT NULL, goods_id INTEGER NOT NULL, quantity INTEGER NOT NULL,
                PRIMARY KEY(player_id,goods_id))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS shop_receipts (
                request_key TEXT PRIMARY KEY, player_id INTEGER NOT NULL, response BLOB NOT NULL)""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS shop_compat_counts (
                player_id INTEGER NOT NULL, shop_id INTEGER NOT NULL, goods_id INTEGER NOT NULL,
                period TEXT NOT NULL, quantity INTEGER NOT NULL,
                PRIMARY KEY(player_id,shop_id,goods_id,period))""")
            # Earlier 801 purchases without a limit were stored for a lifetime.
            # Count them against today before switching every slot to daily stock.
            old_counts = store.db.execute("""SELECT player_id, goods_id, quantity
                FROM shop_compat_counts WHERE shop_id=801 AND period='lifetime'""").fetchall()
            for player_id, goods_id, quantity in old_counts:
                store.db.execute("""INSERT INTO shop_compat_counts VALUES (?,?,?,?,?)
                    ON CONFLICT(player_id,shop_id,goods_id,period)
                    DO UPDATE SET quantity=quantity+excluded.quantity""",
                    (player_id, 801, goods_id, self._period(3), quantity))
            store.db.execute("DELETE FROM shop_compat_counts WHERE shop_id=801 AND period='lifetime'")
            store.db.execute("""CREATE TABLE IF NOT EXISTS shop_refreshes (
                player_id INTEGER, shop_id INTEGER, period TEXT, count INTEGER,
                PRIMARY KEY(player_id,shop_id,period))""")

    def handlers(self):
        return {name: self.handle for name in ("C2L_ShopGoods", "C2L_QueryGoodsInfo",
            "C2L_BuyGoods", "C2L_RefreshShop", "C2L_QueryReCommendShop",
            "C2L_PaymentStore", "C2L_RechargeInfo")}

    def _count(self, player_id, goods_id):
        row = self.store.db.execute("SELECT quantity FROM shop_purchase_counts WHERE player_id=? AND goods_id=?",
                                    (player_id, goods_id)).fetchone()
        return row[0] if row else 0

    def _goods(self, player_id, goods_id):
        item, price, tag = self.offers[goods_id]
        return {"goodsId": goods_id, "itemId": item, "num": 1, "price": price,
            "originalPrice": price, "currencyType": self.CURRENCY_TYPE,
            "canBuyTimes": self.COMPAT_STOCK, "hasBuyTimes": self._count(player_id, goods_id),
            "goodsTag": tag, "limited": 0}

    def _period(self, limited):
        local = datetime.fromtimestamp(int(self.economy.clock()), timezone(timedelta(hours=8)))
        if limited == 3:
            return local.strftime("day:%Y-%m-%d")
        if limited == 2:
            year, week, _ = local.isocalendar()
            return f"week:{year}-{week}"
        if limited == 1:
            return local.strftime("month:%Y-%m")
        return "lifetime"

    def _compat_count(self, player_id, shop_id, row):
        period = self._compat_period(shop_id, row)
        count = self.store.db.execute("""SELECT quantity FROM shop_compat_counts
            WHERE player_id=? AND shop_id=? AND goods_id=? AND period=?""",
            (player_id, shop_id, row["goodsId"], period)).fetchone()
        return min(count[0], 1) if count and shop_id == 801 else (count[0] if count else 0)

    def _compat_period(self, shop_id, row):
        return self._period(3 if shop_id == 801 else row.get("limited"))

    def _compat_goods(self, player_id, shop_id, row):
        row = self._stock_row(player_id, shop_id, row)
        price = row["price"]
        return {"goodsId": row["goodsId"], "itemId": self._compat_item_id(shop_id, row, player_id),
            "num": row["num"], "price": price, "originalPrice": price,
            "currencyType": row["currency"], "canBuyTimes": 1 if shop_id == 801 or row.get("limited") else self.COMPAT_STOCK,
            "hasBuyTimes": self._compat_count(player_id, shop_id, row),
            "goodsTag": row.get("goodsTag") or 0, "limited": 3 if shop_id == 801 else row.get("limited") or 0}

    def _refresh_count(self, player, shop):
        row = self.store.db.execute("SELECT count FROM shop_refreshes WHERE player_id=? AND shop_id=? AND period=?", (player, shop, self._period(3))).fetchone()
        return row[0] if row else 0

    def _refresh_price(self, player, shop):
        count = self._refresh_count(player, shop)
        config = self.economy.shops[shop]
        intervals = config["RefreshInterval"]
        tier = max((i for i, start in enumerate(intervals) if count + 1 >= start), default=0)
        return config["RefreshPrice"][tier]

    def _stock_row(self, player, shop, row):
        # Slot identity and daily purchase count stay fixed; the full content,
        # quantity and pricing tuple rotates together, excluding exchange slots.
        if shop != 801 or row.get("poolItems") or row["itemId"] in self.economy.CURRENCIES:
            return row
        rows = [r for (s, _), r in sorted(self.compat_offers.items()) if s == shop
                and not r.get("poolItems") and r["itemId"] not in self.economy.CURRENCIES]
        index = next(i for i, r in enumerate(rows) if r["goodsId"] == row["goodsId"])
        donor = rows[(index + self._refresh_count(player, shop)) % len(rows)]
        return {**donor, "goodsId": row["goodsId"]}

    def _compat_item_id(self, shop_id, row, player_id=0):
        """Keep a random slot's displayed and delivered shard identical today."""
        pool = row.get("poolItems")
        if not pool:
            return row["itemId"]
        seed = f"{self._period(3)}:{shop_id}:{row['goodsId']}".encode()
        index = (int.from_bytes(hashlib.sha256(seed).digest()[:8], "big") + self._refresh_count(player_id, shop_id)) % len(pool)
        return pool[index]

    # Purchasing gold/expedition (item 1237901/1237900) must also tick the matching
    # daily task: 630018 E_BuyGold (CompleteType 9, value 901) / 630017 E_BuyPower
    # (CompleteType 8, value 900). The value is the item's Item.EffData entry. The
    # client only tracks this locally, so without a server event the "buy gold" row
    # reverts to 0/N on the next task query.
    CURRENCY_TASK_EVENTS = {1237901: (9, 901), 1237900: (8, 900)}

    def _fire_currency_task(self, player_id, item_id, buy_num, key):
        event = self.CURRENCY_TASK_EVENTS.get(item_id)
        if event is not None:
            self.economy._event(player_id, f"buy-currency:{key}", event[0], event[1], buy_num)

    async def handle(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("shop requested before login")
        name = CORE_MESSAGE_REGISTRY.name_for(packet.message_id)
        request = ECONOMY_SCHEMAS[name].decode(packet.body)
        response_name = name.replace("C2L_", "L2C_", 1)
        if name == "C2L_QueryReCommendShop":
            from .recommendations import recommend
            return OutboundMessage(response_name, recommend(self.economy, player_id))
        if name in ("C2L_PaymentStore", "C2L_RechargeInfo"):
            # Optional catalogues have no recoverable local entries. Respond so the
            # shop page does not wait indefinitely for an unregistered request.
            return OutboundMessage(response_name, {"code": 10})
        if name == "C2L_ShopGoods":
            shop_id = request.get("shopId", 0)
            LOGGER.info("shop listing requested shop_id=%s player_id=%s", shop_id, player_id)
            if shop_id in self.retired_shop_ids:
                return OutboundMessage(response_name, {"code": 10, "shopId": shop_id,
                    "NextRefreshTime": 0, "RefreshTimes": 0, "RefreshPrice": 0, "goods": []})
            if shop_id != self.SHOP_ID and not any(k[0] == shop_id for k in self.compat_offers):
                return OutboundMessage(response_name, {"code": 13, "shopId": shop_id})
            goods = ([GOODS.encode(self._goods(player_id, goods_id)) for goods_id in sorted(self.offers)]
                if shop_id == self.SHOP_ID else [GOODS.encode(self._compat_goods(player_id, shop_id, row))
                for (id_, _), row in sorted(self.compat_offers.items()) if id_ == shop_id])
            return OutboundMessage(response_name, {"code": 10, "shopId": shop_id,
                "NextRefreshTime": 0, "RefreshTimes": self._refresh_count(player_id, shop_id),
                "RefreshPrice": self._refresh_price(player_id, shop_id) if shop_id == 801 else 0, "goods": goods})
        if name == "C2L_QueryGoodsInfo":
            goods_id = request.get("goodsId", 0)
            if goods_id in self.offers:
                shop_id, offer = self.SHOP_ID, self._goods(player_id, goods_id)
            else:
                found = next(((id_, row) for (id_, offer_id), row in self.compat_offers.items()
                              if offer_id == goods_id), None)
                if found is None:
                    return OutboundMessage(response_name, {"code": 13, "goodsId": goods_id})
                shop_id, row = found
                offer = self._compat_goods(player_id, shop_id, row)
            return OutboundMessage(response_name, {"code": 10, "shopId": shop_id,
                "goodsId": goods_id, "price": offer["price"],
                "originalPrice": offer["originalPrice"], "hasBuyTimes": offer["hasBuyTimes"],
                "canBuyTimes": offer["canBuyTimes"], "itemNum": offer["num"],
                "currencyType": offer["currencyType"]})
        if name == "C2L_RefreshShop":
            if request.get("shopId") == 801:
                key = hashlib.sha256(f"{player_id}:{context.session.session_id}:{packet.header.request_id}:refresh".encode() + packet.body).hexdigest()
                schema = ECONOMY_SCHEMAS[response_name]
                cached = self.store.db.execute("SELECT response FROM shop_receipts WHERE request_key=? AND player_id=?", (key, player_id)).fetchone()
                if cached:
                    return OutboundMessage(response_name, schema.decode(cached[0]), pushes=self.economy.pushes(player_id))
                with self.economy.transaction():
                    snapshot = self.store.get(player_id)["snapshot"]
                    cost = self._refresh_price(player_id, 801)
                    if snapshot.get("crystal", 0) < cost:
                        return OutboundMessage(response_name, {"code": 13, "shopId": 801})
                    snapshot["crystal"] -= cost
                    self.economy.save_snapshot(player_id, snapshot)
                    self.store.db.execute("INSERT INTO shop_refreshes VALUES (?,?,?,1) ON CONFLICT(player_id,shop_id,period) DO UPDATE SET count=count+1", (player_id, 801, self._period(3)))
                    goods = [GOODS.encode(self._compat_goods(player_id, 801, row))
                             for (shop_id, _), row in sorted(self.compat_offers.items()) if shop_id == 801]
                    values = {"code": 10, "shopId": 801, "NextRefreshTime": 0,
                        "RefreshTimes": self._refresh_count(player_id, 801),
                        "RefreshPrice": self._refresh_price(player_id, 801), "goods": goods}
                    self.store.db.execute("INSERT INTO shop_receipts VALUES (?,?,?)", (key, player_id, schema.encode(values)))
                return OutboundMessage(response_name, values, pushes=self.economy.pushes(player_id))
            # Shop 809 has no CanManualRefresh rule in ShopConfig.
            return OutboundMessage(response_name, {"code": 13, "shopId": request.get("shopId", 0)})
        return self._buy(context, packet, request)

    def _buy(self, context, packet, request):
        player_id = context.session.player_id
        shop_id, goods_id, buy_num = (request.get("shopId", 0), request.get("goodsId", 0),
                                      request.get("buyNum", 0))
        reject = OutboundMessage("L2C_BuyGoods", {"code": 13, "shopId": shop_id,
            "goodsId": goods_id, "buyNum": buy_num})
        if shop_id != self.SHOP_ID:
            return self._buy_compat(context, packet, request, reject)
        if (shop_id != self.SHOP_ID or goods_id not in self.offers or not 1 <= buy_num <= 999
                or self._count(player_id, goods_id) + buy_num > self.COMPAT_STOCK):
            return reject
        item_id, unit_price, _ = self.offers[goods_id]
        cost = unit_price * buy_num
        request_key = hashlib.sha256(
            f"{player_id}:{context.session.session_id}:{packet.header.request_id}:shop".encode()
            + packet.body).hexdigest()
        schema = ECONOMY_SCHEMAS["L2C_BuyGoods"]
        cached = self.store.db.execute("SELECT response FROM shop_receipts WHERE request_key=? AND player_id=?",
                                       (request_key, player_id)).fetchone()
        if cached:
            return OutboundMessage("L2C_BuyGoods", schema.decode(cached[0]),
                pushes=self.economy.pushes(player_id))
        try:
            with self.store.db:
                player = self.store.get(player_id)
                snapshot = player["snapshot"]
                if snapshot.get("crystal", 0) < cost:
                    return reject
                snapshot["crystal"] -= cost
                self.economy.save_snapshot(player_id, snapshot)
                reward = self.economy._grant(player_id, f"shop:{request_key}", {item_id: buy_num})
                self.store.db.execute("""INSERT INTO shop_purchase_counts VALUES (?,?,?)
                    ON CONFLICT(player_id,goods_id) DO UPDATE SET quantity=quantity+excluded.quantity""",
                    (player_id, goods_id, buy_num))
                values = {"code": 10, "itemId": item_id, "itemNum": buy_num,
                    "goodsId": goods_id, "price": unit_price, "originalPrice": unit_price,
                    "hasBuyTimes": self._count(player_id, goods_id),
                    "rewardData": self.economy.reward_bytes(reward), "buyNum": buy_num,
                    "changeItemID": self.CURRENCY_ITEM, "shopId": shop_id}
                self.store.db.execute("INSERT INTO shop_receipts VALUES (?,?,?)",
                                      (request_key, player_id, schema.encode(values)))
                self.economy._event(player_id, f"shop-buy:{request_key}", 24,
                                    goods_id, buy_num, self.SHOP_ID)
                self._fire_currency_task(player_id, item_id, buy_num, request_key)
                self.economy.dp.shop(player_id, item_id, self.CURRENCY_TYPE, buy_num, cost, request_key)
        except UnresolvedEconomy as exc:
            LOGGER.info("purchase rejected goods=%s reason=%s", goods_id, exc)
            return reject
        return OutboundMessage("L2C_BuyGoods", values, pushes=self.economy.pushes(player_id))

    def _buy_compat(self, context, packet, request, reject):
        player_id = context.session.player_id
        shop_id, goods_id, buy_num = request.get("shopId", 0), request.get("goodsId", 0), request.get("buyNum", 0)
        row = self.compat_offers.get((shop_id, goods_id))
        if row:
            row = self._stock_row(player_id, shop_id, row)
        if not row or type(buy_num) is not int or not 1 <= buy_num <= 99:
            return reject
        cap = 1 if shop_id == 801 or row.get("limited") else self.COMPAT_STOCK
        key = hashlib.sha256(f"{player_id}:{context.session.session_id}:{packet.header.request_id}:compat-shop".encode()
                             + packet.body).hexdigest()
        schema = ECONOMY_SCHEMAS["L2C_BuyGoods"]
        cached = self.store.db.execute("SELECT response FROM shop_receipts WHERE request_key=? AND player_id=?",
                                       (key, player_id)).fetchone()
        if cached:
            return OutboundMessage("L2C_BuyGoods", schema.decode(cached[0]), pushes=self.economy.pushes(player_id))
        currency = row["currencyItemId"]
        total = row["price"] * buy_num
        item_count = row["num"] * buy_num
        try:
            with self.economy.transaction():
                if self._compat_count(player_id, shop_id, row) + buy_num > cap:
                    return reject
                if currency == 1237900:
                    self.economy.refresh_stamina(player_id)
                snapshot = self.store.get(player_id)["snapshot"]
                if currency in self.economy.CURRENCIES:
                    field = self.economy.CURRENCIES[currency]
                    if snapshot.get(field, 0) < total:
                        return reject
                    snapshot[field] -= total
                    self.economy.save_snapshot(player_id, snapshot)
                elif currency == 1237900:
                    if snapshot.get("mobility", {}).get("power", 0) < total:
                        return reject
                    snapshot["mobility"]["power"] -= total
                    self.economy.save_snapshot(player_id, snapshot)
                else:
                    paid = self.store.db.execute("""UPDATE inventory SET quantity=quantity-?
                        WHERE player_id=? AND item_id=? AND quantity>=?""", (total, player_id, currency, total))
                    if not paid.rowcount:
                        return reject
                item_id = self._compat_item_id(shop_id, row, player_id)
                granted = self.economy._grant(player_id, f"compat-shop:{key}", {item_id: item_count})
                period = self._compat_period(shop_id, row)
                self.store.db.execute("""INSERT INTO shop_compat_counts VALUES (?,?,?,?,?)
                    ON CONFLICT(player_id,shop_id,goods_id,period)
                    DO UPDATE SET quantity=quantity+excluded.quantity""",
                    (player_id, shop_id, goods_id, period, buy_num))
                values = {"code": 10, "shopId": shop_id, "goodsId": goods_id,
                    "itemId": item_id, "itemNum": item_count, "buyNum": buy_num,
                    "price": row["price"], "originalPrice": row["price"],
                    "hasBuyTimes": self._compat_count(player_id, shop_id, row),
                    "changeItemID": currency, "rewardData": self.economy.reward_bytes(granted)}
                self.store.db.execute("INSERT INTO shop_receipts VALUES (?,?,?)",
                                      (key, player_id, schema.encode(values)))
                self.economy._event(player_id, f"compat-shop:{key}", 24, goods_id, buy_num, shop_id)
                self._fire_currency_task(player_id, item_id, buy_num, key)
                self.economy.dp.shop(player_id, item_id, row["currency"], buy_num, total, key)
        except UnresolvedEconomy as exc:
            LOGGER.info("compat purchase rejected goods=%s reason=%s", goods_id, exc)
            return reject
        return OutboundMessage("L2C_BuyGoods", values, pushes=self.economy.pushes(player_id))
