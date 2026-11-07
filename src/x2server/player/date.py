"""约会 / 契约 (FavorDate): the four exchanges behind the 2.4 client's 约会 page.

The 2.4 client ships the whole page (``FavorDateModule``); the data was switched
off rather than the code. This module owns the state and the replies:

    C2L_QueryHeroDate      641/642  the tab's one-shot query
    C2L_UnLockDateOption   645/646  claim one 契约碎片 of an opened date
    C2L_SelcetDateOption   647/648  pick one of the date's own options
    C2L_OpenContract       649/650  缔结契约

What the client does with the replies (disassembly of the 2.4 build's
``FavorDateModule``):

* ``OnHandleQueryDateData`` stores the whole ``L2C_QueryHeroDate`` into one
  ``HeroDate {heroId, date, journal, skin}``.
* ``GetUnlockChipNumByDateInfo`` counts option pairs with value > 0 - and only
  for dates whose status is UNLOCK(3).
* ``OnHandleUnlockChip`` finds the pair *by key* in the date's list and overwrites
  its value; it never appends.
* ``OnHandleSelectDateOption`` replaces the date's option list with the reply's
  list.
* ``OnHandleMarry`` sets ``HeroDate.skin = 1`` on code 10 and hands the reply's
  rewardData to the reward window.
* ``CheckCanMarry`` requires level >= 19, exp >= 8100, chip count >=
  GlobalParamString['CovenantChipsNum'] (18) and BagModule.GetItemNum(信物) >= 1.
* ``RefreshHeroDateBadge`` lights the 约会 tab when *any* pair of *any* date has
  value 0, without a status gate.

So:

* a **chip pair's ``Key`` is the 拼图位置** (1..18), never the OptionEffect id:
  ``FavorDateTab_MarryView_SetData`` indexes ``nodes[Key - 1]`` and
  ``ChipMaskNode_SetData`` builds the sprite name as ``FavorabilityHero.f12 + Key``.
* a date gets **all** of its chips as pairs (value 0 while unclaimed) **only once
  its status is UNLOCK**; a LOCK date ships just the rows the save already holds.
  Shipping a locked date's zeros would light the tab forever while MarryView has
  nothing to bind.
* **date options (OptionEffect 13/11) are never shipped as pairs** - they are not
  chips, and their Key would be read as a grid position. They stay server-side in
  ``hero_date_options`` and only feed ``completed_dates`` (the 手账 rows behind
  约会完成).
* the select-option reply must be the **whole** list (chips included), otherwise
  choosing a date option would zero the 碎片 count of that date.
* ``status`` is DateStatus: 0 NONE, 1 NOTOPEN, 2 LOCK, 3 UNLOCK; the level gate
  decides 2 vs 3.

Storage is two tables (``hero_date_options``, ``hero_contracts``) keyed by
(player, hero), created by ``favor.ensure_schema``. The catalog both modules read
(``favor_date_catalog.json``) is generated from the patched client, so the server's
date list and the client's ``mShowDateDic`` cannot drift.

Two deliberate choices, both visible to the player:

* **Unlocking a chip is free** once its date is UNLOCK. The request carries no
  price and no table names one, so charging would be inventing a cost; the date's
  好感 level is the gate instead.
* **The 信物 is the only 契约 cost.** ``FavorabilityLevel``'s IsCovenant row
  carries ``CovenantItem = [1204011, 1]`` and the client's CheckCanMarry asks for
  exactly that item; it is spent here, and the contract opens the 好感 ceiling to
  20 (``favor.level_cap``).
"""
from __future__ import annotations

import logging

from x2server.messages.date import (
    DATE_SCHEMAS,
    DATE_STATUS_LOCK,
    DATE_STATUS_UNLOCK,
    KEY_VALUE,
    NPC_DATE,
)
from x2server.network.dispatcher import DispatchContext, OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.types import DecodedPacket

