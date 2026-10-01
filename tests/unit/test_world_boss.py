"""Native temporal-gate routes, persistence, and battle/receipt boundaries."""
import asyncio
import json

import pytest

from tests.unit.test_battle import packet, request
from tests.unit.test_economy import env, rewards
from x2server.messages.battle import CHECKOUT
from x2server.messages.world_boss import INFO, SEARCH, DAILY, CONTAINER, QUESTION, SLOT, BOSS
from x2server.network.dispatcher import DispatchContext
from x2server.network.session import SessionState
from x2server.player.battle import BattleService
from x2server.player.economy import EconomyService
from x2server.player.world_boss import account_state, snapshot_fields, day


def call(service, ctx, name, values=None, number=1):
    return asyncio.run(service.handle(ctx, packet(values or {},name=name,request_id=number)))


def admit_fixture(economy, section):
    """Static catalog tests must arrange a real Boss admission, too."""
    service=economy.world_boss
    static=next((r for r in service.bosses.values() if r['StageID']==section),None)
    if static is None:
        return None
    boss_id=f'fixture:{section}'
    with economy.transaction():
        service.create_boss(boss_id,static)
        service.store.db.execute('UPDATE world_boss_runs SET state=2 WHERE boss_id=?',(boss_id,))
        service.store.db.execute("INSERT OR REPLACE INTO world_boss_members(boss_id,player_id,team,active) VALUES (?,1,'[1003]',1)",(boss_id,))
        service.store.db.execute('''INSERT INTO world_boss_player_days VALUES (1,?,?,?)
            ON CONFLICT(player_id,day) DO UPDATE SET boss_id=excluded.boss_id,type_id=excluded.type_id''',
            (day(service.now()),boss_id,static['BossID']))
    return boss_id


def seed_slots(economy, slots, searches=1):
    with economy.transaction():
        state=account_state(economy.store,1,economy.clock())
        state.update(slots=slots,searches=searches)
        economy.world_boss.save(1,state)


def test_exploration_choice_chest_atomicity_retries_and_relogin(env):
    store,economy,ctx=env
    w=economy.world_boss
    answer=call(w,ctx,'C2L_WorldBossSearch')
    assert answer.values['code']==10 and answer.before_response
    assert call(w,ctx,'C2L_WorldBossSearch').values==answer.values
    assert account_state(store,1,w.now())['searches']==1
    # Native A=0 -> paid box; B=1 -> immediate alternative award.
    seed_slots(economy,[{'event':262001,'value':270001}])
    assert call(w,ctx,'C2L_WorldBossQuestSelect',{'aOrb':0},2).values['code']==10
    assert call(w,ctx,'C2L_WorldBossOpenSearchChest',number=3).values['code']==13
    assert not account_state(store,1,w.now())['slots'][0].get('done')
    p=store.get(1)
    store.save_snapshot(1,dict(p['snapshot'],crystal=100),p['revision'])
    first=call(w,ctx,'C2L_WorldBossOpenSearchChest',number=4)
    assert first.values['code']==10 and rewards(first.values['rewardData'])=={1237901:60000}
    assert store.get(1)['snapshot']['crystal']==50
    assert call(w,ctx,'C2L_WorldBossOpenSearchChest',number=4).values==first.values
    assert call(w,ctx,'C2L_WorldBossOpenSearchChest',number=5).values['code']==13
    rebuilt=EconomyService(store).world_boss
    assert account_state(store,1,rebuilt.now())['slots'][0]['done']


