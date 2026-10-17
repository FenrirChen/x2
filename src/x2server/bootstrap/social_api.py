"""PBS social bridge: marshal SQLite work onto the authenticated game loop."""
import asyncio
import concurrent.futures
import json
import logging
from urllib.parse import parse_qs

from .service import HTTPResponse

LOG=logging.getLogger('x2.social.http')


class SocialAPI:
    ROUTES = frozenset('/FriendService.'+n for n in (
        'GetFriendList','GetFriendListV2','GetApplyList','GetBlackList','ApplyAddFriend',
        'AddFriend','AnswerAddFriend','DeleteFriend','AddBlacklist','RemoveBlacklist','RenameFriend')) | frozenset(
        '/ClubService.'+n for n in ('GetClub','GetClubSimple','GetClubSimpleV2','QueryClub','FilterClub',
        'FetchClubSimple','GetClubMember','GetWishingPage','QueryWishingHistory')) | frozenset((
        '/apply/queryPlayer','/AttribService.GetAttrib','/KVStoreService.GetValuesV2','/RankingService.QueryRank'))

    def __init__(self,identity,service,loop):
        self.identity,self.service,self.loop=identity,service,loop

    @classmethod
    def supports(cls,path):
        return path in cls.ROUTES or path.startswith(('/FriendService.','/ClubService.'))

    @staticmethod
    def response(data=None,code=0,error='',status=200):
        return HTTPResponse(status,'application/json; charset=utf-8',
            json.dumps({'code':code,'error':error,'data':data or {}},ensure_ascii=False).encode('utf8'))

    def respond(self,method,path,body,authorization):
        if method.upper()!='POST':
            return self.response(code=405,error='method_not_allowed',status=405)
        try:
            if path=='/apply/queryPlayer':
                fields=parse_qs(body.decode('utf8'),strict_parsing=True,max_num_fields=16)
                ids=json.loads(fields['players'][0])
                if not isinstance(ids,list) or len(ids)>100:
                    raise ValueError('invalid card list')
                args={'players':ids}
            else:
                args=json.loads(body)
                if not isinstance(args,dict):
                    raise ValueError('invalid PBS request')
                args={k.lower():v for k,v in args.items()}
                if args.get('appid')!=self.identity.contract.web_config.service_app_id:
                    return self.response(code=403,error='forbidden',status=403)
            pid=None
            requested=int(args.get('userid') or 0)
            if not requested and authorization.strip()=='Bearer':
                from x2server.player.social import npc_owner
                if path=='/ClubService.GetClubMember':
                    requested=npc_owner(args.get('member',0)) or 0
                elif path=='/KVStoreService.GetValuesV2':
                    owners={npc_owner(n) for n in args.get('users',[]) if npc_owner(n)}
                    if len(owners)==1:
                        requested=owners.pop()
            if authorization.startswith('Bearer ') and authorization[7:].strip():
                pid=self.identity._mail_player_for_token(authorization[7:].strip())
                if not pid:
                    return self.response(code=401,error='unauthorized',status=401)
                if requested and requested!=pid:
                    return self.response(code=403,error='forbidden',status=403)
            elif authorization.strip()=='Bearer' and requested:
                # Native revival client has the same bare-Bearer PBS contract as mail.
                account=self.identity._accounts.get_by_player(requested) if self.identity._accounts else None
                if not account or account['status']!='active':
                    return self.response(code=401,error='unauthorized',status=401)
                pid=requested
            elif path not in ('/apply/queryPlayer','/AttribService.GetAttrib'):
                # Context-free NPC cards/attributes are public static data. Never
                # infer an owner from the last login or a global singleton player.
                return self.response(code=401,error='missing_account_context',status=401)
            async def invoke():
                await self.service.store.wait_for_import()
                return self.service.http(path,args,pid)
            pending=asyncio.run_coroutine_threadsafe(invoke(),self.loop)
            try:
                data=pending.result(timeout=5)
            except concurrent.futures.TimeoutError:
                pending.cancel()
                return self.response(code=503,error='busy',status=503)
            LOG.info('social query player=%s route=%s',pid,path)
            if path=='/apply/queryPlayer':
                return HTTPResponse(200,'application/json; charset=utf-8',json.dumps({'code':0,'datas':data},ensure_ascii=False).encode('utf8'))
            return self.response(data)
        except (ValueError,TypeError,KeyError,UnicodeDecodeError) as exc:
            LOG.info('social PBS refused route=%s reason=%s',path,exc)
            return self.response(code=13,error='invalid_request')
