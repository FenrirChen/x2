"""关卡内商店 (in-battle shop): the stock the client cannot compute itself.

The live client asked message 157 (``C2L_RequestInsideBattleShop``) with
``shopID 400201, level 4, sectionId 2110151`` and the server had no handler, so it
answered nothing at all and the shop panel stayed empty - a known message with no
reply is invisible in the game, it just looks like an empty store.

Three of the four inputs are recovered from the client's own tables
(``tools/build_battle_shop.py`` writes them into data/battle_shop.json):

* ``table/MazeShop``: ``ShopID`` + ``FloorInterval`` -> the six ``GroupID`` slots
  of that floor, e.g. 400201 floor 4 -> 30201..30206.
* ``table/CurrencyType``: TpyeId 903 = 棱镜 (item 1237903), the currency the
  in-stage shop spends and that is cleared at settlement.
* ``table/Item``: every 用途场景 = 迷宫内 item, i.e. the consumables, 义体药剂,
  元素结晶 and 圣遗物 (the actual purchaseable 增益).

The fourth input - which group sold which item, and at what price - was decided by
the original server and is gone. Slots are therefore paired positionally with the
item families and priced by declared Revival policy; both are recorded in the
catalog so a wrong guess stays visible.

Money handling: the in-stage currency is earned and spent *inside* the battle, and
the client never reports the amount to the server (there is no message for it in
the client's registry; only the local ``DropCurrencyProto``/``ProfileCurrency``
counters exist). The server therefore records the purchase and echoes the price it
sent, and the client settles its own prism counter. Nothing is charged to the
persistent bag, because the item is cleared at settlement anyway.
"""
from __future__ import annotations

import json
import logging
import random
import time
from importlib.resources import files

from x2server.messages.battle_shop import BATTLE_SHOP_SCHEMAS, SHOP_ITEM
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError

LOGGER = logging.getLogger("x2.battle.shop")

# 10 = accepted, 13 = refused; the same pair every other X2 response uses.
OK, REFUSED = 10, 13

# In-stage stock is offered again on every re-open (it is deterministic per
# shop+floor), so no purchase cap is invented. See the module docstring.
UNLIMITED = 999999


