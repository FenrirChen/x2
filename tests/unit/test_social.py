import asyncio
import json

import pytest

from x2server.player.social import SocialService,roster,day,PERIOD,NAMESPACE,snapshot_value,npc_id
from x2server.player.college import CollegeStateRepository
from x2server.player.server_clock import ServerClock
from x2server.player.economy import UnresolvedEconomy
from x2server.messages.social import FRIEND_DATA,INT_LONG
from x2server.messages.college import HELP_POWER_SPEED_PARAM
from x2server.messages.core import PLAYER_DATA
from x2server.player.login import LoginService
from tests.unit.test_economy import env
from tests.unit.test_battle import packet


@pytest.fixture
def social(env):
    store,economy,ctx=env
    stamp=[1791979200]
    economy.clock=lambda:stamp[0]
    college=CollegeStateRepository(store,ServerClock(lambda:stamp[0]))
    service=SocialService(store,economy,college,chooser=lambda values:values[0])
    economy.social=service
    yield service,ctx,stamp


def act(s,ctx,flow,req=None,request_id=1):
    req=dict(req or {})
    for field in ('applyId','optedId','wishingId','donateId'):
        if req.get(field) in s.characters:
            req[field]=npc_id(ctx.session.player_id,req[field])
    if req.get('playerid'):
        req['playerid']=[npc_id(ctx.session.player_id,n) for n in req['playerid']]
    if req.get('helpPowerSpeedParam'):
        rows=[]
        for raw in req['helpPowerSpeedParam']:
            p=HELP_POWER_SPEED_PARAM.decode(raw)
            p['playerIded']=npc_id(ctx.session.player_id,p['playerIded'])
            rows.append(HELP_POWER_SPEED_PARAM.encode(p))
        req['helpPowerSpeedParam']=rows
    return asyncio.run(s.handle(ctx,packet(req,request_id,'C2L_'+flow)))


def create(s,ctx):
    assert act(s,ctx,'CreateClub',{'name':'solo','clubIconId':1270004}).values['code']==10
    target=roster()[0]['id']
    assert act(s,ctx,'ClubApproval',{'applyId':target,'opt':1},2).values['code']==10
    return target


def fund(s,item,num):
    with s.economy.transaction():
        s.economy._grant(1,f'test:{item}:{num}',{item:num})


def test_default_all_official_characters_no_write_on_read(social):
    s,ctx,_=social
    before=s.store.db.total_changes
    data=s.http('/FriendService.GetFriendList',{},1)['Friends']
    assert len(data['Friends'])==39
    assert len({r['Friendid'] for r in data['Friends']})==39
    assert all(int(r['Friendid'])>700000000 for r in data['Friends'])
    assert data['Applys'] is None
    assert s.store.db.total_changes==before
    assert s.http('/ClubService.GetClub',{},1)['Club']['Id']==0


def test_create_invite_refuse_kick_quit_not_auto_recreated(social):
    s,ctx,_=social
    target=create(s,ctx)
    data=s.http('/ClubService.GetClub',{},1)['Club']
    assert data['Owner']=='1' and len(data['MemberList'])==2
    assert all(r['Userid']!=str(npc_id(1,target)) for r in data['ApplyList'])
    other=roster()[1]['id']
    assert act(s,ctx,'ClubApproval',{'applyId':other,'opt':2},3).values['code']==10
    assert all(r['Userid']!=str(npc_id(1,other)) for r in s.http('/ClubService.GetClub',{},1)['Club']['ApplyList'])
    assert act(s,ctx,'UpdateMemberPrivilege',{'optedId':target,'opt':3},4).values['code']==13
    assert act(s,ctx,'DismissMember',{'optedId':target},5).values['code']==10
    assert act(s,ctx,'QuitClub',{'postId':3},6).values['code']==10
    assert s.http('/ClubService.GetClub',{},1)['Club']['Id']==0
    assert act(s,ctx,'CreateClub',{'name':'new'},7).values['code']==10


