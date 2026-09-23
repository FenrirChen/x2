import asyncio
from datetime import datetime
import sqlite3

import pytest

from tests.unit.test_economy import env, checkout, rewards
from tests.unit.test_battle import packet, request
from x2server.player.task_calendar import BEIJING, task_period
from x2server.player.progression import ProgressionService, hero_attributes
from x2server.player.economy import EconomyService
from x2server.player.battle import BattleService
from x2server.messages.battle import CHECKOUT, FIGHT_DATA, FIGHT_HERO, HERO_ATTR, HERO_ATTR_ADD
from x2server.messages.economy import TASK


def ts(value):
    return int(datetime.fromisoformat(value).replace(tzinfo=BEIJING).timestamp())


def test_calendar_boundaries():
    assert task_period(1, ts("2026-09-21T00:00:00")) == (ts("2026-09-21T00:00:00"),ts("2026-09-22T00:00:00"))
    assert task_period(1, ts("2026-09-20T23:59:59"))[1] == ts("2026-09-21T00:00:00")
    assert task_period(2, ts("2026-09-21T04:59:59"))[1] == ts("2026-09-21T05:00:00")
    assert task_period(2, ts("2026-09-21T05:00:00")) == (ts("2026-09-21T05:00:00"),ts("2026-09-28T05:00:00"))


def test_period_reset_independence_and_clock_rollback(env):
    store, _, _ = env
    now = [ts("2026-09-20T23:59:59")]
    economy = EconomyService(store, clock=lambda:now[0])
    economy.login_event(1)
    assert economy.claim(1,630019,1)["code"] == 10
    with economy.transaction():
        p = store.get(1)["snapshot"]
        p["week_activity"] = 30
        economy.save_snapshot(1,p)
    now[0] = ts("2026-09-21T00:00:00")
    economy.login_event(1)
    assert store.get(1)["snapshot"]["daily_activity"] == 0
    assert store.get(1)["snapshot"]["week_activity"] == 30
    assert economy.claim(1,630019,1)["code"] == 10
    assert store.get(1)["snapshot"]["gold"] == 1600
    now[0] = ts("2026-09-21T05:00:00")
    economy.login_event(1)
    assert store.get(1)["snapshot"]["week_activity"] == 0
    assert store.get(1)["snapshot"]["daily_activity"] == 10
    assert len(economy.task_values(1,1)["taskList"]) == 26
    assert len(economy.task_values(1,2)["taskList"]) == 14
    now[0] -= 86400
    economy.login_event(1)
    economy.claim(1,630019,1)
    assert store.get(1)["snapshot"]["gold"] == 1600


def test_legacy_claim_adopted_without_double_grant(env):
    store,economy,_ = env
    with store.db:
        economy._grant(1,"task:initial:630019",economy.gifts([economy.tasks[630019]["GiftGroup"]]))
        store.db.execute("INSERT INTO economy_tasks VALUES (1,630019,1,1)")
    economy.login_event(1)
    economy.claim(1,630019,1)
    assert store.get(1)["snapshot"]["gold"] == 800
    assert store.get(1)["snapshot"]["daily_activity"] == 10


def test_four_section_route_refunds_and_persisted_pending_rewards(env):
    store,economy,ctx = env
    battle = BattleService(store,economy)
    for index,section in enumerate((2110801,2110802,2110803,2110804),1):
        req = request()
        req.update(missionId=section,sceneId=economy.sections[section]["Maps"][0])
        entry = packet(req,index)
        assert asyncio.run(battle.enter(ctx,entry)).values["result"] == 10
        assert asyncio.run(battle.enter(ctx,entry)).values["result"] == 10
        assert store.get(1)["snapshot"]["mobility"]["power"] == 149-6*index
        done = packet({"checkout":CHECKOUT.encode({"chapterId":2010100,"sectionId":section,"success":True,"fightTime":200})},name="C2L_CheckoutMainMissionSign")
        result = asyncio.run(battle.checkout(ctx,done))
        assert result.values["result"] == 10
        assert asyncio.run(battle.checkout(ctx,done)).values == result.values
        assert store.get(1)["snapshot"]["main_section"] == section
    assert store.db.execute("SELECT COUNT(*) FROM economy_clears").fetchone()[0] == 4
    pending = dict(store.db.execute("SELECT item_id,SUM(quantity) FROM pending_rewards GROUP BY item_id"))
    assert pending[1240002] > 0 and pending[1240004] > 0
    # Replaying an older subsection does not regress the frontier; failure refunds once.
    asyncio.run(battle.enter(ctx,packet(request(),10)))
    assert store.get(1)["snapshot"]["mobility"]["power"] == 119
    ctx.session.session_id = "reconnected"
    assert asyncio.run(battle.checkout(ctx,checkout(False))).values["result"] == 10
    assert asyncio.run(battle.checkout(ctx,checkout(False))).values["result"] == 10
    assert store.get(1)["snapshot"]["mobility"]["power"] == 125
    assert store.get(1)["snapshot"]["main_section"] == 2110804
    economy = EconomyService(store)
    assert store.get(1)["snapshot"]["main_section"] == 2110804
    assert dict(store.db.execute("SELECT item_id,SUM(quantity) FROM pending_rewards GROUP BY item_id")) == pending


