import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from app import browser_state as bs
from app.store import initialize, current_user, connect
from app.interactive_browser import file_type


class BrowserStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        key = Path(self.tmp.name) / 'vault.key'
        key.write_bytes(os.urandom(32))
        self.env = patch.dict(os.environ, ANYTUBE_DATA=self.tmp.name, ANYTUBE_VAULT_KEY_FILE=str(key))
        self.env.start()
        self.context = current_user.set('alice')
        initialize(); bs.initialize()

    def tearDown(self):
        current_user.reset(self.context)
        self.env.stop(); self.tmp.cleanup()

    def state(self):
        return {'cookies': [{'name': 'session', 'value': 'sensitive-value', 'domain': 'example.org',
                            'path': '/private', 'expires': -1, 'secure': True, 'httpOnly': True, 'sameSite': 'Lax'}],
                'origins': [{'origin': 'https://example.org', 'localStorage': [{'name': 'auth', 'value': 'secret-storage'}]}]}

    def test_encrypted_roundtrip_and_isolation(self):
        session = bs.create('https://example.org/page')
        bs.save(session['id'], self.state(), explicitly_validated=True)
        self.assertEqual(bs.read(session['id']), self.state())
        with connect() as db:
            raw = db.execute('SELECT encrypted FROM browser_sessions').fetchone()[0]
        self.assertNotIn('sensitive-value', raw)
        self.assertNotIn('secret-storage', raw)
        token = current_user.set('bob')
        try:
            with self.assertRaises(HTTPException) as error: bs.read(session['id'])
            self.assertEqual(error.exception.status_code, 404)
        finally: current_user.reset(token)

    def test_no_sliding_expiration(self):
        session = bs.create('https://example.org')
        bs.save(session['id'], self.state())
        self.assertEqual(bs.get(session['id'])['expires'], session['expires'])
        with patch('app.browser_state.time.time', return_value=session['expires'] + 1):
            with self.assertRaises(HTTPException): bs.read(session['id'])
        with self.assertRaises(HTTPException): bs.get(session['id'])

    def test_revision_and_deleted_source(self):
        session = bs.create('https://example.org', revision='route-a')
        with self.assertRaises(HTTPException): bs.read(session['id'], revision='route-b')
        with self.assertRaises(HTTPException): bs.create('https://example.org', source='foreign')
        bs.delete(session['id'])
        with self.assertRaises(HTTPException): bs.read(session['id'])

    def test_bound_expiry_keeps_marker_without_authentication(self):
        session = bs.create('https://example.org')
        bs.save(session['id'], self.state(), explicitly_validated=True)
        with connect() as db:
            db.execute("UPDATE browser_sessions SET source='fixture',expires=? WHERE id=?",
                       (time.time()-1, session['id']))
        bs.prune()
        self.assertEqual(bs.get(session['id'])['encrypted'], '')
        self.assertEqual(bs.metadata(bs.get(session['id']))['state'], 'expired')
        for _ in range(2):
            with self.assertRaises(HTTPException) as error: bs.read(session['id'])
            self.assertEqual(error.exception.status_code, 409)

    def test_domain_path_secure_and_expiry(self):
        state = self.state()
        self.assertEqual(bs.cookie_header(state, 'https://example.org/private/a'), 'session=sensitive-value')
        for url in ('https://example.org/privately', 'http://example.org/private', 'https://evil.example/private', 'https://sub.example.org/private'):
            self.assertEqual(bs.cookie_header(state, url), '')
        state['cookies'][0]['expires'] = time.time()-1
        self.assertEqual(bs.cookie_header(state, 'https://example.org/private'), '')

    def test_state_allowlist(self):
        state = self.state()
        state['screenshots'] = ['secret']
        state['cookies'].append({**state['cookies'][0], 'domain': 'other.example'})
        state['origins'].append({'origin': 'https://other.example', 'localStorage': []})
        result = bs.sanitize_state(state, 'https://example.org')
        self.assertEqual(result, self.state())
        with self.assertRaises(HTTPException): bs.sanitize_state({'raw': 'x'*bs.STATE_LIMIT}, 'https://example.org')

    def test_files(self):
        self.assertEqual(file_type(b'%PDF-1.7\nfixture')[0], 'application/pdf')
        self.assertEqual(file_type(b'\x89PNG\r\n\x1a\nfixture')[0], 'image/png')
        self.assertEqual(file_type(b'\xff\xd8\xfffixture')[0], 'image/jpeg')
        with self.assertRaises(HTTPException): file_type(b'<html>not a pdf</html>')


class GenericCardsTests(unittest.TestCase):
    def test_attached_identifier_and_opaque_paths(self):
        from app.html_search import infer
        for prefix in ('/video-', '/opaque/'):
            html = '<main>' + ''.join(f'<article class="clip"><a href="{prefix}{i}"><img src="/thumb/{i}.jpg"></a><h2><a href="{prefix}{i}">Documentary {i}</a></h2></article>' for i in range(4)) + '</main>'
            candidates = infer(html, 'https://example.org/search?q=one', 'https://example.org/search?q={query}')
            self.assertTrue(candidates, prefix)

    def test_age_gate_not_result_title(self):
        from app.search_response import classify
        self.assertEqual(classify('<dialog open><h1>Age verification</h1></dialog>', 'https://example.org')[0], 'access_required')
        self.assertEqual(classify('<main><article><h2>Age verification documentary</h2></article></main>', 'https://example.org')[0], 'usable')
        self.assertEqual(classify('<dialog hidden aria-hidden="true">Verify your age</dialog><main>Results</main>', 'https://example.org')[0], 'usable')


class InteractiveLimitsTests(unittest.IsolatedAsyncioTestCase):
    async def test_quota_is_checked_before_browser_launch(self):
        from starlette.requests import Request
        from app.interactive_browser import Open, live, open_session
        request = Request({'type':'http','headers':[(b'authorization',b'Bearer fixture-token')]})
        body = Open(owner='alice', url='https://example.org')
        with patch.dict(os.environ, ANYTUBE_BROWSER_TOKEN='fixture-token'):
            for sessions in ({'a':{'owner':'alice','activity':time.monotonic()}},
                             {'a':{'owner':'bob','activity':time.monotonic()},'b':{'owner':'carol','activity':time.monotonic()}}):
                with patch.dict(live, sessions, clear=True):
                    with self.assertRaises(HTTPException) as error:
                        await open_session('new', body, request)
                    self.assertEqual(error.exception.status_code,409)

    async def test_open_identifier_cannot_change_owner(self):
        from starlette.requests import Request
        from app.interactive_browser import Open, live, open_session
        request = Request({'type':'http','headers':[(b'authorization',b'Bearer fixture-token')]})
        with patch.dict(os.environ, ANYTUBE_BROWSER_TOKEN='fixture-token'), \
             patch.dict(live, {'existing':{'owner':'bob','activity':time.monotonic()}}, clear=True):
            with self.assertRaises(HTTPException) as error:
                await open_session('existing', Open(owner='alice',url='https://example.org'), request)
            self.assertEqual(error.exception.status_code,403)
