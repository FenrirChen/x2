import asyncio
import json
from datetime import datetime, timezone, timedelta

import pytest
from tests.unit.test_origin_season import env
from tests.unit.test_battle import packet,request
from tests.unit.test_season_protocol_tasks import ctx, select, task
from tests.unit.test_restored_shops_favor import listing,buy,fund
from x2server.messages.battle import FIGHT_DATA,FIGHT_HERO,HERO_ATTR_ADD,OUTSIDE_ITEM,CHECKOUT
from x2server.messages.core import HERO_DATA,HERO_GOD_EQUIP
from x2server.messages.season import SEASON_SCHEMAS
from x2server.player.hero import encode_hero_data
from x2server.player.battle import BattleService
from x2server.player.shop import ShopService
from x2server.player.wish import WishService
from x2server.player.server_clock import ServerClock
from x2server.player.season_schedule import ANCHOR,DURATION


def setup_artifact(store,e,s,star=5):
    p=store.get(1)
    p['snapshot']['heroes'][0]['god_equip']={'id':1503,'level':1,'star':star,'jewels':{}}
    store.save_snapshot(1,p['snapshot'],p['revision'])
    with e.transaction():e._grant(1,'erosion-stock',{1238106:10,1238107:10,1238108:12,1238109:12,1238110:12})


def operate(s,op,slot=0,rid=1):
    return asyncio.run(s.handle(ctx(),packet({'type':op,'heroId':1003,'slot':slot},rid,'C2L_BattlepassArtifactOpt')))


def test_erosion_paid_preview_save_discard_idempotence_and_task(env,monkeypatch):
    store,e,s=env
    setup_artifact(store,e,s)
    select(s,6007031)
    monkeypatch.setattr('x2server.player.season_artifact.secrets.randbelow',lambda n:0)
    for slot,cost in enumerate([2,2,3,3,3]):
        before=store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?',(1238106+slot,)).fetchone()[0]
        result=operate(s,1,slot,slot+1)
        assert result.values['code']==10
        assert result.before_response and not result.pushes
        assert s.artifact.attributes(1,store.get(1)['snapshot']['heroes'][0])=={}
        assert operate(s,1,slot,slot+1).values['code']==10
        assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?',(1238106+slot,)).fetchone()[0]==before-cost
    assert task(s,6007031)['taskProgress']==5
    assert operate(s,2,0,20).values['code']==10
    hero=store.get(1)['snapshot']['heroes'][0]
    assert s.artifact.attributes(1,hero)=={145:50}
    wire=HERO_DATA.decode(encode_hero_data(hero,season=s,player_id=1))
    god=HERO_GOD_EQUIP.decode(wire['godEquip'])
    assert SEASON_SCHEMAS['BattlepassArtifactProperty'].decode(god['artifactProperties'][0])=={'slot':0,'attrType':145,'attrVal':50}
    assert len(god['lastRandomartifactProperty'])==4
    assert operate(s,3,1,21).values['code']==10
    assert s.artifact.attributes(1,hero)=={145:50}
    assert operate(s,2,1,22).values['code']==13


def test_erosion_insufficient_closed_slot_and_foreign_hero_roll_back(env):
    store,e,s=env
    setup_artifact(store,e,s,star=1)
    before=store.get(1)
    assert operate(s,1,4).values['code']==13
    assert store.get(1)==before
    store.db.execute('UPDATE inventory SET quantity=1 WHERE player_id=1 AND item_id=1238106');store.db.commit()
    assert operate(s,1,0,2).values['code']==13
    assert not s.state(1).get('artifact_erosion')
    response=asyncio.run(s.handle(ctx(),packet({'type':1,'heroId':1034,'slot':0},3,'C2L_BattlepassArtifactOpt')))
    assert response.values['code']==13


def test_talents_and_saved_erosion_reach_normal_battle_and_expire(env,monkeypatch):
    store,e,s=env
    setup_artifact(store,e,s)
    monkeypatch.setattr('x2server.player.season_artifact.secrets.randbelow',lambda n:0)
    assert operate(s,1).values['code']==10
    assert operate(s,2,rid=2).values['code']==10
    with e.transaction():
        state=s.state(1);state['talents']={'6006001':3,'6006011':2};s.write(1,state)
    battle=BattleService(store,economy=e)
    result=asyncio.run(battle.enter(ctx(),packet(request(),50)))
    assert result.values['result']==10
    hero=FIGHT_HERO.decode(FIGHT_DATA.decode(result.values['data'])['fightHeros'][0])
    attrs={r['attrId']:r['attrValue'] for r in map(HERO_ATTR_ADD.decode,hero['attrAdd'])}
    assert attrs[100]==180
    assert attrs[145]==50
    talents=[SEASON_SCHEMAS['TalentAttr'].decode(x) for x in hero['talentAttr']]
    assert next(t for t in talents if t['id']==6006011)['upValue']==200
    e.clock=lambda:ANCHOR+DURATION
    assert not s.attributes(1) and not s.battle_talents(1)
    assert not s.artifact.attributes(1,store.get(1)['snapshot']['heroes'][0])
    god=HERO_GOD_EQUIP.decode(HERO_DATA.decode(encode_hero_data(store.get(1)['snapshot']['heroes'][0],season=s,player_id=1))['godEquip'])
    assert not god.get('artifactProperties')


