import asyncio
from tests.unit.test_economy import env
from tests.unit.test_battle import packet, request
from x2server.player.battle import BattleService
from x2server.player.appearance import AppearanceService
from x2server.messages.battle import FIGHT_DATA, FIGHT_HERO, DROP_DATA, DROP_REPORT_NPC, DROP_REPORT_ITEM, FIGHT_KILL_DATA, CHECKOUT


def test_equipped_skin_and_264_observer_preserve_budget(env):
    store, economy, ctx = env
    appearance = AppearanceService(store, economy)
    asyncio.run(appearance.handle(ctx, packet({"heroId": 1003, "skinId": 1220301, "type": 1}, name="C2L_HeroWearSkin")))
    service = BattleService(store, economy)
    entry = asyncio.run(service.enter(ctx, packet(request())))
    hero = FIGHT_HERO.decode(FIGHT_DATA.decode(entry.values["data"])["fightHeros"][0])
    assert hero["battleSkinId"] == 1220301
    task = next(t for t in economy.dp.chapters["2010100"]["tasks"] if t.get("completeType") == "E_NPCInteraction")
    values = {"missionId": 2110801, "chapterId": 2010100,
        "npcData": [DROP_REPORT_NPC.encode({"id": task["completeValue1"], "count": 50})],
        "dropItem": [DROP_REPORT_ITEM.encode({"itemId": 1004765, "value": 2, "variant": 1})], "relicList": [1004765]}
    before = store.get(1)
    response = asyncio.run(service.drop_data(ctx, packet(values, name="C2L_FightDropData")))
    assert DROP_DATA.decode(response.values["data"])["dropValues"] == service.drop_budget.budget_for(2110801)
    asyncio.run(service.drop_data(ctx, packet(values, request_id=45, name="C2L_FightDropData")))
    assert store.db.execute("SELECT COUNT(*) FROM fight_drop_observations").fetchone()[0] == 1
    assert store.db.execute("SELECT COUNT(*) FROM fight_drop_items").fetchone()[0] == 1
    assert store.get(1) == before  # recorder has no reward authority


def test_real_checkout_kill_receipt_replay_cannot_add_dp(env):
    store, economy, ctx = env
    service = BattleService(store, economy)
    asyncio.run(service.enter(ctx, packet(request())))
    close = packet({"checkout": CHECKOUT.encode({"chapterId": 2010100, "sectionId": 2110801, "success": True, "fightTime": 20})}, name="C2L_CheckoutMainMissionSign")
    assert asyncio.run(service.checkout(ctx, close)).values["result"] == 10
    task = next(t for t in economy.dp.chapters["2010100"]["tasks"] if t.get("completeType") == "E_KillMonster")
    values = {"sectionId": 2110801, "datas": [FIGHT_KILL_DATA.encode({"heroId": 1003, "unitId": [task["completeValue1"]], "num": [task["completeNum"]]})]}
    for req in (2, 3, 4):
        assert asyncio.run(service.kill_info(ctx, packet(values, request_id=req, name="C2L_FightKillInfo"))).values["code"] == 10
    point = economy.chapter_dp(1, 2010100)
    asyncio.run(service.checkout(ctx, close))
    assert economy.chapter_dp(1, 2010100) == point
    assert store.db.execute("SELECT amount FROM chapter_signals WHERE kind='kill'").fetchone()[0] == task["completeNum"]
