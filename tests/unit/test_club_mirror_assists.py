import asyncio
import copy

import pytest

from tests.unit.test_social import social, create
from tests.unit.test_economy import env
from tests.unit.test_battle import packet, request
from x2server.player.social import roster, SocialService
from x2server.player.battle import BattleService
from x2server.player.economy import UnresolvedEconomy
from x2server.messages.battle import CHECKOUT, BATTLE_SCHEMAS


def setup_mirror(s, ctx, members=3, hp=100):
    create(s, ctx)
    with s.economy.transaction():
        state=s.state(1)
        state['club']['members']={str(r['id']):0 for r in roster()[:members]}
        s.save(1,state)
    # Small HP fixtures make every individual turn and discarded overflow visible.
    s.mirror_health=[dict(r,maxHP=hp) for r in s.mirror_health[:5]]


@pytest.mark.parametrize('success',[False,True])
def test_each_member_turn_discards_overflow_and_continues_next_boss(social,success):
    s,ctx,_=social
    setup_mirror(s,ctx)
    with s.economy.transaction():
        s.bind_run(1,2170001,'one')
        result=s.completed(1,2170001,success,40,'one')
    # Player=40. NPC1=36, NPC2=24 (12 overflow discarded), NPC3 hits next for 18 (45%).
    assert [t['applied'] for t in result['turns']]==[40,36,24,18]
    assert [t['boss'] for t in result['turns']]==[2070001]*3+[2070002]
    assert len(set(t['member'] for t in result['turns']))==4
    state=s.state(1)
    assert state['mirror']['damage']=={'2070001':100,'2070002':18}
    assert state['mirror']['clears']==[2070001]
    assert state['mirror']['count']==2
    metadata={p['Name']:p['Value']['VInt64'] for p in s.http('/ClubService.GetClub',{},1)['Club']['Meta']}
    assert metadata['clubLayer_1']==1 and metadata['clubDamage_2']==18
    with s.economy.transaction():
        assert s.completed(1,2170001,success,40,'one')==result
    assert s.state(1)==state
    with pytest.raises(UnresolvedEconomy):
        s.admission(1,2170001)
    s.admission(1,2170002)
    restored=SocialService(s.store,s.economy,s.college,clock=s.clock)
    assert restored.state(1)['mirror']==state['mirror']


def test_player_kill_moves_all_npcs_to_next_boss_and_stops_at_last(social):
    s,ctx,_=social
    setup_mirror(s,ctx,members=10)
    with s.economy.transaction():
        s.bind_run(1,2170001,'sweep')
        result=s.completed(1,2170001,True,10000,'sweep')
    assert result['npc_damage']==9000
    assert [t['applied'] for t in result['turns']]==[100]*5
    assert s.mirror_current(s.state(1)) is None
    assert s.state(1)['mirror']['count']==2  # NPCs consume no player attempts.


def test_partial_hp_zero_damage_and_invalid_unbound_run(social):
    s,ctx,_=social
    setup_mirror(s,ctx,members=0)
    with s.economy.transaction():
        s.bind_run(1,2170001,'partial')
        result=s.completed(1,2170001,False,31,'partial')
    assert result['npc_damage']==27
    assert s.state(1)['mirror']['damage']=={'2070001':31}
    with s.economy.transaction():
        s.bind_run(1,2170001,'zero')
        result=s.completed(1,2170001,True,0,'zero')
    assert result['turns']==[]
    assert s.state(1)['mirror']['clears']==[]
    before=copy.deepcopy(s.state(1))
    with pytest.raises(UnresolvedEconomy):
        s.completed(1,2170001,False,50,'unbound')
    assert s.state(1)==before


