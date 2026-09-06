import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from support import TestClient
from pydantic import ValidationError
from app.connectors import Connector, default_connector, pointer, search_json, PublicRedirect
from app.main import app, validate_url
from app.store import initialize, saved_sources
from app.worker import run

HEADERS = {'X-AnyTube': '1'}


class ConnectorTests(unittest.TestCase):
    def test_home_feed_uses_configured_url_and_validates_it(self):
        config = default_connector('Dailymotion')
        opener = Mock()
        opener.open.return_value = io.BytesIO(b'{"list":[]}')
        with patch('app.connectors.build_opener',return_value=opener):
            run({'mode':'search','connector':config,'query':'vidéos','limit':10,'home':True})
        target = opener.open.call_args.args[0].full_url
        self.assertIn('sort=recent',target)
        self.assertIn('limit=10',target)
        self.assertNotIn('search=',target)
        with self.assertRaises(ValueError):
            Connector.model_validate({**config,'home_url':'http://127.0.0.1/?q={query}'})

    def test_default_dailymotion_and_nested_mapping(self):
        config = default_connector('Dailymotion')
        opener = Mock()
        opener.open.return_value = io.BytesIO(json.dumps({'list':[{'id':'abc','title':'Chat','thumbnail_480_url':'https://example.org/image.jpg','owner.screenname':'Auteur','duration':'12','views_total':42}]}).encode())
        with patch('app.connectors.build_opener', return_value=opener):
            result = run({'mode':'search','connector':config,'query':'chat & été','limit':3})
        self.assertEqual(result['items'][0]['url'], 'https://www.dailymotion.com/video/abc')
        self.assertEqual(result['items'][0]['channel'], 'Auteur')
        self.assertEqual(result['items'][0]['duration'], 12)
        self.assertIn('chat%20%26%20%C3%A9t%C3%A9', opener.open.call_args.args[0].full_url)
        self.assertEqual(pointer({'a/b':{'~key':[{'title':'ok'}]}}, '/a~1b/~0key/0/title'), 'ok')

    def test_bad_templates_private_destinations_and_mapping_fail_closed(self):
        config = default_connector('Dailymotion')
        for url in ('file:///etc/passwd?q={query}', 'https://{query}.example.org/api', 'http://127.0.0.1?q={query}', 'http://localhost/?q={query}', 'https://example.org/?q={query.__class__}', 'https://example.org/?q={unknown}'):
            with self.subTest(url=url), self.assertRaises((ValueError, ValidationError)):
                Connector.model_validate({**config, 'search_url':url})
        opener = Mock()
        opener.open.return_value = io.BytesIO(b'{"results":[]}')
        with patch('app.connectors.build_opener', return_value=opener), self.assertRaisesRegex(ValueError,'liste JSON'):
            search_json(config, 'chat', 3)
        with self.assertRaises(ValueError):
            PublicRedirect().redirect_request(None, None, 302, '', {}, 'http://192.168.0.5/private')

    def test_oversized_response(self):
        opener = Mock()
        opener.open.return_value = io.BytesIO(b' ' * (2 * 1024 * 1024 + 1))
        with patch('app.connectors.build_opener', return_value=opener), self.assertRaisesRegex(ValueError,'2 Mo'):
            search_json(default_connector('Dailymotion'), 'chat', 3)

    def test_migration_manual_creation_edit_search_and_test_without_save(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'ANYTUBE_DATA':folder}):
            db = sqlite3.connect(Path(folder)/'anytube.db')
            db.execute('CREATE TABLE sources(id TEXT PRIMARY KEY,name TEXT,enabled INTEGER DEFAULT 1)')
            db.execute("INSERT INTO sources VALUES ('Vimeo','Mon Vimeo',0)")
            db.commit(); db.close()
            with TestClient(app) as client:
                self.assertEqual(next(s for s in saved_sources() if s['id']=='Vimeo')['name'], 'Mon Vimeo')
                config = default_connector('Dailymotion')
                body={'name':'Source manuelle','connector':config}
                response=client.post('/api/sources',json=body,headers=HEADERS)
                self.assertEqual(response.status_code,201,response.text)
                key=response.json()['id']
                self.assertTrue(response.json()['search'])
                config['mapping']['title']='/custom_title'
                self.assertEqual(client.patch(f'/api/sources/{key}',json={'name':'Mon API','connector':config},headers=HEADERS).status_code,200)
                initialize()
                saved=next(s for s in saved_sources() if s['id']==key)
                self.assertEqual(saved['connector']['mapping']['title'],'/custom_title')
                async def worker(payload):
                    self.assertEqual(payload['connector']['mapping']['title'],'/custom_title')
                    return {'items':[{'title':'Chat','url':'https://www.dailymotion.com/video/abc'}]}
                count=len(saved_sources())
                with patch('app.main.run_worker',side_effect=worker):
                    result=client.post('/api/search',json={'query':'chat','sources':[key]},headers=HEADERS)
                    self.assertEqual(result.json()['items'][0]['source'],'Mon API')
                    self.assertEqual(client.post('/api/connectors/test',json={'query':'chat','connector':config},headers=HEADERS).status_code,200)
                self.assertEqual(len(saved_sources()),count)
                self.assertEqual(client.post('/api/sources',json={'name':'bad','connector':{**config,'extractor':'unknown'}},headers=HEADERS).status_code,400)
                self.assertEqual(client.post('/api/connectors/test',json={'query':'chat','connector':{**config,'search_url':'http://localhost/?q={query}'}},headers=HEADERS).status_code,422)
                client.delete('/api/sources/Dailymotion',headers=HEADERS)
                validate_url('https://www.dailymotion.com/video/x1zzbf')
                self.assertEqual(client.delete(f'/api/sources/{key}',headers=HEADERS).status_code,200)