def test_coin_receive_retries_and_midnight_and_cap(social):
    s,ctx,stamp=social
    ids=[r['id'] for r in roster()]
    result=act(s,ctx,'ReceiveFriendCoin',{'playerid':ids,'friendPoint':[999]*39})
    assert result.values['code']==10 and len(result.values['playerid'])==15
    assert s.quantity(1,1237917)==300
    assert act(s,ctx,'ReceiveFriendCoin',{'playerid':ids,'friendPoint':[999]*39}).values==result.values
    assert s.quantity(1,1237917)==300
    assert act(s,ctx,'ReceiveFriendCoin',{'playerid':ids},2).values['code']==193
    stamp[0]+=86400
    assert act(s,ctx,'ReceiveFriendCoin',{'playerid':ids},3).values['code']==10
    assert s.quantity(1,1237917)==600
    fund(s,1237917,4395)
    assert act(s,ctx,'SendFriendCoin',{'playerid':[ids[0]]},4).values['code']==10
    assert s.quantity(1,1237917)==5000
    assert act(s,ctx,'SendFriendCoin',{'playerid':[ids[1]]},5).values['code']==10
    assert s.quantity(1,1237917)==5000


def test_friend_state_in_login_snapshot_and_same_id_conflict(social):
    s,ctx,_=social
    target=roster()[0]['id']
    act(s,ctx,'SendFriendCoin',{'playerid':[target]})
    assert act(s,ctx,'SendFriendCoin',{'playerid':[roster()[1]['id']]}).values['code']==13
    wire=LoginService.snapshot_push(s.store.get(1),s.store,now=s.clock()).values
    friends=FRIEND_DATA.decode(wire['FriendData'])
    assert friends['SendCount']==1
    assert INT_LONG.decode(friends['SendPlayer'][0])['val']==npc_id(1,target)
    assert PLAYER_DATA.decode(PLAYER_DATA.encode(wire))['FriendData']==wire['FriendData']


def test_single_random_member_donates_only_once(social):
    s,ctx,_=social
    target=create(s,ctx)
    fund(s,1237901,100000)
    fund(s,1201003,1)
    before=s.quantity(1,1201003)
    result=act(s,ctx,'ClubWishing',{'itemId':1201003},3)
    assert result.values['code']==10
    w=s.state(1)['wishes'][0]
    assert len(w['donors'])==1 and w['donors'][0]['uid']==target
    assert s.quantity(1,1201003)==before
    receipt=act(s,ctx,'ClubWishingReceive',{'donateId':target,'time':w['time']},4)
    assert receipt.values['code']==10
    assert s.quantity(1,1201003)==before+w['num']
    assert act(s,ctx,'ClubWishingReceive',{'donateId':target,'time':w['time']},4).values==receipt.values
    assert act(s,ctx,'ClubWishingReceive',{'donateId':target,'time':w['time']},5).values['code']==13


def test_wish_atomic_insufficient_and_no_members(social):
    s,ctx,_=social
    assert act(s,ctx,'CreateClub',{'name':'solo'}).values['code']==10
    assert act(s,ctx,'ClubWishing',{'itemId':1201003},2).values['code']==13
    act(s,ctx,'ClubApproval',{'applyId':roster()[0]['id'],'opt':1},3)
    fund(s,1201003,1)
    assert act(s,ctx,'ClubWishing',{'itemId':1201003},4).values['code']==13
    assert not s.state(1)['wishes']


def test_npc_wish_exact_material_quantity_and_no_overdonation(social):
    s,ctx,_=social
    target=create(s,ctx)
    fund(s,1201003,3)
    page=s.http('/ClubService.GetWishingPage',{},1)
    assert page['Total']==1
    w=s.state(1)['wishes'][0]
    for i in range(w['num']):
        reply=act(s,ctx,'ClubWishingDonate',{'wishingId':target,'wishingTime':w['time']},i+3)
        assert reply.values['code']==10
    assert s.quantity(1,1201003)==3-w['num']
    assert act(s,ctx,'ClubWishingDonate',{'wishingId':target,'wishingTime':w['time']},20).values['code']==13
    assert s.http('/ClubService.GetWishingPage',{},1)['Total']==1


