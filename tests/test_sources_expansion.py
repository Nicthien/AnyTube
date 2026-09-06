import base64
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.request import Request
from fastapi import HTTPException
from support import TestClient
from app.main import app
from app.store import connect, current_user
from app.connectors import Connector, default_connector, search_json, PublicRedirect
from app.vault import Credential, reveal, scoped_headers, credential_revision
from app.verification import record, evidence, history
from app.registry import identities
from app.inventory import report
from app.playback import register, resource_url, rewrite_hls, rewrite_dash, sessions
from app.discovery import select_source

HEADERS = {'X-AnyTube': '1'}


class SourceExpansionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        key = Path(self.temp.name) / 'external.key'
        key.write_bytes(os.urandom(32))
        self.env = patch.dict(os.environ, {'ANYTUBE_DATA': self.temp.name, 'ANYTUBE_VAULT_KEY_FILE': str(key)})
        self.env.start()
        self.client = TestClient(app).__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.env.stop()
        self.temp.cleanup()

    def credential(self, **changes):
        body = {'name': 'Essai', 'kind': 'bearer', 'domains': ['api.example.org'], 'value': 'secret-never-exported', **changes}
        result = self.client.post('/api/credentials', json=body, headers=HEADERS)
        self.assertEqual(result.status_code, 201, result.text)
        return result.json()['id']

    def test_ciphertext_owner_and_tamper_protection(self):
        identifier = self.credential()
        self.assertEqual(reveal(identifier)['value'], 'secret-never-exported')
        with connect() as db:
            encrypted = db.execute('SELECT encrypted FROM credentials').fetchone()[0]
            self.assertNotIn('secret-never-exported', encrypted)
        self.assertNotIn('secret-never-exported', self.client.get('/api/credentials').text)
        context = current_user.set('other-account')
        try:
            with self.assertRaises(HTTPException) as caught:
                reveal(identifier)
            self.assertEqual(caught.exception.status_code, 404)
        finally:
            current_user.reset(context)
        raw = bytearray(base64.b64decode(encrypted)); raw[-1] ^= 1
        with connect() as db:
            db.execute('UPDATE credentials SET encrypted=?', (base64.b64encode(raw).decode(),))
        with self.assertRaises(HTTPException) as caught:
            reveal(identifier)
        self.assertEqual(caught.exception.status_code, 503)

    def test_key_is_required_and_not_regenerated(self):
        identifier = self.credential()
        Path(os.environ['ANYTUBE_VAULT_KEY_FILE']).write_bytes(os.urandom(32))
        with self.assertRaises(HTTPException):
            reveal(identifier)
        with patch.dict(os.environ, {'ANYTUBE_VAULT_KEY_FILE': ''}):
            self.assertFalse(self.client.get('/api/credentials').json()['ready'])
            self.assertEqual(self.client.post('/api/credentials', json={'name':'x','kind':'bearer','domains':['example.org'],'value':'x'}, headers=HEADERS).status_code,503)

    def test_secret_headers_do_not_follow_cross_host_or_http_redirect(self):
        credential = {'kind':'api_key', 'domains':['api.example.org'], 'header':'X-Key', 'value':'secret'}
        request = Request('https://api.example.org/a', headers=scoped_headers(credential,'https://api.example.org/a'))
        for target in ('https://other.example.org/b', 'http://api.example.org/b'):
            redirected = PublicRedirect(credential).redirect_request(request,None,302,'',{},target)
            self.assertNotIn('secret', str(redirected.headers))
        redirected = PublicRedirect(credential).redirect_request(request,None,302,'',{},'https://api.example.org/b')
        self.assertEqual(redirected.get_header('X-key'),'secret')
        with self.assertRaises(ValueError):
            PublicRedirect(credential).redirect_request(request,None,302,'',{},'http://127.0.0.1/')

    def test_cookie_scopes_expiry_and_header_validation(self):
        body={'name':'cookies','kind':'cookies','domains':['example.org'],
              'value':'# Netscape HTTP Cookie File\nexample.org\tFALSE\t/\tTRUE\t0\tsession\tsecret'}
        value = Credential.model_validate(body).model_dump()
        self.assertEqual(scoped_headers(value,'https://example.org/watch')['Cookie'],'session=secret')
        self.assertFalse(scoped_headers(value,'https://sub.example.org/watch'))
        self.assertFalse(scoped_headers(value,'http://example.org/watch'))
        with self.assertRaises(ValueError):
            Credential.model_validate({**body,'domains':['other.example.org']})
        with self.assertRaises(ValueError):
            Credential(name='x',kind='api_key',domains=['example.org'],value='x',header='Host')

    def test_credential_rotation_invalidates_evidence_and_retains_history(self):
        identifier=self.credential()
        config={**default_connector('Dailymotion'),'credential_id':identifier}
        record(config,'nature','verified',2)
        record(config,'nature','verified',feature='resolve')
        self.assertEqual(len(evidence(config)),2)
        self.assertNotIn('video',{e['feature'] for e in evidence(config)})
        original=credential_revision(config)
        self.client.put(f'/api/credentials/{identifier}',json={'name':'new','kind':'bearer','domains':['api.example.org'],'value':'changed'},headers=HEADERS).raise_for_status()
        self.assertNotEqual(original,credential_revision(config))
        self.assertFalse(evidence(config))
        self.assertTrue(all(e['obsolete'] for e in history(config)))
        self.client.delete(f'/api/credentials/{identifier}',headers=HEADERS).raise_for_status()
        self.assertEqual(credential_revision(config),'revoked')

    def test_post_json_query_is_not_url_encoded_and_page_is_native(self):
        config=Connector(kind='json',method='POST',search_url='https://api.example.org/search',
                         body={'term':'{query}','size':'{limit}'},pagination={'mode':'offset','parameter':'offset'},
                         results_path='/items').model_dump()
        with patch('app.connectors.build_opener') as opener:
            opener.return_value.open.return_value=io.BytesIO(b'{"items":[{"id":"a","title":"ok","url":"https://example.org/a"}]}')
            result=search_json(config,'été & chat',2,offset=4,return_page=True)
        request=opener.return_value.open.call_args.args[0]
        self.assertEqual(request.method,'POST')
        self.assertEqual(json.loads(request.data),{'term':'été & chat','size':'2','offset':4})
        self.assertTrue(result['native_page'])
        self.assertFalse(result['has_more'])

    def test_dailymotion_native_page_and_boolean_contract(self):
        with patch('app.connectors.build_opener') as opener:
            opener.return_value.open.return_value=io.BytesIO(b'{"list":[],"has_more":false}')
            result=search_json(default_connector('Dailymotion'),'nature',10,offset=20,return_page=True)
            self.assertIn('page=3',opener.return_value.open.call_args.args[0].full_url)
            self.assertFalse(result['has_more'])
            opener.return_value.open.return_value=io.BytesIO(b'{"list":[],"has_more":"true"}')
            with self.assertRaises(ValueError):
                search_json(default_connector('Dailymotion'),'nature',10,offset=0,return_page=True)

    def test_inventory_is_complete_but_never_auto_reviewed(self):
        inventory=report([])
        self.assertEqual(inventory['extractor_count'],len(identities()))
        self.assertEqual(inventory['totals']['reviewed_platforms'],0)
        self.assertFalse(inventory['complete_platform_review'])
        for platform in inventory['platforms']:
            for extractor in platform['extractors']:
                self.assertEqual(extractor['features']['video']['verification'],'not_verified')

    def test_collection_accepts_sibling_extractor_only_for_active_source(self):
        source, extractor=select_source('https://www.youtube.com/playlist?list=PL1234567890')
        self.assertEqual(source['id'],'Youtube')
        self.assertNotEqual(extractor,'Generic')
        with self.assertRaises(HTTPException):
            select_source('https://example.org/arbitrary')
        self.client.patch('/api/sources/Youtube',json={'enabled':False},headers=HEADERS)
        with self.assertRaises(HTTPException):
            select_source('https://www.youtube.com/playlist?list=PL1234567890')

    def test_playback_is_private_revocable_and_hides_upstream_urls(self):
        async def worker(payload, **kwargs):
            return {'video':{'title':'Movie','url':'https://www.youtube.com/watch?v=abcdefghijk'},'is_live':False,'subtitles':{},
                    'formats':[{'url':'https://cdn.example.org/movie.m3u8?token=secret','manifest_url':None,'protocol':'m3u8_native','acodec':'aac'}]}
        with patch('app.main.run_worker',side_effect=worker):
            response=self.client.post('/api/playback',json={'url':'https://www.youtube.com/watch?v=abcdefghijk'},headers=HEADERS)
        self.assertEqual(response.status_code,201,response.text)
        self.assertNotIn('token=secret',response.text)
        data=response.json(); uri=data['choices'][0]['url']
        self.assertEqual(self.client.get(uri.replace('/file','/invented')).status_code,404)
        self.client.patch('/api/sources/Youtube',json={'enabled':False},headers=HEADERS)
        self.assertEqual(self.client.get(uri).status_code,410)


