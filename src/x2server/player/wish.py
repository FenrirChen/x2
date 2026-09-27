"""Persistent local wish pools with Beijing-time server rotations."""
import hashlib
import json
import secrets
from importlib.resources import files
from datetime import datetime

from x2server.messages.economy import REWARD, REWARD_ITEM
from x2server.protocol.protobuf import FieldKind, ProtoField, ProtoSchema
from x2server.messages.wish import CARD_POOL, WISH_SCHEMAS
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from .progression import catalog
from .server_clock import BEIJING, ServerClock


class WishService:
    POOL_ID = 22201
    ANCHOR = int(datetime(2026, 9, 24, tzinfo=BEIJING).timestamp())
    CLIENT_DISPLAY_OFFSET = 8 * 3600
    TRANSFORM_HERO = ProtoSchema("TransformHero", (
        ProtoField(1, "heroId", FieldKind.INT32), ProtoField(2, "transform", FieldKind.BOOL)))

    def __init__(self, store, economy=None, clock=None):
        self.store, self.economy = store, economy
        self.clock = clock or ServerClock()
        self.catalog = json.loads(files("x2server").joinpath("data/wish_catalog.json").read_text(encoding="utf-8"))
        self.groups = {
            "up": sorted(int(i) for i, v in self.catalog.items() if v["type"] == "E_Up"),
            "limited": sorted(int(i) for i, v in self.catalog.items() if v["type"] == "E_Limited"),
            "jewel": sorted(int(i) for i, v in self.catalog.items() if v["type"] == "E_Jewel"),
        }
        if [len(self.groups[k]) for k in ("up", "limited", "jewel")] != [30, 3, 10]:
            raise ValueError("unexpected recovered wish pool groups")
        with store.db:
            store.db.execute("""CREATE TABLE IF NOT EXISTS wish_state (
                player_id INTEGER NOT NULL, pool_id INTEGER NOT NULL, total INTEGER NOT NULL DEFAULT 0,
                singles INTEGER NOT NULL DEFAULT 0, tens INTEGER NOT NULL DEFAULT 0,
                since_hero INTEGER NOT NULL DEFAULT 0,
                since_top INTEGER NOT NULL DEFAULT 0,
                first_three_star INTEGER NOT NULL DEFAULT 0,
                since_featured INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(player_id,pool_id))""")
            columns = {r[1] for r in store.db.execute("PRAGMA table_info(wish_state)")}
            if "since_featured" not in columns:
                store.db.execute("ALTER TABLE wish_state ADD COLUMN since_featured INTEGER NOT NULL DEFAULT 0")
            store.db.execute("""CREATE TABLE IF NOT EXISTS wish_receipts (
                player_id INTEGER NOT NULL, request_key TEXT NOT NULL, response BLOB NOT NULL,
                PRIMARY KEY(player_id, request_key))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS wish_last_result (
                player_id INTEGER NOT NULL, pool_id INTEGER NOT NULL, response BLOB NOT NULL,
                PRIMARY KEY(player_id,pool_id))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS wish_pity (
                player_id INTEGER NOT NULL, category TEXT NOT NULL,
                since_hero INTEGER NOT NULL DEFAULT 0, since_top INTEGER NOT NULL DEFAULT 0,
                since_featured INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(player_id,category))""")
            # Existing saves kept counters per pool. Seed each shared group
            # once from its furthest saved progress.
            for player_id, pool_id in store.db.execute(
                    "SELECT DISTINCT player_id,pool_id FROM wish_state"):
                if str(pool_id) not in self.catalog:
                    continue
                category = self._pity_category(pool_id)
                if not store.db.execute("SELECT 1 FROM wish_pity WHERE player_id=? AND category=?",
                        (player_id, category)).fetchone():
                    ids = [int(i) for i in self.catalog if self._pity_category(int(i)) == category]
                    maximum = store.db.execute("""SELECT max(since_hero),max(since_top),max(since_featured)
                        FROM wish_state WHERE player_id=? AND pool_id IN ({})""".format(
                            ",".join("?" for _ in ids)), (player_id, *ids)).fetchone()
                    store.db.execute("INSERT INTO wish_pity VALUES (?,?,?,?,?)",
                        (player_id, category, *[int(n or 0) for n in maximum]))

    def _pity_category(self, pool_id):
        kind = self.catalog[str(pool_id)]["type"]
        return "limited" if kind == "E_Limited" else "jewel" if kind == "E_Jewel" else "standard"

    def _banner_counter(self, pool_id, since_hero, since_top):
        return since_hero if self.catalog[str(pool_id)]["type"] == "E_New" else since_top

    def _fail_counter(self, pool_id, since_hero, since_top):
        return since_top if self.catalog[str(pool_id)]["type"] == "E_Jewel" else since_hero

    def state(self, player_id, pool_id=None):
        pool_id = pool_id or self.POOL_ID
        row = self.store.db.execute("SELECT total,singles,tens,since_hero,since_top,first_three_star,since_featured FROM wish_state WHERE player_id=? AND pool_id=?", (player_id,pool_id)).fetchone()
        local = tuple(row) if row else (0, 0, 0, 0, 0, 0, 0)
        shared = self.store.db.execute("SELECT since_hero,since_top,since_featured FROM wish_pity WHERE player_id=? AND category=?",
            (player_id, self._pity_category(pool_id))).fetchone()
        return (local[0], local[1], local[2], *shared[:2], local[5], shared[2]) if shared else local

    def active_periods(self, now=None, player_id=None):
        """Half-open windows beginning at Beijing midnight on 2026-09-24."""
        now = self.clock.now() if now is None else now
        if player_id is None:
            result = {self.POOL_ID: (1, 2_147_483_647)}
        else:
            created = self.store.get(player_id)["created_at"] or now
            result = {self.POOL_ID: (created, created + 7 * 86400)} if created <= now < created + 7 * 86400 else {}
        if now < self.ANCHOR:
            return result
        for kind, days, batch in (("up", 5, 3), ("limited", 14, 1), ("jewel", 5, 2)):
            ids = self.groups[kind]
            span = days * 86400
            round_index = (now - self.ANCHOR) // span
            start = self.ANCHOR + round_index * span
            offset = (round_index * batch) % len(ids)
            for pool_id in ids[offset:offset + batch]:
                result[pool_id] = (start, start + span)
        return result

    def values(self, player_id):
        self.store.get(player_id)
        pools = []
        active = self.active_periods(player_id=player_id)
        for pool_id, (start, end) in active.items():
            total, singles, tens, since_hero, since_top, _, since_featured = self.state(player_id,pool_id)
            # This client renders CardPool dates as UTC clock faces even when
            # Android is set to Asia/Shanghai. Display only is compensated;
            # active_periods() and draw authorization use real Unix seconds.
            display_offset = self.CLIENT_DISPLAY_OFFSET if pool_id != self.POOL_ID else 0
            pools.append(CARD_POOL.encode({"poolId": pool_id, "startTime": start + display_offset,
                "endTime": end + display_offset, "jackpotRate": 10000,
                "oneDrawCount": singles, "tenDrawCount": tens,
                "securityNum": self._banner_counter(pool_id, since_hero, since_top),
                "totalDrawCount": total, "limitValue": since_featured,
                "failCount": self._fail_counter(pool_id, since_hero, since_top),
                "discountDrawCount": 0, "itemIdSecurity": 0}))
        selected = self.POOL_ID if self.POOL_ID in active and self.state(player_id)[0] < 10 else next((i for i in active if i != self.POOL_ID), next(iter(active), 0))
        return {"code": 10, "cardPoolList": pools,
                "drawCountID": self.catalog[str(selected)]["draw_count_id"] if selected else 0,
                "select": selected}

    async def query(self, context, packet):
        if context.session.player_id is None:
            raise ProtocolError("card pool query before login")
        req = WISH_SCHEMAS["C2L_CardPool"].decode(packet.body)
        if req.get("drawPos") != 1:
            return OutboundMessage("L2C_CardPool", {"code": 13})
        return OutboundMessage("L2C_CardPool", self.values(context.session.player_id))

    def _pick(self, pool_id, group="common"):
        prizes = self.catalog[str(pool_id)]["groups"][group]
        return secrets.SystemRandom().choices(prizes,
            weights=[item["weight"] for item in prizes], k=1)[0]

    @staticmethod
    def _reward(prizes, transforms):
        return REWARD.encode({"rewardItem": [REWARD_ITEM.encode({"itemId": prize["item_id"],
            "itemNum": prize["quantity"], "transform": transform})
            for prize, transform in zip(prizes, transforms, strict=True)],
            "transformHero": [WishService.TRANSFORM_HERO.encode({"heroId": prize["item_id"] - 1210000,
                "transform": transform}) for prize, transform in zip(prizes, transforms, strict=True)
                if 1211000 <= prize["item_id"] < 1212000]})

    @classmethod
    def _reward_with_transform_heroes(cls, raw):
        """Complete pre-fix saved results without changing their prize slots."""
        reward = REWARD.decode(raw)
        if reward.get("transformHero"):
            return raw
        heroes = [REWARD_ITEM.decode(item) for item in reward.get("rewardItem", [])]
        reward["transformHero"] = [cls.TRANSFORM_HERO.encode({
            "heroId": item["itemId"] - 1210000, "transform": item.get("transform", False)})
            for item in heroes if 1211000 <= item["itemId"] < 1212000]
        return REWARD.encode(reward)

    async def draw(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("wish before login")
        req = WISH_SCHEMAS["C2L_LuckDraw"].decode(packet.body)
        pool_id = req.get("drawnId", 0)
        count = {0: 1, 1: 10}.get(req.get("drawType", 0))
        failure = {"code": 13, "drawnId": pool_id}
        if pool_id not in self.active_periods(player_id=player_id) or count is None:
            return OutboundMessage("L2C_LuckDraw", failure)
        key = hashlib.sha256(f"{context.session.session_id}:{packet.header.request_id}:wish".encode() + packet.body).hexdigest()
        cached = self.store.db.execute("SELECT response FROM wish_receipts WHERE player_id=? AND request_key=?", (player_id, key)).fetchone()
        if cached:
            return OutboundMessage("L2C_LuckDraw", WISH_SCHEMAS["L2C_LuckDraw"].decode(cached[0]))
        if pool_id == self.POOL_ID and self.state(player_id, pool_id)[0] + count > 10:
            return OutboundMessage("L2C_LuckDraw", failure)
        with self.store.db:
            snapshot = self.store.get(player_id)["snapshot"]
            config = self.catalog[str(pool_id)]
            ticket_id = config["ticket_item_id"]
            ticket_cost = count * config["one_ticket"]
            ticket = self.store.db.execute("SELECT quantity FROM inventory WHERE player_id=? AND item_id=?", (player_id,ticket_id)).fetchone()
            available = ticket_cost if ticket and ticket[0] >= ticket_cost else 0
            crystal_cost = 0 if available else count * config["one_crystal"]
            if snapshot.get("crystal", 0) < crystal_cost:
                return OutboundMessage("L2C_LuckDraw", failure)
            if available:
                self.store.db.execute("UPDATE inventory SET quantity=quantity-? WHERE player_id=? AND item_id=?", (available, player_id,ticket_id))
            snapshot["crystal"] -= crystal_cost
            total, singles, tens, since_hero, since_top, first_three_star, since_featured = self.state(player_id,pool_id)
            prizes, transforms = [], []
            prototypes = {r["hero_id"]: r for r in catalog()["hero_unlock"]}
            security_ids = {r["item_id"] for r in config["groups"]["security"]}
            top_ids = {r["item_id"] for r in config["groups"]["top"]}
            for _ in range(count):
                if pool_id == self.POOL_ID and total == 9 and not first_three_star:
                    prize = self._pick(pool_id, "security")
                elif config["limit_num"] and since_featured >= config["limit_num"] - 1:
                    prize = self._pick(pool_id, "limit")
                elif pool_id != self.POOL_ID and since_top >= config["three_star_security"] - 1:
                    prize = self._pick(pool_id, "top")
                elif pool_id != self.POOL_ID and since_hero >= config["hero_security"] - 1:
                    prize = self._pick(pool_id, "security")
                else:
                    prize = self._pick(pool_id)
                prizes.append(prize)
                item_id, quantity = prize["item_id"], prize["quantity"]
                star = prototypes.get(item_id - 1210000, {}).get("star", 0) if 1211000 <= item_id < 1212000 else 0
                got_security = star >= 3 if config["type"] != "E_Jewel" else item_id in security_ids or item_id in top_ids
                got_top = star >= 5 if config["type"] != "E_Jewel" else item_id in top_ids
                if got_security:
                    first_three_star = 1
                    since_hero = 0
                else:
                    since_hero += 1
                since_top = 0 if got_top else since_top + 1
                since_featured = 0 if item_id in config["limit_items"] else since_featured + 1
                total += 1
                if 1211000 <= item_id < 1212000:
                    hero_id = item_id - 1210000
                    proto = prototypes.get(hero_id)
                    if proto is None:
                        raise ProtocolError("wish hero has no prototype")
                    if any(h["id"] == hero_id for h in snapshot.get("heroes", [])):
                        transforms.append(True)
                        self.store.db.execute("""INSERT INTO inventory VALUES (?,?,?)
                            ON CONFLICT(player_id,item_id) DO UPDATE SET quantity=quantity+excluded.quantity""",
                            (player_id, proto["fragment_item_id"], proto["fragment_count"] * quantity))
                        # PlayerAttrib.Compensate defines the exact ticket
                        # currency and amount for each duplicate hero.
                        self.store.db.execute("""INSERT INTO inventory VALUES (?,?,?)
                            ON CONFLICT(player_id,item_id) DO UPDATE SET quantity=quantity+excluded.quantity""",
                            (player_id, proto["duplicate_ticket_item_id"],
                             proto["duplicate_ticket_count"] * quantity))
                    else:
                        transforms.append(False)
                        snapshot.setdefault("heroes", []).append({"id": hero_id, "state": 2,
                            "level": proto["level"], "star": proto["star"], "exp": 0,
                            "skills": [{"id": i, "level": 1} for i in proto["initial_skills"]],
                            "compat": "REVIVAL_COMPAT"})
                else:
                    transforms.append(False)
                    self.store.db.execute("""INSERT INTO inventory VALUES (?,?,?)
                        ON CONFLICT(player_id,item_id) DO UPDATE SET quantity=quantity+excluded.quantity""",
                        (player_id, item_id, quantity))
            singles += count == 1
            tens += count == 10
            self.store.db.execute("INSERT OR REPLACE INTO wish_state VALUES (?,?,?,?,?,?,?,?,?)",
                                  (player_id, pool_id, total, singles, tens, since_hero, since_top, first_three_star, since_featured))
            self.store.db.execute("INSERT OR REPLACE INTO wish_pity VALUES (?,?,?,?,?)",
                                  (player_id, self._pity_category(pool_id), since_hero, since_top, since_featured))
            self.store.db.execute("UPDATE players SET snapshot=?,revision=revision+1 WHERE id=?",
                                  (json.dumps(snapshot, ensure_ascii=False, sort_keys=True), player_id))
            values = {"code": 10, "drawnId": pool_id, "rewardData": self._reward(prizes, transforms),
                "luckyValue": 0, "oneDrawCount": singles, "tenDrawCount": tens,
                "limitValue": since_featured,
                "securityNum": self._banner_counter(pool_id, since_hero, since_top),
                "luckyValueCurrent": [0],
                "allHeroCardFirstThreeStar": bool(first_three_star)}
            response_bytes = WISH_SCHEMAS["L2C_LuckDraw"].encode(values)
            self.store.db.execute("INSERT INTO wish_receipts VALUES (?,?,?)",
                (player_id, key, response_bytes))
            self.store.db.execute("INSERT OR REPLACE INTO wish_last_result VALUES (?,?,?)",
                (player_id, pool_id, response_bytes))
        from .hero import encode_hero_data
        pushes = list(self.economy.pushes(player_id)) if self.economy else []
        if any(1211000 <= prize["item_id"] < 1212000 for prize in prizes):
            pushes.insert(0, OutboundMessage("L2C_HeroUpdate", {"code": 10,
                "heros": [encode_hero_data(h) for h in self.store.get(player_id)["snapshot"]["heroes"]]}))
        return OutboundMessage("L2C_LuckDraw", values, pushes=tuple(pushes))

    async def result(self, context, packet):
        if context.session.player_id is None:
            raise ProtocolError("wish result before login")
        req = WISH_SCHEMAS["C2L_RequestDrawResult"].decode(packet.body)
        matched = [pool for pool in self.active_periods(player_id=context.session.player_id)
            if req.get("drawnCountID") == self.catalog[str(pool)]["draw_count_id"]]
        if not matched:
            return OutboundMessage("L2C_RequestDrawResult", {"code": 13})
        # Several simultaneously open pools share a drawCountID. Return the
        # most recently drawn compatible pool if the client asks for a result.
        last_pool = self.store.db.execute("SELECT pool_id FROM wish_last_result WHERE player_id=? ORDER BY rowid DESC LIMIT 1",
            (context.session.player_id,)).fetchone()
        pool_id = last_pool[0] if last_pool and last_pool[0] in matched else matched[0]
        _, singles, tens, _, _, _, since_featured = self.state(context.session.player_id, pool_id)
        last = self.store.db.execute("SELECT response FROM wish_last_result WHERE player_id=? AND pool_id=?",
            (context.session.player_id, pool_id)).fetchone()
        reward = self._reward_with_transform_heroes(
            WISH_SCHEMAS["L2C_LuckDraw"].decode(last[0])["rewardData"]) if last else REWARD.encode({})
        return OutboundMessage("L2C_RequestDrawResult", {"code": 10, "drawnId": pool_id,
            "rewardData": reward, "luckyValue": 0,
            "oneDrawCount": singles, "tenDrawCount": tens, "limitValue": since_featured})

    def handlers(self):
        return {"C2L_CardPool": self.query, "C2L_LuckDraw": self.draw,
                "C2L_RequestDrawResult": self.result}
