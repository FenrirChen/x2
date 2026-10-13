import json

from tests.unit.test_economy import env
from tests.unit.test_bag_client_fixes import stock, use
from x2server.messages.economy import REWARD, REWARD_ITEM, ECONOMY_SCHEMAS
from x2server.player.bag_items import recover_hero_boxes
from x2server.player.progression import catalog


def decoded(reply):
    raw = REWARD.decode(reply.values['rewardData'])
    entries = [REWARD_ITEM.decode(i) for i in raw['rewardItem']]
    # Mirrors the client's unique-item Dictionary.Add precondition.
    assert len({i['itemId'] for i in entries}) == len(entries)
    return raw, {i['itemId']: i for i in entries}


def test_ten_owned_duplicates_have_one_display_row_and_ten_compensations(env, monkeypatch):
    store, economy, ctx = env
    p = store.get(1)
    p['snapshot']['heroes'].append({'id':1005, 'state':2, 'level':1, 'star':3})
    store.save_snapshot(1,p['snapshot'],p['revision'])
    monkeypatch.setattr('x2server.player.bag_items.secrets.randbelow',lambda n:0)
    stock(store,1203000,10)
    reply=use(economy,ctx,1203000,count=10)
    assert reply.values['code']==10
    raw, entries=decoded(reply)
    assert entries[1211005]['itemNum']==10 and entries[1211005]['transform']
    assert len(raw['transformHero'])==10
    proto=next(p for p in catalog()['hero_unlock'] if p['hero_id']==1005)
    for key,qty in [('fragment_item_id','fragment_count'),('duplicate_ticket_item_id','duplicate_ticket_count')]:
        assert entries[proto[key]]['itemNum']==10*proto[qty]
        assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?',(proto[key],)).fetchone()[0]==10*proto[qty]
    assert use(economy,ctx,1203000,count=10).values==reply.values
    assert recover_hero_boxes(economy,1)==0


def test_mixed_new_and_duplicate_rows_recover_only_nine_conversions(env,monkeypatch):
    store,economy,ctx=env
    monkeypatch.setattr('x2server.player.bag_items.secrets.randbelow',lambda n:0)
    stock(store,1203000,10)
    reply=use(economy,ctx,1203000,count=10)
    raw,entries=decoded(reply)
    assert entries[1211005]['itemNum']==10 and not entries[1211005]['transform']
    assert len(raw['transformHero'])==10
    proto=next(p for p in catalog()['hero_unlock'] if p['hero_id']==1005)
    assert entries[proto['fragment_item_id']]['itemNum']==9*proto['fragment_count']
    with store.db:
        store.db.execute('UPDATE inventory SET quantity=0 WHERE player_id=1 AND item_id!=1203000')
        store.db.execute("UPDATE economy_grants SET rewards='{}' WHERE player_id=1 AND source LIKE 'item-opt:%'")
    assert recover_hero_boxes(economy,1)==1
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?',(proto['fragment_item_id'],)).fetchone()[0]==9*proto['fragment_count']
    assert recover_hero_boxes(economy,1)==0


def test_legacy_duplicate_display_rows_replay_without_reroll_or_double_grant(env,monkeypatch):
    store,economy,ctx=env
    monkeypatch.setattr('x2server.player.bag_items.secrets.randbelow',lambda n:0)
    stock(store,1203000,10)
    reply=use(economy,ctx,1203000,count=10)
    raw,entries=decoded(reply)
    hero=entries[1211005]
    raw['rewardItem']=[r for r in raw['rewardItem'] if REWARD_ITEM.decode(r)['itemId']!=1211005]
    raw['rewardItem'].extend(REWARD_ITEM.encode({**hero,'itemNum':1}) for _ in range(10))
    values={**reply.values,'rewardData':REWARD.encode(raw)}
    with store.db:store.db.execute('UPDATE item_opt_receipts SET response=? WHERE player_id=1',(ECONOMY_SCHEMAS['L2C_ItemOpt'].encode(values),))
    before=[tuple(r) for r in store.db.execute('SELECT * FROM inventory ORDER BY item_id')]
    monkeypatch.setattr('x2server.player.bag_items.secrets.randbelow',lambda n: (_ for _ in ()).throw(AssertionError('must not reroll')))
    replay=use(economy,ctx,1203000,count=10)
    _,entries=decoded(replay)
    assert entries[1211005]['itemNum']==10
    assert [tuple(r) for r in store.db.execute('SELECT * FROM inventory ORDER BY item_id')]==before
