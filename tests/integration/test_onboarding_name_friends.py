import asyncio
import json
from urllib.parse import urlencode

from tests.integration.test_local_registration import AccountFlow
from tests.unit.test_battle import packet
from x2server.bootstrap.social_api import SocialAPI
from x2server.messages.core import BASE_INFO
from x2server.messages.battle import PROFILE_HERO
from x2server.messages.social import FRIEND_DATA, LONG_INT
from x2server.network.dispatcher import DispatchContext
from x2server.network.session import SessionState
from x2server.player.appearance import AppearanceService
from x2server.player.battle import BattleService
from x2server.player.economy import EconomyService
from x2server.player.login import LoginService
from x2server.player.social import SocialService, npc_owner


def base(store, pid):
    return BASE_INFO.decode(LoginService.snapshot_push(store.get(pid), store).values['BaseInfo'])


def test_first_name_marker_before_reply_restart_battle_and_plot_replay(tmp_path):
    flow = AccountFlow(tmp_path)
    try:
        assert flow.register('new-named', 'test-password') == {'success': True}
        _, identity = flow.game_session('new-named', 'test-password')
        pid = identity['playerID']
        e = EconomyService(flow.store)
        a = AppearanceService(flow.store, e)
        b = BattleService(flow.store, e)
        ctx = DispatchContext('test', 'local', SessionState('test', 'session', player_id=pid))
        assert base(flow.store, pid)['NickCount'] == 0
        enter = {'missionId':2110001, 'chapter':2010000, 'sceneId':2210001,
                 'heros':[PROFILE_HERO.encode({'heroId':1003,'leader':1})]}
        assert asyncio.run(b.enter(ctx, packet(enter, 1))).values['result'] == 10
        name = packet({'opt':7,'strvals':['首次名字']}, 2, 'C2L_Account')
        answer = asyncio.run(a.handle(ctx, name))
        assert answer.values == {'result':10, 'opt':7}
        updated = BASE_INFO.decode(answer.before_response[0].values['BaseInfo'])
        assert updated['NickCount'] == 1 and updated['NickName'] == '首次名字'
        saved = flow.store.get(pid)
        assert saved['snapshot']['nick_count'] == 1
        assert asyncio.run(a.handle(ctx, name)).values == answer.values
        assert flow.store.get(pid) == saved
        # Abandoning/restarting the prologue cannot reset the naming marker.
        assert asyncio.run(b.enter(ctx, packet(enter, 3))).values['result'] == 10
        assert base(flow.store,pid)['NickCount'] == 1
        snapshot = flow.store.get(pid)['snapshot']
        denied = asyncio.run(a.handle(ctx, packet({'opt':7,'strvals':['剧情免费改名']}, 4, 'C2L_Account')))
        assert denied.values['result'] == 13
        assert flow.store.get(pid)['snapshot'] == snapshot
        assert base(flow.store,pid)['NickName'] == '首次名字'
        flow.accounts.close()
        flow.store.close()
        flow = AccountFlow(tmp_path)
        _, again = flow.game_session('new-named','test-password')
        assert again['playerID'] == pid
        assert base(flow.store,pid)['NickCount'] == 1
        assert base(flow.store,pid)['NickName'] == '首次名字'
    finally:
        flow.accounts.close()
        flow.store.close()


def test_old_named_snapshot_import_keeps_named_flag_without_counter(tmp_path):
    from tests.unit.test_save_manager import make_env, build_full_schema
    store, accounts, manager = make_env(tmp_path)
    try:
        build_full_schema(store)
        accounts.create('named-old','test-password',100)
        accounts.create('named-new','test-password',101)
        source = accounts.get_by_name('named-old')['player_id']
        target = accounts.get_by_name('named-new')['player_id']
        p = store.get(source)
        p['snapshot']['nickname'] = '已有昵称'
        p['snapshot'].pop('nick_count',None)
        store.save_snapshot(source,p['snapshot'],p['revision'])
        assert base(store,source)['NickCount'] == 1
        manager.import_save(target,manager.export_save(source))
        assert base(store,target)['NickCount'] == 1
        ctx = DispatchContext('test','local',SessionState('test','session',player_id=target))
        a = AppearanceService(store,EconomyService(store))
        assert asyncio.run(a.handle(ctx,packet({'opt':7,'strvals':['重播改名']},1,'C2L_Account'))).values['result'] == 13
        assert base(store,target)['NickName'] == '已有昵称'
    finally:
        manager.close()
        store.close()


def test_registration_friend_v1_card_lookup_tcp_sync_and_v2_contract(tmp_path):
    flow = AccountFlow(tmp_path)
    try:
        flow.register('friend-new','test-password')
        _, login = flow.game_session('friend-new','test-password')
        pid = login['playerID']
        e = EconomyService(flow.store)
        assert base(flow.store,pid)['NickCount'] == 0
        social = SocialService(flow.store,e,None)
        e.social = social
        appid = flow.identity.contract.web_config.service_app_id
        async def scenario():
            flow.identity.social_api = SocialAPI(flow.identity,social,asyncio.get_running_loop())
            async def post(path,args,authorization='Bearer'):
                reply = await asyncio.to_thread(flow.identity.respond,'POST',path,
                    json.dumps({'appid':appid,'userid':str(pid),**args}).encode(),authorization=authorization)
                assert reply.status == 200
                result = json.loads(reply.body)
                assert result['code'] == 0, result
                return result['data']
            # Native FriendModule.InitData uses V1, even before naming or level unlock.
            data = await post('/FriendService.GetFriendList',{})
            friends = data['Friends']['Friends']
            assert len(friends) == 39
            ids = [int(row['Friendid']) for row in friends]
            assert all(npc_owner(n) == pid for n in ids)
            cards_reply = await asyncio.to_thread(flow.identity.respond,'POST','/apply/queryPlayer',
                urlencode({'players':json.dumps(ids)}).encode(),
                authorization='Bearer')
            cards = json.loads(cards_reply.body)
            assert cards['code'] == 0 and len(cards['datas']) == 39
            ctx = DispatchContext('test','local',SessionState('test','session',player_id=pid))
            update = await social.handle(ctx,packet({'playerid':ids},1,'C2L_UpdateFriends'))
            assert update.message_name == 'L2C_UpdateFriends' and update.values['code'] == 10
            for response in update.pushes:
                if response.message_name == 'PlayerDataProto':
                    wire = FRIEND_DATA.decode(response.values['FriendData'])
                    assert {LONG_INT.decode(r)['idx'] for r in wire['FriendPos']} == set(ids)
            v2 = await post('/FriendService.GetFriendListV2',{})
            assert v2['Total'] == 39 and isinstance(v2['Friends'],list)
            assert v2['Friends'] == friends
            p0 = await post('/FriendService.GetFriendListV2',{'page':0,'pageNum':20})
            p1 = await post('/FriendService.GetFriendListV2',{'page':1,'pageNum':20})
            assert p0['Total'] == p1['Total'] == 39
            assert p0['Friends'] + p1['Friends'] == friends
            assert (await post('/FriendService.GetFriendListV2',{'page':2,'pageNum':20}))['Friends'] == []
            token = await post('/FriendService.GetFriendList',{},'Bearer '+login['token'])
            assert token['Friends']['Friends'] == friends
            # No naming or tutorial progress is modified by fetching friends.
            assert base(flow.store,pid)['NickCount'] == 0
        asyncio.run(scenario())
    finally:
        flow.accounts.close()
        flow.store.close()
