import asyncio

from tests.unit.test_battle import packet
from tests.unit.test_economy import env
from x2server.messages.wish import CARD_POOL, WISH_SCHEMAS
from x2server.messages.economy import REWARD, REWARD_ITEM
from x2server.player.wish import WishService
from x2server.player.server_clock import ServerClock


def test_duplicate_hero_awards_exchange_ticket_once(env, monkeypatch):
    store, economy, context = env
    player = store.get(1)
    store.save_snapshot(1, dict(player["snapshot"], crystal=1800), player["revision"])
    wish = WishService(store, economy, clock=ServerClock(lambda: WishService.ANCHOR + 1))
    monkeypatch.setattr(wish, "_pick", lambda pool, group="common":
        {"item_id": 1211003, "quantity": 1})
    request = packet({"drawnId": 22202, "drawType": 0}, name="C2L_LuckDraw")
    first = asyncio.run(wish.draw(context, request))
    assert first.values["code"] == 10
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237915").fetchone()[0] == 1
    transforms = REWARD.decode(first.values["rewardData"])["transformHero"]
    assert WishService.TRANSFORM_HERO.decode(transforms[0]) == {"heroId": 1003, "transform": True}
    previous = asyncio.run(wish.result(context, packet({"drawnCountID": 41},
        name="C2L_RequestDrawResult")))
    assert REWARD.decode(previous.values["rewardData"])["transformHero"]
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237927").fetchone() is None
    assert asyncio.run(wish.draw(context, request)).values == first.values
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237915").fetchone()[0] == 1


def test_banner_uses_forty_draw_counter_after_low_rarity_hero(env, monkeypatch):
    store, economy, context = env
    player = store.get(1)
    store.save_snapshot(1, dict(player["snapshot"], crystal=1800), player["revision"])
    wish = WishService(store, economy, clock=ServerClock(lambda: WishService.ANCHOR + 1))
    store.db.execute("INSERT INTO wish_pity VALUES (1,'standard',3,7,0)")
    store.db.execute("UPDATE players SET created_at=? WHERE id=1", (WishService.ANCHOR,))
    before = [CARD_POOL.decode(raw) for raw in wish.values(1)["cardPoolList"]]
    assert next(x for x in before if x["poolId"] == 22201)["securityNum"] == 7
    assert next(x for x in before if x["poolId"] == 22202)["securityNum"] == 7
    monkeypatch.setattr(wish, "_pick", lambda pool, group="common": {"item_id": 1211003, "quantity": 1})
    result = asyncio.run(wish.draw(context, packet({"drawnId": 22202, "drawType": 0}, name="C2L_LuckDraw")))
    assert result.values["securityNum"] == 8
    pools = [CARD_POOL.decode(raw) for raw in wish.values(1)["cardPoolList"]]
    assert next(x for x in pools if x["poolId"] == 22202)["securityNum"] == 8


def test_duplicate_compensation_matches_official_rarity_table(env):
    store, economy, _ = env
    from x2server.player.progression import catalog
    amounts = {r["hero_id"]: r["duplicate_ticket_count"] for r in catalog()["hero_unlock"]}
    assert amounts[1003] == 1
    assert amounts[1004] == 5
    assert set(amounts.values()) == {1, 5, 10}
    assert all(r["duplicate_ticket_item_id"] == 1237915 for r in catalog()["hero_unlock"])


def test_saved_legacy_result_recovers_hero_transform_metadata():
    legacy = REWARD.encode({"rewardItem": [REWARD_ITEM.encode({
        "itemId": 1211003, "itemNum": 1, "transform": True})]})
    fixed = REWARD.decode(WishService._reward_with_transform_heroes(legacy))
    assert WishService.TRANSFORM_HERO.decode(fixed["transformHero"][0]) == {
        "heroId": 1003, "transform": True}


