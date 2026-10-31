import asyncio
import hashlib
import io
import os
import socket
import time
import zipfile

from x2server.bootstrap import http_server
from x2server.bootstrap.service import HTTPResponse


def test_slow_save_download_outlives_one_socket_timeout_without_truncation(monkeypatch):
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_STORED) as archive:
        archive.writestr('payload.bin',os.urandom(4*1024*1024))
    payload=output.getvalue()
    idle=.5
    monkeypatch.setattr(http_server,'SAVE_SEND_IDLE_SECONDS',idle,raising=False)
    original=http_server._handler_for
    def handler(service):
        cls=original(service)
        send=cls._send
        def constrained(self,response):
            self.connection.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,8192)
            self.connection.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
            self.connection.settimeout(idle)
            send(self,response)
        cls._send=constrained
        return cls
    monkeypatch.setattr(http_server,'_handler_for',handler)
    class Service:
        def respond(self,*args,**kwargs):
            return HTTPResponse(200,'application/octet-stream',payload)
    def download(port):
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,32768)
            sock.settimeout(10)
            sock.connect(('127.0.0.1',port))
            sock.sendall(b'POST /save-manager/export HTTP/1.0\r\nHost: localhost\r\nContent-Length: 0\r\n\r\n')
            wire=b''
            while b'\r\n\r\n' not in wire:
                wire+=sock.recv(4096)
            headers,body=wire.split(b'\r\n\r\n',1)
            assert b'Content-Length: '+str(len(payload)).encode() in headers
            received=bytearray(body)
            started=time.monotonic()
            while True:
                chunk=sock.recv(16384)
                if not chunk:break
                received.extend(chunk)
                time.sleep(.008)
            assert time.monotonic()-started>idle
            assert len(received)==len(payload)
            assert hashlib.sha256(received).digest()==hashlib.sha256(payload).digest()
            with zipfile.ZipFile(io.BytesIO(received)) as archive:
                assert archive.testzip() is None
    async def scenario():
        server=http_server.BootstrapHTTPServer('127.0.0.1',0,Service())
        await server.start()
        try:await asyncio.to_thread(download,server.bound_port)
        finally:await server.stop()
    asyncio.run(scenario())


def test_bounded_link_can_finish_many_chunks_beyond_one_write_timeout(monkeypatch):
    from types import SimpleNamespace
    tick=[0.0]
    connection=SimpleNamespace(timeout=.5)
    connection.settimeout=lambda value:setattr(connection,'timeout',value)
    payload=b'x'*(256*1024)
    delivered=bytearray()
    class SlowWriter:
        def write(self,data):
            needed=len(data)/(64*1024)*.2
            if needed>connection.timeout:
                tick[0]+=connection.timeout
                raise TimeoutError('modeled slow link whole-write deadline')
            tick[0]+=needed
            delivered.extend(data)
    monkeypatch.setattr(http_server,'time',SimpleNamespace(monotonic=lambda:tick[0]),raising=False)
    monkeypatch.setattr(http_server,'SAVE_SEND_IDLE_SECONDS',.5,raising=False)
    cls=http_server._handler_for(None)
    handler=cls.__new__(cls)
    handler.path='/save-manager/export'
    handler.connection=connection
    handler.wfile=SlowWriter()
    handler.send_response=lambda *args:None
    handler.send_header=lambda *args:None
    handler.end_headers=lambda:None
    handler._send(HTTPResponse(200,'application/octet-stream',payload))
    assert delivered==payload
    assert tick[0]>.5


def test_interrupted_save_download_closes_connection_and_reports_progress(monkeypatch,caplog):
    from types import SimpleNamespace
    import logging
    monkeypatch.setattr(http_server,'time',SimpleNamespace(monotonic=lambda:1.0))
    cls=http_server._handler_for(None)
    handler=cls.__new__(cls)
    handler.path='/save-manager/export?hidden=never-log-this'
    handler.connection=SimpleNamespace(settimeout=lambda value:None)
    class Writer:
        def write(self,data):raise TimeoutError('stalled')
    handler.wfile=Writer()
    handler.send_response=lambda *args:None
    handler.send_header=lambda *args:None
    handler.end_headers=lambda:None
    with caplog.at_level(logging.WARNING):
        handler._send(HTTPResponse(200,'application/octet-stream',b'x'*(256*1024)))
    assert handler.close_connection
    assert 'completed_bytes=0 total_bytes=262144' in caplog.text
    assert 'error=TimeoutError' in caplog.text
    assert 'never-log-this' not in caplog.text


def test_transfer_total_deadline_still_bounds_a_continuously_slow_reader(monkeypatch,caplog):
    from types import SimpleNamespace
    import logging
    tick=[0.0]
    monkeypatch.setattr(http_server,'time',SimpleNamespace(monotonic=lambda:tick[0]))
    monkeypatch.setattr(http_server,'SAVE_SEND_TOTAL_SECONDS',.5)
    cls=http_server._handler_for(None)
    handler=cls.__new__(cls)
    handler.path='/save-manager/export'
    handler.connection=SimpleNamespace(settimeout=lambda value:None)
    delivered=bytearray()
    class Writer:
        def write(self,data):
            tick[0]+=.3
            delivered.extend(data)
    handler.wfile=Writer()
    handler.send_response=lambda *args:None
    handler.send_header=lambda *args:None
    handler.end_headers=lambda:None
    with caplog.at_level(logging.WARNING):
        handler._send(HTTPResponse(200,'application/octet-stream',b'x'*(256*1024)))
    assert handler.close_connection
    assert len(delivered)==128*1024
    assert 'error=TimeoutError' in caplog.text