def test_questions_zero_based_progress_persistence_and_final_chest(env):
    store,economy,ctx=env
    w=economy.world_boss
    seed_slots(economy,[{'event':263001,'value':271007}])
    assert call(w,ctx,'C2L_WorldBossQuestSelect',{'aOrb':0}).values['code']==10
    fields,_=snapshot_fields(store,1,w.now())
    questions=SEARCH.decode(fields['WorldBossSearch'])['WorldBossQuestion']
    assert QUESTION.decode(CONTAINER.decode(questions[0])['val'])['Step']==0
    for step in range(3):
        values={'questIdx':step,'answerIdx':0}
        answer=call(w,ctx,'C2L_WorldBossLetter',values,10+step)
        assert answer.values['code']==10
        assert call(w,ctx,'C2L_WorldBossLetter',values,10+step).values==answer.values
        assert call(w,ctx,'C2L_WorldBossLetter',values,30+step).values['code']==13
    state=account_state(store,1,w.now())
    assert state['slots'][0]['done']
    with economy.transaction():
        state['searches']=5
        w.save(1,state)
    first=call(w,ctx,'C2L_WorldBossOpenSearchChest',{'slotId':-1},40)
    assert first.values['code']==10 and rewards(first.values['rewardData'])[1237918]==40
    assert call(w,ctx,'C2L_WorldBossOpenSearchChest',{'slotId':-1},41).values['code']==13
    _,daily=snapshot_fields(store,1,w.now())
    assert DAILY.decode(daily)['WorldBossSearchTimes']==6
    assert account_state(store,1,w.now()+86400)['searches']==0
    assert account_state(store,1,w.now())['final']


def test_all_reachable_event_branches_and_rewards_have_native_data(env):
    _,economy,_=env
    w=economy.world_boss
    for event in w.events.values():
        for branch in (1,2):
            kind=event[f'AnswerType{branch}']['value']
            value=event[f'AnswerParam{branch}']
            if kind==2:
                pool=[q for q in w.answers.values() if q['QaType']==value]
                assert pool,(event['EventID'],value)
                for q in pool:
                    for group in q['AnswerReward']:
                        economy.gifts([group],allow_daily_random=True)
            else:
                economy.gifts([w.boxes[value]['BoxReward']],allow_daily_random=True)


def test_boss_list_admission_socket_auth_damage_and_checkout(env):
    store,economy,ctx=env
    w=economy.world_boss
    listing=call(w,ctx,'C2L_QueryWorldBossInfo')
    assert listing.values['code']==10 and ':' in listing.values['entry']
    bosses=[INFO.decode(raw) for raw in listing.values['bossInfos']]
    assert len(bosses)==1 and bosses[0]['worldBoss']
    boss=bosses[0]
    row=economy.entry_catalog.sections[w.bosses[boss['typeId']]['StageID']]
    values=dict(request(),missionId=row['SectionID'],chapter=row['ChapterID'],sceneId=row['Maps'][0])
    battle=BattleService(store,economy)
    assert asyncio.run(battle.enter(ctx,packet(values,9))).values['result']==13
    join={'bossid':boss['bossId'],'bossGroup':boss['group'],'act':1,'typeId':boss['typeId']}
    assert call(w,ctx,'C2L_WorldBossAct',join,10).values['code']==10
    socket=DispatchContext('boss','local',SessionState('boss','session'))
    wire={'bossid':boss['bossId'],'act':1,'playerid':1,'value':[1003]}
    impostor=DispatchContext('bad','local',SessionState('bad','not-authorized'))
    assert call(w,impostor,'C2W_WorldBossAct',dict(wire,bossid=w.internal_id(boss['bossId'])),11).values['code']==13
    assert account_state(store,1,w.now())['normal_challenges']==0
    assert call(w,socket,'C2W_WorldBossAct',wire,11).values['code']==10
    assert account_state(store,1,w.now())['world_challenges']==0
    entry=asyncio.run(battle.enter(ctx,packet(values,12)))
    assert entry.values['result']==10
    assert account_state(store,1,w.now())['world_challenges']==0
    select={'bossId':boss['bossId'],'bossGroup':boss['group'],'heroList':[1003]}
    assert call(w,ctx,'C2L_WorldBossSelectHero',select,20).values['code']==10
    assert asyncio.run(battle.enter(ctx,packet(values,12))).values==entry.values
    assert asyncio.run(battle.enter(ctx,packet(values,13))).values==entry.values
    hp=w.get_boss(boss['bossId'])['hp']
    damage=dict(wire,act=3,value=[500])
    assert call(w,socket,'C2W_WorldBossAct',damage,14).values['code']==10
    assert call(w,socket,'C2W_WorldBossAct',damage,14).values['code']==10
    assert w.get_boss(boss['bossId'])['hp']==hp-500
    assert account_state(store,1,w.now())['world_challenges']==1
    # Equal native deltas on different requests must both count.
    assert call(w,socket,'C2W_WorldBossAct',damage,18).values['code']==10
    assert w.get_boss(boss['bossId'])['hp']==hp-1000
    assert call(w,socket,'C2W_WorldBossAct',dict(wire,act=3,value=[-1]),15).values['code']==13
    done=packet({'checkout':CHECKOUT.encode({'sectionId':row['SectionID'],'chapterId':row['ChapterID'],
        'success':True,'fightTime':120})},name='C2L_CheckoutMainMissionSign',request_id=16)
    settled=asyncio.run(battle.checkout(ctx,done))
    assert settled.values['result']==10
    assert asyncio.run(battle.checkout(ctx,done)).values==settled.values
    assert call(w,socket,'C2W_WorldBossAct',dict(wire,act=3,value=[600]),17).values['code']==13
    assert call(w,socket,'C2W_WorldBossAct',wire,19).values['code']==13


