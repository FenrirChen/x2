"""Official-table favor state; uncertain interactions fail without consuming items."""
from importlib.resources import files
from datetime import datetime, timedelta, timezone
import json
import time

from x2server.messages.favor import FAVOR_SCHEMAS, FAVOR_CHANGE_INFO
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY


def catalog():
    return json.loads(files("x2server").joinpath("data/favor_catalog.json").read_text(encoding="utf-8"))


def favor_state(hero, initial_level=1):
    return hero.get("favor", {"level": initial_level, "exp": 0})


class FavorService:
    def __init__(self, store, economy, clock=time.time):
        self.store, self.economy, self.clock = store, economy, clock
        data = catalog()
        self.heroes = {r["HeroID"]: r for r in data["favorabilityhero"]}
        self.levels = {r["FavorLevel"]: r for r in data["favorabilitylevel"]}
        self.gifts = {r["ItemID"]: r for r in data["gifts"]}
        self.files = {r["FilesID"]: r for r in data["favorabilityfiles"]}
        self.dairy = data["favorabilitydairy"]

    def handlers(self):
        return {"C2L_" + name: self.handle for name in
            ("AddFavor", "UpgradeFetters", "UnlockHeroArchives", "QueryHeroArchives",
             "FavorBreak", "QueryHeroJournal")}

    def _owned(self, player_id, hero_id):
        return next((h for h in self.store.get(player_id)["snapshot"].get("heroes", [])
                     if h["id"] == hero_id and h["state"] == 2 and hero_id in self.heroes), None)

    async def handle(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("favor requested before login")
        name = CORE_MESSAGE_REGISTRY.name_for(packet.message_id)
        req = FAVOR_SCHEMAS[name].decode(packet.body)
        reply = name.replace("C2L_", "L2C_", 1)
        hero_id = req.get("heroId", req.get("heroID", req.get("mainHeroId", 0)))
        hero = self._owned(player_id, hero_id)
        if name == "C2L_AddFavor":
            return self._add(player_id, req, hero)
        if name == "C2L_QueryHeroArchives":
            return OutboundMessage(reply, {"code": 10 if hero else 13, "needRefresh": False})
        if name == "C2L_QueryHeroJournal":
            journal = []
            if hero:
                level = favor_state(hero, self.heroes[hero_id]["InitialLevel"])["level"]
                journal = [r["DairyID"] for r in self.dairy if r["HeroID"] == hero_id and
                    (r["TriggerType"]["value"] == 3 or
                     r["TriggerType"]["value"] == 1 and level >= r.get("TypeNumber", 1))]
            return OutboundMessage(reply, {"code": 10 if hero else 13,
                "heroId": hero_id, "journal": journal})
        if name == "C2L_UnlockHeroArchives":
            file_id = req.get("archivesID", 0)
            entry = self.files.get(file_id)
            if not hero or not entry or entry["HeroID"] != hero_id:
                return OutboundMessage(reply, {"code": 13, "heroID": hero_id, "archivesID": file_id})
            level = favor_state(hero, self.heroes[hero_id]["InitialLevel"])["level"]
            if entry["TriggerType"]["value"] != 1 or level < entry["TypeNumber"]:
                return OutboundMessage(reply, {"code": 13, "heroID": hero_id, "archivesID": file_id})
            with self.economy.transaction():
                snapshot = self.store.get(player_id)["snapshot"]
                target = next(h for h in snapshot["heroes"] if h["id"] == hero_id)
                claimed = target.setdefault("favor_archives", [])
                if file_id not in claimed:
                    claimed.append(file_id)
                    self.economy.save_snapshot(player_id, snapshot)
            return OutboundMessage(reply, {"code": 10, "heroID": hero_id, "archivesID": file_id})
        # UpgradeFetters and FavorBreak carry costs/conditions that must be
        # validated before changing state. No free fallback is permitted.
        return OutboundMessage(reply, {"code": 13,
            **({"heroId": hero_id} if name == "C2L_FavorBreak" else
               {"mainHeroId": hero_id, "positionId": req.get("positionId", 0)})})

    def _add(self, player_id, req, hero):
        hero_id, item_id, num, opt = (req.get("heroId", 0), req.get("optionId", 0),
                                     req.get("num", 0), req.get("opt", -1))
        before = favor_state(hero, self.heroes[hero_id]["InitialLevel"]) if hero else {"level": 0, "exp": 0}
        values = {"code": 13, "opt": opt, "optionId": item_id, "heroId": hero_id,
            "exp": before["exp"], "level": before["level"],
            "newExp": before["exp"], "newLevel": before["level"]}
        day = datetime.fromtimestamp(int(self.clock()), timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
        values["giftsTimes"] = hero.get("favor_gifts", {}).get("count", 0) if hero and hero.get("favor_gifts", {}).get("day") == day else 0
        gift = self.gifts.get(item_id)
        # EffData[0] is the ordinary gift value. The optional second value
        # is a preference bonus; use the ordinary value until that selector
        # is recovered, so ordinary gifts remain usable without overpaying.
        if (not hero or opt != 2 or type(num) is not int or not 1 <= num <= 999 or
                not gift or not gift.get("EffData")):
            return OutboundMessage("L2C_AddFavor", values)
        gain = gift["EffData"][0] * num
        if gain <= 0:
            return OutboundMessage("L2C_AddFavor", values)
        with self.economy.transaction():
            charged = self.store.db.execute("""UPDATE inventory SET quantity=quantity-?
                WHERE player_id=? AND item_id=? AND quantity>=?""", (num, player_id, item_id, num))
            if charged.rowcount != 1:
                return OutboundMessage("L2C_AddFavor", values)
            snapshot = self.store.get(player_id)["snapshot"]
            target = next(h for h in snapshot["heroes"] if h["id"] == hero_id and h["state"] == 2)
            state = favor_state(target, self.heroes[hero_id]["InitialLevel"]).copy()
            state["exp"] += gain
            # Static Exp values through the first break are cumulative.
            while state["level"] < 4 and state["exp"] >= self.levels[state["level"] + 1]["Exp"]:
                state["level"] += 1
            target["favor"] = state
            previous = target.get("favor_gifts", {})
            count = (previous.get("count", 0) if previous.get("day") == day else 0) + num
            target["favor_gifts"] = {"day": day, "count": count}
            self.economy.save_snapshot(player_id, snapshot)
        values.update(code=10, newExp=state["exp"], newLevel=state["level"], giftsTimes=count)
        change = FAVOR_CHANGE_INFO.encode({"beforeLevel": before["level"], "beforeExp": before["exp"],
            "afterLevel": state["level"], "afterExp": state["exp"], "heroID": hero_id, "type": 7})
        return OutboundMessage("L2C_AddFavor", values, pushes=(OutboundMessage(
            "L2C_FavorChangeInfo", {"data": [change]}), *self.economy.pushes(player_id)))
