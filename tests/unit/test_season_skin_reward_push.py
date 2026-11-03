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


import asyncio
import pytest
from tests.unit.test_season_protocol_tasks import ctx
from tests.unit.test_battle import packet
from x2server.player.mail import MailService


def wired(env):
    store,e,s=env
    e.appearance=AppearanceService(store,e)
    snapshot=store.get(1)['snapshot']
    snapshot['heroes'].append({'id':1012,'state':2,'level':1,'star':1})
    store.save_snapshot(1,snapshot,store.get(1)['revision'])
    return store,e


def test_rolled_back_grant_does_not_publish_skin_or_poison_next_grant(env):
    store,e=wired(env)
    with pytest.raises(RuntimeError):
        with e.transaction():
            e._grant(1,'rollback-skin',{1221203:1})
            raise RuntimeError('abort outer transaction')
    assert e._skin_pushes(1)==()
    with e.transaction():
        e._grant(1,'valid-skin',{1221203:1})
    assert len(e._skin_pushes(1))==2
    assert not e._granted_skins


def test_receipt_replay_republishes_skin_without_duplicate_reward(env):
    store,e=wired(env)
    with e.transaction():
        reward=e._grant(1,'same-receipt',{1221203:1})
    assert len(e._skin_pushes(1))==2
    assert e._skin_pushes(2)==()
    with e.transaction():
        assert e._grant(1,'same-receipt',{1221203:1})==reward
    assert len(e._skin_pushes(1))==2
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1221203').fetchone()[0]==1


def test_skin_list_failure_does_not_lose_pending_hint(env,monkeypatch):
    store,e=wired(env)
    with e.transaction():
        e._grant(1,'list-failure',{1221203:1})
    original=e.appearance.skin_values
    def fail(player):
        raise RuntimeError('skin list failure')
    monkeypatch.setattr(e.appearance,'skin_values',fail)
    with pytest.raises(RuntimeError):
        e._skin_pushes(1)
    monkeypatch.setattr(e.appearance,'skin_values',original)
    assert len(e._skin_pushes(1))==2


def test_mail_attachment_handler_includes_appearance_refresh(env):
    store,e=wired(env)
    mail=MailService(store,e)
    mid=mail.send(1,'skin','reward',{1221203:1})
    result=asyncio.run(mail.handle(ctx(),packet({'mailid':mid},90,'C2L_ReceiveAttachment')))
    assert result.values['code']==10
    messages=result.before_response+result.pushes
    assert sum(p.message_name=='L2C_HeroSkinAll' for p in messages)==1
    skin=next(HERO_SKIN.decode(p.values['skin']) for p in messages if p.message_name=='L2C_HeroSkinUpdate')
    assert skin['heroId']==1012 and 1221203 in skin['skinIds']


def test_season_claim_real_handler_refreshes_skin_once_and_replay_does_not_regrant(env):
    store,e=wired(env)
    season=env[2]
    with e.transaction():
        state=season.state(1)
        state['exp']=60000
        season.write(1,state)
    request=packet({'configIds':[60]},190,'C2L_ReceiveBattlePass')
    answer=asyncio.run(season.handle(ctx(),request))
    assert answer.values['code']==10
    messages=answer.before_response+answer.pushes
    assert sum(p.message_name=='L2C_HeroSkinAll' for p in messages)==1
    assert any(p.message_name=='L2C_HeroSkinUpdate' and
               1221203 in HERO_SKIN.decode(p.values['skin'])['skinIds'] for p in messages)
    replay=asyncio.run(season.handle(ctx(),request))
    assert replay.values==answer.values
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1221203').fetchone()[0]==1
