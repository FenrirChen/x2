"""Per-account single-player friends and clubs, using the native client protocol.

Character names/avatars and PBS DTO shapes adapted from bluebird0212's proposals
(issue #33, PR #37). No shared memberships or invented real-player accounts.
All writes run on the game loop; activity_state is already part of complete saves.
"""
from collections import Counter
from functools import lru_cache
from importlib.resources import files
import hashlib
import json
import logging
import random
import uuid

from x2server.messages.club import CLUB_IDS, CLUB_SCHEMAS, SIMPLE_CLUB_DATA
from x2server.messages.social import SOCIAL_IDS, SOCIAL_SCHEMAS, FRIEND_DATA, INT_LONG, LONG_INT, LONG_LONG
from x2server.messages.college import COLLEGE_SCHEMAS, HELP_POWER_SPEED_PARAM
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY
from .economy import UnresolvedEconomy

PERIOD = -37
NAMESPACE = 'singleplayer-social'
COIN, SCORE = 1237917, 1237924
LOG = logging.getLogger('x2.social')
# Revival single-player parameters. Keys are native GlobalParamString names;
# values without a recovered server default are compatibility choices.
PARAMETERS = {'BasicFriendNum':'200','GiveFriendCoinLimit':'10','ReceiveFriendCoinLimit':'15',
    'GiveFriendCoinPoint':'20','DailyFriendApplyLimit':'200','FriendRequestNum':'200',
    'FoundGuildConsume':'0','ChangeGuildNameConsume':'0','RecommendGuildNum':'20',
    'GuildApplyLevel':'17','GuildHelpFreshenTime':'30','GuildHelpTime':'60',
    'GuildHelpCount':'50','GuildHelpSummonCount':'50','GuildWishGiveLimit':'10','GuildWishHelpLimit':'3',
    'GuildChallengeNumLimit':'5'}


@lru_cache(maxsize=1)
def roster():
    return json.loads(files('x2server').joinpath('data/social_characters.json').read_text(encoding='utf8'))['players']


def day(now):
    return (int(now) + 8*3600)//86400


def friend_day(now):
    """Friend gifts reset at Beijing/server 00:00."""
    return day(now)


class SocialRefused(ValueError):
    def __init__(self,code,reason):
        super().__init__(reason)
        self.code=code


def npc_id(pid,canonical):
    return 700000000000+pid*10000+canonical-700000000


def npc_owner(uid):
    return (int(uid)-700000000000)//10000 if int(uid)>700000000000 else None


def canonical_id(pid,uid):
    uid=int(uid)
    if npc_owner(uid)!=pid:
        raise ValueError('foreign or invalid NPC identity')
    return 700000000+(uid-700000000000)%10000


def attrib(uid, name, head, level):
    return dict(Uid=str(uid),CreateTime=0,Name=name,Head=str(head),Level=level,
                Zone='',Server='local',Channel='local',SubChannel='',Os='',Online=True,
                # Club nodes read Ext[iconID]/Ext[firstMedal], not BaseAttrib.Head.
                Ext={'iconID':str(head),'firstMedal':'0'})


def value(name, number):
    return {'Name':name,'Value':{'Type':1,'VString':'','VInt64':number}}


def load_state(store, pid, now):
    row = store.db.execute('SELECT value FROM activity_state WHERE player_id=? AND period=? AND namespace=? AND state_key=?',
                           (pid,PERIOD,NAMESPACE,'state')).fetchone()
    state = json.loads(row[0]) if row else {'version':1,'removed':[],'black':[],'notes':{},'club':None,
        'wishes':[],'wish_counts':{},'history':[],'helped':{},'serial':0,'mirror':{'count':3,'clears':[],'claimed':[]}}
    old_day=state.get('day')
    if state.get('day') != day(now):
        elapsed = max(0,day(now)-state.get('day',day(now)))
        state.update(day=day(now),wish_counts={},given=0,help_count=0,today_score=0)
        mirror = state['mirror']
        mirror['count'] = min(5,mirror['count']+3*elapsed)
        # Unclaimed player donations survive midnight; completed history is bounded.
        state['wishes'] = [w for w in state['wishes'] if w['owner']=='self' and w['got'] < w['num']]
        state['history'] = state['history'][-100:]
    if state.get('friend_day') is None:
        # Preserve current-day claims when upgrading the original midnight version.
        state['friend_day']=friend_day(now)
        state.setdefault('sent',[])
        state.setdefault('received',[])
        if old_day is not None and old_day!=day(now):
            state.update(sent=[],received=[])
    elif state['friend_day'] != friend_day(now):
        state.update(friend_day=friend_day(now),sent=[],received=[])
    return state


