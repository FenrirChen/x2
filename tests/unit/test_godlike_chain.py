"""God descent must update native UI data before its completion callback."""
import asyncio

import pytest

from tests.unit.test_battle import packet
from tests.unit.test_economy import env
from x2server.messages.core import HERO_DATA, HERO_GOD_EQUIP, GOD_SLOT_LOCK_INFO
from x2server.player.progression import ProgressionService, godhole_rules


def prepare(env, hero_id, specific, common=0, imported=False):
    store, economy, ctx = env
    rule = godhole_rules()[hero_id]
    service = ProgressionService(store, economy)
    with economy.transaction():
        state = store.get(1)["snapshot"]
        state["heroes"] = [{"id": hero_id, "state": 2, "level": 60, "star": 46,
                            "skills": ([{"id": rule["SkillID"], "level": 1}] if imported else []),
                            "god_equip": {"id": hero_id + 500, "level": 45, "star": 3}}]
        economy.save_snapshot(1, state)
        economy._grant(1, "godlike-fixture", {i: n for i, n in
                       {rule["ItemID"]: specific, 1206000: common}.items() if n})
    return service, ctx, rule


def send(service, ctx, name, values, seq):
    return asyncio.run(service.handle(ctx, packet(values, seq, name)))


def quantity(store, item):
    row = store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?", (item,)).fetchone()
    return row[0] if row else 0


@pytest.mark.parametrize("hero_id", sorted(godhole_rules()))
def test_every_official_hero_completes_both_steps_and_replay(env, hero_id):
    rule = godhole_rules()[hero_id]
    service, ctx, rule = prepare(env, hero_id, rule["Cost"] * 2)
    first = send(service, ctx, "C2L_HeroGodLike", {"heroId": hero_id}, 100)
    assert first.values["code"] == 10 and not first.pushes
    hero = HERO_DATA.decode(first.before_response[0].values["heros"][0])
    assert hero["id"] == hero_id
    assert quantity(env[0], rule["ItemID"]) == rule["Cost"]
    values = {"heroID": hero_id, "slotIndex": rule["HoleNum"]}
    for seq in (101, 101, 102):
        second = send(service, ctx, "C2L_GodSlotLock", values, seq)
        assert second.values["code"] == 10 and not second.pushes
        hero = HERO_DATA.decode(second.before_response[0].values["heros"][0])
        equip = HERO_GOD_EQUIP.decode(hero["godEquip"])
        assert list(map(GOD_SLOT_LOCK_INFO.decode, equip["godSlotLockInfo"])) == [{"slot": 5, "state": 1}]
        assert quantity(env[0], rule["ItemID"]) == 0
    assert send(service, ctx, "C2L_GodSlotLock", {"heroID": hero_id, "slotIndex": 6}, 103).values["code"] == 13


@pytest.mark.parametrize("specific", [0, 3, 10])
def test_common_stones_cover_both_steps(env, specific):
    service, ctx, rule = prepare(env, 1003, specific, 10 - specific)
    assert rule["Cost"] == 5
    for name, values, seq in (("C2L_HeroGodLike", {"heroId": 1003}, 100),
                              ("C2L_GodSlotLock", {"heroID": 1003, "slotIndex": 5}, 101)):
        assert send(service, ctx, name, values, seq).values["code"] == 10
    assert quantity(env[0], rule["ItemID"]) == quantity(env[0], 1206000) == 0


def test_second_step_insufficient_material_rolls_back_and_can_retry(env):
    service, ctx, rule = prepare(env, 1003, 7, 1)
    assert send(service, ctx, "C2L_HeroGodLike", {"heroId": 1003}, 100).values["code"] == 10
    values = {"heroID": 1003, "slotIndex": 5}
    assert send(service, ctx, "C2L_GodSlotLock", values, 101).values["code"] == 13
    hero = env[0].get(1)["snapshot"]["heroes"][0]
    assert hero["god_shed"]["skill_id"] == rule["SkillID"]
    assert not hero["god_equip"].get("god_slot_lock")
    assert quantity(env[0], rule["ItemID"]) == 2 and quantity(env[0], 1206000) == 1
    with env[1].transaction():
        env[1]._grant(1, "remaining-god-stones", {1206000: 2})
    assert send(service, ctx, "C2L_GodSlotLock", values, 101).values["code"] == 10


def test_imported_first_step_without_server_marker_unlocks_socket(env):
    service, ctx, rule = prepare(env, 1003, 5, imported=True)
    assert send(service, ctx, "C2L_GodSlotLock", {"heroID": 1003, "slotIndex": 5}, 100).values["code"] == 10
    assert quantity(env[0], rule["ItemID"]) == 0


def test_socket_requires_first_descent_and_six_stars(env):
    service, ctx, rule = prepare(env, 1003, 10)
    values = {"heroID": 1003, "slotIndex": 5}
    assert send(service, ctx, "C2L_GodSlotLock", values, 100).values["code"] == 13
    with env[1].transaction():
        state = env[0].get(1)["snapshot"]
        state["heroes"][0]["skills"] = [{"id": rule["SkillID"], "level": 1}]
        state["heroes"][0]["star"] = 45
        env[1].save_snapshot(1, state)
    assert send(service, ctx, "C2L_GodSlotLock", values, 101).values["code"] == 13
    assert quantity(env[0], rule["ItemID"]) == 10
