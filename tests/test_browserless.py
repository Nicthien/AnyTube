import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlsplit
from app.assistant_browser import open_browser, context_options, search_priority
from app.assistant_http import fetch


class BrowserlessTests(unittest.IsolatedAsyncioTestCase):
    async def test_general_search_preferred_over_cinema_location(self):
        self.assertEqual(search_priority({'name':'q','placeholder':'Rechercher une salle : Nice, 75001'}),-1)
        self.assertGreater(search_priority({'name':'q','placeholder':'Rechercher un film'}),search_priority({'name':'q'}))
    async def test_remote_token_and_isolated_context(self):
        p=AsyncMock()
        with patch.dict(os.environ, {'ANYTUBE_BROWSER_CDP_URL':'ws://browserless:3000/chromium','ANYTUBE_BROWSER_CDP_TOKEN':'test-secret'}):
            await open_browser(p)
        target=p.chromium.connect_over_cdp.call_args.args[0]
        self.assertEqual(parse_qs(urlsplit(target).query)['token'],['test-secret'])
        p.chromium.launch.assert_not_called()
        self.assertEqual(context_options()['service_workers'],'block')
        self.assertEqual(context_options()['proxy']['server'],'http://127.0.0.1:9')

    async def test_invalid_remote_scheme(self):
        with patch.dict(os.environ, {'ANYTUBE_BROWSER_CDP_URL':'file:///tmp/browser'}):
            with self.assertRaises(ValueError):
                await open_browser(AsyncMock())

    async def test_http_service_deadline_and_cors_without_cookies(self):
        opener=MagicMock()
        response=opener.open.return_value.__enter__.return_value
        response.read.return_value=b'{}'
        response.url='http://service/observe'
        response.headers={'Content-Type':'application/json','Access-Control-Allow-Origin':'https://example.org','Set-Cookie':'private=secret'}
        with patch('app.assistant_http.build_opener',return_value=opener), patch.dict(os.environ,{},clear=True):
            value=fetch({'url':'http://service/observe','trusted':True,'timeout':94})
        self.assertEqual(opener.open.call_args.kwargs['timeout'],94)
        self.assertEqual(value['headers'],{'Access-Control-Allow-Origin':'https://example.org'})