def test_collected_season_relic_is_owned_outside_season_and_configuration_persists(env):
    store,e,s=env
    from x2server.player.login import relic_item_ids
    relic=next(i for i in sorted(relic_item_ids()) if i in e.items)
    with e.transaction():
        state=s.state(1);state['relics']=[relic];s.write(1,state)
    assert relic in s.owned_relics(1)
    battle=BattleService(store,economy=e)
    result=asyncio.run(battle.enter(ctx(),packet(request(selectedRelicList=[relic]),71)))
    assert result.values['result']==10
    assert result.values['selectedRelicList']==[relic]
    assert store.get(1)['snapshot']['selected_relics']==[relic]
    e.clock=lambda:ANCHOR+DURATION
    assert relic in s.owned_relics(1)


def test_gem_shop_uses_correct_resource_for_each_family(env):
    store,e,_=env
    service=ShopService(store,e)
    goods=listing(service,ctx(),806)
    fund(store,1237904,10000);fund(store,1237905,10000)
    for index,good in enumerate(goods):
        resource=1237904 if good['canBuyTimes']==99 else 1237905
        assert good['currencyType']==resource-1237000
        before=store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?',(resource,)).fetchone()[0]
        other=1237905 if resource==1237904 else 1237904
        other_before=store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?',(other,)).fetchone()[0]
        result=buy(service,ctx(),806,good['goodsId'],rid=100+index)
        assert result.values['code']==10 and result.values['changeItemID']==resource
        assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?',(resource,)).fetchone()[0]==before-good['price']
        assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?',(other,)).fetchone()[0]==other_before


def test_zhuque_tomorrow_and_permanent_rotation_survive_restart(env):
    store,e,s=env
    tomorrow=int(datetime(2026,10,14,tzinfo=timezone(timedelta(hours=8))).timestamp())
    wish=WishService(store,e,clock=ServerClock(lambda:tomorrow))
    active=wish.active_periods()
    assert active[22218]==(tomorrow,tomorrow+2*86400)
    from importlib.resources import files
    swapped=json.loads(files('x2server').joinpath('data/wish_rotation.json').read_text('utf8'))['swapped'][1]
    assert swapped not in active
    restored=WishService(store,e,clock=ServerClock(lambda:tomorrow+20*86400))
    assert 22218 in restored.active_periods()
    original_date=int(datetime(2026,10,22,tzinfo=timezone(timedelta(hours=8))).timestamp())
    assert swapped in wish.active_periods(now=original_date)


def test_jewel_changes_saved_erosion_bonus_without_reroll_and_full_save_preserves_preview(env,monkeypatch,tmp_path):
    store,e,s=env
    setup_artifact(store,e,s)
    monkeypatch.setattr('x2server.player.season_artifact.secrets.randbelow',lambda n:0)
    assert operate(s,1).values['code']==10
    assert operate(s,2,rid=2).values['code']==10
    assert operate(s,1,1,3).values['code']==10
    p=store.get(1);p['snapshot']['heroes'][0]['god_equip']['jewels']['0']=1250015
    store.save_snapshot(1,p['snapshot'],p['revision'])
    assert s.artifact.attributes(1,store.get(1)['snapshot']['heroes'][0])=={145:56}
    from x2server.player.save_manager import SaveManager
    from tests.unit.test_save_manager import build_full_schema
    build_full_schema(store)
    manager=SaveManager(store,backup_root=tmp_path/'backups')
    before=s.state(1)['artifact_erosion']
    try:
        archive=manager.export_save(1)
        with e.transaction():
            state=s.state(1);state['artifact_erosion']={};s.write(1,state)
        manager.import_save(1,archive)
        assert s.state(1)['artifact_erosion']==before
        assert s.artifact.attributes(1,store.get(1)['snapshot']['heroes'][0])=={145:56}
    finally:manager.close()