def test_newcomer_ten_draw_guarantee_cost_replay_and_limit(env, monkeypatch):
    store, economy, context = env
    player = store.get(1)
    store.save_snapshot(1, dict(player["snapshot"], crystal=1800), player["revision"])
    store.db.execute("UPDATE players SET created_at=? WHERE id=1", (WishService.ANCHOR,))
    wish = WishService(store, economy, clock=ServerClock(lambda: WishService.ANCHOR + 1))
    monkeypatch.setattr(wish, "_pick", lambda pool, group="common":
        {"item_id": 1211012, "quantity": 1} if group == "security"
        else {"item_id": 1201006, "quantity": 3})
    request = packet({"drawnId": 22201, "drawType": 1}, name="C2L_LuckDraw")
    first = asyncio.run(wish.draw(context, request))
    assert first.values["code"] == 10
    assert store.get(1)["snapshot"]["crystal"] == 0
    assert wish.state(1) == (10, 0, 1, 0, 0, 1, 10)
    assert first.values["allHeroCardFirstThreeStar"] is True
    assert any(h["id"] == 1012 for h in store.get(1)["snapshot"]["heroes"])
    items = [REWARD_ITEM.decode(raw) for raw in REWARD.decode(first.values["rewardData"])["rewardItem"]]
    assert len(items) == 10
    assert [(i["itemId"], i["itemNum"]) for i in items] == [(1201006, 3)] * 9 + [(1211012, 1)]
    replay = asyncio.run(wish.draw(context, request))
    assert replay.values["rewardData"] == first.values["rewardData"]
    assert wish.state(1)[0] == 10
    rejected = asyncio.run(wish.draw(context, packet({"drawnId": 22201, "drawType": 0},
        request_id=2, name="C2L_LuckDraw")))
    assert rejected.values["code"] == 13
    assert WISH_SCHEMAS["L2C_CardPool"].decode(WISH_SCHEMAS["L2C_CardPool"].encode(wish.values(1)))["select"] == 22203


def test_normal_pool_remains_available_after_newcomer_pool(env, monkeypatch):
    store, economy, context = env
    player = store.get(1)
    store.save_snapshot(1, dict(player["snapshot"], crystal=360), player["revision"])
    wish = WishService(store, economy, clock=ServerClock(lambda: WishService.ANCHOR + 1))
    store.db.execute("INSERT INTO wish_state(player_id,pool_id,total,singles,tens,since_hero,since_top,first_three_star) VALUES (1,22201,10,0,1,0,0,1)")
    monkeypatch.setattr(wish, "_pick", lambda pool, group="common":
        {"item_id": 1201006, "quantity": 3})
    request = packet({"drawnId": 22202, "drawType": 0}, name="C2L_LuckDraw")
    result = asyncio.run(wish.draw(context, request))
    assert result.values["code"] == 10
    assert wish.state(1, 22202)[0] == 1
    assert store.get(1)["snapshot"]["crystal"] == 180
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1201006").fetchone()[0] == 3
    assert wish.values(1)["select"] == 22203
    result = asyncio.run(wish.result(context, packet({"drawnCountID": 41}, name="C2L_RequestDrawResult")))
    assert REWARD.decode(result.values["rewardData"])["rewardItem"]


def test_rotation_at_beijing_midnight_and_wraparound(env):
    store, economy, _ = env
    now = [WishService.ANCHOR - 1]
    wish = WishService(store, economy, clock=ServerClock(lambda: now[0]))
    assert list(wish.active_periods()) == [22203, 22201]
    now[0] += 1
    active = wish.active_periods()
    assert [i for i in active if i in wish.groups["up"]] == wish.groups["up"][:3]
    assert [i for i in active if i in wish.groups["limited"]] == wish.groups["limited"][:1]
    assert [i for i in active if i in wish.groups["jewel"]] == wish.groups["jewel"][:2]
    assert active[22202] == (WishService.ANCHOR, WishService.ANCHOR + 5 * 86400)
    pools = [CARD_POOL.decode(raw) for raw in wish.values(1)["cardPoolList"]]
    first_up = next(p for p in pools if p["poolId"] == 22202)
    assert first_up["startTime"] == WishService.ANCHOR + 8 * 3600
    assert first_up["endTime"] == WishService.ANCHOR + 5 * 86400 + 8 * 3600
    now[0] += 5 * 86400
    active = wish.active_periods()
    assert [i for i in active if i in wish.groups["up"]] == wish.groups["up"][3:6]
    assert [i for i in active if i in wish.groups["limited"]] == wish.groups["limited"][:1]
    assert [i for i in active if i in wish.groups["jewel"]] == wish.groups["jewel"][2:4]
    now[0] = WishService.ANCHOR + 14 * 86400
    assert [i for i in wish.active_periods() if i in wish.groups["limited"]] == wish.groups["limited"][1:2]
    now[0] = WishService.ANCHOR + 50 * 86400
    assert [i for i in wish.active_periods() if i in wish.groups["up"]] == wish.groups["up"][:3]
    now[0] = WishService.ANCHOR + 25 * 86400
    assert [i for i in wish.active_periods() if i in wish.groups["jewel"]] == wish.groups["jewel"][:2]
    now[0] = WishService.ANCHOR + 42 * 86400
    assert [i for i in wish.active_periods() if i in wish.groups["limited"]] == wish.groups["limited"][:1]


