import asyncio
import pytest
from tests.unit.test_activity_runtime import runtime, seed
from tests.unit.test_economy import env, rewards
from tests.unit.test_battle import packet
from x2server.player.battle import BattleService
from x2server.messages.battle import PROFILE_HERO, CHECKOUT, BATTLE_SCHEMAS
from x2server.messages.activity import ACTIVITY_SCHEMAS
from tests.activity_calendar_helpers import activity_start


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
    now[0]=activity_start(theme)+3600
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


@pytest.mark.parametrize('selected', [(1327,1328,1331),(1027,1028,1031),(1331,1327,1328)])
def test_food_trial_team_full_entry_settlement_and_retry(runtime, selected):
    from x2server.messages.battle import FIGHT_DATA, FIGHT_HERO
    from x2server.player.trial_units import catalog
    store,e,ctx,rt,now=runtime
    e.activity=rt.a
    battle=BattleService(store,e)
    seed(rt,{1237900:1000},key='trial-team-stamina')
    row=battle.catalog.sections[2161191]
    before=store.get(1)['snapshot']['heroes']
    request=packet({'missionId':2161191,'chapter':row['ChapterID'],'sceneId':row['Maps'][0],
        'heros':[PROFILE_HERO.encode({'heroId':h,'leader':int(i==0)}) for i,h in enumerate(selected)]},910)
    entry=asyncio.run(battle.enter(ctx,request))
    assert entry.values['result']==10
    heroes=[FIGHT_HERO.decode(raw) for raw in FIGHT_DATA.decode(entry.values['data'])['fightHeros']]
    alias={u['UnitID']:u['TrialHeroID'] for u in catalog()['units'] if u['TrialHeroID'] in row['AssistParam']}
    expected=[alias.get(h,h) for h in selected]
    assert [h['id'] for h in heroes]==expected
    assert all(h['heroGodEquip'] and len(h['heroEquip'])==6 and h['heroSkill'] for h in heroes)
    assert asyncio.run(battle.enter(ctx,request)).values==entry.values
    assert store.get(1)['snapshot']['heroes']==before
    checkout=packet({'checkout':CHECKOUT.encode({'chapterId':row['ChapterID'],'sectionId':2161191,
        'success':True,'fightTime':120})},911,'C2L_CheckoutMainMissionSign')
    result=asyncio.run(battle.checkout(ctx,checkout))
    assert result.values['result']==10
    assert asyncio.run(battle.checkout(ctx,checkout)).values==result.values
    assert rt.r.get(1,rt.r.at(),'clear',2161191)==1
    assert store.get(1)['snapshot']['heroes']==before


def test_trial_rosters_match_all_configured_units_and_reject_foreign_or_duplicate_aliases():
    from x2server.player.trial_units import trial_team, catalog
    from x2server.player.battle_entry import BattleEntryCatalog
    units={u['TrialHeroID']:u for u in catalog()['units']}
    for row in BattleEntryCatalog().sections.values():
        if row.get('AssistType',{}).get('value')!=1:
            continue
        roster=[h for h in row.get('AssistParam',[]) if h>0]
        assert trial_team(row,roster)==roster
        aliases=[units[h]['UnitID'] for h in roster]
        assert trial_team(row,aliases)==roster
        with pytest.raises(ValueError):
            trial_team(row,[999999])
        with pytest.raises(ValueError):
            trial_team(row,[roster[0],aliases[0]])
    # Preserve chapter-seven's solo compensation, without converting mixed teams.
    row={'SectionID':2110607,'ChapterID':2010700,'AssistType':{'value':2}}
    assert trial_team(row,[1003])==[1303]
    assert trial_team(row,[1003,1027])==[None,None]
