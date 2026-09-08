"""Real isolated Chromium, simulated public site, full discovery and normal search.

Run inside the observer image with tests mounted; never changes production data.
"""
import asyncio
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from urllib.parse import urlsplit,parse_qs
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'tests'))
from support import TestClient
from app import assistant_browser as browser, source_assistant as sa
from app.main import app


def markup(query):
    if query.startswith('anytube-no-result-'):
        return '<main>Aucun résultat</main>'
    return ''.join(f'<article class="video"><h2><a href="/watch/{query}-{i}">{query} {i}</a></h2></article>' for i in range(4))


async def fixture(url,method='GET',body=None,headers=None):
    parts=urlsplit(url)
    if '/watch/' in parts.path:
        text='<html><video id="player"></video><script>document.getElementById("player").src="https://example.org/video.mp4";</script></html>'
    elif parts.path=='/search':
        query=parse_qs(parts.query).get('q',[''])[0]
        text='<html><main id="results"></main><script>document.getElementById("results").innerHTML='+json.dumps(markup(query))+';</script></html>'
    else:
        text='<form action="/search"><input type="search" name="q"></form>'
    return {'url':url,'text':text,'content_type':'text/html','base64':base64.b64encode(text.encode()).decode()}


async def fetch(url,**kwargs):
    if url.endswith('/observe'):
        observed=await browser.observe(browser.Observation(**kwargs['body']))
        return {'text':json.dumps(observed)}
    return await fixture(url)


def main():
    with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'ANYTUBE_DATA':folder}):
        with TestClient(app) as client,patch.object(sa,'http',side_effect=fetch),patch.object(browser,'guarded_fetch',side_effect=fixture),patch.object(sa,'settings',return_value=sa.Settings(browser=sa.Service(url='http://fixture-observer'))):
            headers={'X-AnyTube':'1'}
            started=time.monotonic()
            with patch.object(sa,'launch'):
                response=client.post('/api/source-assistant/jobs',headers=headers,json={'target':'https://example.org','queries':['science','music']})
            response.raise_for_status();job=response.json()
            asyncio.run(sa.execute(job['id']))
            saved=sa.load(job['id'])
            assert saved['status']=='added', (saved['status'],saved.get('last_error'),saved['steps'])
            assert saved['candidate']['html']['rendering']=='chromium'
            assert saved['diagnostics'] and any(d.get('outcome')=='confirmed' for d in saved['diagnostics'])
            assert all(proof['method']=='rendered_metadata' for proof in saved['evidence']['listing_evidence'].values())
            search=client.post('/api/search',headers=headers,json={'query':'science','sources':[saved['added_source']],'limit':3})
            search.raise_for_status();assert len(search.json()['items'])==3,search.json()
            print(json.dumps({'scenario':'javascript-rendered-html','status':'passed','seconds':round(time.monotonic()-started,3),'metrics':saved['metrics'],'manual_connector_edits':0}),flush=True)


if __name__=='__main__':
    main()
