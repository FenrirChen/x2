"""Confirmed 1003 growth costs; unknown weapon/equipment operations stay closed."""
from functools import lru_cache
from importlib.resources import files
from collections import Counter
import hashlib
import json
import logging

from x2server.messages.progression import PROGRESSION_SCHEMAS
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY
from x2server.protocol.errors import ProtocolError
from .economy import UnresolvedEconomy


@lru_cache(maxsize=1)
def catalog():
    return json.loads(files("x2server").joinpath("data/progression_catalog.json").read_text(encoding="utf-8"))


def hero_skills(hero):
    return hero.get("skills", [{"id": i, "level": 1} for i in (10030, 10031, 10032, 10033, 10035)]) if hero["id"] == 1003 else hero.get("skills", [])


def hero_attributes(hero):
    level = next(r for r in catalog()["hero_level"] if r["level"] == hero["level"])["attribute_bonus"]
    stage = next(r for r in catalog()["hero_star"] if r["star"] == hero["star"])["attribute_bonus"]
    return {field: int(base * (1 + stage[prefix+"StageBonus"]/1000) * (1 + level[prefix+"LevelBonus"]/1000) + cor)
            for field, prefix, base, cor in (("atk","Damage",60,12), ("def","Defense",40,4), ("hp","HPMax",600,120), ("sp","SPMax",3000,0))}


def advance_player(snapshot):
    """Use the recovered curve; preserve excess XP at terminal level for now."""
    rows = {r["level"]: r for r in catalog()["player_level"]}
    while snapshot["level"] in rows:
        row = rows[snapshot["level"]]
        if not row["next_level"] or snapshot.get("exp", 0) < row["exp_required"]:
            break
        snapshot["exp"] -= row["exp_required"]
        snapshot["level"] = row["next_level"]


class ProgressionService:
    def __init__(self, store, economy):
        self.store, self.economy = store, economy
        with store.db:
            store.db.execute("""CREATE TABLE IF NOT EXISTS progression_receipts (
                player_id INTEGER NOT NULL, request_key TEXT NOT NULL, response BLOB NOT NULL,
                PRIMARY KEY(player_id,request_key))""")

    def handlers(self):
        return {name: self.handle for name in ("C2L_HeroOpt", "C2L_UpHeroSkill")}

    def spend(self, player_id, snapshot, costs):
        for item, amount in costs.items():
            if amount < 0:
                raise UnresolvedEconomy("invalid cost")
            if item in self.economy.CURRENCIES:
                field = self.economy.CURRENCIES[item]
                if snapshot.get(field, 0) < amount:
                    raise UnresolvedEconomy("insufficient currency")
                snapshot[field] = snapshot.get(field, 0) - amount
            elif amount:
                result = self.store.db.execute("UPDATE inventory SET quantity=quantity-? WHERE player_id=? AND item_id=? AND quantity>=?", (amount, player_id, item, amount))
                if not result.rowcount:
                    raise UnresolvedEconomy("insufficient material")

    async def handle(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("hero operation before login")
        self.economy.ensure_periods(player_id)
        name = CORE_MESSAGE_REGISTRY.name_for(packet.message_id)
        req = PROGRESSION_SCHEMAS[name].decode(packet.body)
        logging.getLogger("x2.progression").info("growth request %s player=%s hero=%s", name, player_id, req.get("id",req.get("heroId")))
        response = name.replace("C2L_", "L2C_")
        schema = PROGRESSION_SCHEMAS[response]
        values = {"code": 13, **{k: v for k, v in req.items() if k != "heroName"}}
        key = hashlib.sha256(f"{context.session.session_id}:{packet.header.request_id}:{name}".encode() + packet.body).hexdigest()
        cached = self.store.db.execute("SELECT response FROM progression_receipts WHERE player_id=? AND request_key=?", (player_id,key)).fetchone()
        if cached:
            return OutboundMessage(response, schema.decode(cached[0]), pushes=self.pushes(player_id))
        try:
            with self.economy.transaction():
                snapshot = self.store.get(player_id)["snapshot"]
                hero = next((h for h in snapshot.get("heroes", []) if h["id"] == req.get("id",req.get("heroId"))), None)
                if not hero or hero["id"] != 1003 or hero["state"] != 2:
                    raise UnresolvedEconomy("unrecovered hero")
                costs = Counter()
                event = None
                if name == "C2L_HeroOpt":
                    if req.get("opt") == 1:
                        row = next(r for r in catalog()["hero_level"] if r["level"] == hero["level"])
                        # HeroLevelUP.OnClickUpLevel 0x14010D0 compares the
                        # current hero level against BaseInfo.Level before sending.
                        if not row["next_level"] or hero["level"] >= snapshot["level"] or req.get("upstarConsumeItemId",0) not in (0,1237907):
                            raise UnresolvedEconomy("invalid level request")
                        costs[1237907] = row["exp_required"]
                        hero["level"] = row["next_level"]
                        event = 7
                    elif req.get("opt") == 2:
                        row = next(r for r in catalog()["hero_star"] if r["star"] == hero["star"])
                        options = {1201003: row["fragment_count_field"], **{r["material_item_id"]:r["material_num"] for r in row["universal_fragment_option"]}}
                        item = req.get("upstarConsumeItemId",0)
                        if not row["next_star"] or item not in options:
                            raise UnresolvedEconomy("invalid star request")
                        costs[item] = options[item]
                        hero["star"] = row["next_star"]
                    else:
                        raise UnresolvedEconomy("unrecovered hero operation")
                else:
                    # UI OnTongYongYesBtn_NormalClick passes uplevel=1.
                    if req.get("uplevel") != 1:
                        raise UnresolvedEconomy("unrecovered bulk skill operation")
                    skills = {s["id"]:dict(s) for s in hero_skills(hero)}
                    skill = skills.get(req.get("skillId"))
                    row = next((r for r in catalog()["skill_progression"] if skill and r["skill_id"] == skill["id"] and r["level"] == skill["level"]), None)
                    if not row or not row["next_level"]:
                        raise UnresolvedEconomy("max or unrecovered skill")
                    condition = row["unlock_condition"]
                    if condition and (condition["type"] != "E_HeroLevel" or hero["level"] < condition["value"]):
                        raise UnresolvedEconomy("skill level condition")
                    if any(skills.get(r["skill_id"], {}).get("level",0) < r["level"] for r in row["prerequisite_skills"]):
                        raise UnresolvedEconomy("skill prerequisite")
                    for material in row["materials"]:
                        costs[material["material_item_id"]] += material["material_num"]
                    costs[1237901] += row["gold_cost"]
                    skill["level"] = row["next_level"]
                    hero["skills"] = list(skills.values())
                self.spend(player_id, snapshot, costs)
                self.economy.save_snapshot(player_id, snapshot)
                if event:
                    self.economy._event(player_id, "growth:"+key, event, hero["id"], 1)
                values["code"] = 10
                self.store.db.execute("INSERT INTO progression_receipts VALUES (?,?,?)", (player_id,key,schema.encode(values)))
        except UnresolvedEconomy:
            values["code"] = 13
            return OutboundMessage(response,values)
        return OutboundMessage(response,values,pushes=self.pushes(player_id))

    def pushes(self, player_id):
        from .hero import encode_hero_data
        return (OutboundMessage("L2C_HeroUpdate", {"code":10,"heros":[encode_hero_data(h) for h in self.store.get(player_id)["snapshot"]["heroes"]]}), *self.economy.pushes(player_id))