def test_native_boss_info_reserved_tag_and_shared_health_push(env):
    assert next(f.number for f in INFO.fields if f.name=='topPlayers')==13
    assert next(f.number for f in INFO.fields if f.name=='selfPlayer')==15
    store,economy,ctx=env
    w=economy.world_boss
    bid=admit_fixture(economy,2140101)
    class Client:
        def __init__(self):self.messages=[]
        async def send(self,message,request_id):self.messages.append(message)
    import weakref
    client=Client()
    w.clients['other']=(weakref.WeakMethod(client.send),1,bid)
    asyncio.run(w.broadcast(bid,'origin'))
    assert client.messages[0].message_name=='WorldBossInfo'
    assert client.messages[0].values['maxHp']>0


def test_empty_header_native_socket_and_death_retry_keep_one_ticket(env):
    store,economy,ctx=env
    w=economy.world_boss
    listing=call(w,ctx,'C2L_QueryWorldBossInfo')
    assert listing.before_response[0].message_name=='PlayerDataProto'
    assert 'WorldBossSearch' in listing.before_response[0].values
    boss=next(INFO.decode(raw) for raw in listing.values['bossInfos'] if INFO.decode(raw)['worldBoss'])
    bid=boss['bossId']
    join={'bossid':bid,'bossGroup':boss['group'],'act':1,'typeId':boss['typeId']}
    assert call(w,ctx,'C2L_WorldBossAct',join,2).values['code']==10
    assert call(w,ctx,'C2L_WorldBossAct',join,3).values['code']==10
    assert account_state(store,1,w.now())['world_challenges']==0
    socket=DispatchContext('native','local',SessionState('native',''))
    wire={'bossid':bid,'act':1,'playerid':1,'value':[1003,0,0]}
    joined=call(w,socket,'C2W_WorldBossAct',wire,4)
    assert joined.values['code']==10
    assert INFO.decode(joined.values['bossInfo'])['worldBoss'] is True
    assert account_state(store,1,w.now())['world_challenges']==0
    row=economy.entry_catalog.sections[w.bosses[boss['typeId']]['StageID']]
    values=dict(request(),missionId=row['SectionID'],chapter=row['ChapterID'],sceneId=row['Maps'][0])
    battle=BattleService(store,economy)
    first=asyncio.run(battle.enter(ctx,packet(values,5)))
    assert first.values['result']==10
    assert call(w,socket,'C2W_WorldBossAct',dict(wire,act=3,value=[500]),6).values['code']==10
    done=packet({'checkout':CHECKOUT.encode({'sectionId':row['SectionID'],'chapterId':row['ChapterID'],
        'success':False,'fightTime':30})},name='C2L_CheckoutMainMissionSign',request_id=7)
    assert asyncio.run(battle.checkout(ctx,done)).values['result']==10
    assert call(w,socket,'C2W_WorldBossAct',wire,8).values['code']==13
    now=w.now()
    economy.clock=lambda:now+61
    assert call(w,socket,'C2W_WorldBossAct',wire,9).values['code']==10
    second=asyncio.run(battle.enter(ctx,packet(values,10)))
    assert second.values['result']==10 and second.values!=first.values
    assert account_state(store,1,w.now())['world_challenges']==1
    member=store.db.execute('SELECT * FROM world_boss_members WHERE boss_id=? AND player_id=1',(w.internal_id(bid),)).fetchone()
    assert member['damage']==500