from .favor import (covenant_rules, date_catalog, date_rows, ensure_schema,
                    hero_journal_ids, hero_level)

LOGGER = logging.getLogger("x2.date")


def option_values(store, player_id: int, hero_id: int) -> dict[int, dict[int, int]]:
    """{date_id: {option_id: value}} for one hero."""
    rows = store.db.execute(
        "SELECT date_id, option_id, value FROM hero_date_options WHERE player_id=? AND hero_id=?",
        (player_id, hero_id)).fetchall()
    out: dict[int, dict[int, int]] = {}
    for date_id, option_id, value in rows:
        out.setdefault(int(date_id), {})[int(option_id)] = int(value)
    return out


def unlocked_chips(hero_id: int, values: dict[int, dict[int, int]]) -> int:
    """How many 契约碎片 the save holds: pairs with value > 0, chips only.

    Restricted to the catalog's chip keys (the 拼图位置 1..18) so a chosen *date
    option* - also stored in the same table - cannot pay for the 契约: the client
    would count it, so this is deliberately the stricter number.
    """
    total = 0
    for row in date_rows(hero_id):
        chips = {int(chip) for chip in row.get("chips", ())}
        total += sum(1 for option_id, value in values.get(int(row["id"]), {}).items()
                     if value > 0 and option_id in chips)
    return total


def completed_dates(store, player_id: int, hero_id: int) -> tuple[int, ...]:
    """Dates the save actually played, for the 手账 rows that hang off 约会完成.

    "Played" = one of the date's **own options** (the catalog's ``options``) was
    recorded with value > 0. Chips alone do not count: they are handed out while
    the date is merely open, and the two 手账 entries that need this
    (6101005/6101006) are the story's reward, not the chip's.
    """
    values = option_values(store, player_id, hero_id)
    played = []
    for row in date_rows(hero_id):
        options = {int(option) for option in row.get("options", ())}
        if any(value > 0 and option_id in options
               for option_id, value in values.get(int(row["id"]), {}).items()):
            played.append(int(row["id"]))
    return tuple(played)


def is_married(store, player_id: int, hero_id: int) -> bool:
    return store.db.execute("SELECT 1 FROM hero_contracts WHERE player_id=? AND hero_id=?",
                            (player_id, hero_id)).fetchone() is not None


def write_option(store, player_id: int, hero_id: int, date_id: int, option_id: int,
                 value: int, now: int) -> None:
    """Record an option. Raises are monotonic - a value never drops back to 0."""
    store.db.execute("""INSERT INTO hero_date_options VALUES (?,?,?,?,?,?)
        ON CONFLICT(player_id, hero_id, date_id, option_id)
        DO UPDATE SET value=MAX(value, excluded.value), updated_at=excluded.updated_at""",
                     (player_id, hero_id, date_id, option_id, value, now))


def write_contract(store, player_id: int, hero_id: int, now: int) -> None:
    store.db.execute("INSERT OR IGNORE INTO hero_contracts VALUES (?,?,?)",
                     (player_id, hero_id, now))


def migrate_legacy_chip_keys(store) -> None:
    """旧存档的碎片是按 OptionEffect id 存的 (Key=2141004), 现在 Key 是拼图位置。

    不迁移的话, 已经点过的碎片在 6x3 网格里会变成孤儿(服务端不再下发那个 Key)。
    对不上号的旧行原样留着: 它们只是不再下发, 也不会影响完成度.
    """
    rows = store.db.execute(
        "SELECT player_id, hero_id, date_id, option_id, value, updated_at "
        "FROM hero_date_options").fetchall()
    moved = 0
    with store.db:
        for player_id, hero_id, date_id, option_id, value, updated_at in rows:
            row = next((r for r in date_rows(int(hero_id)) if int(r["id"]) == int(date_id)), None)
            if row is None:
                continue
            chip_ids = [int(x) for x in row.get("chip_ids", ())]
            chips = [int(x) for x in row.get("chips", ())]
            old = int(option_id)
            if old not in chip_ids:
                continue
            position = chips[chip_ids.index(old)]
            store.db.execute("DELETE FROM hero_date_options "
                             "WHERE player_id=? AND hero_id=? AND date_id=? AND option_id=?",
                             (player_id, hero_id, date_id, old))
            write_option(store, player_id, hero_id, date_id, position, int(value), int(updated_at))
            moved += 1
    if moved:
        LOGGER.info("hero_date_options: %s 条旧碎片 Key(OptionEffect id) 迁移为拼图位置", moved)


