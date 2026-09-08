"""Static neutral HTTP fixture, only for the isolated VPN validation server."""
import base64
import json
import os
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit

os.chdir('/fixture/public')
Path('thumbnail.png').write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZ1cAAAAASUVORK5CYII='))
Path('captions.vtt').write_text('WEBVTT\n\n00:00.000 --> 00:01.000\nNeutral fixture.\n')
Path('master.m3u8').write_text('#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=200000,CODECS="avc1.42E01E,mp4a.40.2",RESOLUTION=160x90\nindex.m3u8\n')
Path('index.m3u8').write_text('#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXT-X-MEDIA-SEQUENCE:0\n#EXTINF:2,\nsample.ts\n#EXT-X-ENDLIST\n')
Path('manifest.mpd').write_text('<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static" mediaPresentationDuration="PT2S"><Period><AdaptationSet mimeType="video/mp4"><Representation id="1" bandwidth="200000"><BaseURL>sample.mp4</BaseURL></Representation></AdaptationSet></Period></MPD>')


class Handler(SimpleHTTPRequestHandler):
    extensions_map={**SimpleHTTPRequestHandler.extensions_map,'.m3u8':'application/vnd.apple.mpegurl','.mpd':'application/dash+xml','.vtt':'text/vtt'}
    def do_GET(self):
        if urlsplit(self.path).path=='/api':
            raw=json.dumps({'items':[{'id':str(i),'title':'Neutral documentary '+str(i),'url':'http://93.184.216.34/clip'+str(i)} for i in range(2)]}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        else:super().do_GET()


ThreadingHTTPServer(('93.184.216.34',80),Handler).serve_forever()