class ManifestTests(unittest.TestCase):
    def test_packed_audio_mime_survives_opaque_relay_urls(self):
        from app.relay import media_mime
        packed = b'ID3\x03\x00\x00\x00\x00\x00\x03abc\xff\xf1\x50'
        self.assertEqual(media_mime(packed, 'application/octet-stream'), 'audio/aac')
        self.assertEqual(media_mime(b'\xff\xf9\x50', 'application/octet-stream'), 'audio/aac')
        self.assertEqual(media_mime(b'ID3\x03', 'application/octet-stream'), 'application/octet-stream')
        self.assertEqual(media_mime(packed, 'audio/mp4'), 'audio/mp4')

    def setUp(self):
        self.session={'id':'private','resources':{},'representations':set()}

    def test_hls_rewrites_segments_keys_maps_and_rejects_private(self):
        raw=b'#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="key"\n#EXT-X-MAP:URI="init.mp4"\n#EXTINF:5,\nseg.ts\n'
        out=rewrite_hls(self.session,raw,'https://cdn.example.org/path/index.m3u8',{}).decode()
        self.assertNotIn('URI="key"',out)
        self.assertEqual(len(self.session['resources']),3)
        self.assertTrue(all('/path/' in value['url'] for value in self.session['resources'].values()))
        with self.assertRaises(ValueError):
            rewrite_hls(self.session,b'#EXTM3U\nhttp://127.0.0.1/secret\n','https://example.org/',{})

    def test_dash_substitution_cannot_change_host_or_inject_paths(self):
        raw=b'<MPD xmlns="urn:mpeg:dash:schema:mpd:2011"><Period><AdaptationSet><SegmentTemplate media="track-$RepresentationID$-$Number%05d$.m4s" initialization="init-$RepresentationID$.mp4"/><Representation id="v1"/></AdaptationSet></Period></MPD>'
        result=rewrite_dash(self.session,raw,'https://cdn.example.org/index.mpd',{})
        self.assertIn(b'$Number%05d$',result)
        resource=next(r for r in self.session['resources'].values() if '$Number' in r['url'])
        self.assertEqual(resource_url(self.session,resource,'v1/00002'),'https://cdn.example.org/track-v1-00002.m4s')
        with self.assertRaises(HTTPException):
            resource_url(self.session,resource,'evil/00002')
        with self.assertRaises(HTTPException):
            resource_url(self.session,resource,'v1/https://private')
        with self.assertRaises(ValueError):
            register(self.session,'https://$RepresentationID$.example.org/a')

    def test_dash_rejects_entities_drm_and_external_xlinks(self):
        for raw in (b'<!DOCTYPE foo><MPD/>',b'<MPD><ContentProtection/></MPD>',b'<MPD xmlns:xlink="http://www.w3.org/1999/xlink"><Period xlink:href="https://example.org/"/></MPD>'):
            with self.assertRaises(ValueError):
                rewrite_dash(self.session,raw,'https://example.org/index.mpd',{})
