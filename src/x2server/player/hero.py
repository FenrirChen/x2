"""Persisted hero read model for login and HeroAll query."""

from x2server.messages.core import HERO_ALL, HERO_DATA
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
    return HERO_DATA.encode({**values, "godEquip": b"", "heroSkills": [HERO_SKILL.encode(s) for s in hero_skills(hero)]})


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
