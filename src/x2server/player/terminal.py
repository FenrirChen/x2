"""Account-scoped terminal conversations and moments from the shipped tables."""

from functools import lru_cache
from importlib.resources import files
import json
import time

from x2server.messages.terminal import (BLOG_BOX, BLOG_GROUP, CHAT_GROUP, LETTER_BOX,
                                        LETTER_DATA, LETTER_GROUP, PAIR, TERMINAL_SCHEMAS)
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY
from .favor import catalog, favor_state


@lru_cache(maxsize=1)
def initial_favor_levels():
    """HeroID -> official starting favor level, mirroring login.snapshot_push."""
    return {row["HeroID"]: row["InitialLevel"] for row in catalog()["favorabilityhero"]}


class TerminalService:
    def __init__(self, store, economy, clock=time.time):
        self.store, self.economy, self.clock = store, economy, clock
        data = json.loads(files("x2server").joinpath("data/terminal_catalog.json").read_text(encoding="utf-8"))
        self.letters = {row["PrivateMailID"]: row for row in data["privatemail"]}
        self.roots = [row for row in data["privatemail"] if row.get("IsMasterSequence")]
        self.blogs = {row["BlogID"]: row for row in data["favorabilityblog"]}

    def handlers(self):
        return {"C2L_" + name: self.handle for name in
                ("QueryPrivateLetter", "UpdatePrivateLetter", "AddBlackNpc", "ReplyLetter",
                 "QueryNpcBlog", "ReplyNpcBlog", "LikeNpcBlog")}

    def _owned(self, snapshot):
        return {hero["id"]: hero for hero in snapshot.get("heroes", []) if hero.get("state") == 2}

    @staticmethod
    def _available(row, hero):
        trigger = row.get("TriggerType", {}).get("enum")
        if trigger == "E_FavorabilityLevel":
            return favor_state(hero, initial_favor_levels().get(hero["id"], 1))["level"] >= row.get("TypeNumber", 1)
        # Other triggers depend on calendar, section, or choice events which
        # the current player snapshot does not yet prove occurred.
        return False

    @staticmethod
    def _state(snapshot):
        return snapshot.setdefault("terminal", {"letters": {}, "blogs": {}, "blocked": {}})

    def _extend_auto_chain(self, progress):
        """The client advances through lines without reply choices locally."""
        chain = progress["chain"]
        changed = False
        seen = set(chain)
        while chain:
            current = self.letters.get(chain[-1])
            if not current or current.get("ReplyContent"):
                break
            following = [value for value in current.get("NextPrivateMailID", [])
                         if value in self.letters and self.letters[value]["GroupID"] == current["GroupID"]]
            if len(following) != 1 or following[0] in seen:
                break
            chain.append(following[0])
            seen.add(following[0])
            changed = True
        return changed

    def _letter_box(self, hero_id, snapshot):
        hero = self._owned(snapshot).get(hero_id)
        if not hero:
            return None
        state = self._state(snapshot)["letters"]
        groups = []
        last_time = 0
        for root in self.roots:
            if root["HeroID"] != hero_id or not self._available(root, hero):
                continue
            group_id = root["GroupID"]
            progress = state.get(str(group_id), {})
            chain = progress.get("chain", [root["PrivateMailID"]])
            if progress:
                self._extend_auto_chain(progress)
            valid = [letter_id for letter_id in chain if letter_id in self.letters and
                     self.letters[letter_id]["GroupID"] == group_id]
            if not valid:
                valid = [root["PrivateMailID"]]
            start = progress.get("start", int(self.clock()))
            last_time = max(last_time, progress.get("last", 0))
            entries = [LETTER_DATA.encode({"letterID": letter_id,
                "replyID": progress.get("replies", {}).get(str(letter_id), 0), "index": index})
                for index, letter_id in enumerate(valid)]
            groups.append(LETTER_GROUP.encode({"startTime": start, "letterData": entries,
                                               "status": 1 if progress.get("ended") else 0}))
        if not groups:
            return None
        return LETTER_BOX.encode({"heroID": hero_id, "groups": groups, "lastReplyTime": last_time})

    def _letter_boxes(self, snapshot):
        return [box for hero_id in sorted(self._owned(snapshot))
                if (box := self._letter_box(hero_id, snapshot)) is not None]

    def _blog_box(self, hero_id, snapshot):
        hero = self._owned(snapshot).get(hero_id)
        if not hero:
            return None
        state = self._state(snapshot)["blogs"]
        groups = []
        for blog_id, row in sorted(self.blogs.items()):
            if row["HeroID"] != hero_id or not self._available(row, hero):
                continue
            progress = state.get(str(blog_id), {})
            chats = []
            for chat_id, reply_id in progress.get("replies", {}).items():
                chats.append(CHAT_GROUP.encode({"chatGroupID": int(chat_id),
                    "chat": [PAIR.encode({"Key": reply_id,
                        "Value": progress.get("reply_times", {}).get(chat_id, progress.get("start", 0))})]}))
            groups.append(BLOG_GROUP.encode({"groupID": blog_id,
                "startTime": progress.get("start", int(self.clock())),
                "likeTime": progress.get("like", 0), "chatGroup": chats}))
        if not groups:
            return None
        return BLOG_BOX.encode({"heroID": hero_id, "blogGroup": groups})

    def _blog_boxes(self, snapshot):
        return [box for hero_id in sorted(self._owned(snapshot))
                if (box := self._blog_box(hero_id, snapshot)) is not None]

    def _blocked(self, snapshot):
        return [PAIR.encode({"Key": int(hero), "Value": int(value)})
                for hero, value in sorted(self._state(snapshot)["blocked"].items(), key=lambda item: int(item[0]))]

    def _save(self, player_id, snapshot):
        with self.economy.transaction():
            self.economy.save_snapshot(player_id, snapshot)

    async def handle(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("terminal requested before login")
        name = CORE_MESSAGE_REGISTRY.name_for(packet.message_id)
        req = TERMINAL_SCHEMAS[name].decode(packet.body)
        reply = name.replace("C2L_", "L2C_", 1)
        snapshot = self.store.get(player_id)["snapshot"]
        state = self._state(snapshot)
        if name == "C2L_QueryPrivateLetter":
            kind = req.get("type", 0)
            return OutboundMessage(reply, {"code": 10,
                "letterBoxs": self._letter_boxes(snapshot) if kind in (0, 1) else [],
                "systemLetters": [], "blcakHeros": self._blocked(snapshot)})
        if name == "C2L_QueryNpcBlog":
            return OutboundMessage(reply, {"code": 10,
                "blogBox": self._blog_boxes(snapshot), "blcakHeros": self._blocked(snapshot)})
        if name == "C2L_AddBlackNpc":
            hero_id = req.get("heroID", 0)
            if hero_id not in self._owned(snapshot):
                return OutboundMessage(reply, {"code": 13})
            blocked = state["blocked"]
            blocked[str(hero_id)] = 0 if blocked.get(str(hero_id)) else 1
            self._save(player_id, snapshot)
            return OutboundMessage(reply, {"code": 10, "blcakHeros": self._blocked(snapshot)})
        if name in ("C2L_UpdatePrivateLetter", "C2L_ReplyLetter"):
            hero_id, letter_id = req.get("heroID", 0), req.get("letterID", 0)
            row = self.letters.get(letter_id)
            root = next((r for r in self.roots if r["GroupID"] == (row or {}).get("GroupID")), None)
            hero = self._owned(snapshot).get(hero_id)
            success = bool(row and root and hero and row["HeroID"] == hero_id and
                           self._available(root, hero) and
                           (name != "C2L_ReplyLetter" or req.get("groupID") == row["GroupID"]))
            if success:
                progress = state["letters"].setdefault(str(row["GroupID"]),
                    {"chain": [root["PrivateMailID"]], "replies": {}, "start": int(self.clock())})
                self._extend_auto_chain(progress)
                success = letter_id in progress["chain"]
            if success and name == "C2L_ReplyLetter":
                options = [int(option) for option in row.get("ReplyContent", []) if option]
                reply_id = req.get("replyID", 0)
                success = reply_id in options
                if success:
                    progress["replies"][str(letter_id)] = reply_id
                    index = options.index(reply_id)
                    next_ids = row.get("NextPrivateMailID", [])
                    if index < len(next_ids) and next_ids[index] in self.letters:
                        next_id = next_ids[index]
                        if next_id not in progress["chain"]:
                            progress["chain"].append(next_id)
                        self._extend_auto_chain(progress)
                    progress["last"] = int(self.clock())
            elif success:
                progress["ended"] = bool(req.get("isEnd"))
                progress["last"] = int(self.clock())
            if success:
                self._save(player_id, snapshot)
            values = {"code": 10 if success else 13,
                      "letterBox": self._letter_box(hero_id, snapshot) if success else None,
                      "blcakHeros": self._blocked(snapshot)}
            if name == "C2L_ReplyLetter":
                values.update(heroID=hero_id, groupID=req.get("groupID", 0),
                              letterID=letter_id, replyID=req.get("replyID", 0))
            return OutboundMessage(reply, values)
        hero_id, blog_id = req.get("heroID", 0), req.get("groupID", 0)
        row = self.blogs.get(blog_id)
        hero = self._owned(snapshot).get(hero_id)
        success = bool(row and hero and row["HeroID"] == hero_id and self._available(row, hero))
        if success:
            progress = state["blogs"].setdefault(str(blog_id), {"start": int(self.clock()), "replies": {}})
            if name == "C2L_LikeNpcBlog":
                progress["like"] = int(self.clock()) if not progress.get("like") else 0
            else:
                reply_id = req.get("replyID", 0)
                success = reply_id in row.get("ReplyContent", []) and reply_id != 0
                if success:
                    chat_id = str(req.get("chatGroupID", 0))
                    progress["replies"][chat_id] = reply_id
                    progress.setdefault("reply_times", {})[chat_id] = int(self.clock())
            if success:
                self._save(player_id, snapshot)
        return OutboundMessage(reply, {"code": 10 if success else 13,
            "blogBox": self._blog_box(hero_id, snapshot) if success else None,
            "blcakHeros": self._blocked(snapshot)})
