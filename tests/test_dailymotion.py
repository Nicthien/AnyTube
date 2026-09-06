import io
import json
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from app.dailymotion import search_videos
from app.worker import run


class DailymotionSearchTests(unittest.TestCase):
    def response(self, data):
        opener = Mock()
        opener.open.return_value = io.BytesIO(json.dumps(data).encode())
        return opener

    def test_worker_uses_catalog_metadata_without_extracting_media(self):
        opener = self.response({'list': [{
            'id': 'x123abc', 'title': 'Un chat', 'description': 'Un <b>chat</b> &amp; ses amis',
            'thumbnail_480_url': 'https://s1.dmcdn.net/v/abc/x480',
            'duration': 12, 'views_total': 42, 'owner.screenname': 'Les chats',
        }]})
        with patch('app.dailymotion.build_opener', return_value=opener), patch('app.worker.YoutubeDL') as extractor:
            result = run({'mode': 'search', 'source': 'Dailymotion', 'query': 'chat & été', 'limit': 8})
            extractor.assert_not_called()
        item = result['items'][0]
        self.assertEqual(item['title'], 'Un chat')
        self.assertEqual(item['description'], 'Un chat & ses amis')
        self.assertEqual(item['url'], 'https://www.dailymotion.com/video/x123abc')
        self.assertEqual(item['channel'], 'Les chats')
        self.assertEqual(item['views'], 42)
        self.assertTrue(item['thumbnail'].startswith('https://'))
        request = opener.open.call_args.args[0]
        params = parse_qs(urlsplit(request.full_url).query)
        self.assertEqual(params['search'], ['chat & été'])
        self.assertEqual(params['limit'], ['8'])
        self.assertEqual(params['sort'], ['relevance'])

    def test_empty_results_are_distinct_from_invalid_response(self):
        with patch('app.dailymotion.build_opener', return_value=self.response({'list': []})):
            self.assertEqual(search_videos('aucun résultat', 8), [])
        for response in ({}, {'error': 'quota'}, {'list': None}, {'list': [{'id': '../bad', 'title': 'bad'}]}):
            with self.subTest(response=response), patch('app.dailymotion.build_opener', return_value=self.response(response)):
                with self.assertRaises(ValueError):
                    search_videos('chat', 8)

    def test_api_failure_is_not_silently_converted_to_empty_results(self):
        opener = Mock()
        error = HTTPError('https://api.dailymotion.com/videos', 429, 'Limited', {}, None)
        opener.open.side_effect = error
        try:
            with patch('app.dailymotion.build_opener', return_value=opener):
                with self.assertRaises(HTTPError):
                    run({'mode': 'search', 'source': 'Dailymotion', 'query': 'chat', 'limit': 8})
        finally:
            error.close()
