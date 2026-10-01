"""Canonical bag gifts and recipe operations, committed with replay receipts."""
from collections import Counter
import hashlib
import logging
import secrets

from x2server.messages.economy import ECONOMY_SCHEMAS, REWARD, REWARD_ITEM
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from .economy import UnresolvedEconomy


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
                duplicate = any(h["id"] == proto["hero_id"] for h in snapshot.get("heroes", []))
                if duplicate:
                    ordinary[proto["fragment_item_id"]] += proto["fragment_count"]
                    ordinary[proto["duplicate_ticket_item_id"]] += proto["duplicate_ticket_count"]
                else:
                    snapshot.setdefault("heroes", []).append({"id": proto["hero_id"], "state": 2,
                        "level": proto["level"], "star": proto["star"], "exp": 0,
                        "skills": [{"id": i, "level": 1} for i in proto["initial_skills"]],
                        "compat": "REVIVAL_COMPAT"})
                heroes.append((item, duplicate))
        else:
            ordinary[item] += count
    if heroes:
        economy.save_snapshot(player, snapshot)
    # Explicit bag destinations preserve unrelated gift resolver rules.
    granted = economy._grant(player, source, ordinary, stackable_types=(11, 20))
    return REWARD.encode({
        "rewardItem": [REWARD_ITEM.encode({"itemId": item, "itemNum": n}) for item, n in granted.items()]
            + [REWARD_ITEM.encode({"itemId": item, "itemNum": 1, "transform": duplicate}) for item, duplicate in heroes],
        "rewardEquip": equips,
        "transformHero": [WishService.TRANSFORM_HERO.encode({"heroId": item - 1210000,
            "transform": duplicate}) for item, duplicate in heroes],
    })


def bag_pushes(economy, player):
    from .hero import encode_hero_data
    from .equipment import EquipmentService
    # All read-model updates precede the success callback, which immediately
    # rereads the bag and equipped jewel state on the client.
    result = [OutboundMessage("L2C_HeroUpdate", {"code": 10,
        "heros": [encode_hero_data(h) for h in economy.store.get(player)["snapshot"].get("heroes", [])]})]
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
        heroes = [encode_hero_data(h) for h in self.store.get(player)['snapshot']['heroes']]
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
        if recipe is None or type(count) is not int or not 1 <= count <= 999 or recipe["type"] not in (1, 2, 3):
            return failure
        key = hashlib.sha256(f"{player}:{context.session.session_id}:{packet.header.request_id}:compose".encode() + packet.body).hexdigest()
        try:
            with self.economy.transaction():
                cached = self.store.db.execute("SELECT response FROM bag_operation_receipts WHERE player_id=? AND request_key=?", (player, key)).fetchone()
                if cached:
                    values = ECONOMY_SCHEMAS["L2C_JewelCompose"].decode(cached[0])
                else:
                    if recipe["unlockType"]:
                        cleared = self.store.db.execute("SELECT 1 FROM economy_clears WHERE player_id=? AND section_id=?", (player, recipe["unlockParam"])).fetchone()
                        if recipe["unlockType"] != 1 or not cleared:
                            raise UnresolvedEconomy("recipe not unlocked")
                    if recipe["productNum"] <= 0 or recipe["otherProduct"] or recipe["power"]:
                        raise UnresolvedEconomy("unsupported recipe output/cost")
                    costs = Counter()
                    for item, num in recipe["costs"]:
                        if num <= 0:
                            raise UnresolvedEconomy("invalid recipe cost")
                        costs[item] += num * count
                    if recipe["gold"] < 0:
                        raise UnresolvedEconomy("invalid recipe gold")
                    costs[1237901] += recipe["gold"] * count
                    snapshot = self.store.get(player)["snapshot"]
                    # spend() has no service state beyond economy/store.
                    spender = object.__new__(ProgressionService)
                    spender.store, spender.economy = self.store, self.economy
                    spender.spend(player, snapshot, costs)
                    self.economy.save_snapshot(player, snapshot)
                    granted = self.economy._grant(player, f"compose:{key}",
                        {recipe["product"]: recipe["productNum"] * count}, stackable_types=(11,))
                    values = {"result": 10, "recipeID": recipe_id,
                        "rewardData": self.economy.reward_bytes(granted)}
                    self.store.db.execute("INSERT INTO bag_operation_receipts VALUES (?,?,?)",
                        (player, key, ECONOMY_SCHEMAS["L2C_JewelCompose"].encode(values)))
        except UnresolvedEconomy as exc:
            logging.getLogger("x2.economy").info("compose rejected player=%s recipe=%s count=%s reason=%s", player, recipe_id, count, exc)
            return failure
        logging.getLogger("x2.economy").info("compose accepted player=%s recipe=%s count=%s", player, recipe_id, count)
        return OutboundMessage("L2C_JewelCompose", values, before_response=self.economy.pushes(player))