def test_npc_wish_donation_accepts_client_zero_time(social):
    # The real client always sends wishingTime=0 (captured C2L_ClubWishingDonate
    # body 08eb071000 = wishingId 1003, wishingTime 0), so the donate lookup must
    # not require an exact wish-row time match.
    s,ctx,_=social
    target=create(s,ctx)
    fund(s,1201003,3)
    assert s.http('/ClubService.GetWishingPage',{},1)['Total']==1
    w=s.state(1)['wishes'][0]
    reply=act(s,ctx,'ClubWishingDonate',{'wishingId':target,'wishingTime':0},3)
    assert reply.values['code']==10
    assert s.quantity(1,w['item'])==2


def test_help_validates_members_and_does_not_repeat(social):
    s,ctx,_=social
    target=create(s,ctx)
    base=s.college.load(1)
    row=next(r for r in base['buildings'] if r['buildingId']==701)
    base['build_queue']=dict(buildingId=701,upgradeStartTime=s.clock(),
        upgradeEndTime=s.clock()+3600,target_level=row['buildingLevel']+1)
    with s.economy.transaction():
        s.college.save(1,base)
    req=dict(helpPower=1,helpPowerSpeedParam=[HELP_POWER_SPEED_PARAM.encode(dict(playerIded=target,buildingId=701,buildingLevel=1))])
    result=act(s,ctx,'HelpPowerSpeed',req,3)
    assert result.values['code']==10
    assert s.college.load(1)['build_queue']['upgradeEndTime']==s.clock()+3540
    act(s,ctx,'HelpPowerSpeed',req,3)
    assert s.college.load(1)['build_queue']['upgradeEndTime']==s.clock()+3540
    assert act(s,ctx,'HelpPowerSpeed',req,4).values['code']==13
    req['helpPowerSpeedParam']=[HELP_POWER_SPEED_PARAM.encode(dict(playerIded=roster()[1]['id'],buildingId=701,buildingLevel=1))]
    assert act(s,ctx,'HelpPowerSpeed',req,5).values['code']==13


def test_account_isolation_and_migrated_owner_derived(social):
    s,ctx,_=social
    create(s,ctx)
    s.store.login('second',2,0)
    assert s.http('/ClubService.GetClub',{},2)['Club']['Id']==0
    with s.economy.transaction():
        s.save(2,s.state(1))
    data=s.http('/ClubService.GetClub',{},2)['Club']
    assert data['Id']==s.club_id(2) and data['Owner']=='2'
    assert data['MemberList'][0]['Userid']=='2'
    with pytest.raises(ValueError):
        s.http('/ClubService.GetClub',{'id':s.club_id(1)},2)


def test_mirror_attempts_and_reward_eligibility(social):
    s,ctx,stamp=social
    create(s,ctx)
    for i in range(3):
        with s.economy.transaction():
            s.bind_run(1,2170001,str(i))
    with pytest.raises(UnresolvedEconomy):
        s.admission(1,2170001)
    assert act(s,ctx,'ClubReceiveReward',{'opt':0,'param':2070001},3).values['code']==13
    with s.economy.transaction():
        s.completed(1,2170001,True,run='2')
    assert act(s,ctx,'ClubReceiveReward',{'opt':0,'param':2070001},4).values['code']==10
    assert act(s,ctx,'ClubReceiveReward',{'opt':0,'param':2070001},5).values['code']==13
    stamp[0]+=86400
    assert s.state(1)['mirror']['count']==3


