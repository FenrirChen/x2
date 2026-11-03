from tests.unit.test_origin_season import env
from x2server.messages.appearance import HERO_SKIN
from x2server.player.appearance import AppearanceService


def test_season_pass_skin_reward_refreshes_appearance_page(env):
    """赛季凭证（LV.60 超越凭证）发外观后要推该神格的 L2C_HeroSkinUpdate。

    客户端的“神格外观”页只在登录的 heroSkinAll 与 L2C_HeroSkinUpdate 里重读
    已拥有形象；只把 1221203 放进背包时页面会一直显示「未获得」。
    """
    store, economy, season = env
    appearance = AppearanceService(store, economy)
    economy.appearance = appearance
    snapshot = store.get(1)['snapshot']
    snapshot['heroes'].append({'id': 1012, 'state': 2, 'level': 1, 'star': 1})
    store.save_snapshot(1, snapshot, store.get(1)['revision'])

    with economy.transaction():
        state = season.state(1)
        state['exp'] = 60000
        season.write(1, state)
        answer = season.operate(1, 'ReceiveBattlePass', {'configIds': [60]}, 'claim-lv60')
    assert answer['code'] == 10
    quantity = store.db.execute(
        'SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1221203').fetchone()[0]
    assert quantity == 1

    pushes = economy.pushes(1)
    names = [push.message_name for push in pushes]
    assert 'L2C_HeroSkinAll' in names
    updates = [HERO_SKIN.decode(push.values['skin']) for push in pushes
               if push.message_name == 'L2C_HeroSkinUpdate']
    entry = next(value for value in updates if value['heroId'] == 1012)
    assert 1221203 in entry['skinIds']

    owned = appearance._owned_skins(1)
    assert 1221203 in owned
