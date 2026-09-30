import asyncio
import sqlite3

import pytest

from tests.unit.test_battle import packet
from tests.unit.test_economy import env  # noqa: F401
from tests.unit.test_equipment_main_growth import seed
from x2server.messages.core import HERO_DATA, INT_PAIR
from x2server.messages.economy import ITEM, REWARD
from x2server.player.appearance import avatar_frames
from x2server.player.bag_items import BagItemService
from x2server.player.equipment import EquipmentService
from x2server.player.hero import encode_hero_data


def stock(store, item, amount):
    with store.db:
        store.db.execute("INSERT OR REPLACE INTO inventory VALUES (1,?,?)", (item, amount))


def use(economy, ctx, item, count=1, selected=(), request=20):
    return asyncio.run(economy.handle(ctx, packet({"id": item, "opt": 0, "count": count,
        "selectedItemIndexList": list(selected)}, name="C2L_ItemOpt", request_id=request)))


def test_removed_stacks_repeat_without_writes_or_losing_permanent_frames(env):
    store, economy, ctx = env
    frame = next(iter(avatar_frames()))
    stock(store, frame, 0)
    stock(store, 1202024, 0)
    # Existing avatar callers take only the first push. This must not consume
    # a tombstone or leave a database transaction open.
    economy.pushes(1)[0]
    assert not store.db.in_transaction
    for _ in range(2):
        pushes = economy.pushes(1)
        removed = next(p.values["ids"] for p in pushes if p.message_name == "L2C_ItemRemove")
        assert removed == [1202024]
        ids = {ITEM.decode(x)["id"] for x in economy.inventory_values(1)["items"]}
        assert frame in ids and 1202024 not in ids
        assert not store.db.in_transaction
    stock(store, 1202024, 1)
    assert all(p.message_name != "L2C_ItemRemove" for p in economy.pushes(1))


@pytest.mark.parametrize("item,field,amount", [(1202024, "gold", 100000),
    (1202000, "hero_exp", 100), (1202001, "hero_exp", 500),
    (1202002, "hero_exp", 1000), (1202003, "hero_exp", 2000), (1202004, "hero_exp", 3000)])
def test_cards_persist_and_replay_once(env, item, field, amount):
    store, economy, ctx = env
    stock(store, item, 2)
    before = store.get(1)["snapshot"].get(field, 0)
    answer = use(economy, ctx, item, 2)
    assert answer.values["code"] == 10
    assert use(economy, ctx, item, 2).values == answer.values
    assert not store.db.in_transaction
    with sqlite3.connect(store.path) as reader:
        assert reader.execute("SELECT quantity FROM inventory WHERE item_id=?", (item,)).fetchone()[0] == 0
        assert reader.execute("SELECT COUNT(*) FROM item_opt_receipts").fetchone()[0] == 1
    assert store.get(1)["snapshot"][field] == before + amount * 2
    assert any(p.message_name == "L2C_ItemRemove" for p in answer.before_response)


def test_all_canonical_usable_items_have_a_complete_reward_path(env, monkeypatch):
    store, economy, ctx = env
    monkeypatch.setattr("x2server.player.bag_items.secrets.randbelow", lambda n: 0)
    for index, (item, link) in enumerate(economy.bag_catalog["items"].items()):
        item = int(item)
        stock(store, item, 1)
        pick = any(economy.bag_catalog["gifts"][str(g)]["awardType"] == 4 for g in link["used"])
        reply = use(economy, ctx, item, selected=[0] if pick else [], request=1000+index)
        assert reply.values["code"] == 10, (item, link)
        assert not store.db.in_transaction, item
        assert REWARD.decode(reply.values["rewardData"])


def test_compose_costs_replay_reopen_and_insufficient_material(env):
    store, economy, ctx = env
    service = BagItemService(store, economy)
    stock(store, 1250011, 6)
    p = store.get(1)
    store.save_snapshot(1, dict(p["snapshot"], gold=20000), p["revision"])
    request = packet({"RecipeID": 29000, "composeCount": 2}, name="C2L_JewelCompose")
    reply = asyncio.run(service.compose(ctx, request))
    assert reply.values["result"] == 10
    assert asyncio.run(service.compose(ctx, request)).values == reply.values
    assert not store.db.in_transaction
    with sqlite3.connect(store.path) as reader:
        assert reader.execute("SELECT quantity FROM inventory WHERE item_id=1250011").fetchone()[0] == 0
        assert reader.execute("SELECT quantity FROM inventory WHERE item_id=1250012").fetchone()[0] == 2
        assert reader.execute("SELECT COUNT(*) FROM bag_operation_receipts").fetchone()[0] == 1
    assert store.get(1)["snapshot"]["gold"] == 0
    rejected = asyncio.run(service.compose(ctx, packet({"RecipeID": 29000, "composeCount": 1},
        name="C2L_JewelCompose", request_id=99)))
    assert rejected.values["result"] == 13
    assert store.db.execute("SELECT quantity FROM inventory WHERE item_id=1250012").fetchone()[0] == 2


