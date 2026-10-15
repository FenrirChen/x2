"""Canonical bag gifts and recipe operations, committed with replay receipts."""
from collections import Counter
import hashlib
import json
import logging
import secrets

from x2server.messages.economy import ECONOMY_SCHEMAS, REWARD, REWARD_ITEM
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from .economy import UnresolvedEconomy
from .equipment_factory import EquipmentValidationError


def resolve_bag_gifts(economy, item_id, groups, selected):
    rewards = Counter()
    pick_groups = [economy.bag_catalog["gifts"].get(str(g), {}).get("awardType") == 4 for g in groups]
    if selected and not any(pick_groups):
        raise UnresolvedEconomy("selection on a non-pick box")
    for group in groups:
        row = economy.bag_catalog["gifts"].get(str(group))
        if row is None:
            # Keep explicit server/test extensions outside the canonical catalog.
            rewards.update(economy.gifts([group], allow_daily_random=True))
            continue
        kind, entries, weights = row["awardType"], row["items"], row["weights"]
        if not entries or any(type(n) is not int or n < 0 or kind in (1, 4) and n == 0 for _, n in entries):
            raise UnresolvedEconomy("invalid bag Gift")
        if kind == 4:
            needed = weights[0] if len(weights) == 1 else 0
            if (not needed or len(selected) != needed or len(set(selected)) != len(selected)
                    or any(type(i) is not int or not 0 <= i < len(entries) for i in selected)):
                raise UnresolvedEconomy("invalid pick-box selection")
            entries = [entries[i] for i in selected]
        elif kind in (2, 5):
            # Blind-box compatibility: one weighted result from the canonical
            # candidate list per use; no invented quantities or probabilities.
            if len(weights) != len(entries) or any(w < 0 for w in weights) or sum(weights) <= 0:
                raise UnresolvedEconomy("invalid bag Gift weights")
            draw = secrets.randbelow(sum(weights))
            for entry, weight in zip(entries, weights, strict=True):
                draw -= weight
                if draw < 0:
                    entries = [entry]
                    break
        elif kind != 1 or weights:
            raise UnresolvedEconomy("unsupported bag Gift kind")
        for item, count in entries:
            if item not in economy.items:
                raise UnresolvedEconomy("unknown bag reward")
            if count:
                rewards[item] += count
    return rewards


def bag_reward_view(raw):
    """BagModule keys rewardItem by item ID; unique items must appear once.

    Keep the per-draw transformHero history for mixed new/duplicate outcomes.
    A mixed item is displayed as newly obtained, with its conversions separately
    represented by the already-granted fragment and ticket entries.
    """
    reward = REWARD.decode(raw)
    items = {}
    for entry in reward.get('rewardItem', []):
        item = REWARD_ITEM.decode(entry)
        key = item['itemId']
        if key in items:
            items[key]['itemNum'] += item.get('itemNum', 0)
            items[key]['transform'] = items[key].get('transform', False) and item.get('transform', False)
        else:
            items[key] = dict(item)
    reward['rewardItem'] = [REWARD_ITEM.encode(item) for item in items.values()]
    # UIAPI.ShowGetAwardItem uses TransformHero.heroId directly as an
    # ItemManager key (0x134c0e0-0x134c0f8), despite its misleading name.
    # Normalize legacy bag receipts as well as fresh outcomes. Wish results
    # have a separate client consumer and are deliberately outside this helper.
    from .wish import WishService
    history = []
    for raw_hero in reward.get('transformHero', []):
        hero = WishService.TRANSFORM_HERO.decode(raw_hero)
        if 1000 <= hero.get('heroId', 0) < 2000:
            hero['heroId'] += 1210000
        history.append(WishService.TRANSFORM_HERO.encode(hero))
    reward['transformHero'] = history
    return REWARD.encode(reward)


