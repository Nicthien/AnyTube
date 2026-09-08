import json
import unittest
from unittest.mock import AsyncMock,patch
from app import source_assistant as sa

CANDIDATE={'search_url':'https://example.org/search?q={query}'}
URL='https://example.org/watch/1'


class EvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_rendered_metadata_when_initial_player_is_empty(self):
        responses=[{'text':'<video></video>'},{'text':json.dumps({'url':URL,'html':'<video src="/movie.mp4"></video>','requests':2})}]
        with patch.object(sa,'http',new=AsyncMock(side_effect=responses)) as fetch,patch.object(sa,'settings',return_value=sa.Settings(browser=sa.Service(url='http://observer:8010'))),patch.object(sa,'service_headers',return_value={}):
            self.assertEqual(await sa.confirm_video_page(URL,CANDIDATE),'rendered_metadata')
            request=fetch.call_args.kwargs
            self.assertTrue(request['trusted'])
            self.assertFalse(request['body']['submit_search'])
            from app.assistant_browser import Observation
            Observation.model_validate(request['body'])

    async def test_empty_rendered_player_is_not_evidence(self):
        responses=[{'text':'<video></video>'},{'text':json.dumps({'url':URL,'html':'<video></video>'})}]
        with patch.object(sa,'http',new=AsyncMock(side_effect=responses)),patch.object(sa,'settings',return_value=sa.Settings(browser=sa.Service(url='http://observer:8010'))),patch.object(sa,'service_headers',return_value={}):
            with self.assertRaisesRegex(sa.VideoEvidenceMissing,'après rendu'):await sa.confirm_video_page(URL,CANDIDATE)

    async def test_browser_missing_explained_without_weakening_validation(self):
        with patch.object(sa,'http',new=AsyncMock(return_value={'text':'<video></video>'})),patch.object(sa,'settings',return_value=sa.Settings()):
            with self.assertRaisesRegex(sa.VideoEvidenceMissing,'non configuré'):await sa.confirm_video_page(URL,CANDIDATE)

    async def test_valid_http_does_not_need_browser(self):
        with patch.object(sa,'http',new=AsyncMock(return_value={'text':'<video src="/video.mp4"></video>'})),patch.object(sa,'settings') as settings:
            self.assertEqual(await sa.confirm_video_page(URL,CANDIDATE),'http_metadata')
            settings.assert_not_called()

    async def test_private_rendered_destination_rejected(self):
        responses=[{'text':''},{'text':json.dumps({'url':'http://127.0.0.1/private','html':'<video src="https://example.org/video.mp4"></video>'})}]
        with patch.object(sa,'http',new=AsyncMock(side_effect=responses)),patch.object(sa,'settings',return_value=sa.Settings(browser=sa.Service(url='http://observer:8010'))),patch.object(sa,'service_headers',return_value={}):
            with self.assertRaises(sa.VideoEvidenceMissing):await sa.confirm_video_page(URL,CANDIDATE)
