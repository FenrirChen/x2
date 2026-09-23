"""Loopback-only quiet channel. No history, delivery, broadcast or persistence."""
import logging

from x2server.messages.chat import CHAT_SCHEMAS
from x2server.network.dispatcher import OutboundMessage


class SilentChatService:
    def handlers(self):
        return {"C2L_ChatJoin": self.join, "C2L_ChatAway": self.away}

    async def join(self, context, packet):
        request = CHAT_SCHEMAS["C2L_ChatJoin"].decode(packet.body)
        valid = request.get("PlayerID") == 1 and request.get("channelId") == 1
        if valid:
            context.session.player_id = 1
        logging.getLogger("x2.chat").info("silent channel join accepted=%s", valid)
        return OutboundMessage("L2C_ChatJoin", {"code": 10 if valid else 13})

    async def away(self, context, packet):
        # Presence changes do not leave the channel or clear its identity.
        CHAT_SCHEMAS["C2L_ChatAway"].decode(packet.body)
        return OutboundMessage("L2C_ChatAway", {"code": 10 if context.session.player_id == 1 else 13})