def test_newcomer_dates_follow_account_creation(env):
    store, economy, _ = env
    now = [WishService.ANCHOR + 1]
    created = WishService.ANCHOR - 86400
    store.db.execute("UPDATE players SET created_at=? WHERE id=1", (created,))
    wish = WishService(store, economy, clock=ServerClock(lambda: now[0]))
    pools = [CARD_POOL.decode(raw) for raw in wish.values(1)["cardPoolList"]]
    newcomer = next(p for p in pools if p["poolId"] == 22201)
    assert (newcomer["startTime"], newcomer["endTime"]) == (created, created + 7 * 86400)
    now[0] = created + 7 * 86400
    assert 22201 not in wish.active_periods(player_id=1)


def test_star_soul_pool_is_permanent_and_drawable_after_newcomer_expires(env, monkeypatch):
    store, economy, context = env
    now = [WishService.ANCHOR - 1]
    store.db.execute("UPDATE players SET created_at=? WHERE id=1", (WishService.ANCHOR - 8 * 86400,))
    player = store.get(1)
    store.save_snapshot(1, dict(player["snapshot"], crystal=180), player["revision"])
    wish = WishService(store, economy, clock=ServerClock(lambda: now[0]))
    assert wish.catalog["22203"]["type"] == "E_Hero"
    assert 22203 not in wish.groups["up"] + wish.groups["limited"] + wish.groups["jewel"]
    for instant in (WishService.ANCHOR - 1, WishService.ANCHOR + 1,
                    WishService.ANCHOR + 365 * 86400):
        now[0] = instant
        assert 22203 in wish.active_periods(player_id=1)
        assert 22201 not in wish.active_periods(player_id=1)
        displayed = [CARD_POOL.decode(raw) for raw in wish.values(1)["cardPoolList"]]
        permanent = next(pool for pool in displayed if pool["poolId"] == 22203)
        assert permanent["endTime"] == 2_147_483_647
    monkeypatch.setattr(wish, "_pick", lambda pool, group="common":
        {"item_id": 1211004, "quantity": 1})
    result = asyncio.run(wish.draw(context, packet({"drawnId": 22203, "drawType": 0},
        name="C2L_LuckDraw")))
    assert result.values["code"] == 10
    assert wish.state(1, 22203)[0] == 1
    assert any(hero["id"] == 1004 for hero in store.get(1)["snapshot"]["heroes"])


def test_closed_pool_rejected_and_jewel_pool_uses_own_ticket(env, monkeypatch):
    store, economy, context = env
    wish = WishService(store, economy, clock=ServerClock(lambda: WishService.ANCHOR + 1))
    closed = asyncio.run(wish.draw(context, packet({"drawnId": 22205, "drawType": 0}, name="C2L_LuckDraw")))
    assert closed.values["code"] == 13
    store.db.execute("INSERT INTO inventory VALUES (1,1237925,1)")
    monkeypatch.setattr(wish, "_pick", lambda pool, group="common":
        {"item_id": 1251084, "quantity": 1})
    result = asyncio.run(wish.draw(context, packet({"drawnId": 22700, "drawType": 0}, name="C2L_LuckDraw")))
    assert result.values["code"] == 10
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237925").fetchone()[0] == 0
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1251084").fetchone()[0] == 1
    assert wish.state(1, 22700)[0] == 1