def grant_bag_rewards(economy, player, source, rewards, used_item):
    from .equipment_factory import materialize_instances
    from .progression import catalog
    from .wish import WishService
    from x2server.messages.equipment import HERO_EQUIP, EQUIP_PARAM
    ordinary, heroes, equips = Counter(), [], []
    snapshot = economy.store.get(player)["snapshot"]
    prototypes = {p["hero_id"]: p for p in catalog()["hero_unlock"]}
    star = economy.bag_catalog["items"].get(str(used_item), {}).get("equipmentStar")
    ordinal = 0
    for item, count in rewards.items():
        kind = economy.items[item].get("ItemType", {}).get("value")
        if kind == 10:
            if star is None or not economy.equipment_factory.is_drop_equipment(item):
                raise UnresolvedEconomy("bag equipment lacks canonical star/part evidence")
            left = count
            while left:
                amount = min(left, 99)
                instances = materialize_instances(economy.store.db, player, item, star, amount,
                    source, economy.equipment_factory, ordinal)
                ordinal += amount
                left -= amount
                equips.extend(HERO_EQUIP.encode({**{k: v for k, v in i.items() if k not in ("param", "marker")},
                    "param": EQUIP_PARAM.encode(i["param"])}) for i in instances)
        elif kind == 15:
            proto = prototypes.get(item - 1210000)
            if proto is None:
                raise UnresolvedEconomy("bag hero lacks prototype")
            for _ in range(count):
                existing = next((h for h in snapshot.get('heroes', []) if h['id'] == proto['hero_id']), None)
                duplicate = bool(existing and existing.get('state') == 2)
                if duplicate:
                    ordinary[proto["fragment_item_id"]] += proto["fragment_count"]
                    ordinary[proto["duplicate_ticket_item_id"]] += proto["duplicate_ticket_count"]
                else:
                    unlocked = {"id": proto["hero_id"], "state": 2,
                        "level": proto["level"], "star": proto["star"], "exp": 0,
                        "skills": [{"id": i, "level": 1} for i in proto["initial_skills"]],
                        "compat": "REVIVAL_COMPAT"}
                    if existing is None:
                        snapshot.setdefault('heroes', []).append(unlocked)
                    else:
                        existing.update(unlocked)
                heroes.append((item, duplicate))
        else:
            ordinary[item] += count
    if heroes:
        economy.save_snapshot(player, snapshot)
    # Explicit bag destinations preserve unrelated gift resolver rules.
    granted = economy._grant(player, source, ordinary, stackable_types=(11, 20))
    if heroes:
        logging.getLogger('x2.rewards').info('bag hero delivered player=%s source=%s box=%s heroes=%s converted=%s',
            player, source, used_item, heroes, dict(ordinary))
    return bag_reward_view(REWARD.encode({
        "rewardItem": [REWARD_ITEM.encode({"itemId": item, "itemNum": n}) for item, n in granted.items()]
            + [REWARD_ITEM.encode({"itemId": item, "itemNum": 1, "transform": duplicate}) for item, duplicate in heroes],
        "rewardEquip": equips,
        "transformHero": [WishService.TRANSFORM_HERO.encode({"heroId": item,
            "transform": duplicate}) for item, duplicate in heroes],
    }))