def test_hero_level_star_skill_costs_retries_and_battle_attributes(env):
    store,economy,ctx = env
    service = ProgressionService(store,economy)
    with store.db:
        economy._grant(1,"test",{1237907:500,1201003:10,1201000:10,1202080:1})
    def op(values,n=1,name="C2L_HeroOpt"):
        return asyncio.run(service.handle(ctx,packet(values,n,name)))
    req = {"id":1003,"opt":1,"upstarConsumeItemId":1237907}
    assert op(req).values["code"] == 10
    assert op(req).values["code"] == 10
    p = store.get(1)["snapshot"]
    assert p["hero_exp"] == 380 and p["heroes"][0]["level"] == 2
    assert hero_attributes(p["heroes"][0]) == {"atk":75,"def":46,"hp":752,"sp":3000}
    assert op({"id":1003,"opt":2,"upstarConsumeItemId":1201003},2).values["code"] == 10
    assert store.db.execute("SELECT quantity FROM inventory WHERE item_id=1201003").fetchone()[0] == 0
    assert store.db.execute("SELECT quantity FROM inventory WHERE item_id=1201000").fetchone()[0] == 10
    skill = {"heroId":1003,"skillId":10030,"uplevel":1}
    assert op(skill,3,"C2L_UpHeroSkill").values["code"] == 13
    with store.db:
        p = store.get(1)["snapshot"]
        p["heroes"][0]["level"] = 15
        economy.save_snapshot(1,p)
    assert op(skill,4,"C2L_UpHeroSkill").values["code"] == 10
    assert op(skill,4,"C2L_UpHeroSkill").values["code"] == 10
    assert op(skill,5,"C2L_UpHeroSkill").values["code"] == 13
    assert store.db.execute("SELECT quantity FROM inventory WHERE item_id=1202080").fetchone()[0] == 0
    battle = BattleService(store,economy)
    entry = asyncio.run(battle.enter(ctx,packet(request(),20)))
    hero = FIGHT_HERO.decode(FIGHT_DATA.decode(entry.values["data"])["fightHeros"][0])
    assert HERO_ATTR.decode(hero["heroAttrCount"]) == hero_attributes(store.get(1)["snapshot"]["heroes"][0])
    raw = {r["attrId"]:r.get("attrValue",0) for r in map(HERO_ATTR_ADD.decode,hero["attrAdd"])}
    # The ordinary-player path skips local AddBaseProperty even for an empty
    # converted list. Summary totals alone produce zero movement and damage.
    assert raw[188] == 550
    assert (raw[162],raw[163],raw[164],raw[165]) == (60,40,600,3000)
    assert (raw[170],raw[171],raw[172]) == (12,4,120)
    assert raw[105] == 50
    assert len(raw) == 19


def test_growth_receipt_failure_rolls_back_cost_and_hero(env):
    store,economy,ctx = env
    service = ProgressionService(store,economy)
    with store.db:
        economy._grant(1,"test",{1237907:500})
        store.db.execute("CREATE TRIGGER reject_growth BEFORE INSERT ON progression_receipts BEGIN SELECT RAISE(ABORT,'test'); END")
    before = store.get(1)
    with pytest.raises(sqlite3.IntegrityError):
        asyncio.run(service.handle(ctx,packet({"id":1003,"opt":1},1,"C2L_HeroOpt")))
    assert store.get(1) == before


def test_player_curve_level_gifts_deferred_not_invented(env):
    store,economy,_ = env
    p = store.get(1)
    store.save_snapshot(1,dict(p["snapshot"],level=1),p["revision"])
    with store.db:
        economy._grant(1,"test",{1237908:25})
    p = store.get(1)["snapshot"]
    assert (p["level"],p["exp"],p["mobility"]["power"]) == (3,1,149)
    assert store.db.execute("SELECT COUNT(*) FROM pending_rewards WHERE source LIKE 'level:%'").fetchone()[0] == 2


def test_adopt_existing_clear_without_repaying_rewards(env):
    store,economy,_ = env
    p = store.get(1)
    store.save_snapshot(1,dict(p["snapshot"],main_section=2110001,main_chapter=2010000),p["revision"])
    with store.db:
        store.db.execute("INSERT INTO economy_clears VALUES (1,2110801,'old-run')")
    EconomyService(store)
    p = store.get(1)["snapshot"]
    assert (p["main_section"],p["main_chapter"],p["mobility"]["power"],p["gold"]) == (2110801,2010100,149,0)
    assert store.db.execute("SELECT COUNT(*) FROM economy_grants").fetchone()[0] == 0


def test_hero_cannot_outlevel_account_or_spend_missing_exp(env):
    store,economy,ctx = env
    service = ProgressionService(store,economy)
    p = store.get(1)
    store.save_snapshot(1,dict(p["snapshot"],level=1,hero_exp=500),p["revision"])
    before = store.get(1)
    result = asyncio.run(service.handle(ctx,packet({"id":1003,"opt":1},1,"C2L_HeroOpt")))
    assert result.values["code"] == 13 and store.get(1) == before
    p = store.get(1)
    store.save_snapshot(1,dict(p["snapshot"],level=60,hero_exp=119),p["revision"])
    before = store.get(1)
    result = asyncio.run(service.handle(ctx,packet({"id":1003,"opt":1},2,"C2L_HeroOpt")))
    assert result.values["code"] == 13 and store.get(1) == before