def test_limited_pool_featured_guarantee(env, monkeypatch):
    store, economy, context = env
    player = store.get(1)
    store.save_snapshot(1, dict(player["snapshot"], crystal=180), player["revision"])
    wish = WishService(store, economy, clock=ServerClock(lambda: WishService.ANCHOR + 1))
    store.db.execute("INSERT INTO wish_state(player_id,pool_id,since_featured) VALUES (1,22204,79)")
    monkeypatch.setattr(wish, "_pick", lambda pool, group="common":
        {"item_id": 1211024, "quantity": 1} if group == "limit"
        else {"item_id": 1201006, "quantity": 1})
    result = asyncio.run(wish.draw(context, packet({"drawnId": 22204, "drawType": 0}, name="C2L_LuckDraw")))
    assert result.values["code"] == 10
    assert wish.state(1, 22204)[-1] == 0
    assert any(h["id"] == 1024 for h in store.get(1)["snapshot"]["heroes"])


def test_pity_shared_across_standard_pools_and_separate_from_limited(env, monkeypatch):
    store, economy, context = env
    player = store.get(1)
    store.save_snapshot(1, dict(player["snapshot"], crystal=10000), player["revision"])
    wish = WishService(store, economy, clock=ServerClock(lambda: WishService.ANCHOR + 1))
    calls = []
    def pick(pool, group="common"):
        calls.append((pool, group))
        return {"item_id": 1211024 if group == "top" else 1201006, "quantity": 1}
    monkeypatch.setattr(wish, "_pick", pick)
    store.db.execute("INSERT INTO wish_pity VALUES (1,'standard',9,39,0)")
    first = asyncio.run(wish.draw(context, packet({"drawnId": 22205, "drawType": 0},
        request_id=101, name="C2L_LuckDraw")))
    assert first.values["code"] == 10
    assert calls == [(22205, "top")]
    assert wish.state(1, 22202)[3:5] == (0, 0)
    assert wish.state(1, 22700)[3:5] == (0, 0)
    assert wish.state(1, 22204)[3:5] == (0, 0)
    second = asyncio.run(wish.draw(context, packet({"drawnId": 22202, "drawType": 0},
        request_id=102, name="C2L_LuckDraw")))
    assert second.values["code"] == 10
    assert wish.state(1, 22205)[3:5] == (1, 1)
    limited = asyncio.run(wish.draw(context, packet({"drawnId": 22204, "drawType": 0},
        request_id=103, name="C2L_LuckDraw")))
    assert limited.values["code"] == 10
    assert wish.state(1, 22204)[3:5] == (1, 1)
    assert wish.state(1, 22202)[3:5] == (1, 1)


def test_ten_draw_preserves_order_after_hero_and_duplicate_transforms(env, monkeypatch):
    store, economy, context = env
    player = store.get(1)
    store.save_snapshot(1, dict(player["snapshot"], crystal=1800), player["revision"])
    wish = WishService(store, economy, clock=ServerClock(lambda: WishService.ANCHOR + 1))
    sequence = [1201006] * 5 + [1211024] + [1201007, 1211024, 1201008, 1201009]
    monkeypatch.setattr(wish, "_pick", lambda pool, group="common":
        {"item_id": sequence.pop(0), "quantity": 1})
    result = asyncio.run(wish.draw(context, packet({"drawnId": 22202, "drawType": 1},
        request_id=104, name="C2L_LuckDraw")))
    items = [REWARD_ITEM.decode(raw) for raw in REWARD.decode(result.values["rewardData"])["rewardItem"]]
    assert [item["itemId"] for item in items] == [1201006] * 5 + [1211024, 1201007, 1211024, 1201008, 1201009]
    assert len(items) == 10
    assert items[5]["transform"] is False
    assert items[7]["transform"] is True
