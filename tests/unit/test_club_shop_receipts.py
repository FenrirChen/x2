# -*- coding: utf-8 -*-
"""807 社团商店卖的 FE7「自动开出」凭据必须当场拆开, 不能入库。

客户端 Item 表里 社团宝箱 (1915701 -> 1203022, Gift 776053) 和 6★随机兽主
(1915401 -> 1203023, Gift 776054) 都是 Item.FunctionEff=7 / Item.EffData=礼包组,
而且没有 Item.Used —— 也就是说凭据本身客户端点不开。修好之前这条购买路径会把凭据
原样入库: 客户端只看到 code 10 加背包里一张死凭据, 就是玩家报的「买了没到账」。
"""
from tests.unit.test_economy import env
from tests.unit.test_restored_shops_favor import buy, fund
from x2server.messages.economy import REWARD, REWARD_ITEM
from x2server.messages.equipment import HERO_EQUIP
from x2server.player.shop import ShopService
import json


def _reward(raw):
    payload = REWARD.decode(raw)
    items = {x["itemId"]: x["itemNum"] for x in map(REWARD_ITEM.decode, payload.get("rewardItem", []))}
    equips = [HERO_EQUIP.decode(b) for b in payload.get("rewardEquip", [])]
    return items, equips


def _held(store, item):
    row = store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?",
                           (item,)).fetchone()
    return row[0] if row else 0


def test_club_box_receipt_opens_into_its_gift_contents(env):
    """1915701 社团宝箱: 拆出来后是 776053 的候选之一, 凭据不入库。"""
    store, e, ctx = env
    service = ShopService(store, e)
    fund(store, 1237924, 5000)
    paid = buy(service, ctx, 807, 1915701)
    assert paid.values["code"] == 10
    items, equips = _reward(paid.values["rewardData"])
    assert not equips and len(items) == 1, (items, equips)
    (item, count), = items.items()
    assert [item, count] in e.gift_contents["776053"]["items"], (item, count)
    assert _held(store, 1203022) == 0


def test_club_beast_master_receipt_delivers_a_six_star_instance(env):
    """1915401 6★随机兽主: 照凭据写明的 6★ 落成实例, 随 rewardEquip 与 L2C_EquipUpdate 下发。"""
    store, e, ctx = env
    service = ShopService(store, e)
    fund(store, 1237924, 5000)
    paid = buy(service, ctx, 807, 1915401)
    assert paid.values["code"] == 10
    items, equips = _reward(paid.values["rewardData"])
    assert not items and len(equips) == 1, (items, equips)
    assert equips[0]["star"] == 6
    assert equips[0]["typeId"] in {item for item, _ in e.gift_contents["776054"]["items"]}
    assert _held(store, 1203023) == 0
    pushed = [m for m in paid.pushes if m.message_name == "L2C_EquipUpdate"]
    assert pushed and pushed[0].values["equip"] == [HERO_EQUIP.encode(equips[0])]
    assert store.db.execute("SELECT COUNT(*) FROM equipment_instances WHERE player_id=1").fetchone()[0] == 1


def test_parked_receipt_is_opened_once_at_login(env):
    """修好之前买到的凭据还躺在背包里: 登录补开一次, 之后不再重复。"""
    store, e, ctx = env
    with store.db:
        # 模拟旧版本留下的状态: 凭据在背包, 没有任何 economy_grants 记录。
        store.db.execute("INSERT INTO inventory VALUES (?,?,?)", (1, 1203023, 2))
        store.db.execute("INSERT INTO inventory VALUES (?,?,?)", (1, 1203022, 1))
    e.login_event(1)
    assert _held(store, 1203022) == 0 and _held(store, 1203023) == 0
    ledger = json.loads(store.db.execute("SELECT rewards FROM economy_grants WHERE player_id=1 "
        "AND source='receipt-repair:1:1203022'").fetchone()[0])
    assert set(map(int, ledger)) <= {item for item, _ in e.gift_contents["776053"]["items"]}
    instances = store.db.execute("SELECT star,type_id FROM equipment_instances WHERE player_id=1").fetchall()
    assert len(instances) == 2 and {row[0] for row in instances} == {6}
    assert {row[1] for row in instances} <= {item for item, _ in e.gift_contents["776054"]["items"]}
    # 第二次登录必须什么都不做 —— 补发不能重复。
    before = store.db.execute("SELECT COUNT(*) FROM equipment_instances WHERE player_id=1").fetchone()[0]
    e.login_event(1)
    assert store.db.execute("SELECT COUNT(*) FROM equipment_instances WHERE player_id=1").fetchone()[0] == before


def test_parked_receipt_is_kept_when_its_contents_cannot_be_delivered(env):
    """没有 star 证据的凭据不许被猜着拆开: 原样留在背包, 不吞也不乱发。"""
    store, e, ctx = env
    e.receipt_stars.pop(1203023)
    with store.db:
        store.db.execute("INSERT INTO inventory VALUES (?,?,?)", (1, 1203023, 1))
    e.login_event(1)
    assert _held(store, 1203023) == 1
    assert store.db.execute("SELECT 1 FROM economy_grants WHERE player_id=1 "
                            "AND source='receipt-repair:1:1203023'").fetchone() is None