def recover_hero_boxes(economy, player):
    """Repair only committed random-hero box outcomes; never draw again on login.

    Grant ledgers prove duplicate fragments even after they have been spent.
    A missing ledger is insufficient evidence to charge or compensate an account.
    """
    from .progression import catalog
    prototypes = {r['hero_id']: r for r in catalog()['hero_unlock']}
    fixed = 0
    with economy.transaction():
        rows = economy.store.db.execute('SELECT request_key,response FROM item_opt_receipts WHERE player_id=?',
                                         (player,)).fetchall()
        for key, raw in rows:
            try:
                receipt = ECONOMY_SCHEMAS['L2C_ItemOpt'].decode(raw)
            except (ProtocolError, ValueError, TypeError):
                logging.getLogger('x2.rewards').warning('invalid item receipt skipped player=%s key=%s', player, key)
                continue
            if receipt.get('code') != 10 or receipt.get('itemId') != 1203000:
                continue
            source = f'item-opt:{key}'
            original = economy.store.db.execute('SELECT rewards FROM economy_grants WHERE player_id=? AND source=?',
                                                 (player, source)).fetchone()
            if original is None:
                continue
            try:
                rewards = REWARD.decode(receipt.get('rewardData', b''))
                entries = [REWARD_ITEM.decode(x) for x in rewards.get('rewardItem', [])]
                ledger = {int(i): n for i, n in json.loads(original[0]).items()}
                if rewards.get('transformHero'):
                    # Display rows aggregate repeated hero IDs. Per-draw records
                    # preserve which copies unlocked a hero versus converted.
                    entries = [r for r in entries if r.get('itemId', 0) - 1210000 not in prototypes]
                    from .wish import WishService
                    for raw_hero in rewards.get('transformHero', []):
                        hero = WishService.TRANSFORM_HERO.decode(raw_hero)
                        hero_id = hero.get('heroId', 0)
                        if 1211000 <= hero_id < 1212000:
                            hero_id -= 1210000
                        if hero_id in prototypes:
                            entries.append({'itemId': 1210000 + hero_id, 'itemNum': 1,
                                            'transform': hero.get('transform', False)})
            except (ProtocolError, ValueError, TypeError, AttributeError):
                logging.getLogger('x2.rewards').warning('invalid hero reward receipt skipped player=%s key=%s', player, key)
                continue
            if any(not 0 < r.get('itemNum', 0) <= 999 for r in entries):
                continue
            hero_entries = [r for r in entries if r.get('itemId', 0) - 1210000 in prototypes]
            marker = f'hero-box-recovery:{key}'
            if economy.store.db.execute('SELECT 1 FROM economy_grants WHERE player_id=? AND source=?',
                                         (player, marker)).fetchone():
                continue
            snapshot = economy.store.get(player)['snapshot']
            changed, missing = False, Counter()
            for entry in hero_entries:
                hero_id = entry['itemId'] - 1210000
                proto = prototypes[hero_id]
                if entry.get('transform', False):
                    for field, amount_field in [('fragment_item_id', 'fragment_count'),
                                               ('duplicate_ticket_item_id', 'duplicate_ticket_count')]:
                        missing[proto[field]] += proto[amount_field] * entry.get('itemNum', 1)
                elif not any(h['id'] == hero_id and h.get('state') == 2 for h in snapshot.get('heroes', [])):
                    unlocked = {'id': hero_id, 'state': 2, 'level': proto['level'], 'star': proto['star'],
                        'exp': 0, 'skills': [{'id': i, 'level': 1} for i in proto['initial_skills']],
                        'compat': 'REVIVAL_COMPAT'}
                    existing = next((h for h in snapshot.get('heroes', []) if h['id'] == hero_id), None)
                    if existing is None:
                        snapshot.setdefault('heroes', []).append(unlocked)
                    else:
                        existing.update(unlocked)
                    changed = True
            missing = {i: n - ledger.get(i, 0) for i, n in missing.items() if n > ledger.get(i, 0)}
            if changed or missing:
                if changed:
                    economy.save_snapshot(player, snapshot)
                economy._grant(player, marker, missing)
                fixed += 1
                logging.getLogger('x2.rewards').info('hero box recovered player=%s source=%s hero_restored=%s rewards=%s',
                                                    player, source, changed, missing)
            elif not hero_entries:
                if not entries and not ledger and not rewards.get('rewardEquip'):
                    # The committed success receipt proves at least one box was
                    # consumed, but old receipts omitted the requested count.
                    # Return that proven minimum rather than invent a hero.
                    refund = economy._grant(player, marker, {1203000: 1})
                    receipt['rewardData'] = economy.reward_bytes(refund)
                    economy.store.db.execute('UPDATE item_opt_receipts SET response=? WHERE player_id=? AND request_key=?',
                        (ECONOMY_SCHEMAS['L2C_ItemOpt'].encode(receipt), player, key))
                    fixed += 1
                    logging.getLogger('x2.rewards').warning('empty hero box refunded player=%s source=%s count=1; original bulk count unavailable',
                                                           player, source)
                else:
                    logging.getLogger('x2.rewards').warning('hero box requires operator review player=%s source=%s: no saved hero outcome',
                                                           player, source)
    return fixed


