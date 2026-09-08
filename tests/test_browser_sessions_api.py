import os
import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from starlette.websockets import WebSocketDisconnect
from support import TestClient
from app.main import app
from app.store import current_user, connect
from app import browser_state as state


class BrowserSessionsApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        key = Path(self.tmp.name) / 'key'; key.write_bytes(os.urandom(32))
        self.env = patch.dict(os.environ, ANYTUBE_DATA=self.tmp.name, ANYTUBE_VAULT_KEY_FILE=str(key),
            ANYTUBE_INTERACTIVE_URL='http://interactive-browser:8010', ANYTUBE_INTERACTIVE_TOKEN='test-only-token',
            ANYTUBE_PUBLIC_URL='')
        self.env.start()
        self.client = TestClient(app); self.client.__enter__()
        self.headers = {'X-AnyTube': '1'}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.env.stop(); self.tmp.cleanup()

    def create(self):
        response = self.client.post('/api/browser-sessions', json={'url':'https://example.org'}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        return response.json()['id']

    def test_foreign_owner_never_calls_browser(self):
        identifier = self.create()
        with connect() as db:
            db.execute('UPDATE browser_sessions SET owner=? WHERE id=?', ('someone-else', identifier))
        with patch('app.browser_sessions.call', new_callable=AsyncMock) as remote:
            for suffix in ('open', 'validate', 'close'):
                self.assertEqual(self.client.post(f'/api/browser-sessions/{identifier}/{suffix}', headers=self.headers).status_code, 404)
            self.assertEqual(self.client.delete(f'/api/browser-sessions/{identifier}', headers=self.headers).status_code, 404)
            remote.assert_not_called()

    def test_validate_persists_supported_state_and_closes(self):
        identifier = self.create()
        cookie = {'name':'login','value':'private-value','domain':'example.org','path':'/','expires':-1,'secure':True}
        with patch('app.browser_sessions.call', new_callable=AsyncMock, return_value={'revision':'direct','state': {'cookies':[cookie], 'origins':[]}}) as remote:
            result = self.client.post(f'/api/browser-sessions/{identifier}/validate', headers=self.headers)
            self.assertEqual(result.status_code, 200)
            self.assertNotIn('private-value', result.text)
            self.assertEqual(remote.call_count, 2)
            self.assertEqual(remote.call_args.args[1], 'DELETE')
        self.assertEqual(state.read(identifier)['cookies'][0]['value'], 'private-value')

    def test_file_type_limit_and_owner_before_transfer(self):
        identifier = self.create()
        with patch('app.browser_sessions.call', new_callable=AsyncMock, return_value={'transferred':True}) as remote:
            response = self.client.post(f'/api/browser-sessions/{identifier}/file', content=b'<html>not a document</html>', headers=self.headers)
            self.assertEqual(response.status_code, 422); remote.assert_not_called()
            response = self.client.post(f'/api/browser-sessions/{identifier}/file', content=b'%PDF-'+b'x'*(20*1024*1024), headers=self.headers)
            self.assertEqual(response.status_code, 413); remote.assert_not_called()
            response = self.client.post(f'/api/browser-sessions/{identifier}/file', content=b'%PDF-1.7\nfixture', headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(remote.call_count, 1)

    def test_websocket_foreign_origin_is_rejected(self):
        identifier = self.create()
        with self.assertRaises(WebSocketDisconnect) as failure:
            with self.client.websocket_connect(f'/api/browser-sessions/{identifier}/screen', headers={'Origin':'https://evil.example'}):
                pass
        self.assertEqual(failure.exception.code, 1008)

    def test_expired_encrypted_state_is_pruned(self):
        identifier = self.create()
        with connect() as db:
            db.execute('UPDATE browser_sessions SET expires=? WHERE id=?', (time.time()-1, identifier))
        state.prune()
        self.assertEqual(self.client.get(f'/api/browser-sessions/{identifier}').status_code, 404)

    def test_runtime_integrated_browser_keeps_saved_preferences(self):
        from app import source_assistant as assistant
        with patch.object(assistant, 'settings', return_value=assistant.Settings()) as saved:
            self.assertTrue(assistant.runtime_settings().browser.url.endswith(':8010'))
            self.assertEqual(assistant.service_headers('browser'), {'Authorization':'Bearer test-only-token'})

    def test_access_pause_resume_then_normal_search(self):
        from app import source_assistant as assistant
        from discovery_fixtures import fetch, json_worker, Opener
        async def gate(url, **kwargs):
            return {'text':'{}' if url.endswith('/api/v1/config') else '<dialog open><h1>Age verification</h1></dialog>',
                    'url':url,'status':200,'content_type':'text/html'}
        with patch.object(assistant,'launch'), patch.object(assistant,'settings',return_value=assistant.Settings()), \
             patch.object(assistant,'http',side_effect=gate):
            job=self.client.post('/api/source-assistant/jobs',json={'target':'https://example.org/html/'},headers=self.headers).json()
            asyncio.run(assistant.execute(job['id']))
        paused=self.client.get('/api/source-assistant/jobs/'+job['id']).json()
        self.assertEqual(paused['status'],'intervention_needed')
        self.assertEqual(paused['access_type'],'age_verification')
        self.assertGreater(paused['remaining_seconds'],0)
        self.assertEqual(paused['metrics']['ai_calls'],0)
        identifier=self.create()
        state.save(identifier,{'cookies':[],'origins':[]},explicitly_validated=True)
        with patch.object(assistant,'launch'), patch.object(assistant,'settings',return_value=assistant.Settings()), \
             patch.object(assistant,'http',side_effect=fetch),patch('app.main._run_worker',side_effect=json_worker), \
             patch('app.connectors.build_opener',return_value=Opener()):
            resumed=self.client.post('/api/source-assistant/jobs/'+job['id']+'/resume',
                                    json={'browser_session_id':identifier},headers=self.headers)
            self.assertEqual(resumed.status_code,201,resumed.text)
            child=resumed.json()
            asyncio.run(assistant.execute(child['id']))
            saved=self.client.get('/api/source-assistant/jobs/'+child['id']).json()
            self.assertEqual(saved['status'],'added',saved.get('message'))
            self.assertEqual(state.get(identifier)['source'],saved['added_source'])
            result=self.client.post('/api/search',json={'query':'science','sources':[saved['added_source']],'limit':3},headers=self.headers).json()
            self.assertEqual(len(result['items']),3)
            self.assertFalse(result['errors'])
