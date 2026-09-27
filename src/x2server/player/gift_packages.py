"""Operator-selected client gift packages and one-time local purchases."""

from __future__ import annotations

import hashlib
import json
import secrets
from collections import Counter
from importlib.resources import files

from x2server.messages.economy import ECONOMY_SCHEMAS, GIFT_PACKAGE_DATA
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError

from .economy import UnresolvedEconomy


class GiftPackageService:
    def __init__(self, store, economy):
        self.store, self.economy = store, economy
        data = json.loads(files("x2server").joinpath("data/selected_gift_packages.json").read_text(encoding="utf-8"))
        self.packages = {row["GiftPackageID"]: row for row in data["packages"]}
        self.gifts = {row["GiftGroup"]: row for row in data["gifts"]}
        if set(self.packages) != set(range(2700000, 2700034)):
            raise ValueError("selected gift package list changed")
        with store.db:
            store.db.execute("""CREATE TABLE IF NOT EXISTS gift_package_claims (
                player_id INTEGER NOT NULL, package_id INTEGER NOT NULL, period TEXT NOT NULL,
                claimed_at INTEGER NOT NULL, PRIMARY KEY(player_id,package_id,period))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS gift_package_receipts (
                request_key TEXT PRIMARY KEY, player_id INTEGER NOT NULL, response BLOB NOT NULL)""")

    def handlers(self):
        return {"C2L_QueryGiftPackage": self.query, "C2L_BuyGiftPackage": self.buy,
                "C2L_RechargeGoodsInfo": self.recharge}

    def _period(self, package):
        if package["GiftPackageType"]["value"] == 2:
            from datetime import datetime, timedelta, timezone
            return datetime.fromtimestamp(self.economy.clock(), timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
        return "once"

    def listing(self, player_id):
        values = []
        for package_id, package in sorted(self.packages.items()):
            claimed = self.store.db.execute("SELECT 1 FROM gift_package_claims WHERE player_id=? AND package_id=? AND period=?",
                (player_id, package_id, self._period(package))).fetchone()
            values.append(GIFT_PACKAGE_DATA.encode({"id": package_id, "state": int(bool(claimed)),
                "unShelves": False}))
        return values

    async def query(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("gift packages queried before login")
        return OutboundMessage("L2C_QueryGiftPackage", {"code": 10, "datas": self.listing(player_id)})

    def _rewards(self, package):
        rewards = Counter()
        for group in package["GiftID"]:
            row = self.gifts[group]
            items, counts = row["GiftValue"], row["Num"]
            if len(items) != len(counts):
                raise UnresolvedEconomy("invalid gift package items")
            kind = row["AwardType"]["value"]
            if kind == 1:
                selected = zip(items, counts)
            elif kind == 2:
                weights = row["Probability"]
                if len(weights) != len(items) or min(weights) < 0 or sum(weights) != 1000:
                    raise UnresolvedEconomy("invalid gift package weights")
                draw = secrets.randbelow(1000)
                index = 0
                for index, weight in enumerate(weights):
                    draw -= weight
                    if draw < 0:
                        break
                selected = [(items[index], counts[index])]
            else:
                raise UnresolvedEconomy("unsupported gift package award")
            for item, count in selected:
                if item not in self.economy.items or type(count) is not int or count <= 0:
                    raise UnresolvedEconomy("unavailable gift package reward")
                rewards[item] += count
        return dict(rewards)

    def _claim(self, context, packet, package_id, *, recharge=False):
        player_id = context.session.player_id
        package = self.packages.get(package_id)
        reply = "L2C_RechargeGoodsInfo" if recharge else "L2C_BuyGiftPackage"
        reject = OutboundMessage(reply, {"code": 13})
        if package is None or (package["CurrencyType"] == 919) != recharge:
            return reject
        if package["GiftPackageType"]["value"] == 3 and self.store.get(player_id)["snapshot"]["level"] < package["Param1"][0]:
            return reject
        period = self._period(package)
        request_key = hashlib.sha256(f"gift:{player_id}:{context.session.session_id}:{packet.header.request_id}".encode()
                                     + packet.body).hexdigest()
        cached = self.store.db.execute("SELECT response FROM gift_package_receipts WHERE request_key=? AND player_id=?",
                                       (request_key, player_id)).fetchone()
        if cached and not recharge:
            return OutboundMessage(reply, ECONOMY_SCHEMAS[reply].decode(cached[0]),
                                   pushes=self.economy.pushes(player_id))
        try:
            rewards = self._rewards(package)
            with self.economy.transaction():
                inserted = self.store.db.execute("INSERT OR IGNORE INTO gift_package_claims VALUES (?,?,?,?)",
                    (player_id, package_id, period, int(self.economy.clock())))
                if not inserted.rowcount:
                    return reject
                price = package.get("Price", 0) if package["CurrencyType"] == 902 else 0
                if price:
                    snapshot = self.store.get(player_id)["snapshot"]
                    if snapshot.get("crystal", 0) < price:
                        raise UnresolvedEconomy("insufficient crystal")
                    snapshot["crystal"] -= price
                    self.economy.save_snapshot(player_id, snapshot)
                self.economy._grant(player_id, f"gift:{package_id}:{period}", rewards)
                if not recharge:
                    result = {"code": 10, "rewardData": self.economy.reward_bytes(rewards),
                              "datas": self.listing(player_id)}
                    self.store.db.execute("INSERT INTO gift_package_receipts VALUES (?,?,?)",
                        (request_key, player_id, ECONOMY_SCHEMAS[reply].encode(result)))
        except UnresolvedEconomy:
            return reject
        if recharge:
            # The client enters an unavailable payment SDK when this reply is 10.
            # A separate gift success push displays the granted contents.
            return OutboundMessage(reply, {"code": 13}, pushes=(OutboundMessage("L2C_BuyGiftPackage",
                {"code": 10, "rewardData": self.economy.reward_bytes(rewards),
                 "datas": self.listing(player_id)}), *self.economy.pushes(player_id)))
        return OutboundMessage(reply, result, pushes=self.economy.pushes(player_id))

    async def buy(self, context, packet):
        if context.session.player_id is None:
            raise ProtocolError("gift package bought before login")
        request = ECONOMY_SCHEMAS["C2L_BuyGiftPackage"].decode(packet.body)
        if request.get("num") != 1:
            return OutboundMessage("L2C_BuyGiftPackage", {"code": 13})
        return self._claim(context, packet, request.get("giftPackageID", 0))

    async def recharge(self, context, packet):
        if context.session.player_id is None:
            raise ProtocolError("gift package recharge before login")
        request = ECONOMY_SCHEMAS["C2L_RechargeGoodsInfo"].decode(packet.body)
        package = next((p for p in self.packages.values() if p["CurrencyType"] == 919
                        and p.get("Price") == request.get("rechargeID")), None)
        return self._claim(context, packet, package["GiftPackageID"] if package else 0, recharge=True)
