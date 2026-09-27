"""Client-table collection awards with a durable, one-time claim ledger."""
from importlib.resources import files
import json

from x2server.messages.lobby import LOBBY_SCHEMAS
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from .economy import UnresolvedEconomy


class CollectionService:
    def __init__(self, store, economy):
        self.store, self.economy = store, economy
        catalog = json.loads(files("x2server").joinpath("data/collection_catalog.json").read_text(encoding="utf-8"))
        self.awards = {row["CollectionID"]: row for row in catalog["collection"]}
        known = {row["GiftGroup"] for row in economy.catalog["gifts"]}
        economy.catalog["gifts"].extend(row for row in catalog["gifts"] if row["GiftGroup"] not in known)
        with store.db:
            store.db.execute("""CREATE TABLE IF NOT EXISTS collection_awards (
                player_id INTEGER NOT NULL, award_id INTEGER NOT NULL,
                PRIMARY KEY(player_id, award_id))""")

    def handlers(self):
        return {"C2L_QueryCollectionAward": self.query,
                "C2L_GetCollectionAward": self.claim}

    def claimed(self, player_id):
        return [row[0] for row in self.store.db.execute(
            "SELECT award_id FROM collection_awards WHERE player_id=? ORDER BY award_id", (player_id,))]

    async def query(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("collection queried before login")
        return OutboundMessage("L2C_QueryCollectionAward", {"awardID": self.claimed(player_id)})

    async def claim(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("collection claimed before login")
        request = LOBBY_SCHEMAS["C2L_GetCollectionAward"].decode(packet.body)
        award_id = request.get("collectionAwardID", 0)
        reject = OutboundMessage("L2C_GetCollectiontAward", {"code": 13, "awardID": self.claimed(player_id)})
        row = self.awards.get(award_id)
        if row is None or row["CollectionType"]["value"] != 1 or row["ConditionType"]["value"] != 1:
            return reject
        try:
            rewards = self.economy.gifts([row["GiftGroup"]])
            with self.economy.transaction():
                owned = {hero["id"] for hero in self.store.get(player_id)["snapshot"].get("heroes", [])
                         if hero.get("state") == 2}
                if not set(row["CompleteValue1"]) <= owned:
                    return reject
                cursor = self.store.db.execute("INSERT OR IGNORE INTO collection_awards VALUES (?,?)",
                                               (player_id, award_id))
                if not cursor.rowcount:
                    return reject
                self.economy._grant(player_id, f"collection:{award_id}", rewards)
        except UnresolvedEconomy:
            return reject
        return OutboundMessage("L2C_GetCollectiontAward", {"code": 10,
            "awardID": self.claimed(player_id), "rewardData": self.economy.reward_bytes(rewards)},
            pushes=self.economy.pushes(player_id))
