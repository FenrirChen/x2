import asyncio
import pytest
from tests.unit.test_activity_runtime import runtime, seed
from tests.unit.test_economy import env, rewards
from tests.unit.test_battle import packet
from x2server.player.battle import BattleService
from x2server.messages.battle import PROFILE_HERO, CHECKOUT, BATTLE_SCHEMAS
from x2server.messages.activity import ACTIVITY_SCHEMAS
from x2server.player.activity_rotation import ActivityRotation


@pytest.mark.parametrize('section', [2161191,2161192,2161193])
def test_food_fantasy_entry_checkout_and_repeat(runtime, section):
    store,e,ctx,rt,now=runtime
    e.activity=rt.a
    battle=BattleService(store,e)
    seed(rt,{1237900:1000},key='stamina')
    row=battle.catalog.sections[section]
    from x2server.player.trial_units import section_trial
    hero=section_trial(row,[1003]) or 1003
    entry=asyncio.run(battle.enter(ctx,packet({'missionId':section,'chapter':row['ChapterID'],
        'sceneId':row['Maps'][0], 'heros':[PROFILE_HERO.encode({'heroId':hero,'leader':1})]},901)))
    assert entry.values['result']==10
    request=packet({'checkout':CHECKOUT.encode({'chapterId':row['ChapterID'],'sectionId':section,
        'success':True,'fightTime':120,'heros':[PROFILE_HERO.encode({'heroId':hero,'state':0})]})},902,'C2L_CheckoutMainMissionSign')
    result=asyncio.run(battle.checkout(ctx,request))
    assert result.values['result']==10
    assert asyncio.run(battle.checkout(ctx,request)).values==result.values
    assert rt.r.get(1,rt.r.at(),'clear',section)==1


@pytest.mark.parametrize('theme,sections,shops',[
    (0,[2161111,2161114,2161117],[7,8,9]),
    (5,[2160411,2160431,2160451],[1,2,3])])
def test_story_first_clear_grants_actual_shop_repair_recipes(runtime,theme,sections,shops):
    store,e,ctx,rt,now=runtime
    now[0]=ActivityRotation.ANCHOR+theme*ActivityRotation.SECONDS+3600
    e.activity=rt.a
    BattleService(store,e)
    for sid,kind in zip(sections,shops):
        row=rt.a.sections[sid]
        key=f'repair-story-{sid}'
        with e.transaction():
            store.db.execute("""INSERT INTO economy_runs
                (uuid,player_id,session_id,section_id,settled,section_type,entry_source)
                VALUES (?,1,'session',?,0,14,'ActivityStory')""",(key,sid))
            rt.r.bind_run(1,sid,key)
            result,_=e.settle(1,key,sid,True,section_type=14)
        recipe=rt.cafe.levels[kind,1]['CafeUnlockCon'][0]
        assert rewards(result).get(recipe)==1
        assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?',(recipe,)).fetchone()[0]==1
        reply=asyncio.run(rt.handle(ctx,packet({'storeType':kind},700+kind,'C2L_CafeStoreUnLock')))
        assert reply.values['code']==10
        ACTIVITY_SCHEMAS['L2C_CafeStoreUnLock'].encode(reply.values)