def test_every_canonical_gem_recipe_and_invalid_counts(env):
    store, economy, ctx = env
    service = BagItemService(store, economy)
    recipes = [(int(k), r) for k, r in economy.bag_catalog["recipes"].items() if r["type"] == 1]
    assert len(recipes) == 78
    for recipe_id, rule in recipes:
        for item, num in rule["costs"]:
            stock(store, item, num)
        p = store.get(1)
        store.save_snapshot(1, dict(p["snapshot"], gold=rule["gold"]), p["revision"])
        previous = store.db.execute("SELECT quantity FROM inventory WHERE item_id=?", (rule["product"],)).fetchone()
        previous = previous[0] if previous else 0
        answer = asyncio.run(service.compose(ctx, packet({"RecipeID": recipe_id, "composeCount": 1},
            name="C2L_JewelCompose", request_id=recipe_id)))
        assert answer.values["result"] == 10, rule
        assert store.db.execute("SELECT quantity FROM inventory WHERE item_id=?", (rule["product"],)).fetchone()[0] == previous + rule["productNum"]
        assert not store.db.in_transaction
    receipts = store.db.execute("SELECT COUNT(*) FROM bag_operation_receipts").fetchone()[0]
    for recipe, count in [(29000, 0), (29000, -1), (29000, 1000), (999999, 1)]:
        answer = asyncio.run(service.compose(ctx, packet({"RecipeID": recipe, "composeCount": count},
            name="C2L_JewelCompose", request_id=99999)))
        assert answer.values["result"] == 13
    assert store.db.execute("SELECT COUNT(*) FROM bag_operation_receipts").fetchone()[0] == receipts


def test_random_empty_reward_is_not_a_free_reroll(env, monkeypatch):
    store, economy, ctx = env
    monkeypatch.setattr("x2server.player.bag_items.secrets.randbelow", lambda n: n-1)
    stock(store, 1203001, 1)
    reply = use(economy, ctx, 1203001)
    assert reply.values["code"] == 10
    assert use(economy, ctx, 1203001).values == reply.values
    assert store.db.execute("SELECT quantity FROM inventory WHERE item_id=1203001").fetchone()[0] == 0


def test_jewel_seen_acknowledges_owned_hero_and_persists(env):
    store, economy, ctx = env
    service = BagItemService(store, economy)
    for _ in range(2):
        reply = asyncio.run(service.jewel_seen(ctx, packet({"heroId": 1003}, name="C2L_GodEquipJewelDot")))
        assert reply.values["code"] == 10
    assert store.db.execute("SELECT COUNT(*) FROM bag_jewel_seen").fetchone()[0] == 1
    assert not store.db.in_transaction


@pytest.mark.parametrize("kind", [1, 2])
def test_unload_clears_both_equipment_lists_and_preserves_other_slots(env, kind):
    store, economy, ctx = env
    service = EquipmentService(store, economy)
    equip_id, _ = seed(store, service, 6)
    p = store.get(1)
    hero = p["snapshot"]["heroes"][0]
    hero["equips"] = [{"position": 0, "equip_id": equip_id}]
    hero["season_equips"] = [{"position": 0, "equip_id": 90}, {"position": 1, "equip_id": 91}]
    store.save_snapshot(1, p["snapshot"], p["revision"])
    reply = asyncio.run(service.handle(ctx, packet({"heroID": 1003, "posIdx": 0, "optType": kind}, name="C2L_DoUnEquip")))
    assert reply.values["code"] == 10
    hero = store.get(1)["snapshot"]["heroes"][0]
    assert hero["equips"] == []
    assert hero["season_equips"] == [{"position": 1, "equip_id": 91}]
    wire = HERO_DATA.decode(encode_hero_data(hero))
    assert INT_PAIR.decode(wire["seasonEquips"][0]) == {"Key": 1, "Value": 91}
    rejected = asyncio.run(service.handle(ctx, packet({"heroID": 1003, "equipID": equip_id, "optType": 2}, name="C2L_DoEquip")))
    assert rejected.values["code"] == 13


def test_pick_box_rejects_bad_selection_without_consuming(env):
    store, economy, ctx = env
    stock(store, 1290001, 1)
    reply = use(economy, ctx, 1290001, selected=[999])
    assert reply.values["code"] == 13
    assert store.db.execute("SELECT quantity FROM inventory WHERE item_id=1290001").fetchone()[0] == 1
    assert store.db.execute("SELECT COUNT(*) FROM item_opt_receipts").fetchone()[0] == 0
