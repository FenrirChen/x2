"""Configured Current Echoes chest rewards follow admitted mode and replay safely."""
import asyncio,json,uuid,time
import pytest
from tests.unit.test_economy import env,rewards
from tests.unit.test_battle import packet,request
from tests.unit.test_bag_client_fixes import use
from x2server.player.battle import BattleService
from x2server.messages.battle import BATTLE_SCHEMAS,CHECKOUT,OUTSIDE_ITEM,FIGHT_DATA
from x2server.player.economy import EconomyService
from x2server.player.store import PlayerStore

def enter(env,section,expert,seq=1):
    store,e,ctx=env;b=BattleService(store,e);row=b.catalog.sections[section]
    parent=row.get('OpenParam',0)
    if parent:
        with store.db:store.db.execute('INSERT OR IGNORE INTO economy_clears VALUES (1,?,?)',(parent,'prerequisite'))
    values=dict(request(),missionId=section,chapter=row['ChapterID'],sceneId=row['Maps'][0],expertMode=expert)
    entry=asyncio.run(b.enter(ctx,packet(values,seq)))
    assert entry.values['result']==10
    return b,row,entry

def finish(b,ctx,row,success=True,reported_expert=False,echo=()):
    return asyncio.run(b.checkout(ctx,packet({'checkout':CHECKOUT.encode({'sectionId':row['SectionID'],
        'chapterId':row['ChapterID'],'success':success,'fightTime':20,'expertMode':reported_expert,
        'outsideItems':list(echo)})},name='C2L_CheckoutMainMissionSign')))

@pytest.mark.parametrize('section',[2110151,2110160,2110851,2110860,2110951])
@pytest.mark.parametrize('expert',[False,True])
def test_challenge_clear_grants_one_correct_box_and_replay_cannot_duplicate(env,section,expert):
    store,e,ctx=env;b,row,entry=enter(env,section,expert)
    fields=e.section_rewards.get(section)['special_reward_fields']
    expected=fields['ExpertChestReward' if expert else 'ChestReward'];other=fields['ChestReward' if expert else 'ExpertChestReward']
    # Checkout cannot alter admitted mode, nor inflate a client-side chest echo.
    echo=[OUTSIDE_ITEM.encode({'id':expected,'num':99}),OUTSIDE_ITEM.encode({'id':other,'num':99})]
    result=finish(b,ctx,row,reported_expert=not expert,echo=echo)
    assert result.values['result']==10
    assert rewards(result.values['rewardData'])[expected]==1
    assert other not in rewards(result.values['rewardData'])
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?',(expected,)).fetchone()[0]==1
    assert finish(b,ctx,row,reported_expert=not expert,echo=echo).values==result.values
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?',(expected,)).fetchone()[0]==1

@pytest.mark.parametrize('expert',[False,True])
def test_failed_challenge_has_no_chest(env,expert):
    store,e,ctx=env;b,row,_=enter(env,2110151,expert)
    result=finish(b,ctx,row,False)
    assert result.values['result']==10
    for item in (1203501,1203701):
        assert item not in rewards(result.values['rewardData'])
        assert not store.db.execute('SELECT 1 FROM inventory WHERE player_id=1 AND item_id=?',(item,)).fetchone()

def test_repeated_success_new_run_grants_new_box_and_opening_is_idempotent(env,monkeypatch):
    store,e,ctx=env
    for n in range(2):
        b,row,_=enter(env,2110151,False,seq=10+n)
        assert finish(b,ctx,row).values['result']==10
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1203501').fetchone()[0]==2
    monkeypatch.setattr('x2server.player.bag_items.secrets.randbelow',lambda size:0)
    first=use(e,ctx,1203501,request=50)
    assert first.values['code']==10 and rewards(first.values['rewardData'])=={1237913:100}
    assert use(e,ctx,1203501,request=50).values==first.values
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1203501').fetchone()[0]==1

def test_all_101_configured_sections_and_both_modes_have_openable_chests(env):
    store,e,ctx=env;BattleService(store,e)
    profiles=[p for p in e.section_rewards.sections.values() if p.get('special_reward_fields',{}).get('ChestReward')]
    assert len(profiles)==101
    for p in profiles:
        for expert in (False,True):
            run=str(uuid.uuid4());response=BATTLE_SCHEMAS['L2C_FightData'].encode({'data':FIGHT_DATA.encode({'expertMode':expert})})
            with store.db:store.db.execute('INSERT INTO battle_entries(player_id,request_key,uuid,created_at,response) VALUES (1,?,?,?,?)',(run,run,int(time.time()),response))
            item,mode,field=e.challenge_chest_for_run(1,run,p)
            assert mode==expert and item==p['special_reward_fields'][field]
            assert all(str(g) in e.bag_catalog['gifts'] for g in e.bag_catalog['items'][str(item)]['used'])

def test_unconfigured_stage_does_not_gain_chest(env):
    store,e,ctx=env;b,row,_=enter(env,2110801,False)
    result=finish(b,ctx,row)
    assert result.values['result']==10
    assert not any(1203501<=item<=1203800 for item in rewards(result.values['rewardData']))


def test_expert_chest_opens_using_original_gift_weights(env,monkeypatch):
    store,e,ctx=env;b,row,_=enter(env,2110151,True)
    result=finish(b,ctx,row)
    assert rewards(result.values['rewardData'])[1203701]==1
    monkeypatch.setattr('x2server.player.bag_items.secrets.randbelow',lambda size:0)
    opened=use(e,ctx,1203701,request=52)
    assert opened.values['code']==10 and rewards(opened.values['rewardData'])=={1237914:1}
    assert use(e,ctx,1203701,request=52).values==opened.values
