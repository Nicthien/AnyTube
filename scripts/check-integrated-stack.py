"""Run only as root inside the disposable AnyTube validation container.

Creates an ephemeral test account. Does not accept a production target or secrets.
"""
import asyncio
import hashlib
import http.client
import json
import os
import secrets
import sys
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.store import connect

if os.environ.get('ANYTUBE_ENVIRONMENT') != 'validation-060':
    raise RuntimeError('Only the isolated validation stack may run this fixture.')
token = secrets.token_urlsafe(32)
with connect() as db:
    db.execute("INSERT OR REPLACE INTO users(id,name,password,admin) VALUES ('fixture-060','Fixture 060','disabled-password',1)")
    db.execute('INSERT INTO sessions VALUES (?,?,?,?)', (hashlib.sha256(token.encode()).hexdigest(),'fixture-060',time.time()+1200,time.time()))
os.setgroups([]); os.setgid(10003); os.setuid(10003)


def request(path, method='GET', data=None):
    connection = http.client.HTTPConnection('127.0.0.1',8000,timeout=100)
    try:
        connection.request(method,path,json.dumps(data) if data is not None else None,
            headers={'Cookie':'anytube_session='+token,'X-AnyTube':'1','Content-Type':'application/json'})
        response=connection.getresponse(); raw=response.read()
        assert response.status<300,(path,response.status,raw[:300])
        return json.loads(raw)
    finally:
        connection.close()


async def main():
    from websockets.asyncio.client import connect as ws_connect
    identifier = request('/api/browser-sessions','POST',{'url':'https://example.org'})['id']
    try:
        for attempt in range(10):
            try:
                await asyncio.to_thread(request,f'/api/browser-sessions/{identifier}/open','POST')
                break
            except AssertionError:
                if attempt==9:raise
                await asyncio.sleep(3)
        async with ws_connect(f'ws://127.0.0.1:8000/api/browser-sessions/{identifier}/screen',
                origin='http://127.0.0.1:8000',proxy=None,additional_headers={'Cookie':'anytube_session='+token},max_size=2*1024*1024) as ws:
            async with asyncio.timeout(35):
                while True:
                    frame=json.loads(await ws.recv())
                    if frame.get('type')=='frame':
                        assert frame['image'] and frame['url'].startswith('https://example.org')
                        break
        saved=await asyncio.to_thread(request,f'/api/browser-sessions/{identifier}/validate','POST')
        assert saved['state']=='saved'
        print('INTEGRATED_FIREWALL_CDP_SESSION_OK',flush=True)
        initial=request('/api/network/settings')
        assert initial['mode']=='direct'
        direct=await asyncio.to_thread(request,'/api/network/test','POST')
        assert direct['ok'],direct
        await asyncio.to_thread(request,'/api/network/settings','PUT',{'mode':'proxy','proxy_url':'http://192.0.2.123:8888'})
        blocked=await asyncio.to_thread(request,'/api/network/test','POST')
        assert not blocked['ok'],blocked
        assert request('/api/health')['status']=='ok'
        print('DEAD_PROXY_FAIL_CLOSED_UI_ACCESSIBLE_OK',flush=True)
        await asyncio.to_thread(request,'/api/network/settings','PUT',{'mode':'direct'})
        assert (await asyncio.to_thread(request,'/api/network/test','POST'))['ok']
        print('EXPLICIT_DIRECT_RESTORE_OK',flush=True)
    finally:
        await asyncio.to_thread(request,f'/api/browser-sessions/{identifier}','DELETE')


asyncio.run(main())
