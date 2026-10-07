"""Account-scoped terminal conversations and moments from the shipped tables."""

from datetime import datetime
from importlib.resources import files
import json
import time

from x2server.messages.terminal import (BLOG_BOX, BLOG_GROUP, CHAT_GROUP, LETTER_BOX,
                                        LETTER_DATA, LETTER_GROUP, PAIR, TERMINAL_SCHEMAS)
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY
from .server_clock import BEIJING


class TerminalService:
    def __init__(self, store, economy, clock=time.time):
        self.store, self.economy, self.clock = store, economy, clock
        # The query paths write too: a 时光 letter unlocks itself and an
        # auto-read line records its option effect. Writes are therefore
        # deferred to one _flush at the end of the request instead of saving at
        # every write site, which also keeps one request to one revision bump.
        self._player_id = 0
        self._dirty = False
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

    def _available(self, row, hero, snapshot):
        """Whether this letter or moment should render for the current player.

        All four recovered trigger types are handled. An unknown type stays
        False on purpose: whatever is sent gets rendered by the client, so it is
        better to omit a row than to send one it cannot resolve.
        """
        trigger = (row.get("TriggerType") or {}).get("enum")
        if trigger == "E_FavorabilityLevel":
            return hero.get("favor", {}).get("level", 1) >= row.get("TypeNumber", 1)
        if trigger == "E_SpecialDay":
            return self._special_day_open(row, snapshot)
        if trigger == "E_SectionPass":
            section = int(row.get("TypeNumber", 0))
            return bool(section and self.store.db.execute(
                "SELECT 1 FROM economy_clears WHERE player_id=? AND section_id=?",
                (self._player_id, section)).fetchone())
        if trigger == "E_OptionEffect":
            return str(row.get("TypeNumber", 0)) in self._state(snapshot)["effects"]
        return False

    def _special_day_open(self, row, snapshot):
        """时光来信: TypeNumber is YYYYMMDD and the shipped years stop at 2021/2022.

        Only month and day are compared, so the letter opens again on that date
        every year. Reaching the date records it in "unlocked" for good:
        otherwise a reply kept in the snapshot would outlive its letter and the
        conversation would vanish on the following 1 January.
        """
        row_id = str(row.get("PrivateMailID") or row.get("BlogID") or "")
        if not row_id or row_id == "None":
            return False
        unlocked = self._state(snapshot)["unlocked"]
        if row_id in unlocked:
            return True
        date = int(row.get("TypeNumber", 0))
        month, day = (date // 100) % 100, date % 100
        today = datetime.fromtimestamp(int(self.clock()), BEIJING)
        if (today.month, today.day) < (month, day):
            return False
        unlocked[row_id] = True
        self._dirty = True
        return True

    @staticmethod
    def _state(snapshot):
        """Terminal save block. Snapshots written before 时光/选项效果 only
        carry the first three keys, so every key is defaulted individually."""
        state = snapshot.setdefault("terminal", {})
        for key in ("letters", "blogs", "blocked", "effects", "unlocked"):
            state.setdefault(key, {})
        return state

    @staticmethod
    def _options(row):
        """The reply options a player can actually tap.

        A 0 inside ReplyContent is the "this line has no branch, keep reading"
        placeholder (20160105 is [0]), not a choice. Counting it as one stalls
        the conversation: the lines behind it never enter the chain and the
        option effects hanging off them cannot be earned.
        """
        return [int(option) for option in row.get("ReplyContent", []) if option]

    def _grant_effects(self, snapshot, row):
        """Remember what this line hands out, for the E_OptionEffect gate."""
        effects = self._state(snapshot)["effects"]
        for effect in row.get("OptionEffectID") or []:
            if str(effect) not in effects:
                effects[str(effect)] = True
                self._dirty = True

    def _extend_auto_chain(self, snapshot, progress):
        """The client advances through lines without reply choices locally.

        A line walked past this way still records its option effect: it carries
        no reply action to hook, so an E_OptionEffect letter behind it could
        never unlock otherwise.
        """
        chain = progress["chain"]
        changed = False
        seen = set(chain)
        while chain:
            current = self.letters.get(chain[-1])
            if not current or self._options(current):
                break
            following = [value for value in current.get("NextPrivateMailID", [])
                         if value in self.letters and self.letters[value]["GroupID"] == current["GroupID"]]
            if len(following) != 1 or following[0] in seen:
                break
            self._grant_effects(snapshot, current)
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
            if root["HeroID"] != hero_id or not self._available(root, hero, snapshot):
                continue
            group_id = root["GroupID"]
            progress = state.get(str(group_id), {})
            chain = progress.get("chain", [root["PrivateMailID"]])
            if progress:
                self._extend_auto_chain(snapshot, progress)
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
            if row["HeroID"] != hero_id or not self._available(row, hero, snapshot):
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

    def _flush(self, player_id, snapshot):
        """One write per request at most.

        The query paths write as well (a 时光 letter unlocks itself, an
        auto-read line records its option effect) and _letter_box visits every
        hero, so saving at each write site would bump the revision many times
        for a single read.
        """
        if not self._dirty:
            return
        self._dirty = False
        self._save(player_id, snapshot)

    async def handle(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("terminal requested before login")
        name = CORE_MESSAGE_REGISTRY.name_for(packet.message_id)
        req = TERMINAL_SCHEMAS[name].decode(packet.body)
        reply = name.replace("C2L_", "L2C_", 1)
        self._player_id = player_id
        self._dirty = False
        snapshot = self.store.get(player_id)["snapshot"]
        state = self._state(snapshot)
        if name == "C2L_QueryPrivateLetter":
            kind = req.get("type", 0)
            values = {"code": 10,
                "letterBoxs": self._letter_boxes(snapshot) if kind in (0, 1) else [],
                "systemLetters": [], "blcakHeros": self._blocked(snapshot)}
            self._flush(player_id, snapshot)
            return OutboundMessage(reply, values)
        if name == "C2L_QueryNpcBlog":
            values = {"code": 10,
                "blogBox": self._blog_boxes(snapshot), "blcakHeros": self._blocked(snapshot)}
            self._flush(player_id, snapshot)
            return OutboundMessage(reply, values)
        if name == "C2L_AddBlackNpc":
            hero_id = req.get("heroID", 0)
            if hero_id not in self._owned(snapshot):
                return OutboundMessage(reply, {"code": 13})
            blocked = state["blocked"]
            blocked[str(hero_id)] = 0 if blocked.get(str(hero_id)) else 1
            self._dirty = True
            values = {"code": 10, "blcakHeros": self._blocked(snapshot)}
            self._flush(player_id, snapshot)
            return OutboundMessage(reply, values)
        if name in ("C2L_UpdatePrivateLetter", "C2L_ReplyLetter"):
            hero_id, letter_id = req.get("heroID", 0), req.get("letterID", 0)
            row = self.letters.get(letter_id)
            root = next((r for r in self.roots if r["GroupID"] == (row or {}).get("GroupID")), None)
            hero = self._owned(snapshot).get(hero_id)
            success = bool(row and root and hero and row["HeroID"] == hero_id and
                           self._available(root, hero, snapshot) and
                           (name != "C2L_ReplyLetter" or req.get("groupID") == row["GroupID"]))
            if success:
                progress = state["letters"].setdefault(str(row["GroupID"]),
                    {"chain": [root["PrivateMailID"]], "replies": {}, "start": int(self.clock())})
                self._extend_auto_chain(snapshot, progress)
                success = letter_id in progress["chain"]
            if success and name == "C2L_ReplyLetter":
                options = self._options(row) or [0]  # A placeholder line accepts the 0 the client sends.
                reply_id = req.get("replyID", 0)
                success = reply_id in options
                if success:
                    progress["replies"][str(letter_id)] = reply_id
                    self._grant_effects(snapshot, row)
                    index = options.index(reply_id)
                    next_ids = row.get("NextPrivateMailID", [])
                    if index < len(next_ids) and next_ids[index] in self.letters:
                        next_id = next_ids[index]
                        if next_id not in progress["chain"]:
                            progress["chain"].append(next_id)
                        self._extend_auto_chain(snapshot, progress)
                    progress["last"] = int(self.clock())
            elif success:
                # The client reports isEnd only after reading a whole thread. A
                # line with no reply option has no other hook, so its
                # OptionEffectID is recorded here.
                progress["ended"] = bool(req.get("isEnd"))
                progress["last"] = int(self.clock())
                if progress["ended"]:
                    self._grant_effects(snapshot, row)
            if success:
                self._dirty = True
            values = {"code": 10 if success else 13,
                      "letterBox": self._letter_box(hero_id, snapshot) if success else None,
                      "blcakHeros": self._blocked(snapshot)}
            if name == "C2L_ReplyLetter":
                values.update(heroID=hero_id, groupID=req.get("groupID", 0),
                              letterID=letter_id, replyID=req.get("replyID", 0))
            self._flush(player_id, snapshot)
            return OutboundMessage(reply, values)
        hero_id, blog_id = req.get("heroID", 0), req.get("groupID", 0)
        row = self.blogs.get(blog_id)
        hero = self._owned(snapshot).get(hero_id)
        success = bool(row and hero and row["HeroID"] == hero_id and self._available(row, hero, snapshot))
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
                self._dirty = True
        values = {"code": 10 if success else 13,
            "blogBox": self._blog_box(hero_id, snapshot) if success else None,
            "blcakHeros": self._blocked(snapshot)}
        self._flush(player_id, snapshot)
        return OutboundMessage(reply, values)
