"""Persist the client's step-level tutorial acknowledgements."""
import logging

from x2server.messages.core import C2L_GUIDE_STEP
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError

LOGGER = logging.getLogger("x2.tutorial")


class TutorialService:
    def __init__(self, store):
        self.store = store

    def handlers(self):
        return {"C2L_GuideStep": self.guide_step}

    async def guide_step(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("guide step before login")
        request = C2L_GUIDE_STEP.decode(packet.body)
        step_id, state = request.get("stepId", 0), request.get("stepState", 0)
        if step_id <= 0 or state not in (0, 1, 2):
            return OutboundMessage("L2C_GuideStep", {"code": 13})
        player = self.store.get(player_id)
        snapshot = player["snapshot"]
        if snapshot.get("tutorial_mode") != "skip":
            steps = snapshot.setdefault("guide_steps", {})
            steps[str(step_id)] = max(state, steps.get(str(step_id), 0))
            self.store.save_snapshot(player_id, snapshot, player["revision"])
        LOGGER.info("guide step player=%s step=%s state=%s", player_id, step_id, state)
        return OutboundMessage("L2C_GuideStep", {"code": 10})