def covenant_skins() -> dict[int, tuple[int, int]]:
    """{heroId: (契约形象 id, 花嫁头像 id)} for the 契约 reward.

    ``covenant_skins.json`` is generated next to ``favor_date_catalog.json`` from
    the client's Appearance / Picture tables (the row whose AcquireCondition is 3,
    plus the 头像 row numbered ``外观 + 50000``). Only 1010 has one - the other 24
    heroes keep the system but have no 契约 art in the client, so their 契约 grants
    an empty reward list. ``headId`` is 0 when the head row is missing.
    """
    try:
        from .favor import _load_catalog
        payload = _load_catalog("covenant_skins.json")
    except Exception as exc:  # noqa: BLE001 - a reward lookup must not kill the request
        LOGGER.error("covenant_skins.json unavailable (%s); 契约 rewards stay empty", exc)
        return {}
    return {int(skin["heroId"]): (int(skin["id"]), int(skin.get("headId", 0)))
            for skin in payload.get("skins", ()) if int(skin.get("heroId", 0)) > 0}


class DateService:
    def __init__(self, store, economy=None, clock=None) -> None:
        self.store = store
        self.economy = economy
        self.clock = clock
        ensure_schema(store)
        migrate_legacy_chip_keys(store)
        # Optional injection for deployments that push the login snapshot directly;
        # when absent the economy's own pushes carry the new 外观/头像.
        self.snapshot_push = None

    def handlers(self) -> dict:
        return {
            "C2L_QueryHeroDate": self.query_date,
            "C2L_UnLockDateOption": self.unlock_option,
            "C2L_SelcetDateOption": self.select_option,
            "C2L_OpenContract": self.open_contract,
        }

    # ------------------------------------------------------------- helpers

    def _now(self) -> int:
        return int(self.clock()) if self.clock else 0

    def _owns(self, player_id: int, hero_id: int) -> bool:
        snapshot = self.store.get(player_id)["snapshot"]
        return any(int(hero.get("id", 0)) == hero_id and hero.get("state") == 2
                   for hero in snapshot.get("heroes", []))

    @staticmethod
    def _date_row(hero_id: int, date_id: int) -> dict | None:
        return next((row for row in date_rows(hero_id) if int(row["id"]) == date_id), None)

    @staticmethod
    def _status(row: dict, level: int) -> int:
        return DATE_STATUS_UNLOCK if level >= int(row["level"]) else DATE_STATUS_LOCK

    def _pairs(self, hero_id: int, date_id: int, chips, values, status: int) -> list[bytes]:
        """The date's 碎片 list, keyed by 拼图位置 (the catalog's ``chips``).

        A LOCK date carries no zero-value chip. The client's red dot walks every
        date's pairs and counts value 0 without checking ``status``, so a locked
        date's 9 zeros light the 约会 tab even though the 契约 page only binds
        chips of an UNLOCK date - a dot with nothing to tap. Rows the save already
        holds are still shipped, so a value can never be lost.

        Only chips go out: a non-chip option's Key would index the same 6x3 grid,
        and keeping the list chip-only is what makes the 完成度 = 已收集/总数.
        """
        recorded = values.get(int(date_id), {})
        out = []
        for chip in chips:
            key = int(chip)
            value = int(recorded.get(key, 0))
            if status != DATE_STATUS_UNLOCK and value <= 0:
                continue
            out.append(KEY_VALUE.encode({"Key": key, "Value": value}))
        return out

    def _push(self, player_id: int) -> tuple[OutboundMessage, ...]:
        out = []
        if self.snapshot_push is not None:
            try:
                out.append(self.snapshot_push(player_id))
            except Exception as exc:  # noqa: BLE001 - answered alone rather than not at all
                LOGGER.error("contract snapshot push failed (%s)", exc)
        if self.economy is not None:
            out.extend(self.economy.pushes(player_id))
        return tuple(out)

    # ------------------------------------------------------------ handlers

    async def query_date(self, context: DispatchContext, packet: DecodedPacket) -> OutboundMessage:
        """C2L_QueryHeroDate: the 约会 tab's one-shot query.

        ``date`` is the hero's IsUse=1 rows with their status and option pairs,
        ``journal`` is the same 手账 id list 657/658 carries, and ``skin`` is the
        契约 flag - the client stores it and sets it to 1 on a successful 649.
        """
        if context.session.player_id is None:
            raise ProtocolError("hero date query before login")
        request = DATE_SCHEMAS["C2L_QueryHeroDate"].decode(packet.body)
        hero_id = int(request.get("heroId", 0))
        player_id = context.session.player_id
        level, _exp = hero_level(self.store, player_id, hero_id)
        values = option_values(self.store, player_id, hero_id)
        dates = []
        for row in date_rows(hero_id):
            status = self._status(row, level)
            dates.append(NPC_DATE.encode({
                "status": status,
                "option": self._pairs(hero_id, row["id"], row.get("chips", ()),
                                      values, status),
                "id": int(row["id"]),
            }))
        journal = hero_journal_ids(hero_id, level, completed_dates(self.store, player_id, hero_id))
        skin = 1 if is_married(self.store, player_id, hero_id) else 0
        LOGGER.info("hero date served player=%s hero=%s level=%s dates=%s skin=%s",
                    player_id, hero_id, level, [int(row["id"]) for row in date_rows(hero_id)], skin)
        return OutboundMessage("L2C_QueryHeroDate", {
            "code": 10,
            "date": dates,
            "journal": journal,
            "skin": skin,
            "heroId": hero_id,
        })

    async def unlock_option(self, context: DispatchContext,
                            packet: DecodedPacket) -> OutboundMessage:
        """C2L_UnLockDateOption: hand the player one 契约碎片 of an opened date.

        The reply carries the single pair that changed; the client finds it by key
        in the list the query handed out and overwrites the value, so a chip id
        that is not in the catalog's list for that date can never take effect -
        which is why anything unknown is refused instead of stored.
        """
        if context.session.player_id is None:
            raise ProtocolError("date option unlock before login")
        request = DATE_SCHEMAS["C2L_UnLockDateOption"].decode(packet.body)
        hero_id = int(request.get("heroId", 0))
        date_id = int(request.get("dateId", 0))
        option_id = int(request.get("optionId", 0))
        player_id = context.session.player_id
        failure = OutboundMessage("L2C_UnLockDateOption",
                                  {"code": 13, "heroId": hero_id, "dateId": date_id})
        if not self._owns(player_id, hero_id):
            return failure
        row = self._date_row(hero_id, date_id)
        if row is None or option_id not in {int(chip) for chip in row.get("chips", ())}:
            LOGGER.info("date option refused player=%s hero=%s date=%s option=%s (not a chip)",
                        player_id, hero_id, date_id, option_id)
            return failure
        level, _exp = hero_level(self.store, player_id, hero_id)
        if level < int(row["level"]):
            LOGGER.info("date option refused player=%s hero=%s date=%s level=%s < %s",
                        player_id, hero_id, date_id, level, row["level"])
            return failure
        with self.store.db:
            write_option(self.store, player_id, hero_id, date_id, option_id, 1, self._now())
        values = option_values(self.store, player_id, hero_id)
        value = int(values.get(date_id, {}).get(option_id, 1))
        LOGGER.info("date option unlocked player=%s hero=%s date=%s chip=%s (chips=%s)",
                    player_id, hero_id, date_id, option_id,
                    unlocked_chips(hero_id, values))
        return OutboundMessage("L2C_UnLockDateOption", {
            "code": 10,
            "heroId": hero_id,
            "dateId": date_id,
            "option": KEY_VALUE.encode({"Key": option_id, "Value": value}),
        }, pushes=self._push(player_id))

    async def select_option(self, context: DispatchContext,
                            packet: DecodedPacket) -> OutboundMessage:
        """C2L_SelcetDateOption: pick one of the date's own options.

        The choice is **stored only** (it is the 约会完成 flag behind the 手账
        rows) and never sent as a pair. The reply is a *whole-list* replacement, so
        it ships every chip again with its current value: a reply that carried
        nothing would wipe the date's 碎片.
        """
        if context.session.player_id is None:
            raise ProtocolError("date option select before login")
        request = DATE_SCHEMAS["C2L_SelcetDateOption"].decode(packet.body)
        hero_id = int(request.get("heroId", 0))
        date_id = int(request.get("dateId", 0))
        option_effect_id = int(request.get("optionEffectId", 0))
        player_id = context.session.player_id
        failure = OutboundMessage("L2C_SelcetDateOption",
                                  {"code": 13, "heroId": hero_id, "dateId": date_id})
        if not self._owns(player_id, hero_id) or option_effect_id <= 0:
            return failure
        row = self._date_row(hero_id, date_id)
        if row is None:
            return failure
        # 碎片 Key 是拼图位置 1..18, 不能被当成「约会选项」写进来(否则会白送一枚碎片)。
        if option_effect_id in {int(chip) for chip in row.get("chips", ())}:
            LOGGER.info("date option refused player=%s hero=%s date=%s effect=%s (is a chip)",
                        player_id, hero_id, date_id, option_effect_id)
            return failure
        level, _exp = hero_level(self.store, player_id, hero_id)
        if level < int(row["level"]):
            LOGGER.info("date option select refused player=%s hero=%s date=%s level=%s < %s",
                        player_id, hero_id, date_id, level, row["level"])
            return failure
        with self.store.db:
            write_option(self.store, player_id, hero_id, date_id, option_effect_id, 1, self._now())
        values = option_values(self.store, player_id, hero_id)
        LOGGER.info("date option selected player=%s hero=%s date=%s effect=%s (played=%s)",
                    player_id, hero_id, date_id, option_effect_id,
                    completed_dates(self.store, player_id, hero_id))
        return OutboundMessage("L2C_SelcetDateOption", {
            "code": 10,
            "heroId": hero_id,
            "dateId": date_id,
            "option": self._pairs(hero_id, date_id, row.get("chips", ()), values,
                                  self._status(row, level)),
        }, pushes=self._push(player_id))

    async def open_contract(self, context: DispatchContext,
                            packet: DecodedPacket) -> OutboundMessage:
        """C2L_OpenContract: 缔结契约 - the mirror of the client's CheckCanMarry.

        The gates are the client's own (level >= marryNeedLevel, exp >= the next
        level's Exp, every 契约碎片, one 信物) and are re-checked here rather than
        trusted, because the client's button state is only a hint: an edited save
        or a stale page must not be able to buy the 外观 for free.

        The 信物 spend, the contract row, the 19-level break and the reward all
        happen in one transaction. The contract row is the idempotency key, and the
        reward is written straight into ``inventory`` because the two 契约 items
        (1221004 外观 / 1271004 花嫁头像) predate ``economy_catalog.items``; the
        appearance page reads owned 外观 from the very same inventory table.
        """
        if context.session.player_id is None:
            raise ProtocolError("contract before login")
        request = DATE_SCHEMAS["C2L_OpenContract"].decode(packet.body)
        hero_id = int(request.get("heroId", 0))
        player_id = context.session.player_id
        failure = OutboundMessage("L2C_OpenContract", {"code": 13, "heroId": hero_id})
        rules = covenant_rules()
        if not rules or not self._owns(player_id, hero_id) or is_married(self.store, player_id, hero_id):
            return failure
        if not date_rows(hero_id):
            return failure
        level, exp = hero_level(self.store, player_id, hero_id)
        values = option_values(self.store, player_id, hero_id)
        chips = unlocked_chips(hero_id, values)
        need_chips = int(date_catalog().get("chips_num", 0))
        reasons = []
        if level < int(rules.get("need_level", 99)):
            reasons.append("level %s < %s" % (level, rules.get("need_level")))
        if exp < int(rules.get("need_exp", 1 << 30)):
            reasons.append("exp %s < %s" % (exp, rules.get("need_exp")))
        if chips < need_chips:
            reasons.append("chips %s < %s" % (chips, need_chips))
        item_id = int(rules.get("item_id", 0))
        item_num = int(rules.get("item_num", 1))
        held = self.store.db.execute("SELECT quantity FROM inventory WHERE player_id=? AND item_id=?",
                                     (player_id, item_id)).fetchone()
        if item_id <= 0 or (held is None or held[0] < item_num):
            reasons.append("信物 %s x%s missing" % (item_id, item_num))
        if reasons:
            LOGGER.info("contract refused player=%s hero=%s (%s)", player_id, hero_id, "; ".join(reasons))
            return failure
        if self.economy is None:
            LOGGER.error("contract for player=%s hero=%s needs the economy; refused", player_id, hero_id)
            return failure

        rewards = {}
        appearance, head_icon = covenant_skins().get(hero_id, (0, 0))
        if appearance:
            rewards[appearance] = 1
        # 花嫁头像(1271004)和外观是同一次契约的两件产物: 外观让立绘可切换, 头像
        # 让个人页能换上花嫁头。头像号是外观号 + 50000, 目录里没有 Picture 行时是 0。
        if head_icon:
            rewards[head_icon] = 1
        need_level = int(rules.get("need_level", 19))
        with self.economy.transaction():
            snapshot = self.store.get(player_id)["snapshot"]
            target = next((h for h in snapshot.get("heroes", [])
                           if int(h.get("id", 0)) == hero_id and h.get("state") == 2), None)
            if target is None:
                return failure
            charged = self.store.db.execute("""UPDATE inventory SET quantity=quantity-?
                WHERE player_id=? AND item_id=? AND quantity>=?""",
                (item_num, player_id, item_id, item_num))
            if charged.rowcount != 1:
                return failure
            write_contract(self.store, player_id, hero_id, self._now())
            # 契约本身就是 19 级那次「突破」: FavorabilityLevel 的 19 行同时带
            # IsBreak(第 4 次) 和 IsCovenant, 而 Language 13430054 写的是
            # 「缔结契约后好感可升至 20 级」。不记这一笔的话 advance 会把 19 级钉死,
            # 契约完也升不到 20。这里直接改快照, 和 favor 的突破存储保持同一形状。
            breaks = target.setdefault("favor_breaks", [])
            if need_level not in breaks:
                breaks.append(need_level)
            for item, count in rewards.items():
                self.store.db.execute("""INSERT INTO inventory VALUES (?,?,?)
                    ON CONFLICT(player_id,item_id) DO UPDATE SET quantity=quantity+excluded.quantity""",
                    (player_id, item, count))
            self.economy.save_snapshot(player_id, snapshot)
        LOGGER.info("contract opened player=%s hero=%s level=%s exp=%s chips=%s reward=%s",
                    player_id, hero_id, level, exp, chips, rewards)
        return OutboundMessage("L2C_OpenContract", {
            "code": 10,
            "heroId": hero_id,
            "rewardData": self.economy.reward_bytes(rewards),
        }, pushes=self._push(player_id))