def test_native_hp_field_28_and_real_checkout_are_atomic_and_idempotent(social):
    s,ctx,_=social
    setup_mirror(s,ctx)
    battle=BattleService(s.store,s.economy)
    row=battle.catalog.sections[2170001]
    values=request()
    values.update(missionId=2170001,chapter=row['ChapterID'],sceneId=row['Maps'][0])
    entry=asyncio.run(battle.enter(ctx,packet(values,101)))
    assert entry.values['result']==10
    raw=CHECKOUT.encode(dict(chapterId=row['ChapterID'],sectionId=2170001,
                             success=False,fightTime=90,hp=40))
    # Native tag e0 01 is field 28, varint; this field is damage, not remaining HP.
    assert b'\xe0\x01\x28' in raw and CHECKOUT.decode(raw)['hp']==40
    checkout=packet({'checkout':raw},102,'C2L_CheckoutMainMissionSign')
    result=asyncio.run(battle.checkout(ctx,checkout))
    assert result.values['result']==10
    assert s.state(1)['mirror']['damage']=={'2070001':100,'2070002':18}
    assert any(p.message_name=='L2C_ClubActiMainData' for p in result.before_response)
    before=copy.deepcopy(s.state(1))
    replay=asyncio.run(battle.checkout(ctx,checkout))
    assert replay.values==result.values and s.state(1)==before
    bad=packet({'checkout':CHECKOUT.encode(dict(CHECKOUT.decode(raw),hp=41))},103,'C2L_CheckoutMainMissionSign')
    assert asyncio.run(battle.checkout(ctx,bad)).values['result']==13
    assert s.state(1)==before
    reward=s.operate(1,s.state(1),'ClubReceiveReward',{'opt':0,'param':2070001})
    assert reward['code']==10


def test_interrupted_mirror_battle_spends_no_attempt(social):
    """A server update stops the client before CHECKOUT: no attempt, no damage."""
    s,ctx,_=social
    setup_mirror(s,ctx)
    battle=BattleService(s.store,s.economy)
    def enter(section,request_id):
        row=battle.catalog.sections[section]
        values=request()
        values.update(missionId=section,chapter=row['ChapterID'],sceneId=row['Maps'][0])
        return asyncio.run(battle.enter(ctx,packet(values,request_id)))
    assert enter(2170001,101).values['result']==10
    assert s.state(1)['mirror']['count']==3
    assert 'damage' not in s.state(1)['mirror']
    # The reconnect is cut off as well; neither run may cost an attempt.
    assert enter(2170001,102).values['result']==10
    assert s.state(1)['mirror']['count']==3
    row=battle.catalog.sections[2170001]
    raw=CHECKOUT.encode(dict(chapterId=row['ChapterID'],sectionId=2170001,
                             success=False,fightTime=90,hp=40))
    checkout=packet({'checkout':raw},103,'C2L_CheckoutMainMissionSign')
    assert asyncio.run(battle.checkout(ctx,checkout)).values['result']==10
    assert s.state(1)['mirror']['count']==2
    assert s.state(1)['mirror']['damage']=={'2070001':100,'2070002':18}
    # The abandoned runs stay in the state without blocking the advanced layer.
    assert enter(2170002,104).values['result']==10


def test_health_catalog_matches_native_curve(social):
    s,_,_=social
    assert len(s.mirror_health)==52
    for r in s.mirror_health:
        expected=(int(r['baseHP']*(r['hpBonus']*0.001)) if r['monsterLevel']<36
                  else r['baseHP']*r['hpBonus'])+r['hpCOR']
        assert r['maxHP']==expected>0
    assert 1 not in s.mirror_sections


def test_pending_mirror_runs_cannot_overspend_attempts(social):
    s,ctx,_ = social
    setup_mirror(s,ctx,members=0)
    with s.economy.transaction():
        state=s.state(1)
        state['mirror']['count']=1
        s.save(1,state)
        s.bind_run(1,2170001,'first')
        s.bind_run(1,2170001,'second')
        s.completed(1,2170001,False,1,'first')
    before=copy.deepcopy(s.state(1))
    with pytest.raises(UnresolvedEconomy,match='exhausted'):
        with s.economy.transaction():
            s.completed(1,2170001,False,1,'second')
    assert s.state(1)==before
    assert s.completed(1,2170001,False,1,'first')['done']
