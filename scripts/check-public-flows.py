"""Real worker traffic through AnyTube's gateway to the neutral VPN fixture."""
import asyncio
import base64
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import egress
from app.connectors import Connector
from app.playback import rewrite_hls, rewrite_dash


async def main():
    config={'mode':'proxy','revision':'fixture','proxy_url':os.environ['TEST_PROXY']}
    base='http://93.184.216.34'
    async with await asyncio.start_server(egress.client,'127.0.0.1',0) as server:
        port=server.sockets[0].getsockname()[1]
        async def worker(payload):
            process=await asyncio.create_subprocess_exec(sys.executable,'-m','app.worker',
                env={**os.environ,'ANYTUBE_PROXY':f'http://127.0.0.1:{port}'},
                stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            raw,_=await asyncio.wait_for(process.communicate(json.dumps(payload).encode()),80)
            value=json.loads(raw)
            assert not value.get('error'),value
            return value
        with patch.object(egress,'route_settings',new=AsyncMock(return_value=config)):
            connector=Connector(kind='json',search_url=base+'/api?q={query}',results_path='/items').model_dump()
            found=await worker({'mode':'search','connector':connector,'query':'science','limit':3})
            assert len(found['items'])==2
            resolved=await worker({'mode':'resolve','url':base+'/master.m3u8'})
            assert resolved['formats']
            for path in ('thumbnail.png','captions.vtt','sample.mp4','sample.ts'):
                result=await worker({'mode':'fetch','url':base+'/'+path})
                assert base64.b64decode(result['data'])
            session={'id':'fixture','resources':{},'representations':set()}
            for path, rewrite in (('master.m3u8',rewrite_hls),('index.m3u8',rewrite_hls),('manifest.mpd',rewrite_dash)):
                result=await worker({'mode':'fetch','url':base+'/'+path})
                transformed=rewrite(session,base64.b64decode(result['data']),base+'/'+path,{})
                assert b'/api/playback/fixture/resource/' in transformed
                assert base.encode() not in transformed
            with tempfile.TemporaryDirectory() as folder:
                downloaded=await worker({'mode':'media','url':base+'/master.m3u8','folder':folder,'max_bytes':10*1024*1024})
                assert (Path(folder)/downloaded['filename']).stat().st_size>1000
            print('PUBLIC_SEARCH_EXTRACTION_DOWNLOAD_THUMBNAIL_HLS_DASH_SUBTITLES_VIA_GATEWAY_OK',flush=True)


asyncio.run(main())
