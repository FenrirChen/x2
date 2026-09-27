"""Persisted hero read model for login and HeroAll query."""

from x2server.messages.core import HERO_ALL, HERO_DATA, HERO_GOD_EQUIP, INT_PAIR
from x2server.messages.favor import HERO_FETTER, HERO_ARCHIVE
from .favor import catalog, favor_state
from functools import lru_cache
from x2server.network.dispatcher import DispatchContext, OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.types import DecodedPacket

from .store import PlayerStore


def encode_hero_data(hero: dict) -> bytes:
    # TEMPORARY_COMPAT: the client initializes GoldEquipAttr for every owned hero.
    # An empty nested object represents no equipped god item; omitting it throws.
    from .progression import hero_skills
    from x2server.messages.battle import HERO_SKILL
    values = {k:v for k,v in hero.items() if k in ("id", "state", "level", "star", "exp")}
    artifact = hero.get("god_equip")
    god_equip = HERO_GOD_EQUIP.encode({"id": artifact["id"], "level": artifact["level"],
        "star": artifact["star"], "godEquipAttr": b"",
        "jewel": [INT_PAIR.encode({"Key": int(slot), "Value": int(item)})
                  for slot, item in sorted(artifact.get("jewels", {}).items(), key=lambda pair: int(pair[0]))]}) if artifact else b""
    data = favor_catalog()
    level = favor_state(hero, next((r["InitialLevel"] for r in data["favorabilityhero"]
                                    if r["HeroID"] == hero["id"]), 1))["level"]
    archives = [HERO_ARCHIVE.encode({"fileId": row["FilesID"],
        "status": (2 if row["FilesID"] in hero.get("favor_archives", []) or
                   row["TriggerType"]["value"] == 1 and level >= row["TypeNumber"] else 0)})
        for row in data["favorabilityfiles"] if row["HeroID"] == hero["id"]]
    fetters = [HERO_FETTER.encode({"posId": row["FettersID"],
        "level": hero.get("favor_fetters", {}).get(str(row["FettersID"]), 0)})
        for row in data["favorabilityfetters"] if row["HeroID"] == hero["id"] and row.get("IsOpen") == 1]
    return HERO_DATA.encode({**values, "godEquip": god_equip,
        "equips": [INT_PAIR.encode({"Key": e["position"], "Value": e["equip_id"]})
                   for e in hero.get("equips", [])],
        "heroSkills": [HERO_SKILL.encode(s) for s in hero_skills(hero)],
        "fetters": fetters, "archives": archives})


@lru_cache(maxsize=1)
def favor_catalog():
    return catalog()


def encode_hero_all(snapshot: dict) -> bytes:
    return HERO_ALL.encode({"heros": [encode_hero_data(hero) for hero in snapshot.get("heroes", [])]})


class HeroService:
    def __init__(self, store: PlayerStore) -> None:
        self.store = store

    async def query_all(self, context: DispatchContext, packet: DecodedPacket) -> OutboundMessage:
        if context.session.player_id is None:
            raise ProtocolError("hero query requested before login")
        snapshot = self.store.get(context.session.player_id)["snapshot"]
        return OutboundMessage("L2C_HeroAll", {"heros": [encode_hero_data(hero)
            for hero in snapshot.get("heroes", [])]})
