"""Owned appearance catalog and persistent equipped state."""
from importlib.resources import files
import json
import logging

from x2server.messages.appearance import (APPEARANCE_SCHEMAS as SCHEMAS, HERO_SKIN,
    HERO_DUBBING_DATA, SEASON_ICON_DATA, ICON_INFO, PICTURE_ID_ENTRY)
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY

DEFAULT_HEAD_ICON = 1000001
HEAD_ICON_Q_FAVOR_LEVEL = 10
_HEAD_ICON_CATALOG = None


def head_icon_catalog():
    global _HEAD_ICON_CATALOG
    if _HEAD_ICON_CATALOG is None:
        _HEAD_ICON_CATALOG = json.loads(files("x2server").joinpath("data/head_icons.json").read_text(encoding="utf-8"))
    return _HEAD_ICON_CATALOG


def granted_head_icons(snapshot, favors=None):
    return json.loads(files("x2server").joinpath("data/appearance_catalog.json").read_text(encoding="utf-8"))["head_icons"]


def avatar_frames():
    return {r["ItemID"] for r in json.loads(files("x2server").joinpath("data/reward_items.json").read_text(encoding="utf-8"))
            if r.get("ItemType", {}).get("value") == 20}


def head_icon_info(snapshot, favors=None):
    icons = granted_head_icons(snapshot, favors)
    return ICON_INFO.encode({"IconType": 1, "IconID": int(snapshot.get("head_icon", DEFAULT_HEAD_ICON) or DEFAULT_HEAD_ICON),
        "OrnamentID": snapshot.get("avatar_frame", 0), "PictureID": [PICTURE_ID_ENTRY.encode({"Key": i, "Value": value})
            for i, value in enumerate(icons)]})