def test_http_bridge_native_bare_bearer_and_token_binding(social):
    from types import SimpleNamespace
    from x2server.bootstrap.social_api import SocialAPI
    s,ctx,_=social
    target=create(s,ctx)
    identity=SimpleNamespace(contract=SimpleNamespace(web_config=SimpleNamespace(service_app_id='app')),
        _accounts=SimpleNamespace(get_by_player=lambda pid: {'status':'active','player_id':pid} if pid==1 else None),
        _mail_player_for_token=lambda token: 1 if token=='valid' else None)
    async def scenario():
        api=SocialAPI(identity,s,asyncio.get_running_loop())
        async def post(path,args,auth='Bearer'):
            reply=await asyncio.to_thread(api.respond,'POST',path,json.dumps({'appid':'app',**args}).encode(),auth)
            return reply,json.loads(reply.body)
        reply,body=await post('/FriendService.GetFriendList',{'userid':'1'})
        assert body['code']==0 and len(body['data']['Friends']['Friends'])==39
        reply,body=await post('/ClubService.GetClubMember',{'member':str(npc_id(1,target))})
        assert body['data']['Id']==s.club_id(1)
        reply,body=await post('/ClubService.GetClub',{'userid':'2'},'Bearer valid')
        assert reply.status==403
        reply,body=await post('/ClubService.GetClub',{'userid':'1'},'Bearer expired')
        assert reply.status==401
        reply,body=await post('/ClubService.GetClub',{'userid':'1'},'')
        assert reply.status==401
        ids=[str(npc_id(1,target))]
        reply,body=await post('/AttribService.GetAttrib',{'users':ids})
        assert body['data']['AttribList'][0]['Uid']==ids[0]
        reply,body=await post('/KVStoreService.GetValuesV2',{'users':ids,'keys':[f'club_speed_{ids[0]}_1']})
        assert body['data']['Pairs'][0]['pairs'][0]['key']==f'club_speed_{ids[0]}_1'
    asyncio.run(scenario())


def test_npc_cards_and_outgoing_identity_follow_save_owner(social):
    s,ctx,_=social
    target=create(s,ctx)
    a=s.http('/apply/queryPlayer',{'players':[npc_id(1,target)]},None)[0]
    assert a['roleID']==npc_id(1,target)
    assert a['assistHero']['id']==roster()[0]['hero']
    s.store.login('second',2,0)
    with s.economy.transaction():
        s.save(2,s.state(1))
    b=s.http('/ClubService.GetClub',{},2)['Club']
    assert b['MemberList'][1]['Userid']==str(npc_id(2,target))
    with pytest.raises(ValueError):
        s.http('/ClubService.GetClubMember',{'member':npc_id(1,target)},2)


def test_state_persisted_and_save_boundary_includes_social(social):
    from x2server.player.save_manager import SaveManager,PLAYER_TABLES
    s,ctx,_=social
    create(s,ctx)
    assert {'activity_state','activity_receipts'}<=set(PLAYER_TABLES)
    # Save manager's schema boundary must accept the social implementation
    # without a private unexported table or global NPC-membership table.
    manager=SaveManager(s.store)
    manager._check_boundary()
    assert SocialService(s.store,s.economy,s.college).state(1)['club']['name']=='solo'
    manager.close()


def test_real_complete_export_import_remaps_npc_identity(social,tmp_path):
    from x2server.player.save_manager import SaveManager
    from tests.unit.test_save_manager import build_full_schema
    s,ctx,_=social
    target=create(s,ctx)
    act(s,ctx,'SendFriendCoin',{'playerid':[target]},3)
    build_full_schema(s.store)
    s.store.login('second',2,0)
    manager=SaveManager(s.store,backup_root=tmp_path/'import_backup')
    archive=manager.export_save(1)
    parsed=manager.parse_save(archive)
    assert any(r['namespace']==NAMESPACE for r in parsed.rows['activity_state'])
    manager.import_save(2,archive)
    data=s.http('/ClubService.GetClub',{},2)['Club']
    assert data['Owner']=='2' and data['MemberList'][1]['Userid']==str(npc_id(2,target))
    assert s.state(2)['sent']==[target]
    assert s.quantity(2,1237917)==20
    assert s.http('/apply/queryPlayer',{'players':[npc_id(2,target)]},2)[0]['showCardBase']['sendCoinPlayers']==[2]
    manager.close()


