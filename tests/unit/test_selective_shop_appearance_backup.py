import asyncio
import sqlite3
from tests.unit.test_economy import env
from tests.unit.test_battle import packet
from x2server.messages.economy import GOODS, ITEM
from x2server.player.shop import ShopService
from x2server.player.appearance import AppearanceService, avatar_frames, head_icon_info
from x2server.messages.appearance import ICON_INFO
from x2server.player.recommendations import recommend, TAG, HOT_AREA, banner_response


def test_refresh_changes_full_stock_keeps_daily_limits_and_receipt(env):
    store, economy, ctx = env
    service = ShopService(store, economy)
    p = store.get(1)
    store.save_snapshot(1, dict(p["snapshot"], crystal=1000), p["revision"])
    with store.db:
        store.db.execute("INSERT INTO shop_compat_counts VALUES (1,801,1899001,?,1)", (service._period(3),))
    before = service._compat_goods(1, 801, service.compat_offers[(801, 1899001)])
    assert before["canBuyTimes"] == 3 and before["hasBuyTimes"] == 1
    request = packet({"shopId": 801}, name="C2L_RefreshShop", request_id=92)
    answer = asyncio.run(service.handle(ctx, request))
    assert answer.values["code"] == 10
    after = next(GOODS.decode(raw) for raw in answer.values["goods"]
                 if GOODS.decode(raw)["goodsId"] == 1899001)
    assert after["itemId"] != before["itemId"]   # refresh rerolls the displayed shard
    assert after["canBuyTimes"] == 3             # the daily limit is not rerolled
    assert after["hasBuyTimes"] == 1             # the day's buy count is kept
    assert store.get(1)["snapshot"]["crystal"] == 950
    assert asyncio.run(service.handle(ctx, request)).values == answer.values
    assert service._refresh_count(1, 801) == 1
    assert store.get(1)["snapshot"]["crystal"] == 950


def test_recommendation_images_jump_and_no_daily_rotation(env):
    _, economy, _ = env
    rows = recommend(economy, 1)["recommendTag"]
    assert rows
    for raw in rows:
        row = TAG.decode(raw)
        assert HOT_AREA.decode(row["hotAreaParam"][0])["jumpId"] > 0
        path = "/gifticon/" + row["cdnLinkPic"].rsplit("/", 1)[1]
        response = banner_response("GET", path)
        assert response.status == 200 and response.body.startswith(b'\x89PNG')
    assert banner_response("GET", "/gifticon/../selected_gift_packages.json").status == 404
    assert recommend(economy, 1)["recommendTag"] == rows


def test_frames_selection_and_skin_ownership_unchanged(env):
    store, economy, ctx = env
    service = AppearanceService(store, economy)
    frame = max(avatar_frames())
    assert len(avatar_frames()) == 75
    items = {ITEM.decode(raw)["id"] for raw in economy.inventory_values(1)["items"]}
    assert avatar_frames() <= items
    request = packet({"opt": 2, "values": [1, 1000001, frame]}, name="C2L_Account")
    assert asyncio.run(service.handle(ctx, request)).values["result"] == 10
    assert ICON_INFO.decode(head_icon_info(store.get(1)["snapshot"]))["OrnamentID"] == frame
    assert len(service._icon_values(1)["headIconList"]) == 155
    assert len(service._icon_values(1)["sceneIconList"]) == 9
    assert service._owned_skins(1) != set(service.skins)


def test_online_backup_without_schema_or_save_changes(env, tmp_path):
    store, _, _ = env
    destination = tmp_path / "backup.sqlite"
    before = store.get(1)
    store.backup_to(destination)
    with sqlite3.connect(destination) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("SELECT revision FROM players WHERE id=1").fetchone()[0] == before["revision"]
    assert store.get(1) == before
