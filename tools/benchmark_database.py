"""Isolated full-server load test: HTTP auth, 50 TCP clients and real save jobs.

Never pass the live database. A new temporary database is seeded automatically.
Run with PYTHONPATH=src python -m tools.benchmark_database --clients 50
 --rounds 40 --history-blobs 6000 --database-mib 1800 --report analysis/db_load.json
"""
import argparse
from contextlib import closing
import asyncio
from collections import defaultdict
import json
import os
from pathlib import Path
import socket
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error
from urllib.parse import urlencode

from x2server.messages.core import CORE_SCHEMAS
from x2server.messages.battle import BATTLE_SCHEMAS, CHECKOUT, PROFILE_HERO
from x2server.messages.economy import ECONOMY_SCHEMAS
from x2server.messages.mail import MAIL_SCHEMAS
from x2server.messages.lobby import LOBBY_SCHEMAS
from x2server.protocol.codec import ProtocolCodec
from x2server.protocol.framing import PacketStreamDecoder
from x2server.protocol.headers import RequestHeader, ResponseHeader
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY

SCHEMAS = {**CORE_SCHEMAS, **BATTLE_SCHEMAS, **ECONOMY_SCHEMAS, **MAIL_SCHEMAS, **LOBBY_SCHEMAS}


def post(port, route, data=None, token=None, raw=False):
    if isinstance(data, dict):
        data = urlencode(data).encode()
    request = urllib.request.Request(f'http://127.0.0.1:{port}{route}', data=data or b'')
    if token:
        request.add_header('Authorization', 'Bearer ' + token)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        response = opener.open(request, timeout=180)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        body = response.read()
        if response.status != 200:
            raise RuntimeError(f'HTTP {route}: {response.status} {body[:150]!r}')
        return body if raw else json.loads(body)


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def seed(path, clients, history_blobs, database_mib, owned_heroes, diagnostic_rows=0):
    from tests.unit.test_save_manager import build_full_schema
    from x2server.player.accounts import AccountStore
    from x2server.player.save_manager import SaveManager
    from x2server.player.store import PlayerStore
    store = PlayerStore(path)
    build_full_schema(store)
    accounts = AccountStore(store)
    ids = []
    try:
        for n in range(clients + 2):
            name = f'load-user-{n:03d}'
            assert accounts.create(name, 'load-password', int(time.time())) == 'created'
            pid = accounts.get_by_name(name)['player_id']; ids.append(pid)
            old = store.get(pid)
            store.save_snapshot(pid, {**old['snapshot'], 'level': 60,
                'mobility': {'power': 100000},
                'heroes': [{'id': hid, 'state': 2, 'level': 20, 'star': 1} for hid in range(1003,1003+owned_heroes)]}, old['revision'])
        payload = os.urandom(4096)
        with store.db:
            store.db.executemany("""INSERT INTO battle_entries
                (player_id,request_key,uuid,created_at,response) VALUES (?,?,?,?,?)""",
                ((ids[-2],f'history-{i}',f'history-{i}',0,
                  payload + i.to_bytes(4,'little')) for i in range(history_blobs)))
            # Real indexed history rows belonging to a DIFFERENT player. No
            # padding table, sparse file, or live player data is used.
            count = max(0, (database_mib * 1024 * 1024 - path.stat().st_size) // 16384)
            filler = b'background-history' * 960
            store.db.executemany("""INSERT INTO battle_entries
                (player_id,request_key,uuid,created_at,response) VALUES (?,?,?,?,?)""",
                ((ids[-1],f'padding-{i}',f'padding-{i}',0,filler) for i in range(count)))
        if diagnostic_rows:
            assert history_blobs > 0
            from x2server.messages.battle import BATTLE_SCHEMAS
            stamp = int(time.time()) - 48*3600 - 1
            pid = ids[-2]
            with store.db:
                store.db.execute("INSERT INTO economy_runs(uuid,player_id,session_id,section_id,settled) VALUES ('history-0',?,'history',2110801,1)", (pid,))
                reply = BATTLE_SCHEMAS['L2C_CheckoutMainMission'].encode({'result':10,'success':True})
                store.db.execute("INSERT INTO battle_receipts VALUES ('history-0','history',?,?)", (stamp,reply))
                raw = BATTLE_SCHEMAS['C2L_FightDropData'].encode({'missionId':2110801,'chapterId':2010100})
                text = json.dumps({'padding':'x'*32768})
                for i in range(diagnostic_rows):
                    rid = store.db.execute('INSERT INTO fight_drop_observations VALUES (NULL,?,?,?,?,?,?,?,?,?)',
                        (pid,'history-0','history',i,str(i),stamp,raw,text,text)).lastrowid
                    store.db.execute('INSERT INTO fight_drop_items VALUES (?,0,1,1,0,0)', (rid,))
                    store.db.execute('INSERT INTO fight_drop_claims VALUES (?,"currency",0,?)', (rid,'{}'))
        manager = SaveManager(store)
        try:
            manager.prepare_indexes()
        finally:
            manager.close()
    finally:
        accounts.close(); store.close()
    return ids


class Client:
    def __init__(self, reader, writer, timings, think_seconds=0, phase=0):
        self.reader, self.writer = reader, writer
        self.pending = {}; self.request_id = 0; self.session = ''
        self.timings = timings
        self.think_seconds, self.phase = think_seconds, phase
        self.receiver = asyncio.create_task(self.receive())

    async def receive(self):
        decoder = PacketStreamDecoder(ResponseHeader)
        try:
            while data := await self.reader.read(65536):
                for packet in decoder.feed(data):
                    self.session = packet.header.session_id
                    future = self.pending.get(packet.header.request_id)
                    if future and not future.done():
                        future.set_result(packet)
            raise ConnectionError('server closed TCP connection')
        except BaseException as exc:
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(exc)

    async def call(self, name, values):
        if self.think_seconds and name != 'C2L_Login':
            await asyncio.sleep(self.think_seconds * (.75 + ((self.phase * 17 + self.request_id * 7) % 50) / 100))
        self.request_id += 1; rid = self.request_id
        future = asyncio.get_running_loop().create_future(); self.pending[rid] = future
        started = time.perf_counter()
        self.writer.write(ProtocolCodec().encode(name, values,
            RequestHeader(request_id=rid,session_id=self.session)))
        await self.writer.drain()
        try:
            packet = await asyncio.wait_for(future, 30)
            expected = {'C2L_CheckoutMainMissionSign': 'L2C_CheckoutMainMission'}.get(name, name.replace('C2L_', 'L2C_', 1))
            if packet.message_id != CORE_MESSAGE_REGISTRY.entry_for_name(expected).message_id:
                raise RuntimeError(f'wrong response message ID for {name}: {packet.message_id}')
            result = SCHEMAS[expected].decode(packet.body)
            if result.get('code', result.get('result', 10)) != 10:
                raise RuntimeError(f'{name} refused: {result!r}')
            self.timings[name].append(time.perf_counter() - started)
            return result
        finally:
            self.pending.pop(rid, None)

    async def close(self):
        self.writer.close(); await self.writer.wait_closed()
        self.receiver.cancel(); await asyncio.gather(self.receiver, return_exceptions=True)


def stats(values):
    values = sorted(values)
    if not values:
        return {}
    return {'count':len(values),'p50_ms':round(statistics.median(values)*1000,2),
            'p95_ms':round(values[min(len(values)-1,int(len(values)*.95))]*1000,2),
            'p99_ms':round(values[min(len(values)-1,int(len(values)*.99))]*1000,2),
            'max_ms':round(values[-1]*1000,2)}


async def scenario(args, path, ids, http, game):
    timings = defaultdict(list); clients = []
    save_times = {}; archive_size = 0
    # Authentication is real HTTP; issue tokens before the synchronized workload.
    tokens = []
    for n in range(args.clients):
        name = f'load-user-{n:03d}'
        account = await asyncio.to_thread(post,http,'/loginwithpw',{'account':name,'password':'load-password'})
        game_auth = await asyncio.to_thread(post,http,'/apply/httpLogin',
            {'accountid':name,'token':account['token'],'logintype':'GAME'})
        tokens.append(game_auth['token'])
    save_token = (await asyncio.to_thread(post,http,'/save-manager/auth',
        {'account':f'load-user-{args.clients:03d}','password':'load-password'}))['token']
    started = time.perf_counter()
    archive = await asyncio.to_thread(post,http,'/save-manager/export',None,save_token,True)
    save_times['initial_export_seconds'] = round(time.perf_counter()-started,3)
    archive_size = len(archive)
    try:
        for _ in range(args.clients):
            reader, writer = await asyncio.open_connection('127.0.0.1',game)
            clients.append(Client(reader,writer,timings,args.think_seconds,len(clients)))
        await asyncio.gather(*(c.call('C2L_Login',{'id':pid,'token':token})
            for c,pid,token in zip(clients,ids,tokens)))
        gate = asyncio.Event()
        progress = 0
        async def play(client):
            nonlocal progress
            await gate.wait()
            for index in range(args.rounds):
                await client.call('C2L_ShopGoods',{'shopId':801})
                await client.call('C2L_GameTask',{'type':1})
                await client.call('C2L_MailData',{'pageIndex':0,'pageSize':20})
                await client.call('C2L_FightData',{'missionId':2110801,'chapter':2010100,'sceneId':2210801,
                    'heros':[PROFILE_HERO.encode({'heroId':1003+i,'leader':int(i==0)}) for i in range(args.team_size)]})
                checkout = {'checkout':CHECKOUT.encode({'chapterId':2010100,'sectionId':2110801,
                                                       'success':True,'fightTime':200})}
                await client.call('C2L_CheckoutMainMissionSign',checkout)
                # Exact settlement replay must never duplicate rewards.
                await client.call('C2L_CheckoutMainMissionSign',checkout)
                progress += 1
                await asyncio.sleep(.02)
        async def save():
            await gate.wait()
            while progress < args.clients:
                await asyncio.sleep(.01)
            started = time.perf_counter()
            await asyncio.to_thread(post,http,'/save-manager/import',archive,save_token)
            save_times['concurrent_import_seconds'] = round(time.perf_counter()-started,3)
        started = time.perf_counter()
        tasks = [asyncio.create_task(play(c)) for c in clients] + [asyncio.create_task(save())]
        gate.set()
        await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - started
        return {'clients':args.clients,'think_seconds':args.think_seconds,'owned_heroes_per_account':args.owned_heroes,'selected_team_size':args.team_size,'rounds':args.rounds,'completed_player_battles':progress,
                'archive_bytes':archive_size,'workload_seconds':round(elapsed,3),
                'timings':{k:stats(v) for k,v in timings.items()},'save':save_times}
    finally:
        await asyncio.gather(*(c.close() for c in clients))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clients',type=int,default=50)
    parser.add_argument('--rounds',type=int,default=12)
    parser.add_argument('--owned-heroes',type=int,default=1)
    parser.add_argument('--think-seconds',type=float,default=0)
    parser.add_argument('--team-size',type=int,default=1)
    parser.add_argument('--history-blobs',type=int,default=128)
    parser.add_argument('--database-mib',type=int,default=64)
    parser.add_argument('--diagnostic-rows',type=int,default=0)
    parser.add_argument('--report',type=Path,required=True)
    args = parser.parse_args()
    assert 1 <= args.clients <= 100 and args.rounds > 1 and args.think_seconds >= 0
    assert 1 <= args.team_size <= 3 and args.team_size <= args.owned_heroes <= 20
    args.report.parent.mkdir(parents=True,exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONPATH=str(root/'src'), PYTHONIOENCODING='utf-8',
        X2_BIND_HOST='127.0.0.1',X2_PUBLIC_HOST='127.0.0.1',
        X2_LOCAL_ACCOUNT='',X2_LOCAL_PASSWORD='',X2_READ_TIMEOUT='60',X2_IDLE_TIMEOUT='180')
    ports = [free_port() for _ in range(3)]
    env.update(dict(zip(('X2_HTTP_PORT','X2_GAME_PORT','X2_CHAT_PORT'),map(str,ports))))
    report = {}
    scratch = root / 'runtime' / 'database_load_tmp'
    scratch.mkdir(parents=True,exist_ok=True)
    env.update(TEMP=str(scratch), TMP=str(scratch))
    with tempfile.TemporaryDirectory(prefix='x2-load-',dir=scratch) as temporary:
        path = Path(temporary)/'isolated.sqlite3'
        ids = seed(path,args.clients,args.history_blobs,args.database_mib,args.owned_heroes,args.diagnostic_rows)
        report['initial_database_bytes'] = path.stat().st_size
        report['initial_expired_diagnostic_reports'] = args.diagnostic_rows
        log_path = args.report.with_suffix('.server.log')
        with log_path.open('w',encoding='utf-8') as log:
            options = {'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
            proc = subprocess.Popen([getattr(sys, '_base_executable', sys.executable) if os.name == 'nt' else sys.executable,'-B','-m','tools.local_game_server',
                '--database',str(path),'--seconds','0'],cwd=root,env=env,
                stdout=log,stderr=log,**options)
            try:
                for _ in range(300):
                    if proc.poll() is not None:
                        raise RuntimeError('isolated server failed: '+str(log_path))
                    try:
                        with socket.create_connection(('127.0.0.1',ports[1]),timeout=.2):
                            break
                    except OSError:
                        time.sleep(.1)
                else:
                    raise TimeoutError('isolated startup')
                report.update(asyncio.run(scenario(args,path,ids,*ports[:2])))
                with closing(sqlite3.connect(path)) as db:
                    report['settled_runs'] = db.execute('SELECT COUNT(*) FROM economy_runs WHERE settled=1').fetchone()[0]
                    report['battle_receipts'] = db.execute('SELECT COUNT(*) FROM battle_receipts').fetchone()[0]
                    report['positive_gold_players'] = sum(json.loads(r[0]).get('gold',0)>0 for r in
                        db.execute('SELECT snapshot FROM players WHERE id<=?',(ids[args.clients-1],)))
                    report['quick_check'] = db.execute('PRAGMA quick_check').fetchone()[0]
                    if args.diagnostic_rows:
                        report['diagnostic_children_remaining'] = db.execute('SELECT count(*) FROM fight_drop_items').fetchone()[0]
                        report['diagnostic_json_rows_remaining'] = db.execute("SELECT count(*) FROM fight_drop_observations WHERE decoded!='{}'").fetchone()[0]
                        assert report['diagnostic_children_remaining'] == 0
                        assert report['diagnostic_json_rows_remaining'] < args.diagnostic_rows

                assert report['settled_runs']==report['battle_receipts']==args.clients*args.rounds+int(bool(args.diagnostic_rows))
                assert report['positive_gold_players']==args.clients
                assert report['quick_check']=='ok'
            except BaseException as exc:
                report['error'] = repr(exc)
                raise
            finally:
                proc.terminate(); proc.wait(timeout=30)
                args.report.write_text(json.dumps(report,indent=2),encoding='utf-8')
        text = log_path.read_text(encoding='utf-8',errors='replace')
        import re
        lags = [float(x) for x in re.findall(r'event loop stalled lag=([0-9.]+)',text)]
        report['loop_stalls_over_500ms'] = len(lags)
        report['max_reported_loop_stall_seconds'] = max(lags,default=0)
        report['sqlite_busy_errors'] = text.count('sqlite_error=SQLITE_BUSY')
        report['connection_timeouts'] = text.count('connection read/idle timeout')
        report['save_write_seconds'] = [float(x) for x in re.findall(r'import write done .*?write_elapsed=([0-9.]+)',text)]
        report['slo_pass'] = (not report['sqlite_busy_errors'] and not report['connection_timeouts']
            and max(lags,default=0)<.5
            and all(v['p95_ms']<2000 and v['max_ms']<5000 for k,v in report['timings'].items() if k!='C2L_Login'))
        args.report.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))
        if not report['slo_pass']:
            raise SystemExit('load-test SLO failed; inspect report')


if __name__=='__main__':
    main()