def test_fixed_griffon_every_day_kill_and_restart_do_not_respawn(env):
    from datetime import datetime, timezone, timedelta
    store,economy,ctx=env
    w=economy.world_boss
    monday=int(datetime(2026,9,28,12,tzinfo=timezone(timedelta(hours=8))).timestamp())
    for weekday in range(7):
        now=monday+weekday*86400
        economy.clock=lambda:now
        # Previous common Boss instances remain in storage but disappear
        # from the visible listing, including after upgrading an old save.
        with economy.transaction():
            w.create_boss(f'old-normal:{weekday}',w.bosses[2040201])
        result=call(w,ctx,'C2L_QueryWorldBossInfo',number=100+weekday)
        bosses=[INFO.decode(b) for b in result.values['bossInfos']]
        assert len(bosses)==1 and bosses[0]['typeId']==2040101
        boss=bosses[0]
        with economy.transaction():
            internal=w.internal_id(boss['bossId'])
            store.db.execute('UPDATE world_boss_runs SET state=3,hp=0 WHERE boss_id=?',(internal,))
        for hour in (13,23):
            economy.clock=lambda:now+(hour-12)*3600
            again=call(w,ctx,'C2L_QueryWorldBossInfo',number=200+weekday*2+hour)
            value=INFO.decode(again.values['bossInfos'][0])
            assert len(again.values['bossInfos'])==1
            assert value['bossId']==boss['bossId'] and value['state']==3 and value['curHp']==0
        rebuilt=EconomyService(store)
        rebuilt.clock=economy.clock
        reloaded=call(rebuilt.world_boss,ctx,'C2L_QueryWorldBossInfo',number=300+weekday)
        assert INFO.decode(reloaded.values['bossInfos'][0])['curHp']==0
        join={'bossid':boss['bossId'],'bossGroup':boss['group'],'act':1,'typeId':boss['typeId']}
        assert call(w,ctx,'C2L_WorldBossAct',join,400+weekday).values['code']==13
    assert store.db.execute('SELECT count(*) FROM world_boss_player_days WHERE player_id=1').fetchone()[0]==7