class AppearanceService:
    def __init__(self, store, economy):
        self.store, self.economy = store, economy
        data = json.loads(files("x2server").joinpath("data/appearance_catalog.json").read_text(encoding="utf-8"))
        self.skins = {r["id"]: r for r in data["appearance"]}
        self.voices = {r["id"]: r for r in data["dubbing"]}
        self.heads, self.scenes = set(data["head_icons"]), set(data["scene_icons"])
        self.starter_head = data["starter_head_icon"]
        with store.db:
            store.db.execute("""CREATE TABLE IF NOT EXISTS appearance_wear (
                player_id INTEGER NOT NULL, hero_id INTEGER NOT NULL, type INTEGER NOT NULL,
                skin_id INTEGER NOT NULL, PRIMARY KEY(player_id,hero_id,type))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS appearance_voice_unlock (
                player_id INTEGER NOT NULL, dubbing_id INTEGER NOT NULL,
                PRIMARY KEY(player_id,dubbing_id))""")

    def handlers(self):
        return {"C2L_" + name: self.handle for name in (
            "Account", "HeroSkinAll", "HeroWearSkin", "SeasonIcon", "PutOnOrPutOffSeasonIcon",
            "SeasonIconStatusUp", "QueryHeroDubbing", "SaveHeroDubbing")}

    def _owned_heroes(self, player_id):
        return {h["id"] for h in self.store.get(player_id)["snapshot"].get("heroes", []) if h.get("state") == 2}

    def _inventory(self, player_id):
        return {r[0] for r in self.store.db.execute(
            "SELECT item_id FROM inventory WHERE player_id=? AND quantity>0", (player_id,))}

    def _owned_skins(self, player_id):
        heroes = {h["id"]: h for h in self.store.get(player_id)["snapshot"].get("heroes", [])
                  if h.get("state") == 2}
        items = self._inventory(player_id)
        # PlayerStage 11 is the first five-star stage in the client table.
        return {i for i, r in self.skins.items() if r["hero_id"] in heroes and
                (r["acquire"] == "E_Default" or i in items or
                 r["acquire"] == "E_Stage" and heroes[r["hero_id"]].get("star", 0) >= 11)}

    def skin_values(self, player_id):
        owned = self._owned_skins(player_id)
        worn = {(r[0], r[1]): r[2] for r in self.store.db.execute(
            "SELECT hero_id,type,skin_id FROM appearance_wear WHERE player_id=?", (player_id,))}
        return {"skinList": [HERO_SKIN.encode({"heroId": hero,
            "skinIds": sorted(i for i in owned if self.skins[i]["hero_id"] == hero),
            "battleSkin": worn.get((hero, 1), 0), "outerSkin": worn.get((hero, 3), 0)})
            for hero in sorted(self._owned_heroes(player_id))]}

    def _icon_values(self, player_id):
        items = self._inventory(player_id)
        snapshot = self.store.get(player_id)["snapshot"]
        favors = {int(hero["id"]): hero.get("favor", {})
                  for hero in snapshot.get("heroes", [])}
        heads = self.heads | {self.starter_head}
        scenes = self.scenes
        return {"code": 10,
            "putOnHeadIcon": snapshot.get("head_icon", self.starter_head),
            "putOnSceneIcon": snapshot.get("scene_icon", 0),
            # Compatibility: permanently opened catalogs are already seen.
            # Client AccountInfoModule marks rankId == 0 as new.
            "headIconList": [SEASON_ICON_DATA.encode({"id": i, "rankId": 1}) for i in sorted(heads)],
            "sceneIconList": [SEASON_ICON_DATA.encode({"id": i, "rankId": 1}) for i in sorted(scenes)]}

    def _voice_values(self, player_id):
        heroes = self._owned_heroes(player_id)
        saved = {r[0] for r in self.store.db.execute(
            "SELECT dubbing_id FROM appearance_voice_unlock WHERE player_id=?", (player_id,))}
        return {"code": 10, "heroDubbingDatas": [HERO_DUBBING_DATA.encode({
            "heroId": hero, "dubbingIds": sorted(i for i, r in self.voices.items()
                if r["hero_id"] == hero and (r["unlock_condition"] == 1350123 or i in saved))})
            for hero in sorted(heroes)]}

    async def handle(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("appearance requested before login")
        name = CORE_MESSAGE_REGISTRY.name_for(packet.message_id)
        req = SCHEMAS[name].decode(packet.body) if name in SCHEMAS else {}
        if name == "C2L_Account":
            opt, values = req.get("opt", -1), req.get("values", [])
            logging.getLogger("x2.appearance").info(
                "account update player=%s opt=%s values=%s strvals=%s", player_id, opt, values, req.get("strvals", []))
            if opt == 3:
                if len(values) != 2 or values[0] <= 0 or values[1] < 0:
                    return OutboundMessage("L2C_Account", {"result": 13, "opt": opt})
                with self.economy.transaction():
                    snapshot = self.store.get(player_id)["snapshot"]
                    groups = snapshot.setdefault("guide_groups", {})
                    old = groups.get(str(values[0]))
                    if old is not None and old != values[1]:
                        return OutboundMessage("L2C_Account", {"result": 13, "opt": opt})
                    groups[str(values[0])] = values[1]
                    self.economy.save_snapshot(player_id, snapshot)
                logging.getLogger("x2.tutorial").info("guide group player=%s group=%s next=%s",
                    player_id, values[0], values[1])
                return OutboundMessage("L2C_Account", {"result": 10, "opt": opt},
                    before_response=(self.economy.pushes(player_id)[0],))
            if opt == 7:
                names = req.get("strvals", [])
                if len(names) != 1 or not names[0].strip() or len(names[0]) > 16 or any(
                        not char.isprintable() for char in names[0]):
                    return OutboundMessage("L2C_Account", {"result": 13, "opt": opt})
                requested = names[0]
                with self.economy.transaction():
                    snapshot = self.store.get(player_id)["snapshot"]
                    current = snapshot.get("nickname", "")
                    if current and current != requested:
                        return OutboundMessage("L2C_Account", {"result": 13, "opt": opt})
                    if not current:
                        snapshot["nickname"] = requested
                        self.economy.save_snapshot(player_id, snapshot)
                logging.getLogger("x2.tutorial").info("first name player=%s set=%s", player_id, not current)
                return OutboundMessage("L2C_Account", {"result": 10, "opt": opt},
                    before_response=(self.economy.pushes(player_id)[0],))
            # The 2.4 avatar picker sends the selected id together with a
            # second decoration/slot value in ``values``.  The server only
            # owns the selected id; rejecting the otherwise valid packet
            # makes every avatar change appear to fail with code 13.
            if opt not in (1, 2) or not values:
                return OutboundMessage("L2C_Account", {"result": 13, "opt": opt})
            if opt == 2 and len(values) == 3 and values[0] == 1:
                frame = values[2]
                if frame != 0 and frame not in avatar_frames():
                    return OutboundMessage("L2C_Account", {"result": 13, "opt": opt})
                with self.economy.transaction():
                    snapshot = self.store.get(player_id)["snapshot"]
                    snapshot["avatar_frame"] = frame
                    self.economy.save_snapshot(player_id, snapshot)
                return OutboundMessage("L2C_Account", {"result": 10, "opt": opt}, before_response=(self.economy.pushes(player_id)[0],))
            owned = (self._owned_heroes(player_id) if opt == 1 else
                set(granted_head_icons(self.store.get(player_id)["snapshot"], {
                    int(hero["id"]): hero.get("favor", {})
                    for hero in self.store.get(player_id)["snapshot"].get("heroes", [])})) |
                {SEASON_ICON_DATA.decode(x)["id"] for x in self._icon_values(player_id)["headIconList"]})
            selected = next((int(value) for value in values if int(value) in owned), None)
            if selected is None:
                return OutboundMessage("L2C_Account", {"result": 13, "opt": opt})
            with self.economy.transaction():
                snapshot = self.store.get(player_id)["snapshot"]
                snapshot["show" if opt == 1 else "head_icon"] = selected
                self.economy.save_snapshot(player_id, snapshot)
            update = (self.economy.pushes(player_id)[0],)
            # The picker marks "in use" from state that the PlayerDataProto push
            # carries (IconInfo.IconID / Show). Deliver it before the response
            # frame, like every other Account option, so the open page re-renders
            # with the new value instead of needing a page re-entry.
            return OutboundMessage("L2C_Account", {"result": 10, "opt": opt},
                                   before_response=update)
        if name == "C2L_HeroSkinAll":
            return OutboundMessage("L2C_HeroSkinAll", self.skin_values(player_id))
        if name == "C2L_SeasonIcon":
            return OutboundMessage("L2C_SeasonIcon", self._icon_values(player_id))
        if name == "C2L_QueryHeroDubbing":
            return OutboundMessage("L2C_QueryHeroDubbing", self._voice_values(player_id))
        if name == "C2L_SaveHeroDubbing":
            # Official condition 1350101 is a bare click. Condition 1350124
            # additionally requires favor level 5. All other conditions need
            # their own event or break proof before they can be accepted.
            voice = self.voices.get(req.get("dubbingId"))
            hero = next((h for h in self.store.get(player_id)["snapshot"].get("heroes", [])
                if h["id"] == req.get("heroId") and h.get("state") == 2), None)
            allowed = bool(voice and hero and voice["hero_id"] == hero["id"] and (
                voice["unlock_condition"] in (1350123, 1350101) or
                voice["unlock_condition"] == 1350124 and hero.get("favor", {}).get("level", 1) >= 5))
            if allowed and voice["unlock_condition"] != 1350123:
                with self.economy.transaction():
                    self.store.db.execute("INSERT OR IGNORE INTO appearance_voice_unlock VALUES (?,?)",
                                          (player_id, req["dubbingId"]))
            return OutboundMessage("L2C_SaveHeroDubbing", {
                "code": 10 if allowed else 13,
                "heroDubbingDatas": self._voice_values(player_id)["heroDubbingDatas"] if allowed else []})
        if name == "C2L_HeroWearSkin":
            hero, skin, kind = req.get("heroId"), req.get("skinId"), req.get("type")
            valid = (kind in (1, 3) and skin in self._owned_skins(player_id) and
                     self.skins[skin]["hero_id"] == hero)
            if not valid:
                return OutboundMessage("L2C_HeroWearSkin", {"code": 13,
                    "heroId": hero or 0, "skinId": skin or 0, "type": kind or 0})
            with self.economy.transaction():
                self.store.db.execute("INSERT OR REPLACE INTO appearance_wear VALUES (?,?,?,?)",
                                      (player_id, hero, kind, skin))
            # The client handles wear success by firing a UI event only. Its
            # equipped-skin cache is updated by L2C_HeroSkinUpdate, so deliver
            # the new HeroSkin before the success event is processed.
            updated = next(value for value in self.skin_values(player_id)["skinList"]
                           if HERO_SKIN.decode(value)["heroId"] == hero)
            return OutboundMessage("L2C_HeroWearSkin", {"code": 10,
                "heroId": hero, "skinId": skin, "type": kind},
                before_response=(OutboundMessage("L2C_HeroSkinUpdate", {"skin": updated}),))
        if name == "C2L_PutOnOrPutOffSeasonIcon":
            kind, icon = req.get("type"), req.get("id")
            owned = self._icon_values(player_id)
            allowed = ({SEASON_ICON_DATA.decode(x)["id"] for x in owned["headIconList"]}
                       if kind == 1 else {SEASON_ICON_DATA.decode(x)["id"] for x in owned["sceneIconList"]}
                       if kind == 2 else set())
            if icon not in allowed and not (icon == 0 and kind == 2):
                return OutboundMessage("L2C_PutOnOrPutOffSeasonIcon", {"code": 13})
            with self.economy.transaction():
                snapshot = self.store.get(player_id)["snapshot"]
                snapshot["head_icon" if kind == 1 else "scene_icon"] = icon
                self.economy.save_snapshot(player_id, snapshot)
            owned = self._icon_values(player_id)
            return OutboundMessage("L2C_PutOnOrPutOffSeasonIcon", {k: owned[k] for k in
                ("code", "putOnHeadIcon", "putOnSceneIcon")},
                pushes=(self.economy.pushes(player_id)[0],))
        if name == "C2L_SeasonIconStatusUp":
            return OutboundMessage("L2C_SeasonIconStatusUp", {
                "code": 13, "type": req.get("type", 0), "id": req.get("id", 0)})
        raise ProtocolError("unknown appearance request")
