"""Persist the player's month/day birthday for the divination story prompt."""

from datetime import date

from x2server.messages.core import C2L_FILL_BIRTHDAY
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError

from .login import LoginService


class BirthdayService:
    def __init__(self, store):
        self.store = store

    def handlers(self):
        return {"C2L_FillBirthday": self.fill}

    async def fill(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("birthday submitted before login")
        request = C2L_FILL_BIRTHDAY.decode(packet.body)
        month, day = request.get("month"), request.get("day")
        try:
            # The client asks for month/day only; a leap year permits February 29.
            date(2000, month, day)
        except (TypeError, ValueError):
            return OutboundMessage("L2C_FillBirthday", {"code": 13})
        player = self.store.get(player_id)
        snapshot = player["snapshot"]
        birthday = month * 100 + day
        if snapshot.get("birthday") != birthday:
            snapshot["birthday"] = birthday
            self.store.save_snapshot(player_id, snapshot, player["revision"])
            player = self.store.get(player_id)
        return OutboundMessage("L2C_FillBirthday", {"code": 10},
            before_response=(LoginService.snapshot_push(player),))
