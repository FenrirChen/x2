from tests.unit.test_economy import env
from tests.unit.test_bag_client_fixes import stock, use
from tests.unit.test_save_manager import build_full_schema
from x2server.player.save_manager import SaveManager
from x2server.player.bag_items import bag_reward_view, recover_hero_boxes
from x2server.player.wish import WishService
from x2server.messages.economy import ECONOMY_SCHEMAS, REWARD, REWARD_ITEM
import pytest
from types import SimpleNamespace


def client_single_hero_contract(e, response):
    reward=REWARD.decode(response.values['rewardData'])
    history=[WishService.TRANSFORM_HERO.decode(x) for x in reward['transformHero']]
    items=[REWARD_ITEM.decode(x) for x in reward['rewardItem']]
    # Native UIAPI 0x134bf94-0x134c118 chooses the one-hero path only when
    # both lists contain one entry. The field is passed directly to ItemManager.
    if len(history)==len(items)==1 and not history[0].get('transform',False):
        item=e.items.get(history[0]['heroId'])
        assert item is not None, 'native UIAPI would dereference null Item'
        assert item['ItemType']['value']==15
        assert history[0]['heroId']==items[0]['itemId']
    return reward,history,items


def test_three_reload_duplicates_then_new_hero_popup(env,monkeypatch):
    store,e,ctx=env
    p=store.get(1)
    p['snapshot']['heroes'] += [{'id':hid,'state':2,'level':1,'star':5} for hid in (1005,1008,1012)]
    store.save_snapshot(1,p['snapshot'],p['revision'])
    build_full_schema(store)
    stock(store,1203000,1)
    manager=SaveManager(store)
    archive=manager.export_save(1)
    # Original gift weights: 1005 -> 1008 -> 1012 -> 1014.
    for index,(roll,hid) in enumerate(zip((0,90,190,280),(1005,1008,1012,1014))):
        manager.import_save(1,archive)
        ctx.session.session_id='reload-'+str(index)
        monkeypatch.setattr('x2server.player.bag_items.secrets.randbelow',lambda n,r=roll:r)
        result=use(e,ctx,1203000,request=20)
        assert result.values['code']==10
        reward,history,items=client_single_hero_contract(e,result)
        assert history==[{'heroId':1210000+hid,'transform':index<3}]
        assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1203000').fetchone()[0]==0
        assert any(h['id']==hid and h['state']==2 for h in store.get(1)['snapshot']['heroes'])
        before=store.get(1)
        assert use(e,ctx,1203000,request=20).values==result.values
        assert store.get(1)==before
        assert recover_hero_boxes(e,1)==0
    manager.close()


def test_legacy_single_new_hero_receipt_normalized_without_regrant(env,monkeypatch):
    store,e,ctx=env
    stock(store,1203000,1)
    monkeypatch.setattr('x2server.player.bag_items.secrets.randbelow',lambda n:0)
    result=use(e,ctx,1203000)
    raw=REWARD.decode(result.values['rewardData'])
    raw['transformHero']=[WishService.TRANSFORM_HERO.encode({'heroId':1005,'transform':False})]
    old=dict(result.values,rewardData=REWARD.encode(raw))
    with pytest.raises(AssertionError,match='dereference null Item'):
        client_single_hero_contract(e,SimpleNamespace(values=old))
    with store.db:
        store.db.execute('UPDATE item_opt_receipts SET response=? WHERE player_id=1',
            (ECONOMY_SCHEMAS['L2C_ItemOpt'].encode(old),))
    before=store.get(1)
    replay=use(e,ctx,1203000)
    client_single_hero_contract(e,replay)
    assert store.get(1)==before
    assert bag_reward_view(replay.values['rewardData'])==replay.values['rewardData']


def test_cross_account_reload_then_new_hero_has_valid_popup(env,monkeypatch):
    store,e,ctx=env
    build_full_schema(store)
    stock(store,1203000,2)
    manager=SaveManager(store)
    archive=manager.export_save(1)
    target=store.login('box-import-target',2,0)
    assert target['id']==2
    for i in range(4):
        manager.import_save(2,archive)
        ctx.session.player_id=2
        ctx.session.session_id='target-reload-'+str(i)
        monkeypatch.setattr('x2server.player.bag_items.secrets.randbelow',lambda n:0)
        result=use(e,ctx,1203000,request=20)
        assert result.values['code']==10
        _,history,_=client_single_hero_contract(e,result)
        assert history==[{'heroId':1211005,'transform':False}]
        assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=2 AND item_id=1203000').fetchone()[0]==1
        assert recover_hero_boxes(e,2)==0
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1203000').fetchone()[0]==2
    manager.close()


@pytest.mark.parametrize('index',range(11))
def test_every_single_new_hero_matches_native_popup_lookup(env,monkeypatch,index):
    store,e,ctx=env
    gift=e.bag_catalog['gifts']['776052']
    roll=sum(gift['weights'][:index])
    monkeypatch.setattr('x2server.player.bag_items.secrets.randbelow',lambda n:roll)
    stock(store,1203000,1)
    reply=use(e,ctx,1203000)
    assert reply.values['code']==10
    _,history,_=client_single_hero_contract(e,reply)
    assert history[0]['heroId']==gift['items'][index][0]


def test_full_item_id_history_restores_proven_missing_new_hero(env,monkeypatch):
    store,e,ctx=env
    stock(store,1203000,1)
    monkeypatch.setattr('x2server.player.bag_items.secrets.randbelow',lambda n:0)
    reply=use(e,ctx,1203000)
    client_single_hero_contract(e,reply)
    p=store.get(1)
    p['snapshot']['heroes']=[h for h in p['snapshot']['heroes'] if h['id']!=1005]
    store.save_snapshot(1,p['snapshot'],p['revision'])
    assert recover_hero_boxes(e,1)==1
    assert any(h['id']==1005 and h['state']==2 for h in store.get(1)['snapshot']['heroes'])
    assert recover_hero_boxes(e,1)==0
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1203000').fetchone()[0]==0