@pytest.mark.parametrize('opt,req,field,expected',[(1,{'name':'changed'},'name','changed'),
    (2,{'clubIconId':1270004},'icon',1270004),(3,{'notice':'hello'},'notice','hello')])
def test_native_club_edit_options(social,opt,req,field,expected):
    s,ctx,_=social
    create(s,ctx)
    assert act(s,ctx,'UpdateClubInfo',{'opt':opt,**req},3).values['code']==10
    assert s.state(1)['club'][field]==expected


def test_friend_support_ignores_forged_stats_and_rejects_foreign_npc(social):
    from x2server.messages.social import ASSIST_DATA
    from x2server.messages.battle import FIGHT_HERO,HERO_ATTR
    s,ctx,_=social
    target=roster()[0]['id']
    raw=ASSIST_DATA.encode(dict(assistPlayerID=npc_id(1,target),heroID=1003,heroLevel=120,heroStar=46,heroPower=999999))
    data=ASSIST_DATA.decode(s.assist(1,raw,{'AssistType':{'value':2}}))
    hero=FIGHT_HERO.decode(data['battleData'])
    assert hero['level']==60 and hero['star']==1
    assert HERO_ATTR.decode(hero['heroAttrCount'])['atk']>0
    with pytest.raises(ValueError):
        s.assist(2,raw,{'AssistType':{'value':2}})
    with pytest.raises(ValueError):
        s.assist(1,raw,{'AssistType':{'value':1}})


def test_friend_support_complete_battle_entry_and_replay(social):
    from x2server.messages.social import ASSIST_DATA
    from x2server.messages.battle import PROFILE_HERO,BATTLE_SCHEMAS
    from x2server.player.battle import BattleService
    s,ctx,_=social
    target=roster()[1]
    req=dict(missionId=2110101,chapter=2010200,sceneId=2210101,
        heros=[PROFILE_HERO.encode({'heroId':1003,'leader':1})],
        assistData=ASSIST_DATA.encode({'assistPlayerID':npc_id(1,target['id']),'heroID':target['hero'],'heroPower':999999}))
    service=BattleService(s.store,s.economy)
    result=asyncio.run(service.enter(ctx,packet(req,50)))
    assert result.values['result']==10
    assert ASSIST_DATA.decode(result.values['assistData'])['heroID']==target['hero']
    assert BATTLE_SCHEMAS['L2C_FightData'].decode(BATTLE_SCHEMAS['L2C_FightData'].encode(result.values))['assistData']==result.values['assistData']
    replay=asyncio.run(service.enter(ctx,packet(req,50)))
    assert replay.values==result.values
    assert [h['id'] for h in s.store.get(1)['snapshot']['heroes']]==[1003]


def test_approval_native_reserved_field_and_wish_closed_loop(social):
    from dataclasses import replace
    from x2server.protocol.protobuf import encode_varint
    s,ctx,_=social
    act(s,ctx,'CreateClub',{'name':'native'})
    target=roster()[0]['id']
    # Independent native wire fixture: field 2 is absent, opt=1 is field 3.
    body=b'\x08'+encode_varint(npc_id(1,target))+b'\x18\x01'
    p=replace(packet({},2,'C2L_ClubApproval'),body=body)
    reply=asyncio.run(s.handle(ctx,p))
    assert reply.values['code']==10
    assert str(target) in s.state(1)['club']['members']
    fund(s,1201003,1)
    fund(s,1237901,10000)
    assert act(s,ctx,'ClubWishing',{'itemId':1201003},3).values['code']==10
    assert act(s,ctx,'ClubWishingReceive',{'donateId':target},4).values['code']==10
    assert s.quantity(1,1201003)==4
    assert act(s,ctx,'ClubWishingReceive',{'donateId':target},5).values['code']==13


