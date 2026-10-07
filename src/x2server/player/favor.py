"""Official-table favor state; uncertain interactions fail without consuming items."""
from importlib.resources import files
from datetime import datetime, timedelta, timezone
import json
import logging
import time
from collections import Counter

from x2server.messages.favor import FAVOR_SCHEMAS, FAVOR_CHANGE_INFO
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY

LOGGER = logging.getLogger("x2.favor")

_INTERACTION_MAP = None


def catalog():
    return json.loads(files("x2server").joinpath("data/favor_catalog.json").read_text(encoding="utf-8"))


def interaction_map():
    """ExpressionAnimStatus InteractiveID -> HeroID for the daily tap."""
    global _INTERACTION_MAP
    if _INTERACTION_MAP is None:
        data = json.loads(files("x2server").joinpath("data/interaction_hero.json").read_text(encoding="utf-8"))
        _INTERACTION_MAP = data.get("by_interaction", {})
    return _INTERACTION_MAP


def favor_state(hero, initial_level=1):
    return hero.get("favor", {"level": initial_level, "exp": 0})


class FavorService:
    def __init__(self, store, economy, clock=time.time):
        self.store, self.economy, self.clock = store, economy, clock
        data = catalog()
        self.heroes = {r["HeroID"]: r for r in data["favorabilityhero"]}
        self.levels = {r["FavorLevel"]: r for r in data["favorabilitylevel"]}
        self.gifts = {r["ItemID"]: r for r in data["gifts"]}
        self.favorites = {r["HeroID"]: set(r["FavoriteGoodID"])
                          for r in data["sendgiftcontrol"]}
        self.files = {r["FilesID"]: r for r in data["favorabilityfiles"]}
        self.dairy = data["favorabilitydairy"]
        step_fields = ("Level", "FavorabilityLevel", "StarLevel", "HeroLevel", "CurrencyNum")
        candidates = Counter(tuple(tuple(r[key]) for key in step_fields)
            for r in data["favorabilityfetters"] if r.get("CurrencyID") == 901
            and all(len(r.get(key, [])) == 10 and all(type(v) is int and v > 0 for v in r[key]) for key in step_fields))
        self.fetter_steps = dict(zip(step_fields, candidates.most_common(1)[0][0])) if candidates else {}
        self.fetter_steps["CurrencyID"] = 901
        with store.db:
            store.db.execute("""CREATE TABLE IF NOT EXISTS favor_touch_log (
                player_id INTEGER NOT NULL, hero_id INTEGER NOT NULL, day TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(player_id, hero_id, day))""")

    def handlers(self):
        return {"C2L_" + name: self.handle for name in
            ("AddFavor", "UpgradeFetters", "UnlockHeroArchives", "QueryHeroArchives",
             "FavorBreak", "QueryHeroJournal")}

    def _owned(self, player_id, hero_id):
        return next((h for h in self.store.get(player_id)["snapshot"].get("heroes", [])
                     if h["id"] == hero_id and h["state"] == 2 and hero_id in self.heroes), None)

    def _interaction_target(self, player_id, interaction_id):
        try:
            hero_id = interaction_map().get(str(int(interaction_id or 0)))
        except (TypeError, ValueError):
            return None
        return self._owned(player_id, int(hero_id)) if hero_id else None

    def _showcase_hero(self, player_id):
        """Last resort for unmapped taps: the shown god, else any owned god."""
        snapshot = self.store.get(player_id)["snapshot"]
        hero = self._owned(player_id, snapshot.get("show", 0)) if snapshot.get("show") else None
        if hero:
            return hero
        for owned in sorted(h["id"] for h in snapshot.get("heroes", [])
                            if h.get("state") == 2 and h["id"] in self.heroes):
            return self._owned(player_id, owned)
        return None

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
        if name == "C2L_FavorBreak":
            return self._break(player_id, hero_id, hero)
        if name == "C2L_UpgradeFetters":
            return self._upgrade_fetters(player_id, hero_id, req.get("positionId", 0))
        if name == "C2L_QueryHeroArchives":
            from .hero import encode_hero_data
            return OutboundMessage(reply, {"code": 10 if hero else 13, "needRefresh": bool(hero)},
                pushes=(OutboundMessage("L2C_HeroUpdate", {"code": 10,
                    "heros": [encode_hero_data(hero)]}),) if hero else ())
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
            from .hero import encode_hero_data
            return OutboundMessage(reply, {"code": 10, "heroID": hero_id, "archivesID": file_id},
                pushes=(OutboundMessage("L2C_HeroUpdate", {"code": 10,
                    "heros": [encode_hero_data(target)]}),))
        return OutboundMessage(reply, {"code": 13,
            "mainHeroId": hero_id, "positionId": req.get("positionId", 0)})

    def _upgrade_fetters(self, player_id, hero_id, position):
        values = {"code": 13, "mainHeroId": hero_id, "positionId": position}
        row = next((r for r in catalog()["favorabilityfetters"]
                    if r["HeroID"] == hero_id and r["FettersID"] == position
                    and r.get("IsOpen") == 1), None)
        with self.economy.transaction():
            snapshot = self.store.get(player_id)["snapshot"]
            hero = next((h for h in snapshot.get("heroes", [])
                         if h["id"] == hero_id and h.get("state") == 2), None)
            level = hero.get("favor_fetters", {}).get(str(position), 0) if hero else -1
            if not row or not hero or not 0 <= level < 10 or "Level" not in self.fetter_steps:
                return OutboundMessage("L2C_UpgradeFetters", values)
            # The shared ten-step table is the canonical consensus. Individual
            # damaged exports do not make an otherwise valid position unusable.
            row = self.fetter_steps
            favor = favor_state(hero, self.heroes[hero_id]["InitialLevel"])["level"]
            if (favor < row["FavorabilityLevel"][level]
                    or hero["star"] < row["StarLevel"][level]
                    or hero["level"] < row["HeroLevel"][level]
                    or row["CurrencyID"] != 901
                    or snapshot.get("gold", 0) < row["CurrencyNum"][level]):
                return OutboundMessage("L2C_UpgradeFetters", values)
            snapshot["gold"] -= row["CurrencyNum"][level]
            hero.setdefault("favor_fetters", {})[str(position)] = level + 1
            self.economy.save_snapshot(player_id, snapshot)
        from .hero import encode_hero_data
        values["code"] = 10
        return OutboundMessage("L2C_UpgradeFetters", values, pushes=(
            OutboundMessage("L2C_HeroUpdate", {"code": 10, "heros": [encode_hero_data(hero)]}),
            *self.economy.pushes(player_id)))

    def _advance(self, hero_id, state, breaks):
        cap = self.heroes[hero_id]["LevelLimit"]
        while state["level"] < cap:
            current = state["level"]
            if self.levels[current].get("IsBreak") and current not in breaks:
                break
            if state["exp"] < self.levels[current + 1]["Exp"]:
                break
            state["level"] += 1
        return state

    def grant_favor(self, player_id, hero_id, amount):
        """Add 好感经验 to one hero and report the change.

        心愿任务 的领取 pays two things: the task's gift group (an item group, paid by
        the economy) and its own ``FavorabilityGift`` - a plain experience amount
        (50/60/75 in the client's table) that goes onto the named god through the same
        curve a touch or a 送礼 uses. This is the entry point for the second half, so a
        task claim and a manual interaction cannot drift apart.

        Runs inside the caller's transaction (``EconomyService.claim_favor_task`` opens
        one); it must not start its own, or a nested COMMIT would break that savepoint.

        Returns the L2C_FavorChangeInfo push for the caller to attach, so the 角色页 bar
        moves without the page asking again. An unusable hero or a zero gain answers
        with no push rather than a fabricated one.
        """
        if hero_id <= 0 or amount <= 0 or hero_id not in self.heroes:
            LOGGER.info("favor grant skipped player=%s hero=%s amount=%s",
                        player_id, hero_id, amount)
            return ()
        snapshot = self.store.get(player_id)["snapshot"]
        target = next((h for h in snapshot.get("heroes", [])
                       if h["id"] == hero_id and h.get("state") == 2), None)
        if target is None:
            LOGGER.info("favor grant skipped player=%s hero=%s amount=%s (not owned)",
                        player_id, hero_id, amount)
            return ()
        before = favor_state(target, self.heroes[hero_id]["InitialLevel"])
        state = before.copy()
        state["exp"] += amount
        self._advance(hero_id, state, target.get("favor_breaks", []))
        target["favor"] = state
        self.economy.save_snapshot(player_id, snapshot)
        LOGGER.info("favor granted player=%s hero=%s gain=%s %s/%s -> %s/%s",
                    player_id, hero_id, amount, before["level"], before["exp"],
                    state["level"], state["exp"])
        # type 0 = E_AddFavorType.FAVOR_TASK, the bar animation for a task payout
        # (a manual tap is 6, a gift is 7). Same message the two other sources push.
        change = FAVOR_CHANGE_INFO.encode({"beforeLevel": before["level"],
            "beforeExp": before["exp"], "afterLevel": state["level"], "afterExp": state["exp"],
            "heroID": hero_id, "type": 0})
        return (OutboundMessage("L2C_FavorChangeInfo", {"data": [change]}),)

    def _break(self, player_id, hero_id, hero):
        failure = OutboundMessage("L2C_FavorBreak", {"code": 13, "heroId": hero_id})
        if not hero:
            return failure
        current = favor_state(hero, self.heroes[hero_id]["InitialLevel"])["level"]
        row = self.levels[current]
        if not row.get("IsBreak") or current in hero.get("favor_breaks", []):
            return failure
        costs = list(zip(row.get("BreakItem", []), row.get("BreakItemNum", []), strict=True))
        if not costs:
            return failure
        with self.economy.transaction():
            for item_id, quantity in costs:
                available = self.store.db.execute("SELECT quantity FROM inventory WHERE player_id=? AND item_id=?",
                                                  (player_id, item_id)).fetchone()
                if not available or available[0] < quantity:
                    return failure
            for item_id, quantity in costs:
                charged = self.store.db.execute("""UPDATE inventory SET quantity=quantity-?
                    WHERE player_id=? AND item_id=? AND quantity>=?""",
                    (quantity, player_id, item_id, quantity))
                if charged.rowcount != 1:
                    raise RuntimeError("favor break inventory changed during transaction")
            snapshot = self.store.get(player_id)["snapshot"]
            target = next(h for h in snapshot["heroes"] if h["id"] == hero_id and h["state"] == 2)
            breaks = target.setdefault("favor_breaks", [])
            breaks.append(current)
            state = favor_state(target, self.heroes[hero_id]["InitialLevel"]).copy()
            target["favor"] = self._advance(hero_id, state, breaks)
            self.economy.save_snapshot(player_id, snapshot)
        from .hero import encode_hero_data
        return OutboundMessage("L2C_FavorBreak", {"code": 10, "heroId": hero_id}, pushes=(
            OutboundMessage("L2C_HeroUpdate", {"code": 10, "heros": [encode_hero_data(target)]}),
            *self.economy.pushes(player_id)))

    def _add(self, player_id, req, hero):
        hero_id, item_id, num, opt = (req.get("heroId", 0), req.get("optionId", 0),
                                     req.get("num", 0), req.get("opt", -1))
        if opt != 2:
            # The client's daily tap animation arrives as opt=1 with heroId=0
            # and the interaction id in optionId. ExpressionAnimStatus maps
            # InteractiveID -> HeroID (data/interaction_hero.json, 36 live
            # requests all carried heroId=0); without that lookup the touch is
            # booked against no god and the daily interactive task never moves.
            target = (hero
                      or self._interaction_target(player_id, item_id)
                      or self._interaction_target(player_id, hero_id)
                      or self._showcase_hero(player_id))
            target_id = target["id"] if target else 0
            LOGGER.info("hero interaction player=%s opt=%s optionId=%s heroId=%s num=%s target=%s",
                        player_id, opt, item_id, hero_id, num, target_id)
            if target is None:
                return OutboundMessage("L2C_AddFavor", {"code": 13, "opt": opt,
                    "optionId": item_id, "heroId": hero_id})
            day = datetime.fromtimestamp(int(self.clock()), timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
            row = self.store.db.execute("SELECT count FROM favor_touch_log WHERE player_id=? AND hero_id=? AND day=?",
                                        (player_id, target_id, day)).fetchone()
            used = row[0] if row else 0
            if used >= 3:
                # Still push state so an open task page re-renders, but never
                # count a rejected tap towards the interactive task.
                return OutboundMessage("L2C_AddFavor", {"code": 13, "opt": opt,
                    "optionId": item_id, "heroId": target_id}, pushes=self.economy.pushes(player_id))
            with self.economy.transaction():
                self.store.db.execute("INSERT INTO favor_touch_log VALUES (?,?,?,1) "
                                      "ON CONFLICT(player_id,hero_id,day) DO UPDATE SET count=count+1",
                                      (player_id, target_id, day))
                self.economy.record_event(player_id, f"touch:{target_id}:{day}:{used + 1}", 19, target_id)
            return OutboundMessage("L2C_AddFavor", {"code": 10, "opt": opt,
                "optionId": item_id, "heroId": target_id}, pushes=self.economy.pushes(player_id))
        before = favor_state(hero, self.heroes[hero_id]["InitialLevel"]) if hero else {"level": 0, "exp": 0}
        values = {"code": 13, "opt": opt, "optionId": item_id, "heroId": hero_id,
            "exp": before["exp"], "level": before["level"],
            "newExp": before["exp"], "newLevel": before["level"]}
        day = datetime.fromtimestamp(int(self.clock()), timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
        values["giftsTimes"] = hero.get("favor_gifts", {}).get("count", 0) if hero and hero.get("favor_gifts", {}).get("day") == day else 0
        gift = self.gifts.get(item_id)
        # SendGiftControl.FavoriteGoodID is the official hero preference list.
        if (not hero or opt != 2 or type(num) is not int or not 1 <= num <= 999 or
                not gift or not gift.get("EffData")):
            return OutboundMessage("L2C_AddFavor", values)
        gain = gift["EffData"][0] * num * (2 if item_id in self.favorites.get(hero_id, ()) else 1)
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
            self._advance(hero_id, state, target.get("favor_breaks", []))
            target["favor"] = state
            previous = target.get("favor_gifts", {})
            count = (previous.get("count", 0) if previous.get("day") == day else 0) + num
            target["favor_gifts"] = {"day": day, "count": count}
            self.economy.save_snapshot(player_id, snapshot)
            # 好感日常任务 E_SendDesignativeHeroGift(68) 数的是「给指定英雄送了指定的
            # 礼物」: hero 与 item 就是这条条件的两个维度, num 是一次送出的数量(条件的
            # CompleteNum 多为 3, 一次送 3 个与分三次各送 1 个都算达标)。token 带上
            # hero/item/day/累计次数, 重放的同一请求不会再计一次。
            self.economy.credit_favor_task(
                player_id, f"gift:{hero_id}:{item_id}:{day}:{count}",
                self.economy.TASK_EVENT_SEND_DESIGNATIVE_HERO_GIFT, hero_id, item_id, num)
            self.economy.achievements.record(player_id, f'gift:{hero_id}:{day}:{count}', 18, num)
        values.update(code=10, newExp=state["exp"], newLevel=state["level"], giftsTimes=count)
        change = FAVOR_CHANGE_INFO.encode({"beforeLevel": before["level"], "beforeExp": before["exp"],
            "afterLevel": state["level"], "afterExp": state["exp"], "heroID": hero_id, "type": 7})
        from .hero import encode_hero_data
        return OutboundMessage("L2C_AddFavor", values, pushes=(OutboundMessage(
            "L2C_FavorChangeInfo", {"data": [change]}), OutboundMessage("L2C_HeroUpdate",
            {"code": 10, "heros": [encode_hero_data(target)]}), *self.economy.pushes(player_id)))