def test_battle_drop_ack_charges_once_and_migration_refunds_unstarted(env):
    store,economy,ctx=env
    w=economy.world_boss
    boss=INFO.decode(call(w,ctx,'C2L_QueryWorldBossInfo').values['bossInfos'][0])
    bid=boss['bossId']
    join={'bossid':bid,'bossGroup':boss['group'],'act':1,'typeId':boss['typeId']}
    assert call(w,ctx,'C2L_WorldBossAct',join,2).values['code']==10
    socket=DispatchContext('native','local',SessionState('native',''))
    wire={'bossid':bid,'act':1,'playerid':1,'value':[1003,0,0]}
    assert call(w,socket,'C2W_WorldBossAct',wire,3).values['code']==10
    row=economy.entry_catalog.sections[w.bosses[boss['typeId']]['StageID']]
    values=dict(request(),missionId=row['SectionID'],chapter=row['ChapterID'],sceneId=row['Maps'][0])
    battle=BattleService(store,economy)
    first=asyncio.run(battle.enter(ctx,packet(values,4)))
    assert first.values['result']==10
    assert account_state(store,1,w.now())['world_challenges']==0
    # Abandoning an entry that never loaded must not charge it, either.
    with economy.transaction():
        store.db.execute('UPDATE economy_runs SET settled=1 WHERE uuid=?',(first.values['uuid'],))
        w.finish_battle(1,first.values['uuid'],False)
    assert account_state(store,1,w.now())['world_challenges']==0
    assert call(w,socket,'C2W_WorldBossAct',wire,20).values['code']==10
    first=asyncio.run(battle.enter(ctx,packet(values,21)))
    assert first.values['result']==10
    with store.db:
        store.db.execute('UPDATE battle_entries SET created_at=0 WHERE uuid=?',(first.values['uuid'],))
    assert call(w,socket,'C2W_WorldBossAct',wire,22).values['code']==10
    renewed=asyncio.run(battle.enter(ctx,packet(values,23)))
    assert renewed.values['result']==10 and renewed.values['uuid']!=first.values['uuid']
    assert account_state(store,1,w.now())['world_challenges']==0
    # Simulate the previous release consuming a ticket on 421, but never
    # receiving a 264/damage/887. Constructor migration uses code, not SQL
    # intervention in the active save.
    with store.db:
        store.db.execute('UPDATE world_boss_members SET charged=1')
        store.db.execute('ALTER TABLE world_boss_members DROP COLUMN combat_confirmed')
    rebuilt=EconomyService(store)
    assert account_state(store,1,rebuilt.world_boss.now())['world_challenges']==0
    report=packet({'missionId':row['SectionID'],'chapterId':row['ChapterID'],'sceneId':row['Maps'][0]},
        name='C2L_FightDropData',request_id=5)
    response=asyncio.run(battle.drop_data(ctx,report))
    assert response.values['result']==10 and response.before_response
    assert account_state(store,1,w.now())['world_challenges']==1
    assert asyncio.run(battle.drop_data(ctx,report)).values['result']==10
    assert account_state(store,1,w.now())['world_challenges']==1
    with store.db:
        store.db.execute('ALTER TABLE world_boss_members DROP COLUMN combat_confirmed')
    EconomyService(store)
    assert account_state(store,1,w.now())['world_challenges']==1


def test_boss_rank_mail_uses_native_gifts_once_after_kill_or_timeout(env):
    store,economy,_=env
    w=economy.world_boss
    bid=admit_fixture(economy,2140101)
    with economy.transaction():
        store.db.execute('UPDATE world_boss_members SET damage=500 WHERE boss_id=?',(bid,))
        store.db.execute('UPDATE world_boss_runs SET hp=0,state=3 WHERE boss_id=?',(bid,))
        w.get_boss(bid)
        w.get_boss(bid)
    row=store.db.execute('SELECT * FROM player_mail WHERE source_key=?',(f'worldboss:{bid}:rank',)).fetchone()
    assert row and store.db.execute('SELECT count(*) FROM player_mail').fetchone()[0]==1
    template=w.mail_templates[w.bosses[2040101]['ChallengeReward'][0]]
    assert {int(i):n for i,n in json.loads(row['attachments']).items()}==economy.gifts([template['gift']],allow_daily_random=True)
    from x2server.player.mail import MailService
    mail=MailService(store,economy)
    claimed=mail._claim(1,[row['id']])
    assert claimed
    before=store.get(1)['snapshot']
    assert mail._claim(1,[row['id']]) is None
    assert store.get(1)['snapshot']==before
    rebuilt=EconomyService(store).world_boss
    with economy.transaction():rebuilt.get_boss(bid)
    assert store.db.execute('SELECT count(*) FROM player_mail').fetchone()[0]==1
    other=admit_fixture(economy,2140201)
    with economy.transaction():
        store.db.execute('UPDATE world_boss_members SET damage=500 WHERE boss_id=?',(other,))
        store.db.execute('UPDATE world_boss_runs SET finish=0 WHERE boss_id=?',(other,))
        assert w.get_boss(other)['state']==4
    assert store.db.execute('SELECT count(*) FROM player_mail').fetchone()[0]==2