def bag_pushes(economy, player):
    from .hero import encode_hero_data
    from .equipment import EquipmentService
    # All read-model updates precede the success callback, which immediately
    # rereads the bag and equipped jewel state on the client.
    result = [OutboundMessage("L2C_HeroUpdate", {"code": 10,
        "heros": [encode_hero_data(h, season=economy.season, player_id=player) for h in economy.store.get(player)["snapshot"].get("heroes", [])]})]
    if economy.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='equipment_instances'").fetchone():
        # values() needs only store; avoid constructing a service/committing DDL
        # from inside the caller's transaction when replaying a receipt.
        reader = object.__new__(EquipmentService)
        reader.store = economy.store
        result.append(OutboundMessage("L2C_EquipUpdate", {"code": 10, **reader.values(player)}))
    return (*result, *economy.pushes(player))


class BagItemService:
    def __init__(self, store, economy):
        self.store, self.economy = store, economy
        with store.db:
            store.db.execute("""CREATE TABLE IF NOT EXISTS bag_operation_receipts (
                player_id INTEGER NOT NULL, request_key TEXT NOT NULL, response BLOB NOT NULL,
                PRIMARY KEY(player_id,request_key))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS bag_jewel_seen (
                player_id INTEGER NOT NULL, hero_id INTEGER NOT NULL,
                PRIMARY KEY(player_id,hero_id))""")

    def handlers(self):
        return {"C2L_JewelCompose": self.compose, "C2L_GodEqupJewelCompose": self.compose_equipped,
                "C2L_GodEquipJewelDot": self.jewel_seen}

    async def compose_equipped(self, context, packet):
        from .progression import ProgressionService, jewel_ids
        from .hero import encode_hero_data
        player = context.session.player_id
        if player is None:
            raise ProtocolError('equipped compose before login')
        req = ECONOMY_SCHEMAS['C2L_GodEqupJewelCompose'].decode(packet.body)
        recipe = self.economy.bag_catalog['recipes'].get(str(req.get('RecipeID', 0)))
        slot = req.get('HoleIsID', -1)
        schema = ECONOMY_SCHEMAS['L2C_GodEqupJewelCompose']
        failure = OutboundMessage(schema.name, {'result': 13, 'ID': 0})
        if (not recipe or recipe['type'] != 1 or slot not in range(6)
                or recipe['product'] not in jewel_ids() or recipe['productNum'] != 1
                or recipe['otherProduct'] or recipe['power'] or recipe['gold'] < 0):
            return failure
        key = hashlib.sha256(f'{player}:{context.session.session_id}:{packet.header.request_id}:equipped-compose'.encode() + packet.body).hexdigest()
        try:
            with self.economy.transaction():
                cached = self.store.db.execute('SELECT response FROM bag_operation_receipts WHERE player_id=? AND request_key=?', (player, key)).fetchone()
                if cached:
                    values = schema.decode(cached[0])
                else:
                    snapshot = self.store.get(player)['snapshot']
                    hero = next((h for h in snapshot.get('heroes', []) if h['id'] == req.get('HeroID') and h['state'] == 2), None)
                    artifact = hero.get('god_equip') if hero else None
                    old = artifact.get('jewels', {}).get(str(slot), 0) if artifact else 0
                    costs = Counter()
                    for item, count in recipe['costs']:
                        if count <= 0:
                            raise UnresolvedEconomy('invalid equipped compose cost')
                        costs[item] += count
                    if not old or old not in costs:
                        raise UnresolvedEconomy('equipped jewel does not match recipe')
                    if recipe['unlockType'] and (recipe['unlockType'] != 1 or not self.store.db.execute(
                            'SELECT 1 FROM economy_clears WHERE player_id=? AND section_id=?', (player, recipe['unlockParam'])).fetchone()):
                        raise UnresolvedEconomy('recipe not unlocked')
                    # One ingredient is worn; the remainder comes from the bag.
                    costs[old] -= 1
                    costs[1237901] += recipe['gold']
                    spender = object.__new__(ProgressionService)
                    spender.store, spender.economy = self.store, self.economy
                    spender.spend(player, snapshot, {i: n for i, n in costs.items() if n})
                    artifact['jewels'][str(slot)] = recipe['product']
                    self.economy.save_snapshot(player, snapshot)
                    values = {'result': 10, 'ID': recipe['product']}
                    self.store.db.execute('INSERT INTO bag_operation_receipts VALUES (?,?,?)', (player, key, schema.encode(values)))
        except UnresolvedEconomy as exc:
            logging.getLogger('x2.economy').info('equipped compose rejected player=%s request=%s reason=%s', player, req, exc)
            return failure
        logging.getLogger('x2.economy').info('equipped compose accepted player=%s request=%s product=%s', player, req, values['ID'])
        heroes = [encode_hero_data(h, season=self.economy.season, player_id=player) for h in self.store.get(player)['snapshot']['heroes']]
        return OutboundMessage(schema.name, values, before_response=(
            OutboundMessage('L2C_HeroUpdate', {'code': 10, 'heros': heroes}), *self.economy.pushes(player)))

    async def jewel_seen(self, context, packet):
        player = context.session.player_id
        if player is None:
            raise ProtocolError("jewel dot before login")
        req = ECONOMY_SCHEMAS["C2L_GodEquipJewelDot"].decode(packet.body)
        hero = req.get("heroId", 0)
        owned = any(h["id"] == hero and h["state"] == 2 for h in self.store.get(player)["snapshot"].get("heroes", []))
        if owned:
            with self.economy.transaction():
                self.store.db.execute("INSERT OR IGNORE INTO bag_jewel_seen VALUES (?,?)", (player, hero))
        return OutboundMessage("L2C_GodEquipJewelDot", {"code": 10 if owned else 13})

    async def compose(self, context, packet):
        from .progression import ProgressionService
        player = context.session.player_id
        if player is None:
            raise ProtocolError("compose before login")
        req = ECONOMY_SCHEMAS["C2L_JewelCompose"].decode(packet.body)
        recipe_id, count = req.get("RecipeID", 0), req.get("composeCount", 0)
        failure = OutboundMessage("L2C_JewelCompose", {"result": 13, "recipeID": recipe_id})
        recipe = self.economy.bag_catalog["recipes"].get(str(recipe_id))
        if recipe is None or type(count) is not int or not 1 <= count <= 999 or recipe["type"] not in (1, 2, 3, 4):
            return failure
        # RecipeType 4 (装备合成) draws a greedy equipment box, so the client caps
        # its quantity widget at 10 for those rows (CollegeFurnaceComposeTab_Refresh
        # 0x1BC9064 csel w22, w0, w9 with w9 = 10 when RecipeType == 4).
        if recipe["type"] == 4 and count > 10:
            return failure
        # RecipeType 3/4 also charge PowerNeed (Recipe offset 0x1C), which the client
        # prices as 星能 at the furnace level's discount, not as 体力. Compute it before
        # the transaction so the answer below can announce the new star energy. Rows of
        # RecipeType 1/2 carry power == 0 and pay nothing.
        energy = self._compose_star_energy(player, recipe, count)
        key = hashlib.sha256(f"{player}:{context.session.session_id}:{packet.header.request_id}:compose".encode() + packet.body).hexdigest()
        reward_equips: tuple = ()
        try:
            with self.economy.transaction():
                cached = self.store.db.execute("SELECT response FROM bag_operation_receipts WHERE player_id=? AND request_key=?", (player, key)).fetchone()
                if cached:
                    values = ECONOMY_SCHEMAS["L2C_JewelCompose"].decode(cached[0])
                    reward_equips = tuple(REWARD.decode(values.get("rewardData", b"")).get("rewardEquip", []))
                else:
                    if recipe["unlockType"]:
                        cleared = self.store.db.execute("SELECT 1 FROM economy_clears WHERE player_id=? AND section_id=?", (player, recipe["unlockParam"])).fetchone()
                        if recipe["unlockType"] != 1 or not cleared:
                            raise UnresolvedEconomy("recipe not unlocked")
                    if recipe["productNum"] <= 0 or recipe["gold"] < 0 or recipe["power"] < 0:
                        raise UnresolvedEconomy("unsupported recipe output/cost")
                    costs = Counter()
                    for item, num in recipe["costs"]:
                        if num <= 0:
                            raise UnresolvedEconomy("invalid recipe cost")
                        costs[item] += num * count
                    costs[1237901] += recipe["gold"] * count
                    # PowerNeed is 星能 (currency 9), not 体力. It is not an inventory row
                    # either: the college state owns it, so settle that clock first and
                    # debit it there.
                    if energy:
                        self._spend_star_energy(player, energy)
                    snapshot = self.store.get(player)["snapshot"]
                    # spend() has no service state beyond economy/store.
                    spender = object.__new__(ProgressionService)
                    spender.store, spender.economy = self.store, self.economy
                    spender.spend(player, snapshot, costs)
                    granted = Counter()
                    if recipe["type"] == 4:
                        granted, reward_equips = self._compose_equip_box(player, recipe, count, key)
                    else:
                        granted[recipe["product"]] += recipe["productNum"] * count
                        if recipe["type"] == 3:
                            granted.update(self._compose_extra_drop(player, recipe, count))
                    self.economy.save_snapshot(player, snapshot)
                    granted = self.economy._grant(player, f"compose:{key}", granted, stackable_types=(11,))
                    values = {"result": 10, "recipeID": recipe_id,
                        "rewardData": self.economy.reward_bytes(granted, reward_equips)}
                    self.store.db.execute("INSERT INTO bag_operation_receipts VALUES (?,?,?)",
                        (player, key, ECONOMY_SCHEMAS["L2C_JewelCompose"].encode(values)))
        except (UnresolvedEconomy, EquipmentValidationError) as exc:
            logging.getLogger("x2.economy").info("compose rejected player=%s recipe=%s count=%s reason=%s", player, recipe_id, count, exc)
            return failure
        logging.getLogger("x2.economy").info("compose accepted player=%s recipe=%s count=%s equips=%s",
            player, recipe_id, count, len(reward_equips))
        pushes = self.economy.pushes(player)
        if reward_equips:
            pushes = pushes + (OutboundMessage("L2C_EquipUpdate", {"code": 10, "equip": list(reward_equips)}),)
        college = getattr(self.economy, "college", None)
        if energy and college is not None:
            # The compose page re-reads its 星能 quote for the next craft, and the client
            # keeps that number in the college module, so the refreshed growth base (584)
            # has to land before the answer.
            pushes = (OutboundMessage("L2C_QueryGrowthBase", college.growth_base(player)),) + pushes
        return OutboundMessage("L2C_JewelCompose", values, before_response=pushes)

    def _compose_star_energy(self, player, recipe, count):
        """星能 (currency 9) that ``count`` compose batches cost, or 0 for free rows.

        CollegeFurnaceComposeTab_RefreshConsume 0x1BC913C prices ONE batch at
        ``ceil(PowerNeed × GetFurnaceRecipePowerDiscount / 1000)`` and compares it with
        GameAPI_GetCurrencyNum(0, 9, 0) — currency 9 is 星能 (CurrencyType 909, icon 909),
        and GetFurnaceRecipePowerDiscount (0x1B00B6C) is CollegeLevel[707]'s EffectValue1
        for EffectType1 == 13. The same panel derives the quantity widget from
        ``current star energy // that price``, so the total is the per-batch price × count.
        """
        power = int(recipe.get("power") or 0)
        if power <= 0:
            return 0
        return -(-power * self._furnace_power_ratio(player) // 1000) * count

    def _spend_star_energy(self, player, amount):
        """Debit the college star energy, settling its regen clock first.

        The college state lives in CollegeStateRepository (``economy.college`` in
        run_server), so this goes through that repository's savepoints instead of
        writing college_state by hand. A BagItemService without one refuses the craft
        rather than granting it for free.
        """
        college = getattr(self.economy, "college", None)
        if college is None:
            raise UnresolvedEconomy("college state unavailable")
        with college.transaction():
            state = college.load(player)
            college.settle(state)
            available = int(state.get("star_energy", 0))
            if available < amount:
                raise UnresolvedEconomy("insufficient star energy")
            state["star_energy"] = available - amount
            college.save(player, state)

    def _compose_extra_drop(self, player, recipe, count):
        """RecipeType 3 OtherProduct / OtherProductID (Recipe offsets 0x44 / 0x48).

        CollegeFurnaceComposeTab_Refresh 0x1BC9088 reads OtherProduct and prints
        (OtherProduct + GetFurnaceRecipeExtraPercent)/10 as a percent, so the field is
        the extra-drop chance in permille and OtherProductID names the Gift group it
        draws from. GetFurnaceRecipeExtraPercent (0x1B00C28) is CollegeLevel[707]'s
        EffectValue2 for EffectType2 == 14, i.e. the furnace upgrade bonus.
        """
        if not recipe["otherProductId"]:
            return Counter()
        chance = min(1000, recipe["otherProduct"] + self._furnace_extra_permille(player))
        if chance <= 0:
            return Counter()
        hits = sum(1 for _ in range(count) if secrets.randbelow(1000) < chance)
        if not hits:
            return Counter()
        deferred: Counter = Counter()
        extra = self.economy.gifts([recipe["otherProductId"]] * hits,
                                   deferred=deferred, allow_daily_random=True)
        if deferred:
            # Roll back the entire compose instead of consuming materials and
            # silently discarding an unsupported extra reward destination.
            raise UnresolvedEconomy("unresolved compose extra reward")
        return Counter(extra)

    def _furnace_level_row(self, player):
        """The saved CollegeLevel row for the furnace (building 707), or None.

        Both furnace effects the compose panel reads come off this row: EffectType2 == 14
        is the extra-drop bonus (GetFurnaceRecipeExtraPercent, 0x1B00C28) and
        EffectType1 == 13 is the PowerNeed discount (GetFurnaceRecipePowerDiscount,
        0x1B00B6C).
        """
        from .college_upgrade import _catalog
        if not self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='college_state'").fetchone():
            return None
        row = self.store.db.execute("SELECT state_json FROM college_state WHERE player_id=?", (player,)).fetchone()
        if not row:
            return None
        state = json.loads(row[0])
        buildings = (state.get("buildings") or []) + (state.get("wonders") or [])
        level = next((b.get("buildingLevel", 1) for b in buildings if b.get("buildingId") == 707), 1)
        catalog = _catalog()
        building = next((b for b in catalog["buildings"] if b["ID"] == 707), None)
        ids = (building or {}).get("LevelID") or []
        if not 1 <= level <= len(ids):
            return None
        return next((r for r in catalog["levels"] if r["BuildID"] == ids[level - 1]), None)

    def _furnace_extra_permille(self, player):
        """CollegeModule_GetFurnaceRecipeExtraPercent(707) for the saved furnace level."""
        level_row = self._furnace_level_row(player)
        if not level_row or level_row.get("EffectType2") != 14:
            return 0
        return (level_row.get("EffectValue2") or [0])[0]

    def _furnace_power_ratio(self, player):
        """CollegeModule_GetFurnaceRecipePowerDiscount(707), in permille.

        The furnace level scales the 星能 a recipe's PowerNeed costs; 1000 means full
        price (level 1 has no discount) and 660 would price 50 at 33.
        """
        level_row = self._furnace_level_row(player)
        if not level_row or level_row.get("EffectType1") != 13:
            return 1000
        return (level_row.get("EffectValue1") or [1000])[0] or 1000

    def _compose_equip_box(self, player, recipe, count, key):
        """RecipeType 4's ProductID is a Gift group of 兽主 type ids (775001..775019).

        Gift.GiftShow only names a display item, so the produced star is not in the
        recovered tables. The row's RecipeLevel is the only star-shaped value left
        (1..6, matching EquibStage/MinorCountTiers), so it is used as a
        REVIVAL_COMPATIBILITY choice for the instance star.
        """
        from x2server.messages.equipment import HERO_EQUIP, EQUIP_PARAM
        from .equipment_factory import materialize_instances
        deferred: Counter = Counter()
        granted = Counter(self.economy.gifts([recipe["product"]] * count,
                                             deferred=deferred, allow_daily_random=True))
        star = min(6, max(1, recipe["level"] or 1))
        equips, ordinal = [], 0
        for item, amount in sorted(deferred.items()):
            instances = materialize_instances(self.store.db, player, item, star, amount,
                f"compose:{key}", self.economy.equipment_factory, ordinal)
            ordinal += amount
            equips.extend(HERO_EQUIP.encode({**{k: v for k, v in instance.items() if k not in ("param", "marker")},
                "param": EQUIP_PARAM.encode(instance["param"])}) for instance in instances)
        return granted, tuple(equips)