class BattleShopService:
    def __init__(self, store, economy=None):
        self.store = store
        self.economy = economy
        catalog = json.loads(
            files("x2server").joinpath("data/battle_shop.json").read_text(encoding="utf-8"))
        self.shops = catalog["shops"]
        self.slots = catalog["slots"]
        self.currency = catalog["currency"]
        self.discount = int(catalog["provenance"].get("discount", 100))
        with store.db:
            store.db.execute("""CREATE TABLE IF NOT EXISTS battle_shop_visits (
                player_id INTEGER NOT NULL, shop_id INTEGER NOT NULL, level INTEGER NOT NULL,
                section_id INTEGER NOT NULL, created_at INTEGER NOT NULL,
                PRIMARY KEY(player_id, shop_id, level))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS battle_shop_purchases (
                player_id INTEGER NOT NULL, shop_id INTEGER NOT NULL, level INTEGER NOT NULL,
                item_id INTEGER NOT NULL, num INTEGER NOT NULL, price INTEGER NOT NULL,
                money_type INTEGER NOT NULL, section_id INTEGER NOT NULL, created_at INTEGER NOT NULL)""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS battle_shop_pickups (
                player_id INTEGER NOT NULL, item_id INTEGER NOT NULL, num INTEGER NOT NULL,
                section_id INTEGER NOT NULL, created_at INTEGER NOT NULL)""")

    # ---- data -------------------------------------------------------------

    def shop_ids(self) -> tuple[int, ...]:
        return tuple(sorted(int(shop) for shop in self.shops))

    def resolve_floor(self, shop_id: int, level: int) -> tuple[int, list[int]] | None:
        """The floor row to serve: the exact one, else the deepest one not above it.

        The client's ``level`` is the battle's current layer; the table only has
        rows for the floors a shop exists on, so a level between two rows uses the
        earlier row rather than answering nothing.
        """
        shop = self.shops.get(str(shop_id))
        if not shop:
            return None
        floors = {int(key): value for key, value in shop["floors"].items()}
        if not floors:
            return None
        chosen = level if level in floors else max((f for f in floors if f <= level), default=min(floors))
        return chosen, list(floors[chosen]["groups"])

    def stock(self, shop_id: int, level: int) -> list[dict] | None:
        """Six deterministic offers, one per recovered shop slot."""
        resolved = self.resolve_floor(shop_id, level)
        if resolved is None:
            return None
        floor, groups = resolved
        offers = []
        for index, slot in enumerate(self.slots):
            pool = slot["items"]
            if not pool:
                continue
            # Deterministic per (shop, floor, slot): re-opening the same shop must
            # show the same stock instead of re-rolling for free.
            pick = random.Random(f"{shop_id}:{floor}:{slot['slot']}").choice(pool)
            offers.append({
                "itemId": pick["itemId"], "num": 1, "price": slot["price"],
                "discount": self.discount, "moneyType": self.currency["moneyType"],
                "groupId": groups[index] if index < len(groups) else 0,
                "star": pick["star"],
            })
        return offers

    def _visited(self, player_id: int, shop_id: int, level: int):
        return self.store.db.execute(
            "SELECT 1 FROM battle_shop_visits WHERE player_id=? AND shop_id=? AND level=?",
            (player_id, shop_id, level)).fetchone()

    # ---- handlers ---------------------------------------------------------

    def handlers(self):
        return {
            "C2L_RequestInsideBattleShop": self.request_shop,
            "C2L_BuyInsideBattleShopItems": self.buy,
            "C2L_RecordInsideBattleItems": self.record_items,
        }

    async def request_shop(self, context, packet):
        """Answer the stock query; a known shop always answers, even when empty."""
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("in-battle shop requested before login")
        request = BATTLE_SHOP_SCHEMAS["C2L_RequestInsideBattleShop"].decode(packet.body)
        shop_id, level = request.get("shopID", 0), request.get("level", 0)
        section = request.get("sectionId", 0)
        offers = self.stock(shop_id, level)
        if offers is None:
            # An unknown shop is not an empty shop: saying so keeps a missing table
            # row attributable instead of looking like a shop that sells nothing.
            LOGGER.info("in-battle shop unknown shop=%s level=%s section=%s player=%s",
                        shop_id, level, section, player_id)
            return OutboundMessage("L2C_RequestInsideBattleShop",
                                   {"result": REFUSED, "shopID": shop_id, "level": level})
        with self.store.db:
            self.store.db.execute(
                "INSERT OR REPLACE INTO battle_shop_visits VALUES (?,?,?,?,?)",
                (player_id, shop_id, level, section, int(time.time())))
        LOGGER.info("in-battle shop stock shop=%s level=%s section=%s player=%s items=%s",
                    shop_id, level, section, player_id, [offer["itemId"] for offer in offers])
        return OutboundMessage("L2C_RequestInsideBattleShop", {
            "result": OK, "shopID": shop_id, "level": level,
            "shopItems": [SHOP_ITEM.encode(offer) for offer in offers],
        })

    async def buy(self, context, packet):
        """Record one in-battle purchase and echo the price that was quoted.

        The second wired field of ``C2L_BuyInsideBattleShopItems`` is declared
        ``itemNum``, but the live client does NOT put a quantity there: every
        captured purchase (logs/packets.jsonl, 155 at 00:16:35..00:17:11) sent
        ``itemNum = 1297`` for items priced 30/60/80/180, and 1297 was exactly the
        in-stage 棱镜 counter the shop header displayed. It is therefore the amount
        of the shop currency the client holds, and the server answers with the
        authoritative price. Reading it as "buy 1297 of these" made every purchase
        fail - which is what the client showed as 购买失败 before this comment
        existed.
        """
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("in-battle purchase before login")
        request = BATTLE_SHOP_SCHEMAS["C2L_BuyInsideBattleShopItems"].decode(packet.body)
        item_id = request.get("itemID", 0)
        wallet = request.get("itemNum", 0)
        section = request.get("sectionId", 0)
        refuse = OutboundMessage("L2C_BuyInsideBattleShopItems",
                                 {"result": REFUSED, "itemID": item_id, "itemNum": 0})
        visit = self.store.db.execute(
            # ORDER BY rowid, not created_at: two floors opened in the same second
            # would otherwise resolve to whichever row SQLite happened to return,
            # and the buy would be checked against the wrong floor's stock.
            "SELECT shop_id, level FROM battle_shop_visits WHERE player_id=? ORDER BY rowid DESC LIMIT 1",
            (player_id,)).fetchone()
        if visit is None:
            LOGGER.info("in-battle purchase without an open shop item=%s player=%s",
                        item_id, player_id)
            return refuse
        shop_id, level = visit["shop_id"], visit["level"]
        offer = next((o for o in (self.stock(shop_id, level) or []) if o["itemId"] == item_id), None)
        if offer is None:
            LOGGER.info("in-battle purchase of an item this shop does not sell item=%s shop=%s level=%s player=%s",
                        item_id, shop_id, level, player_id)
            return refuse
        if wallet and wallet < offer["price"]:
            # The client already knows the price it displayed, so this only fires if
            # the two disagree; refusing keeps the client's own counter honest.
            LOGGER.info("in-battle purchase refused for price item=%s price=%s wallet=%s player=%s",
                        item_id, offer["price"], wallet, player_id)
            return refuse
        with self.store.db:
            self.store.db.execute("INSERT INTO battle_shop_purchases VALUES (?,?,?,?,?,?,?,?,?)",
                                  (player_id, shop_id, level, item_id, offer["num"],
                                   offer["price"], offer["moneyType"], section or 0,
                                   int(time.time())))
            if self.economy:
                run = self.store.db.execute("SELECT uuid,section_id FROM economy_runs WHERE player_id=? AND settled=0 ORDER BY rowid DESC LIMIT 1", (player_id,)).fetchone()
                if run and (not section or section == run["section_id"]):
                    static = self.economy.entry_catalog.sections.get(run["section_id"], {})
                    chapter = static.get("ChapterID", 0)
                    key = f"{run['uuid']}:shop:{shop_id}:{level}:{item_id}:{wallet}"
                    self.economy.dp.observe(player_id, chapter, key, "buy", item_id, offer["num"])
                    self.economy.dp.observe(player_id, chapter, key, "spend", offer["moneyType"], offer["price"])
                    self.economy.dp.refresh(player_id, chapter)
        LOGGER.info("in-battle purchase shop=%s level=%s item=%s x%s price=%s type=%s wallet=%s player=%s",
                    shop_id, level, item_id, offer["num"], offer["price"], offer["moneyType"],
                    wallet, player_id)
        return OutboundMessage("L2C_BuyInsideBattleShopItems", {
            "result": OK, "itemID": item_id, "itemNum": offer["num"],
            "itemPrice": offer["price"], "priceType": offer["moneyType"],
        })

    async def record_items(self, context, packet):
        """Acknowledgement for the items the client picked up in the stage.

        Nothing is granted: these are the stage-internal items (棱镜 and the shop
        goods) that the client clears at settlement. The row exists so a pickup is
        visible in the save when a purchased effect is questioned later.
        """
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("in-battle pickup before login")
        request = BATTLE_SHOP_SCHEMAS["C2L_RecordInsideBattleItems"].decode(packet.body)
        item_id = request.get("itemID", 0)
        count = request.get("itemNum", 0)
        with self.store.db:
            self.store.db.execute("INSERT INTO battle_shop_pickups VALUES (?,?,?,?,?)",
                                  (player_id, item_id, count, 0, int(time.time())))
        LOGGER.info("in-battle pickup item=%s x%s player=%s", item_id, count, player_id)
        return OutboundMessage("L2C_RecordInsideBattleItems", {"result": OK})