def test_personal_radar_discovery_damage_death_and_ownership(env):
    store,economy,ctx=env
    w=economy.world_boss
    p=store.login('second-player',2,0)
    store.save_snapshot(2,dict(store.get(1)['snapshot'],nickname='second-player'),p['revision'])
    other=DispatchContext('second','local',SessionState('second','session2',player_id=2))
    first=call(w,ctx,'C2L_QueryWorldBossInfo')
    second=call(w,other,'C2L_QueryWorldBossInfo')
    a=INFO.decode(first.values['bossInfos'][0])
    b=INFO.decode(second.values['bossInfos'][0])
    assert a['typeId']==b['typeId'] and a['bossId']!=b['bossId']
    search=SEARCH.decode(first.before_response[0].values['WorldBossSearch'])
    slot=CONTAINER.decode(search['Slots'][0])
    assert SLOT.decode(slot['val'])['Event']==260001
    discovered=BOSS.decode(CONTAINER.decode(search['WorldBoss'][0])['val'])
    assert discovered['BossID']==a['bossId'] and discovered['ID']==a['typeId']
    assert account_state(store,1,w.now())['searches']==0
    assert not call(w,ctx,'C2L_QueryWorldBossInfo',number=8).before_response
    join={'bossid':a['bossId'],'bossGroup':a['group'],'act':1,'typeId':a['typeId']}
    assert call(w,other,'C2L_WorldBossAct',join,2).values['code']==13
    assert call(w,other,'C2L_QueryWorldBossInfo',{'bossId':a['bossId'],'bossGroup':a['group']},3).values['code']==13
    assert call(w,ctx,'C2L_WorldBossAct',join,2).values['code']==10
    socket=DispatchContext('native','local',SessionState('native',''))
    wire={'bossid':a['bossId'],'act':1,'playerid':1,'value':[1003,0,0]}
    assert call(w,socket,'C2W_WorldBossAct',wire,3).values['code']==10
    row=economy.entry_catalog.sections[w.bosses[a['typeId']]['StageID']]
    battle=BattleService(store,economy)
    values=dict(request(),missionId=row['SectionID'],chapter=row['ChapterID'],sceneId=row['Maps'][0])
    assert asyncio.run(battle.enter(ctx,packet(values,4))).values['result']==10
    assert call(w,socket,'C2W_WorldBossAct',dict(wire,act=3,value=[a['maxHp']]),5).values['code']==10
    assert w.get_boss(a['bossId'])['hp']==0 and w.get_boss(a['bossId'])['state']==3
    assert w.get_boss(b['bossId'])['hp']==b['maxHp'] and w.get_boss(b['bossId'])['state']==1
    assert account_state(store,1,w.now())['world_challenges']==1
    assert account_state(store,2,w.now())['world_challenges']==0
    rebuilt=EconomyService(store).world_boss
    again=call(rebuilt,ctx,'C2L_QueryWorldBossInfo',number=6)
    assert INFO.decode(again.values['bossInfos'][0])['curHp']==0
    dead_slot=SLOT.decode(CONTAINER.decode(SEARCH.decode(again.before_response[0].values['WorldBossSearch'])['Slots'][0])['val'])
    assert dead_slot['Event']==0
    assert call(rebuilt,ctx,'C2L_WorldBossAct',join,7).values['code']==13


def test_first_search_discovers_one_boss_and_preserves_other_slot_indices(env):
    store,economy,ctx=env
    w=economy.world_boss
    seed_slots(economy,[{'event':262001,'value':270001}],searches=0)
    found=call(w,ctx,'C2L_WorldBossSearch')
    assert found.values['bossEvent']==260001 and found.values['slotIdx']==1
    assert found.values['bossId']
    assert call(w,ctx,'C2L_WorldBossSearch').values==found.values
    state=account_state(store,1,w.now())
    assert state['searches']==1 and state['slots'][0]['value']==270001
    call(w,ctx,'C2L_QueryWorldBossInfo',number=2)
    assert account_state(store,1,w.now())['slots']==state['slots']


