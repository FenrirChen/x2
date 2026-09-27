import asyncio

from tests.unit.test_battle import packet
from tests.unit.test_economy import env
from x2server.messages.appearance import HERO_DUBBING_DATA, HERO_SKIN, SEASON_ICON_DATA
from x2server.player.appearance import AppearanceService


def invoke(service, context, name, values=None):
    return asyncio.run(service.handle(context, packet(values or {}, name="C2L_" + name)))


def test_skin_catalog_wear_and_locked_skin_rejected(env):
    store, economy, context = env
    service = AppearanceService(store, economy)
    data = HERO_SKIN.decode(service.skin_values(1)["skinList"][0])
    assert 1220301 in data["skinIds"]
    assert 1220303 not in data["skinIds"]
    assert invoke(service, context, "HeroWearSkin", {"heroId": 1003,
        "skinId": 1220303, "type": 1}).values["code"] == 13
    first = invoke(service, context, "HeroWearSkin", {"heroId": 1003,
        "skinId": 1220301, "type": 1})
    assert first.values["code"] == 10
    assert [message.message_name for message in first.before_response] == ["L2C_HeroSkinUpdate"]
    assert HERO_SKIN.decode(first.before_response[0].values["skin"])["battleSkin"] == 1220301
    assert HERO_SKIN.decode(service.skin_values(1)["skinList"][0])["battleSkin"] == 1220301
    store.db.execute("INSERT INTO inventory VALUES (1,1220303,1)")
    paid = invoke(service, context, "HeroWearSkin", {"heroId": 1003,
        "skinId": 1220303, "type": 1})
    assert paid.values["code"] == 10
    assert HERO_SKIN.decode(paid.before_response[0].values["skin"])["battleSkin"] == 1220303
    assert HERO_SKIN.decode(AppearanceService(store, economy).skin_values(1)["skinList"][0])["battleSkin"] == 1220303
    daily = invoke(service, context, "HeroWearSkin", {"heroId": 1003,
        "skinId": 1220303, "type": 3})
    assert daily.values == {"code": 10, "heroId": 1003, "skinId": 1220303, "type": 3}
    assert not daily.pushes
    assert HERO_SKIN.decode(daily.before_response[0].values["skin"])["outerSkin"] == 1220303
    assert HERO_SKIN.decode(AppearanceService(store, economy).skin_values(1)["skinList"][0])["outerSkin"] == 1220303


def test_avatar_inventory_and_voice_conditions(env):
    store, economy, context = env
    service = AppearanceService(store, economy)
    icons = invoke(service, context, "SeasonIcon").values
    assert [SEASON_ICON_DATA.decode(x)["id"] for x in icons["headIconList"]] == [1000001]
    assert invoke(service, context, "PutOnOrPutOffSeasonIcon", {"type": 1,
        "id": 1270300}).values["code"] == 13
    store.db.execute("INSERT INTO inventory VALUES (1,1270300,1)")
    assert invoke(service, context, "PutOnOrPutOffSeasonIcon", {"type": 1,
        "id": 1270300}).values["code"] == 10
    assert service._icon_values(1)["putOnHeadIcon"] == 1270300
    assert invoke(service, context, "Account", {"opt": 2,
        "values": [1270301]}).values["result"] == 13
    assert invoke(service, context, "Account", {"opt": 2,
        "values": [1270300]}).values["result"] == 10
    voices = HERO_DUBBING_DATA.decode(service._voice_values(1)["heroDubbingDatas"][0])["dubbingIds"]
    assert 1350301 in voices  # Official default-unlock condition.
    assert 1350306 not in voices
    assert invoke(service, context, "SaveHeroDubbing", {"heroId": 1003,
        "dubbingId": 1350302}).values["code"] == 13  # Favor breakthrough needed.
    assert invoke(service, context, "SaveHeroDubbing", {"heroId": 1003,
        "dubbingId": 1350306}).values["code"] == 10  # Bare click-unlock condition.
    assert 1350306 in HERO_DUBBING_DATA.decode(
        AppearanceService(store, economy)._voice_values(1)["heroDubbingDatas"][0])["dubbingIds"]
