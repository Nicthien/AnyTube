import asyncio
import json
import tempfile
import io
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from support import TestClient
from app.main import app, jobs
from app.store import initialize, saved_sources
from app.worker import normalize, protect_network

HEADERS = {'X-AnyTube': '1'}


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.env = patch.dict('os.environ', {'ANYTUBE_DATA': self.folder.name})
        self.env.start()
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.env.stop()
        self.folder.cleanup()

    def test_sources_persist_and_do_not_reappear_after_delete(self):
        c = self.client
        self.assertEqual(c.post('/api/sources', json={'id': 'Vimeo'}).status_code, 403)
        self.assertEqual(c.post('/api/sources', json={'id': 'Vimeo'}, headers=HEADERS).status_code, 201)
        self.assertEqual(c.post('/api/sources', json={'id': 'Vimeo'}, headers=HEADERS).status_code, 409)
        self.assertEqual(c.post('/api/sources', json={'id': 'Invalid'}, headers=HEADERS).status_code, 400)
        c.patch('/api/sources/Vimeo', json={'enabled': False}, headers=HEADERS)
        initialize()
        self.assertFalse(next(s for s in saved_sources() if s['id'] == 'Vimeo')['enabled'])
        c.delete('/api/sources/Youtube', headers=HEADERS)
        initialize()
        self.assertNotIn('Youtube', [s['id'] for s in saved_sources()])

    def test_search_selection_partial_failure_and_url_only(self):
        async def worker(payload):
            if payload['source'] == 'Dailymotion':
                raise RuntimeError('Source indisponible')
            return {'items': [{'title': 'Nature', 'url': 'https://www.youtube.com/watch?v=abcdefghijk'}]}
        self.client.post('/api/sources', json={'id': 'CNN'}, headers=HEADERS)
        with patch('app.main.run_worker', side_effect=worker) as mock:
            result = self.client.post('/api/search', json={'query': 'nature'}, headers=HEADERS).json()
            self.assertEqual(len(result['items']), 1)
            self.assertEqual(result['errors'][0]['source'], 'Dailymotion')
            self.assertIn('CNN', result['skipped'])
            result = self.client.post('/api/search', json={'query': 'nature', 'sources': ['Youtube']}, headers=HEADERS).json()
            self.assertEqual(result['errors'], [])
            self.assertEqual(mock.call_count, 3)
        self.assertEqual(self.client.post('/api/search', json={'query': 'a', 'sources': []}, headers=HEADERS).status_code, 400)
        self.client.patch('/api/sources/Youtube', json={'enabled': False}, headers=HEADERS)
        self.assertEqual(self.client.post('/api/search', json={'query': 'a', 'sources': ['Youtube']}, headers=HEADERS).status_code, 400)

    def test_reject_arbitrary_media_and_serve_range(self):
        for url in ('file:///etc/passwd', 'http://127.0.0.1/', 'https://www.youtube.com:9000/watch?v=abcdefghijk'):
            self.assertEqual(self.client.post('/api/media', json={'url': url}, headers=HEADERS).status_code, 400)
        key = 'a' * 32
        folder = Path(self.folder.name) / 'media' / 'cache' / self.client.get('/api/account/me').json()['user']['id'] / key
        folder.mkdir(parents=True)
        (folder / 'video.mp4').write_bytes(b'0123456789')
        jobs[key] = {'id': key, 'status': 'ready', 'owner':self.client.get('/api/account/me').json()['user']['id']}
        response = self.client.get(f'/api/media/{key}/file', headers={'Range': 'bytes=2-5'})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, b'2345')
        self.assertIn('attachment', self.client.get(f'/api/media/{key}/file?download=true').headers['content-disposition'])
        self.assertEqual(self.client.delete(f'/api/media/{key}', headers=HEADERS).status_code, 200)
        self.assertFalse(folder.exists())

    def test_private_network_is_blocked_after_dns(self):
        import socket
        original = socket.getaddrinfo
        try:
            protect_network()
            for host in ('127.0.0.1', '192.168.0.5', '::1', '169.254.169.254'):
                with self.assertRaises(OSError):
                    socket.getaddrinfo(host, 80)
        finally:
            socket.getaddrinfo = original

    def test_untrusted_metadata_and_security_headers(self):
        item = normalize({'url': 'javascript:bad()', 'thumbnail': 'file:///bad', 'title': '<script>bad</script>'})
        self.assertIsNone(item['url'])
        self.assertIsNone(item['thumbnail'])
        policy = self.client.get('/').headers['content-security-policy']
        self.assertIn("frame-src 'none'", policy)
        self.assertIn("script-src 'self'", policy)
        self.assertEqual(self.client.get('/static/app.js').status_code, 200)

    def test_sponsor_lookup_uses_hash_prefix_and_filters_video(self):
        response = [{'videoID': 'abcdefghijk', 'segments': [{'segment': [2, 5], 'actionType': 'skip'}]}, {'videoID': 'other', 'segments': []}]
        with patch('app.main.urlopen', return_value=io.BytesIO(json.dumps(response).encode())) as request:
            result = self.client.get('/api/sponsors/abcdefghijk').json()
            self.assertEqual(result['segments'][0]['segment'], [2, 5])
            self.assertNotIn('abcdefghijk', request.call_args.args[0])
        self.assertEqual(self.client.get('/api/sponsors/invalid').status_code, 400)
        with patch('app.main.urlopen', side_effect=TimeoutError):
            self.assertEqual(self.client.get('/api/sponsors/abcdefghijk').json()['status'], 'unavailable')

    def test_home_limit_cache_config_changes_and_inactive_sources(self):
        async def worker(payload):
            self.assertEqual(payload['limit'], 10)
            self.assertTrue(payload['home'])
            return {'items':[{'title':str(i), 'url':f'https://example.org/{i}'} for i in range(12)]}
        with patch('app.main.run_worker', side_effect=worker) as run:
            first = self.client.get('/api/home/Youtube').json()
            self.assertEqual(len(first['items']),10)
            self.assertEqual(first['label'],'Recherche : vidéos')
            self.client.get('/api/home/Youtube')
            self.assertEqual(run.call_count,1)
            self.client.patch('/api/sources/Youtube',json={'name':'YouTube modifié'},headers=HEADERS)
            self.assertEqual(self.client.get('/api/home/Youtube').json()['items'][0]['source'],'YouTube modifié')
            self.assertEqual(run.call_count,2)
            self.client.patch('/api/sources/Youtube',json={'enabled':False},headers=HEADERS)
            self.assertEqual(self.client.get('/api/home/Youtube').status_code,404)
            self.client.post('/api/sources',json={'id':'CNN'},headers=HEADERS)
            self.assertEqual(self.client.get('/api/home/CNN').json()['items'],[])
            self.assertEqual(run.call_count,2)

    def test_home_failure_is_retryable_and_does_not_block_other_sources(self):
        async def worker(payload):
            if payload['source']=='Dailymotion':
                raise RuntimeError('Indisponible')
            return {'items':[{'title':'ok','url':'https://example.org/video'}]}
        with patch('app.main.run_worker',side_effect=worker) as run:
            self.assertIn('error',self.client.get('/api/home/Dailymotion').json())
            self.assertEqual(len(self.client.get('/api/home/Youtube').json()['items']),1)
            self.client.get('/api/home/Dailymotion')
            self.assertEqual(run.call_count,3)

    def test_home_rankings_have_separate_cache_and_explicit_support(self):
        from urllib.parse import urlsplit, parse_qs
        async def worker(payload):
            return {'items': [{'title': payload['ranking'], 'url': 'https://example.org/video'}]}
        with patch('app.main.run_worker', side_effect=worker) as run:
            for ranking, sort in [('trending', 'trending'), ('views', 'visited'), ('recent', 'recent')]:
                result = self.client.get(f'/api/home/Dailymotion?ranking={ranking}').json()
                self.assertEqual(result['items'][0]['title'], ranking)
                target = run.call_args.args[0]['connector']['home_url']
                self.assertEqual(parse_qs(urlsplit(target).query)['sort'], [sort])
                self.assertIn('{limit}', target)
            self.client.get('/api/home/Dailymotion?ranking=views')
            self.assertEqual(run.call_count, 3)
            result = self.client.get('/api/home/Youtube?ranking=trending').json()
            self.assertIn('pas disponible', result['message'])
            self.assertEqual(run.call_count, 3)
            self.assertEqual(self.client.get('/api/home/Youtube?ranking=invalid').status_code, 422)
            config = saved_sources()[0]['connector']
            config['home_views_url'] = 'https://example.org/popular?limit={limit}'
            self.client.patch('/api/sources/Dailymotion', json={'connector': config}, headers=HEADERS)
            self.client.get('/api/home/Dailymotion?ranking=views')
            self.assertEqual(run.call_args.args[0]['connector']['home_url'], config['home_views_url'])
            config['home_views_url'] = 'http://127.0.0.1/videos'
            self.assertEqual(self.client.patch('/api/sources/Dailymotion', json={'connector': config}, headers=HEADERS).status_code, 422)