def test_shared_save_upgrade_preserves_only_own_damage(env):
    store,economy,ctx=env
    w=economy.world_boss
    static=w.bosses[w.policy['daily_boss_id']]
    old=f'world:{day(w.now())}:{static["BossID"]}'
    with economy.transaction():
        w.create_boss(old,static)
        maximum=w.get_boss(old)['max_hp']
        store.db.execute('UPDATE world_boss_runs SET state=3,hp=0 WHERE boss_id=?',(old,))
        store.db.execute('''INSERT INTO world_boss_members
            (boss_id,player_id,team,damage,charged,combat_confirmed) VALUES (?,1,'[1003]',500,1,1)''',(old,))
    listed=call(w,ctx,'C2L_QueryWorldBossInfo')
    personal=INFO.decode(listed.values['bossInfos'][0])
    assert personal['curHp']==personal['maxHp']-500 and personal['state']==1
    member=store.db.execute('SELECT * FROM world_boss_members WHERE boss_id=? AND player_id=1',(w.internal_id(personal['bossId']),)).fetchone()
    assert member['damage']==500 and member['charged']==1
    assert store.db.execute('SELECT charged FROM world_boss_members WHERE boss_id=?',(old,)).fetchone()[0]==0
    assert account_state(store,1,w.now())['world_challenges']==1


@pytest.mark.parametrize('player_level,boss_level,hp', [
    (1,10,1305105), (29,10,1305105), (30,30,6087985),
    (35,30,6087985), (46,40,10020000), (60,60,29225000),
    (99,90,87675000), (100,100,121075000), (150,100,121075000)])
def test_personal_level_hp_and_battle_entry(env, player_level, boss_level, hp):
    store,economy,ctx=env
    p=store.get(1)
    store.save_snapshot(1,dict(p['snapshot'],level=player_level),p['revision'])
    w=economy.world_boss
    with economy.transaction():
        bid=w.public_bosses(1)
        boss=w.get_boss(bid)
        assert boss['max_hp']==boss['hp']==hp
        assert w.info(boss,1)['level']==boss_level
        store.db.execute('UPDATE world_boss_runs SET state=2 WHERE boss_id=?',(bid,))
        store.db.execute("INSERT INTO world_boss_members(boss_id,player_id,team,active) VALUES (?,1,'[1003]',1)",(bid,))
    row=economy.entry_catalog.sections[w.bosses[boss['type_id']]['StageID']]
    values=dict(request(),missionId=row['SectionID'],chapter=row['ChapterID'],sceneId=row['Maps'][0])
    response=asyncio.run(BattleService(store,economy).enter(ctx,packet(values,4)))
    if player_level < w.activity['OpenLever']:
        assert response.values['result']==13  # Preserve the activity unlock gate.
        return
    assert response.values['result']==10
    assert response.values['monsterInitLevel']==boss_level
    rebuilt=EconomyService(store).world_boss
    assert rebuilt.get_boss(bid)['monster_level']==boss_level
    assert rebuilt.get_boss(bid)['max_hp']==hp


def test_level_upgrade_keeps_damage_and_dead_boss(env):
    store,economy,ctx=env
    w=economy.world_boss
    with economy.transaction():
        bid=w.public_bosses(1)
        store.db.execute('UPDATE world_boss_runs SET hp=max_hp-500 WHERE boss_id=?',(bid,))
    p=store.get(1)
    store.save_snapshot(1,dict(p['snapshot'],level=100),p['revision'])
    with economy.transaction():
        w.public_bosses(1)
        boss=w.get_boss(bid)
        assert boss['max_hp']==121075000 and boss['hp']==121074500
        store.db.execute('UPDATE world_boss_runs SET hp=0,state=3 WHERE boss_id=?',(bid,))
        w.public_bosses(1)
        assert w.get_boss(bid)['hp']==0
