"""Account-scoped terminal conversations and moments from the shipped tables."""

from datetime import datetime
from importlib.resources import files
import json
import time

from x2server.messages.favor import (ADD_FAVOR_TYPE_REPLY_BLOG,
                                     ADD_FAVOR_TYPE_REPLY_LETTER)
from x2server.messages.terminal import (BLOG_BOX, BLOG_GROUP, CHAT_GROUP, LETTER_BOX,
                                        LETTER_DATA, LETTER_GROUP, PAIR, TERMINAL_SCHEMAS)
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY
from .server_clock import BEIJING

# 通讯提升默契的两条途径: 「私聊回信 (含生日对话) 读完」与「时光点赞 / 评论」都加好感。
# 数值取本工程既有的兼容口径, 只保证「点赞 < 评论」。
REPLY_FAVOR = 10       # 普通回信选项: 少量提升默契
BLOG_LIKE_FAVOR = 10   # 时光点赞
BLOG_REPLY_FAVOR = 20  # 时光评论
# 发放的 FavorChangeInfo.type 用客户端自己的枚举档: 私聊回信=ReplyLetter(3), 时光点赞/
# 评论=ReplyBlog(4)。发错档客户端会当成「角色页触摸」, 默契条不刷新 (见 messages/favor.py)。
#
# 私聊为避免连弹横幅, 一段对话里每次该加的默契先累加 (pending_favor), 客户端发出收尾的
# C2L_UpdatePrivateLetter(isEnd=true) 时合并成一次发放 (见 _settle_letter_favor); 但推送
# 本身必须照发 (见 _grant_favor) —— 曾把它整个丢掉, 结果「点赞 / 回信 / 生日对话读完」
# 都看不到默契变化, 玩家反馈「没加默契」。


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
        # OptionEffect: OptionEffectID -> [[EffectType, EffectParm1, EffectParm2], ...]。
        # 私聊 / 时光语句的 OptionEffectID 指到这张表; EffectType==1 是「给 EffectParm1
        # 这位神格 +EffectParm2 点默契」(心形正向选项)。缺失时退化为空表 (只是不发那部分
        # 好感), 不能让通讯整页打不开。
        try:
            self.option_effects = json.loads(files("x2server").joinpath(
                "data/option_effect.json").read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - 通讯页必须能开
            self.option_effects = {}

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
        """记住这封信给出的选项效果，供 E_OptionEffect 门槛判定, 并累计表内好感。

        效果 id 只记一次 (幂等): 复看已解锁的会话、重复走到同一句都不会再发一次好感。
        EffectType==1 是「给 EffectParm1 这位神格 +EffectParm2 点默契」—— 规范里
        「心形正向选项大幅提升默契」就是它。加法只入队列, 实际发放推迟到整段读完
        (_settle_letter_favor)。
        """
        effects = self._state(snapshot)["effects"]
        for effect in row.get("OptionEffectID") or []:
            key = str(effect)
            if not effect or key in effects:
                continue
            effects[key] = True
            self._dirty = True
            for kind, param1, param2 in self.option_effects.get(key, ()):
                if int(kind) == 1:
                    self._queue_letter_favor(snapshot, row.get("GroupID"),
                                             int(param1), int(param2))

    def _grant_favor(self, hero_id, amount, change_type):
        """给某位神格加默契, 返回要推给客户端的 L2C_FavorChangeInfo 元组。

        走的是玩家页同一个 `FavorService.grant_favor` (同一条好感曲线), 所以通讯加
        的默契和触摸/送礼完全同口径。economy 没接 favor (单测单独装配服务) 或数值
        非正时静默跳过并返回空元组。

        **推送必须带出去**: 客户端只有收到 FavorChangeInfo 才会刷新某位神格的默契
        (角色页的进度条 / 「默契 +N」提示)。上一版把这条推送丢掉了, 客户端便完全
        不知道默契变过, 表现就是「点赞 / 回信 / 生日对话结束后没加默契」。
        """
        favor = getattr(self.economy, "favor", None) if self.economy is not None else None
        if favor is None or hero_id <= 0 or amount <= 0:
            return ()
        with self.economy.transaction():
            return favor.grant_favor(self._player_id, hero_id, amount,
                                     change_type=change_type)

    def _queue_letter_favor(self, snapshot, group_id, hero_id, amount):
        """把这封信该加的默契记到会话组上, 等整段读完再一次性结算。

        私聊的每个选项各自是一次 C2L_ReplyLetter, 客户端最后再发一次
        C2L_UpdatePrivateLetter(isEnd=true) 表示整段读完。逐次发放会连弹好几次横幅,
        所以先累加进 progress["pending_favor"] (按神格分开记, 心形效果的目标神格可能
        不是会话主神格)。整段读完时由 _settle_letter_favor 合并成一次发放。
        """
        if amount <= 0 or group_id in (None, 0):
            return
        progress = self._state(snapshot)["letters"].get(str(group_id))
        if progress is None:
            return
        pending = progress.setdefault("pending_favor", {})
        key = str(int(hero_id))
        pending[key] = int(pending.get(key, 0)) + int(amount)
        self._dirty = True

    def _settle_letter_favor(self, snapshot, progress):
        """整段对话读完: 把这次会话累计的默契合并成一次发放, 返回那一条推送。

        合并发放是为了不「连点几个选项、横幅连弹好几次」; 但推送本身不能省 —— 客户端
        要靠它刷新默契条并弹一次「默契 +N」, 否则玩家读完整段对话却看不到任何默契变化。
        """
        pending = progress.pop("pending_favor", None) or {}
        pushes = ()
        for hero, amount in pending.items():
            pushes += self._grant_favor(int(hero), int(amount), ADD_FAVOR_TYPE_REPLY_LETTER)
        return pushes

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
        # 本次请求要带出去的 L2C_FavorChangeInfo (私聊读完结算 / 时光点赞评论)。攒起来
        # 挂在回包上, 客户端才能刷新默契条并提示「默契 +N」。
        pushes: tuple = ()
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
                    # 回信选项加默契: 表内效果由 _grant_effects 按 OptionEffect 记(心形正向),
                    # 普通选项再补一个保守小值。只在「这次选的不是原先那一项」时记, 免得
                    # 反复点同一个选项刷默契。两者都只入队列, 等整段读完 (isEnd) 由
                    # _settle_letter_favor 合并成一次发放。
                    if progress["replies"].get(str(letter_id)) != reply_id:
                        self._queue_letter_favor(snapshot, row["GroupID"], hero_id, REPLY_FAVOR)
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
                # OptionEffectID is recorded here. 也正是这一刻结算整段对话攒下的默契
                # (合并成一次发放, 并推送一条变更通知)。
                progress["ended"] = bool(req.get("isEnd"))
                progress["last"] = int(self.clock())
                if progress["ended"]:
                    self._grant_effects(snapshot, row)
                    pushes += self._settle_letter_favor(snapshot, progress)
            if success:
                self._dirty = True
            values = {"code": 10 if success else 13,
                      "letterBox": self._letter_box(hero_id, snapshot) if success else None,
                      "blcakHeros": self._blocked(snapshot)}
            if name == "C2L_ReplyLetter":
                values.update(heroID=hero_id, groupID=req.get("groupID", 0),
                              letterID=letter_id, replyID=req.get("replyID", 0))
            self._flush(player_id, snapshot)
            return OutboundMessage(reply, values, pushes=pushes)
        hero_id, blog_id = req.get("heroID", 0), req.get("groupID", 0)
        row = self.blogs.get(blog_id)
        hero = self._owned(snapshot).get(hero_id)
        success = bool(row and hero and row["HeroID"] == hero_id and self._available(row, hero, snapshot))
        if success:
            progress = state["blogs"].setdefault(str(blog_id), {"start": int(self.clock()), "replies": {}})
            if name == "C2L_LikeNpcBlog":
                # 时光点赞加默契: 只在「由未赞变已赞」的那一次发 (取消赞不发, 再赞因为
                # like 置 0 后会重新计 —— 与客户端点赞按钮的开关语义一致)。单次动作
                # 即时发放并推送, 客户端才会当场提示「默契 +N」。
                if not progress.get("like"):
                    progress["like"] = int(self.clock())
                    pushes += self._grant_favor(hero_id, BLOG_LIKE_FAVOR,
                                                ADD_FAVOR_TYPE_REPLY_BLOG)
                else:
                    progress["like"] = 0
            else:
                reply_id = req.get("replyID", 0)
                success = reply_id in row.get("ReplyContent", []) and reply_id != 0
                if success:
                    chat_id = str(req.get("chatGroupID", 0))
                    # 时光评论加默契: 每条动态的每个评论区首次留言才发一次。
                    if chat_id not in progress["replies"]:
                        pushes += self._grant_favor(hero_id, BLOG_REPLY_FAVOR,
                                                    ADD_FAVOR_TYPE_REPLY_BLOG)
                    progress["replies"][chat_id] = reply_id
                    progress.setdefault("reply_times", {})[chat_id] = int(self.clock())
            if success:
                self._dirty = True
        values = {"code": 10 if success else 13,
            "blogBox": self._blog_box(hero_id, snapshot) if success else None,
            "blcakHeros": self._blocked(snapshot)}
        self._flush(player_id, snapshot)
        return OutboundMessage(reply, values, pushes=pushes)
