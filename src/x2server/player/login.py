"""Evidence-led minimal login; additional snapshot synchronization is separate."""
import logging
import secrets
import time
from typing import Any

from x2server.bootstrap.local_identity import LocalIdentityService
from x2server.messages.core import C2L_LOGIN, BASE_INFO, RECONNECT, STRING_PAIR
from x2server.network.dispatcher import DispatchContext, OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.types import DecodedPacket
from .store import PlayerStore

LOGGER = logging.getLogger("x2.login")


class LoginService:
    def __init__(self, identity: LocalIdentityService, store: PlayerStore) -> None:
        self.identity = identity
        self.store = store

    async def login(self, context: DispatchContext, packet: DecodedPacket) -> OutboundMessage:
        values = C2L_LOGIN.decode(packet.body)
        if not self.identity.validates_game_identity(values.get("id", 0), values.get("token", "")):
            raise ProtocolError("local login authentication failed")
        now = int(time.time())
        player = self.store.login(self.identity.account, values["id"], now)
        context.session.session_id = secrets.token_urlsafe(24)
        context.session.player_id = player["id"]
        result: dict[str, Any] = {"code": 10, "id": player["id"], "loginCount": player["login_count"],
                  "startDataVersion": 0, "serverTime": now, "isCreateRole": player["login_count"] == 1,
                  "logicCode": 0, "sgroupId": "1"}
        # Explicit empty collections for the first controlled compatibility probe.
        for name in ("heroAll", "itemAll", "noticeAll", "cardPool", "heroSkinAll", "growthBase",
                     "rechargeNoticeAll", "equipAll", "taskDaily", "taskWeekly", "taskChallenge", "limitTaskChallenge"):
            result[name] = b""
        LOGGER.info("authenticated login response prepared player=%s login_count=%s",
                    player["id"], player["login_count"])
        push = self.snapshot_push(player)
        return OutboundMessage("L2C_Login", result, pushes=(push,))

    @staticmethod
    def snapshot_push(player: dict[str, Any]) -> OutboundMessage:
        snapshot = player["snapshot"]
        base = BASE_INFO.encode({"Id": player["id"], "NickName": snapshot["nickname"],
            "Level": snapshot["level"], "Show": snapshot.get("show", 1003),
            "Gold": snapshot.get("gold", 0), "Crystal": snapshot.get("crystal", 0),
            "Exp": snapshot.get("exp", 0)})
        return OutboundMessage("PlayerDataProto", {"BaseInfo": base}, data_version=1)

    async def reconnect(self, context: DispatchContext, packet: DecodedPacket) -> OutboundMessage:
        values = RECONNECT.decode(packet.body)
        if not self.identity.validates_game_identity(values.get("id", 0), values.get("token", "")):
            return OutboundMessage("L2C_ReConnect", {"code": 0})
        try:
            player = self.store.get(values["id"])
        except KeyError:
            return OutboundMessage("L2C_ReConnect", {"code": 0})
        context.session.player_id = player["id"]
        # Same-process reconnect keeps the authenticated transport session supplied
        # by the client; a fresh login is required after identity-service restart.
        if not context.session.session_id:
            context.session.session_id = secrets.token_urlsafe(24)
        LOGGER.info("authenticated reconnect player=%s", player["id"])
        return OutboundMessage("L2C_ReConnect", {"code": 10, "id": player["id"],
            "serverTime": int(time.time())})

    async def server_config(self, context: DispatchContext, packet: DecodedPacket) -> OutboundMessage:
        if context.session.player_id is None:
            raise ProtocolError("configuration requested before login")
        # An absent repeated field becomes null in this generated C# decoder.
        # Echo one confirmed constructor default to materialize the list without
        # inventing a table override: ServerData..ctor 0x13CD05C stores 120 at 0x10.
        pair = STRING_PAIR.encode({"key": "PowerBuyNum", "val": "120"})
        LOGGER.info("server configuration response prepared with packaged default")
        return OutboundMessage("L2C_ServerTableConfig", {"code": 10, "keyVal": [pair]})