def test_club_and_attribute_http_use_each_characters_real_icon(social):
    s,ctx,_=social
    create(s,ctx)
    club=s.http('/ClubService.GetClub',{},1)['Club']
    candidates=club['ApplyList']
    for row in candidates:
        canonical=700000000+(int(row['Userid'])-700000000000)%10000
        assert row['Attrib']['Ext']['iconID']==str(s.characters[canonical]['head'])
        assert row['Attrib']['Ext']['firstMedal']=='0'
    assert len({row['Attrib']['Ext']['iconID'] for row in candidates})>1
    attrs=s.http('/AttribService.GetAttrib',{'users':[r['Userid'] for r in candidates]},None)['AttribList']
    assert [r['Ext']['iconID'] for r in attrs]==[r['Attrib']['Ext']['iconID'] for r in candidates]


def test_friend_reset_at_midnight_and_all_npcs_send(social):
    from datetime import datetime,timedelta,timezone
    s,ctx,stamp=social
    def at(d,h,m=0):
        return int(datetime(2026,10,d,h,m,tzinfo=timezone(timedelta(hours=8))).timestamp())
    stamp[0]=at(14,23)
    target=roster()[0]['id']
    assert act(s,ctx,'ReceiveFriendCoin',{'playerid':[target]}).values['code']==10
    stamp[0]=at(14,23,59)
    assert s.state(1)['received']==[target]
    assert act(s,ctx,'ReceiveFriendCoin',{'playerid':[target]},2).values['code']==192
    assert s.refresh_friends(1) is None
    stamp[0]=at(15,0)
    push=s.refresh_friends(1)
    assert FRIEND_DATA.decode(push.values['FriendData'])['ReceiveCount']==0
    assert s.refresh_friends(1) is None
    rows=s.http('/FriendService.GetFriendList',{},1)['Friends']['Friends']
    assert len(rows)==39 and all(row['Values'][0]['Value']['VInt64']==1 for row in rows)
    assert act(s,ctx,'ReceiveFriendCoin',{'playerid':[target]},3).values['code']==10
    assert s.quantity(1,1237917)==40


def test_legacy_imported_and_other_grant_friend_points_are_capped(social):
    s,ctx,_=social
    with s.economy.transaction():
        s.store.db.execute('INSERT INTO inventory VALUES (1,1237917,9000)')
    wire=LoginService.snapshot_push(s.store.get(1),s.store,now=s.clock())
    assert s.quantity(1,1237917)==5000
    target=roster()[0]['id']
    assert act(s,ctx,'SendFriendCoin',{'playerid':[target]}).values['code']==10
    assert s.quantity(1,1237917)==5000
    assert act(s,ctx,'ReceiveFriendCoin',{'playerid':[target]},2).values['code']==252
    assert not s.state(1)['received']
    with s.economy.transaction():
        s.store.db.execute('UPDATE inventory SET quantity=4995 WHERE item_id=1237917')
        reward=s.economy._grant(1,'mail:cap-regression',{1237917:100})
    assert reward=={1237917:5} and s.quantity(1,1237917)==5000


def test_legacy_daily_claim_migration_preserves_today_but_resets_yesterday(social):
    s,ctx,stamp=social
    target=roster()[0]['id']
    state=s.state(1)
    state.pop('friend_day')
    state.update(sent=[target],received=[target])
    with s.economy.transaction():
        s.save(1,state)
    assert s.state(1)['received']==[target]
    state['day']-=1
    with s.economy.transaction():
        s.save(1,state)
    assert not s.state(1)['received'] and not s.state(1)['sent']