def snapshot_value(store, pid, now):
    state = load_state(store,pid,now)
    sent, received = [npc_id(pid,n) for n in state['sent']], [npc_id(pid,n) for n in state['received']]
    friends = [npc_id(pid,r['id']) for r in roster() if r['id'] not in state['removed'] and r['id'] not in state['black']]
    # SilentOrbit leaves absent repeated fields null. Zero entries initialise lists.
    def pairs(schema, vals):
        return [schema.encode({'idx':i,'val':n}) for i,n in enumerate(vals)] or [schema.encode({'idx':0,'val':0})]
    return FRIEND_DATA.encode({'SendPlayer':pairs(INT_LONG,sent),'ReceivePlayer':pairs(INT_LONG,received),
        'SendCount':len(sent),'ReceiveCount':len(received),
        'FriendPos':[LONG_INT.encode({'idx':n,'val':i}) for i,n in enumerate(friends)] or [LONG_INT.encode({'idx':0,'val':0})],
        'FriendPoint':[LONG_INT.encode({'idx':n,'val':0}) for n in friends] or [LONG_INT.encode({'idx':0,'val':0})],
        'FriendChat':[LONG_LONG.encode({'idx':0,'val':0})],'LastRecommendTime':0,'SendReqCount':0})


class SocialService:
    def __init__(self, store, economy, college, clock=None, chooser=None):
        self.store,self.economy,self.college = store,economy,college
        self.clock = clock or economy.clock
        self.choose = chooser or random.SystemRandom().choice
        self.characters = {r['id']:r for r in roster()}
        self.catalog = json.loads(files('x2server').joinpath('data/club_catalog.json').read_text(encoding='utf8'))
        self.wish_rows = {int(k):v for k,v in self.catalog['wishes'].items()}
        self.mirror_sections = {s:r for r in self.catalog['mirror'] for s in r['stageIds']}
        with store.db:
            store.db.execute('''CREATE TABLE IF NOT EXISTS activity_state (
                player_id INTEGER NOT NULL,period INTEGER NOT NULL,namespace TEXT NOT NULL,
                state_key TEXT NOT NULL,value TEXT NOT NULL,PRIMARY KEY(player_id,period,namespace,state_key))''')
            store.db.execute('''CREATE TABLE IF NOT EXISTS activity_receipts (
                player_id INTEGER NOT NULL,request_key TEXT NOT NULL,period INTEGER NOT NULL,
                message TEXT NOT NULL,response BLOB NOT NULL,PRIMARY KEY(player_id,request_key))''')
        from .friend_currency import repair
        repair(store)

    def state(self,pid):
        return load_state(self.store,pid,self.clock())

    def refresh_friends(self,pid):
        """One midnight rollover push; offline accounts refresh on their next request."""
        row=self.store.db.execute('SELECT value FROM activity_state WHERE player_id=? AND period=? AND namespace=? AND state_key=?',
                                  (pid,PERIOD,NAMESPACE,'state')).fetchone()
        if row and json.loads(row[0]).get('friend_day')==friend_day(self.clock()):
            return None
        with self.economy.transaction():
            self.save(pid,self.state(pid))
        # Native FriendModule.OnReceiveFriendDataDirty refreshes the coin buttons.
        return OutboundMessage('PlayerDataProto',{'FriendData':snapshot_value(self.store,pid,self.clock())},data_version=1)

    async def watch(self,tcp):
        import asyncio
        while True:
            for pid in tcp.authenticated_player_ids():
                try:
                    push=self.refresh_friends(pid)
                    if push:
                        await tcp.push_to_player(pid,push)
                        state=self.state(pid)
                        if state['club']:
                            await tcp.push_to_player(pid,OutboundMessage('L2C_ClubWishingCount',{
                                'code':10,'wishingCount':int(sum(state['wish_counts'].values())>0),
                                'guildWishGiveCount':state['given'],'guildHelpPowerCount':state['help_count']}))
                    weekly=self.economy.endless.refresh_week(pid)
                    if weekly:
                        await tcp.push_to_player(pid,weekly)
                except Exception:
                    LOG.exception('friend midnight refresh player=%s',pid)
            next_midnight=(friend_day(self.clock())+1)*86400-8*3600
            await asyncio.sleep(min(60,max(1,next_midnight-self.clock())))

    def save(self,pid,state):
        self.store.db.execute('''INSERT INTO activity_state VALUES (?,?,?,?,?)
            ON CONFLICT(player_id,period,namespace,state_key) DO UPDATE SET value=excluded.value''',
            (pid,PERIOD,NAMESPACE,'state',json.dumps(state,separators=(',',':'))))

    @staticmethod
    def club_id(pid):
        return 900000000+pid

    def friends(self,state):
        return [r for r in roster() if r['id'] not in state['removed'] and r['id'] not in state['black']]

    def metadata(self,pid,state):
        club=state['club']
        return [value('clubGroupChatUUID',self.club_id(pid)),value('clubLevel',1),
                value('clubMemLimit',50),value('clubIconId',club['icon']),value('clubTodayScore',state['today_score'])]

    def member(self,pid,state,uid):
        snap=self.store.get(pid)['snapshot']
        c=self.characters.get(uid)
        attributes = attrib(uid,c['name'],c['head'],snap['level']) if c else attrib(pid,snap.get('nickname','解神者'),snap.get('head_icon',1000001),snap['level'])
        return dict(Userid=str(uid),Post=state['club']['members'].get(str(uid),0) if c else 3,
            Time=state['club']['time'],Actives=[],Score=0,WeekScore=0,HistoryScore=0,Medal=0,
            RoundMedal=0,WinNum=0,WinTime=0,Attrib=attributes,IsOnline=True)

    def club_data(self,pid,state,simple=False):
        club=state['club']
        if not club:
            return dict(Id=0,Name='',Desc='',Notice='',Owner='',Time=0,Type=2,Meta=[],MemberList=[],ApplyList=[],EventList=[],MemberNum=0)
        data=dict(Id=self.club_id(pid),Name=club['name'],Desc=club['desc'],Notice=club['notice'],Owner=str(pid),
            Time=club['time'],Type=1,Meta=self.metadata(pid,state),HistoryScore=0,TotalScore=0,CurScore=0,
            WeekScore=0,ResetWeekTime=0,TotalMedal=0,RoundMedal=0,MemberNum=1+len(club['members']))
        if not simple:
            data.update(MemberList=[self.member(pid,state,pid)]+[self.member(pid,state,int(n)) for n in club['members']],
                ApplyList=[dict(Userid=str(r['id']),Time=club['time'],Metadata='',IsOnline=True,
                    Attrib=attrib(r['id'],r['name'],r['head'],self.store.get(pid)['snapshot']['level']))
                    for r in self.friends(state) if str(r['id']) not in club['members'] and r['id'] not in club['rejected']],EventList=[])
        return data

    def cards(self,ids,pid=None):
        state=self.state(pid) if pid else None
        cards=[]
        for uid in ids[:100]:
            uid=int(uid)
            r=self.characters.get(uid)
            if not r:
                continue
            level=self.store.get(pid)['snapshot']['level'] if pid else 60
            cards.append(dict(roleID=uid,roleName=r['name'],roleLevel=level,
                showCardExtra=dict(autograph='',birthday=0,heroNum=1,achvPoint=0,hardestSectionId=0,achvPointMax=0),
                showCardBase=dict(iconInfo=dict(iconType=0,iconID=r['head'],ornamentID=0,framePicId=0),nickName=r['name'],
                    roleLevel=level,playerID=uid,medalShow={'pos':[]},show=0,lastLogoutTime=0,
                    sendCoinPlayers=[pid] if state and uid in state['sent'] else [],outerSkin=0),
                assistHero=dict(id=r['hero'],level=min(level,60),star=self.npc_star(r['hero']),outerSkin=0),playerInfoBrowse=0))
        return cards

    @staticmethod
    def npc_star(hero_id):
        from .progression import catalog
        row=next((r for r in catalog()['hero_unlock'] if r['hero_id']==hero_id),None)
        return row['star'] if row else 1

    def friend_list(self,pid,state):
        level=self.store.get(pid)['snapshot']['level']
        return {'Friends':{'Friends':[dict(Friendid=str(r['id']),Nickname=state['notes'].get(str(r['id']),''),Time=0,
            Online=True,Values=[value('FriendCoin',1)] if r['id'] not in state['received'] else [],
            SharingValues=[],Attrib=attrib(r['id'],r['name'],r['head'],level)) for r in self.friends(state)],
            'Applys':None,'Blacks':[dict(Friendid=str(n),Time=0,Attrib=attrib(n,self.characters[n]['name'],self.characters[n]['head'],level))
                for n in state['black'] if n in self.characters],'SendApplys':[]}}

    def wishing_page(self,pid,state):
        if not state['club']:
            return {'Total':0,'List':[]}
        # NPC wishes only appear for invited members, once per member/day. No reward on reads.
        owned=[n for n in self.wish_rows if self.quantity(pid,n)>0]
        if owned:
            for uid in state['club']['members']:
                if not any(w['owner']==uid for w in state['wishes']):
                    r=self.wish_rows[owned[int(uid)%len(owned)]]
                    self.new_wish(state,uid,owned[int(uid)%len(owned)],r['numLimit'])
            self.save(pid,state)
        items=[]
        for w in state['wishes']:
            items.append(dict(Wid=w['id'],Userid=str(pid) if w['owner']=='self' else w['owner'],ItemId=w['item'],
                Time=w['time'],WantNum=w['num'],DonateNum=sum(d['num'] for d in w['donors']),GotNum=w['got'],
                LimitNum=w['num'],DonateCount=len(w['donors']),Donors=[dict(Userid=str(d['uid']),Num=d['num'],Time=d['time']) for d in w['donors']],Exp=0))
        return {'Total':len(items),'List':items}

    def new_wish(self,state,owner,item,num):
        state['serial']+=1
        row=dict(id=state['serial'],owner=owner,item=item,num=num,got=0,time=int(self.clock()),donors=[])
        state['wishes'].append(row)
        return row

    def quantity(self,pid,item):
        currency=self.economy.CURRENCIES.get(item)
        if currency:
            return self.store.get(pid)['snapshot'].get(currency,0)
        row=self.store.db.execute('SELECT quantity FROM inventory WHERE player_id=? AND item_id=?',(pid,item)).fetchone()
        return row[0] if row else 0

    def charge(self,pid,costs):
        if any(q<=0 or self.quantity(pid,n)<q for n,q in costs.items()):
            raise UnresolvedEconomy('social materials insufficient')
        snap=self.store.get(pid)['snapshot']
        changed=False
        for n,q in costs.items():
            currency=self.economy.CURRENCIES.get(n)
            if currency:
                snap[currency]-=q
                changed=True
            else:
                self.store.db.execute('UPDATE inventory SET quantity=quantity-? WHERE player_id=? AND item_id=?',(q,pid,n))
        if changed:
            self.economy.save_snapshot(pid,snap)

    def grant(self,pid,state,rewards):
        if rewards:
            self.economy._grant(pid,'social:'+uuid.uuid4().hex,rewards)

    def client_data(self,pid,data):
        if isinstance(data,list):
            return [self.client_data(pid,x) for x in data]
        if isinstance(data,dict):
            return {k:self.client_data(pid,v) for k,v in data.items()}
        if type(data) in (int,str):
            try:
                number=int(data)
            except ValueError:
                return data
            if number in self.characters:
                result=npc_id(pid,number)
                return str(result) if isinstance(data,str) else result
        return data

    def http(self,path,args,pid):
        args=dict(args)
        if path=='/apply/queryPlayer':
            owner=pid or (npc_owner(args['players'][0]) if args['players'] else None)
            if not owner:
                return []
            args['players']=[canonical_id(owner,n) for n in args['players']]
            return self.client_data(owner,self._http(path,args,owner))
        if path=='/AttribService.GetAttrib':
            attributes=[]
            for n in args.get('users',[]):
                owner=npc_owner(n)
                if owner:
                    canonical=canonical_id(owner,n)
                    r=self.characters.get(canonical)
                    if r:
                        attributes.append(attrib(n,r['name'],r['head'],60))
            return {'AttribList':attributes}
        for key in ('friendid','playerid','member'):
            if args.get(key) and int(args[key])!=pid:
                args[key]=canonical_id(pid,args[key])
        if path=='/KVStoreService.GetValuesV2':
            args['keys']=[str(k).replace(str(npc_id(pid,n)),str(n)) for k in args.get('keys',[]) for n in self.characters
                if str(npc_id(pid,n)) in str(k)]
        result=self.client_data(pid,self._http(path,args,pid))
        if path=='/KVStoreService.GetValuesV2':
            for row in result['Pairs']:
                for pair in row['pairs']:
                    pair['key']=pair['key'].replace(str(canonical_id(pid,row['userid'])),row['userid'])
        return result

    def _http(self,path,args,pid):
        """Runs on the main loop, including all state reads and writes."""
        with self.economy.transaction():
            state=self.state(pid) if pid else None
            if path=='/apply/queryPlayer':
                return self.cards(args['players'],pid)
            if path=='/AttribService.GetAttrib':
                ids=args.get('userids') or args.get('users') or []
                return {'AttribList':[attrib(int(n),self.characters[int(n)]['name'],self.characters[int(n)]['head'],60)
                    for n in ids if int(n) in self.characters]}
            if not pid:
                raise ValueError('missing account context')
            if path in ('/FriendService.GetFriendList','/FriendService.GetFriendListV2'):
                return self.friend_list(pid,state)
            if path=='/FriendService.GetApplyList':
                return {'send_applys':[],'applys':None}
            if path=='/FriendService.GetBlackList':
                return {'blacks':self.friend_list(pid,state)['Friends']['Blacks']}
            target=int(args.get('friendid') or args.get('playerid') or 0)
            if path.startswith('/FriendService.'):
                if target not in self.characters:
                    raise ValueError('invalid character')
                if path.endswith(('ApplyAddFriend','AddFriend','AnswerAddFriend')):
                    for key in ('removed','black'):
                        state[key]=[n for n in state[key] if n!=target]
                elif path.endswith('DeleteFriend'):
                    state['removed']=list(set(state['removed']+[target]))
                elif path.endswith('AddBlacklist'):
                    state['black']=list(set(state['black']+[target]))
                elif path.endswith('RemoveBlacklist'):
                    state['black']=[n for n in state['black'] if n!=target]
                elif path.endswith('RenameFriend'):
                    state['notes'][str(target)]=str(args.get('nickname',''))[:30]
                else:
                    raise ValueError('unsupported friendship operation')
                self.save(pid,state)
                return {}
            if path=='/ClubService.GetClub':
                if args.get('id') and int(args['id'])!=self.club_id(pid):
                    raise ValueError('foreign club')
                return {'Club':self.club_data(pid,state)}
            if path=='/ClubService.GetClubSimple':
                return {'Club':self.club_data(pid,state,True)}
            if path=='/ClubService.GetClubSimpleV2':
                return {'Clubs':[self.club_data(pid,state,True)] if state['club'] else []}
            if path in ('/ClubService.QueryClub','/ClubService.FilterClub'):
                return {'Total':int(bool(state['club'])),'Pages':[self.club_data(pid,state,True)] if state['club'] else []}
            if path=='/ClubService.FetchClubSimple':
                return {'ClubList':[self.club_data(pid,state,True)] if state['club'] else []}
            if path=='/ClubService.GetClubMember':
                uid=int(args.get('member',0))
                if not state['club'] or (uid!=pid and str(uid) not in state['club']['members']):
                    return {'Id':0,'Member':None}
                return {'Id':self.club_id(pid),'Member':self.member(pid,state,uid)}
            if path=='/ClubService.GetWishingPage':
                return self.wishing_page(pid,state)
            if path=='/ClubService.QueryWishingHistory':
                return {'Total':len(state['history']),'Items':[{**h,'Userid':str(pid) if h['Userid']=='self' else h['Userid']} for h in state['history']]}
            if path=='/KVStoreService.GetValuesV2':
                pairs=[]
                for key in args.get('keys',[]):
                    try:
                        _,_,uid,slot=key.split('_')
                        uid,slot=int(uid),int(slot)
                    except (ValueError,AttributeError):
                        continue
                    if not state['club'] or str(uid) not in state['club']['members'] or slot not in (1,2):
                        continue
                    # NPC construction requests last until midnight and are assisted once/day.
                    bid=701 if slot==1 else 721
                    end=(state['day']+1)*86400-8*3600
                    if f'npc:{state["day"]}:{uid}:{bid}' in state['helped']:
                        continue
                    val=json.dumps(dict(buildId=bid,upgradeEndTime=end,buildLevel=1),separators=(',',':'))
                    existing=next((p for p in pairs if p['userid']==str(uid)),None)
                    if existing is None:
                        existing={'userid':str(uid),'pairs':[]}
                        pairs.append(existing)
                    existing['pairs'].append({'key':key,'val':val})
                return {'Pairs':pairs}
            if path=='/RankingService.QueryRank':
                return {'Total':0,'TotalPage':0,'Members':[],'MemberRank':0,'MemberScore':0,'MemberMetadata':''}
            raise ValueError('unsupported social route')

    def handlers(self):
        return {'C2L_'+name:self.handle for name,_,_ in (*SOCIAL_IDS,*CLUB_IDS)} | {'C2L_HelpPowerSpeed':self.handle}

    async def handle(self,context,packet):
        pid=context.session.player_id
        if pid is None:
            raise ProtocolError('social before login')
        name=CORE_MESSAGE_REGISTRY.name_for(packet.message_id)
        schemas=SOCIAL_SCHEMAS if name in SOCIAL_SCHEMAS else CLUB_SCHEMAS if name in CLUB_SCHEMAS else COLLEGE_SCHEMAS
        req=schemas[name].decode(packet.body)
        reply='L2C_'+name[4:]
        key=f'social:{context.session.session_id}:{packet.header.request_id}'
        signature=name+':'+hashlib.sha256(packet.body).hexdigest()
        old=self.store.db.execute('SELECT message,response FROM activity_receipts WHERE player_id=? AND request_key=?',(pid,key)).fetchone()
        if old:
            if old[0]!=signature:
                return OutboundMessage(reply,{'code':13})
            before=(OutboundMessage('L2C_QueryGrowthBase',self.college.growth_base(pid)),) if name=='C2L_HelpPowerSpeed' else ()
            return OutboundMessage(reply,schemas[reply].decode(old[1]),before_response=before,pushes=self.pushes(pid))
        try:
            with self.economy.transaction():
                state=self.state(pid)
                for field in ('applyId','optedId','wishingId','donateId'):
                    if req.get(field,0)>700000000000:
                        req[field]=canonical_id(pid,req[field])
                if req.get('playerid'):
                    req['playerid']=[canonical_id(pid,n) for n in req['playerid']]
                if name=='C2L_HelpPowerSpeed':
                    converted=[]
                    for p in req.get('helpPowerSpeedParam') or []:
                        p=HELP_POWER_SPEED_PARAM.decode(p)
                        p['playerIded']=canonical_id(pid,p.get('playerIded',0))
                        converted.append(HELP_POWER_SPEED_PARAM.encode(p))
                    req['helpPowerSpeedParam']=converted
                result=self.operate(pid,state,name[4:],req)
                result=self.client_data(pid,result)
                if name=='C2L_HelpPowerSpeed':
                    params=[]
                    for p in result.get('helpPowerSpeedParam') or []:
                        p=HELP_POWER_SPEED_PARAM.decode(p)
                        p['playerIded']=npc_id(pid,p['playerIded'])
                        params.append(HELP_POWER_SPEED_PARAM.encode(p))
                    result['helpPowerSpeedParam']=params
                self.save(pid,state)
                raw=schemas[reply].encode(result)
                self.store.db.execute('INSERT INTO activity_receipts VALUES (?,?,?,?,?)',(pid,key,PERIOD,signature,raw))
        except (ValueError,KeyError,UnresolvedEconomy) as exc:
            LOG.info('social refused player=%s flow=%s reason=%s',pid,name,exc)
            result={'code':getattr(exc,'code',13)}
        before=(OutboundMessage('L2C_QueryGrowthBase',self.college.growth_base(pid)),) if name=='C2L_HelpPowerSpeed' and result.get('code')==10 else ()
        return OutboundMessage(reply,result,before_response=before,pushes=self.pushes(pid))

    def pushes(self,pid):
        from .login import LoginService
        state=self.state(pid)
        return (LoginService.snapshot_push(self.store.get(pid),self.store,now=self.clock()),
                OutboundMessage('L2C_ClubWishingCount',{'code':10,
                    'wishingCount':int(sum(state['wish_counts'].values())>0),
                    'guildWishGiveCount':state['given'],'guildHelpPowerCount':state['help_count']}),
                OutboundMessage('L2C_ItemUpdate',{'code':10,**self.economy.inventory_values(pid)}))

    def operate(self,pid,state,flow,req):
        result={'code':10}
        if flow=='QueryChatFriendsTime':
            from x2server.protocol.protobuf import ProtoSchema,ProtoField,FieldKind
            pair=ProtoSchema('KeyValuePair_Int64_Int64',(ProtoField(1,'Key',FieldKind.INT64),ProtoField(2,'Value',FieldKind.INT64)))
            return {'chatFriendsTime':[pair.encode({'Key':0,'Value':0})]}
        if flow=='UpdateFriends':
            return result
        if flow in ('SendFriendReq','SendFriendCoin','ReceiveFriendCoin'):
            ids=list(dict.fromkeys(req.get('playerid') or []))
            friends={r['id'] for r in self.friends(state)}
            if not ids or len(ids)>200 or not set(ids)<=set(self.characters):
                raise ValueError('invalid friend ids')
            if flow=='SendFriendReq':
                state['removed']=[n for n in state['removed'] if n not in ids]
                state['black']=[n for n in state['black'] if n not in ids]
                return {**result,'playerid':ids}
            if not set(ids)<=friends:
                raise ValueError('not friends')
            field='sent' if flow=='SendFriendCoin' else 'received'
            limit=10 if field=='sent' else 15
            eligible=[n for n in ids if n not in state[field]][:max(0,limit-len(state[field]))]
            if not eligible:
                if len(state[field])>=limit:
                    raise SocialRefused(194 if field=='sent' else 193,'daily friendship limit')
                raise SocialRefused(195 if field=='sent' else 192,'already sent or collected')
            room=max(0,5000-self.quantity(pid,COIN))
            gain=min(room,20*len(eligible))
            if gain<=0 and field=='received':
                raise SocialRefused(252,'friendship point holding cap')
            state[field]+=eligible
            if gain:
                self.grant(pid,state,{COIN:gain})
            # 每日 630023「赠送好友 1 次友情点」: TaskCondition.CompleteType 71
            # (E_GiveFriendCoin)。此前只发了友情点、没有任何事件上报, 任务进度永远是 0,
            # 所以「赠送友情点」的每日任务完成不了。只在**赠送**时记 (收取侧不算赠送),
            # 且只按本次新赠送的好友数 (已扣除今天送过的人) 计数; 事件键带这批好友,
            # economy_events 按 (task_period, key) 幂等去重, 同一批 targets 重发不会重复计。
            if flow=='SendFriendCoin' and eligible:
                self.economy.record_event(
                    pid, f"sendcoin:{pid}:{','.join(str(n) for n in sorted(eligible))}",
                    71, 0, len(eligible))
            return {**result,'playerid':eligible}
        if flow=='RecommandClub':
            club=state['club']
            rows=[SIMPLE_CLUB_DATA.encode(dict(clubId=self.club_id(pid),name=club['name'],desc=club['desc'],
                memNum=1+len(club['members']),memLimit=50,score=0,autoLevel=0,applyLevel=17,icon=club['icon']))] if club else [SIMPLE_CLUB_DATA.encode({'clubId':0,'icon':1270004,'memLimit':50})]
            return {**result,'simpleClubData':rows,'pageTotal':int(bool(club))}
        if flow=='CreateClub':
            if state['club'] or self.store.get(pid)['snapshot']['level']<17:
                raise ValueError('club exists or locked')
            name=str(req.get('name','')).strip()
            if not 1<=len(name)<=20:
                raise ValueError('club name invalid')
            state['club']=dict(name=name,desc=str(req.get('desc',''))[:200],notice='',icon=int(req.get('clubIconId') or 1270004),
                time=int(self.clock()),members={},rejected=[])
            return {**result,'clubId':self.club_id(pid),'opt':0}
        if not state['club']:
            raise ValueError('no club')
        club=state['club']
        if flow in ('AppalyJoinClub','QuickJoinClub'):
            requested=req.get('clubIds') or [req.get('clubId',0)]
            if self.club_id(pid) not in requested:
                raise ValueError('foreign club')
            return {**result,'clubId':self.club_id(pid),'result':0}
        if flow=='ClubApproval':
            target=req.get('applyId',0)
            if target not in {r['id'] for r in self.friends(state)} or str(target) in club['members']:
                raise ValueError('not an invitation candidate')
            if req.get('opt')==1:
                if len(club['members'])>=49:
                    raise ValueError('club full')
                club['members'][str(target)]=0
                club['rejected']=[n for n in club['rejected'] if n!=target]
            elif req.get('opt')==2:
                club['rejected']=list(set(club['rejected']+[target]))
            else:
                raise ValueError('unknown approval option')
        elif flow=='UpdateMemberPrivilege':
            target=str(req.get('optedId',0))
            if target not in club['members'] or req.get('opt') not in (0,1,2):
                raise ValueError('cannot transfer ownership to NPC')
            club['members'][target]=req['opt']
        elif flow=='DismissMember':
            target=str(req.get('optedId',0))
            if target not in club['members']:
                raise ValueError('not a member')
            del club['members'][target]
            state['wishes']=[w for w in state['wishes'] if w['owner']!=target]
        elif flow=='QuitClub':
            state['club']=None
            state['wishes']=[w for w in state['wishes'] if w['owner']=='self' and w['got']<w['num']]
            result['postId']=req.get('postId',0)
        elif flow=='UpdateClubInfo':
            opt=req.get('opt',0)
            if opt==1 and str(req.get('name','')).strip():
                club['name']=str(req['name']).strip()[:20]
            elif opt==2 and req.get('clubIconId',0)>0:
                club['icon']=req['clubIconId']
            elif opt==3:
                club['notice']=str(req.get('notice',''))[:200]
            else:
                raise ValueError('invalid club update')
            result['opt']=opt
        elif flow=='UpdateClubRecruit':
            club['desc']=str(req.get('desc',''))[:200]
            club['rejected']=[]  # Reopening recruitment restores refused invitation candidates.
        elif flow=='JoinClubListner':
            pass
        elif flow=='ClubWishing':
            item=req.get('itemId',0)
            row=self.wish_rows.get(item)
            if not row or self.store.get(pid)['snapshot']['level']<row['unlockLevel'] or not club['members']:
                raise ValueError('wish locked or no NPC donor')
            if self.economy.items.get(item,{}).get('ItemType',{}).get('value')==12 and self.quantity(pid,item)<=0:
                raise ValueError('wish for unowned character fragment')
            if sum(state['wish_counts'].values())>0:
                raise ValueError('one club wish per day')
            count=state['wish_counts'].get(str(item),0)
            if count>=row['numLimit'] or any(w['owner']=='self' and w['item']==item and w['got']<w['num'] for w in state['wishes']):
                raise ValueError('wish daily limit or pending')
            cost=row['consume']
            if cost and cost[0]!=901:
                raise ValueError('unresolved wish currency')
            self.charge(pid,{1237901:cost[1]} if cost else {})
            w=self.new_wish(state,'self',item,row['numLimit'])
            donor=int(self.choose(list(club['members'])))
            w['donors']=[dict(uid=donor,num=w['num'],time=w['time'],received=False)]
            state['wish_counts'][str(item)]=count+w['num']
            result['itemId']=item
        elif flow=='ClubWishingCount':
            result.update(wishingCount=int(sum(state['wish_counts'].values())>0),
                guildWishGiveCount=state['given'],guildHelpPowerCount=state['help_count'])
        elif flow=='ClubWishingReceive':
            target=req.get('donateId',0)
            stamp=req.get('time',0)
            picked=[(w,d) for w in state['wishes'] if w['owner']=='self' for d in w['donors']
                if not d['received'] and (target<=0 or target in (d['uid'],w['id'],pid))
                and (not stamp or stamp in (d['time'],d['time']+1514736000))]
            if not picked:
                raise ValueError('no matching unclaimed donation')
            rewards=Counter()
            for w,d in picked:
                rewards[w['item']]+=d['num']
                d['received']=True
                w['got']+=d['num']
                state['history'].append(dict(Wid=w['id'],Userid='self',Donor=str(d['uid']),ItemId=w['item'],ItemNum=d['num'],Time=d['time']+1514736000))
            self.grant(pid,state,rewards)
            result.update(donateId=target,rewardData=self.economy.reward_bytes(rewards))
        elif flow=='ClubWishingDonate':
            target=req.get('wishingId',0)
            stamp=req.get('wishingTime',0)
            w=next((w for w in state['wishes'] if w['owner']!='self' and int(w['owner'])==target
                    and w['time']==stamp and w['got']<w['num'] and w['owner'] in club['members']),None)
            if not w:
                raise ValueError('invalid donation target or already full')
            if state['given']>=10:
                raise ValueError('daily donation limit')
            self.charge(pid,{w['item']:1})
            w['got']+=1
            w['donors'].append(dict(uid=pid,num=1,time=int(self.clock()),received=True))
            state['given']+=1
            # Awards come from GuildWish.Award; no made-up flat gold/score grant.
            rewards=self.economy.gifts(self.wish_rows[w['item']]['award'],allow_daily_random=True)
            self.grant(pid,state,rewards)
            state['history'].append(dict(Wid=w['id'],Userid=w['owner'],Donor=str(pid),ItemId=w['item'],ItemNum=1,Time=int(self.clock())+1514736000))
            result.update(wishingId=target,rewardData=self.economy.reward_bytes(rewards))
        elif flow=='HelpPowerSpeed':
            return self.help(pid,state,req)
        elif flow=='ClubActiMainData':
            m=state['mirror']
            result.update(challegeCount=m['count'],receivedLayer=m['claimed'] or [-1],scoreRewardFlag=0,battledSectionIds=m.get('sections') or [-1])
        elif flow=='ClubReceiveReward':
            m=state['mirror']
            param=req.get('param',0)
            if req.get('opt')!=0 or param not in m['clears'] or param in m['claimed']:
                raise ValueError('mirror reward not eligible')
            row=next((r for r in self.catalog['mirror'] if r['bossId']==param),None)
            if not row:
                raise ValueError('unknown mirror reward')
            rewards=self.economy.gifts([row['challengeReward']])
            m['claimed'].append(param)
            self.grant(pid,state,rewards)
            result.update(param=param,rewardData=self.economy.reward_bytes(rewards))
        else:
            raise ValueError('unsupported club operation')
        return result

    def help(self,pid,state,req):
        params=[HELP_POWER_SPEED_PARAM.decode(p) for p in req.get('helpPowerSpeedParam') or []]
        if req.get('helpPower') not in (1,2) or not params or len(params)>98:
            raise ValueError('invalid help request')
        valid=[]
        for p in params:
            if state['help_count']+len(valid)>=50:
                break
            uid,bid=p.get('playerIded',0),p.get('buildingId',0)
            key=f'npc:{state["day"]}:{uid}:{bid}'
            if str(uid) in state['club']['members'] and bid in (701,721) and p.get('buildingLevel')==1 and key not in state['helped']:
                state['helped'][key]=1
                valid.append(p)
        if not valid:
            raise ValueError('already assisted or foreign NPC')
        state['help_count']+=len(valid)
        donor=int(self.choose(list(state['club']['members'])))
        base=self.college.load(pid)
        completed=[]
        for key in ('build_queue','wonder_queue'):
            q=base.get(key)
            if not q or q.get('upgradeEndTime',0)<=self.clock():
                continue
            identity=f'own:{key}:{q["buildingId"]}:{q.get("upgradeStartTime",0)}:{q.get("target_level",0)}:{donor}'
            if identity in state['helped']:
                continue
            state['helped'][identity]=1
            q['upgradeEndTime']=max(int(self.clock()),q['upgradeEndTime']-60)
        completed=self.college.settle(base)
        self.college.save(pid,base)
        # The native help-all callback requires nonempty rewardData. GuildWish 778000 is the help reward.
        rewards=self.economy.gifts([778000],allow_daily_random=True)
        self.grant(pid,state,rewards)
        result=dict(code=10,helpPower=req['helpPower'],helpPowerSpeedParam=[HELP_POWER_SPEED_PARAM.encode(p) for p in valid],rewardData=self.economy.reward_bytes(rewards))
        return result

    def admission(self,pid,section):
        state=self.state(pid)
        if not state['club'] or section not in self.mirror_sections or state['mirror']['count']<=0:
            raise UnresolvedEconomy('mirror locked or attempts exhausted')

    def assist(self,pid,raw,config):
        from x2server.messages.social import ASSIST_DATA
        from x2server.messages.battle import FIGHT_HERO,HERO_ATTR,HERO_ATTR_ADD,HERO_SKILL
        from .progression import battle_hero_base,hero_attributes,hero_skills,catalog
        req=ASSIST_DATA.decode(raw)
        if not req.get('assistPlayerID'):
            return None
        uid=canonical_id(pid,req['assistPlayerID'])
        entry=self.characters.get(uid)
        if config.get('AssistType',{}).get('value')!=2 or uid not in {r['id'] for r in self.friends(self.state(pid))}:
            raise ValueError('friend support unavailable')
        if not entry or req.get('heroID',entry['hero'])!=entry['hero']:
            raise ValueError('friend support identity mismatch')
        # Authoritative NPC loadout; ignore client supplied stats, star, level and skills.
        hero=dict(id=entry['hero'],state=2,level=min(60,self.store.get(pid)['snapshot']['level']),star=self.npc_star(entry['hero']),exp=0)
        base=battle_hero_base()[str(hero['id'])]
        data=FIGHT_HERO.encode({**hero,'heroAttrCount':HERO_ATTR.encode(hero_attributes(hero)),
            'heroSkill':[HERO_SKILL.encode(r) for r in hero_skills(hero)],
            'attrAdd':[HERO_ATTR_ADD.encode({'attrId':r['attrId'],'attrValue':base[r['name']]}) for r in catalog()['battle_base_1003']['attributes']]})
        return ASSIST_DATA.encode(dict(assistPlayerID=npc_id(pid,uid),friendShipLevel=1,playerName=entry['name'],
            heroID=hero['id'],heroSkinID=0,heroStar=hero['star'],heroPower=0,assistTimes=1,heroLevel=hero['level'],battleData=data,md5=''))

    def bind_run(self,pid,section,run):
        self.admission(pid,section)
        state=self.state(pid)
        state['mirror']['count']-=1
        self.save(pid,state)

    def completed(self,pid,section,success):
        if success:
            state=self.state(pid)
            layer=self.mirror_sections[section]['bossId']
            if layer not in state['mirror']['clears']:
                state['mirror']['clears'].append(layer)
            if section not in state['mirror'].setdefault('sections',[]):
                state['mirror']['sections'].append(section)
            self.save(pid,state)
