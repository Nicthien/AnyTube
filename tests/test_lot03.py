"""Contracts observed in the public NRK search API; no outgoing requests."""
import io
import json
import unittest
from unittest.mock import Mock, patch
from app.connectors import Connector, default_connector, search_json


class NewSourceTests(unittest.TestCase):
    def test_microsoft_native_offset_does_not_expand_page_size(self):
        from urllib.parse import parse_qs, urlsplit
        payload = {'count': 145, 'results': [{'uid': 'azure', 'title': 'Azure', 'url': '/shows/azure/'}]}
        opener = Mock()
        opener.open.return_value = io.BytesIO(json.dumps(payload).encode())
        with patch('app.connectors.build_opener', return_value=opener):
            page = search_json(default_connector('MicrosoftLearnPlaylist'), 'azure', 3, offset=120, return_page=True)
        query = parse_qs(urlsplit(opener.open.call_args.args[0].full_url).query)
        self.assertEqual(query['$skip'], ['120'])
        self.assertEqual(query['$top'], ['3'])
        self.assertTrue(page['has_more'])
        self.assertEqual(page['items'][0]['webpage_url'], 'https://learn.microsoft.com/shows/azure/')

    def test_apple_episode_duration_is_converted_from_milliseconds(self):
        payload = {'results': [{'trackId': 1, 'trackName': 'Episode', 'trackTimeMillis': 1660000,
                               'trackViewUrl': 'https://podcasts.apple.com/fr/podcast/test/id123?i=456'}]}
        opener = Mock()
        opener.open.return_value = io.BytesIO(json.dumps(payload).encode())
        with patch('app.connectors.build_opener', return_value=opener):
            items = search_json(default_connector('ApplePodcasts'), 'science', 3)
        self.assertEqual(items[0]['duration'], 1660)
        self.assertIn('entity=podcastEpisode', opener.open.call_args.args[0].full_url)

    def test_wikimedia_last_page_and_empty_search(self):
        for payload, expected in [
            ({'query': {'searchinfo': {'totalhits': 0}}}, 0),
            ({'query': {'searchinfo': {'totalhits': 4}, 'pages': [
                {'pageid': 1, 'title': 'File:Example.webm', 'imageinfo': [
                    {'descriptionurl': 'https://commons.wikimedia.org/wiki/File:Example.webm', 'duration': 12}]}]}}, 1),
        ]:
            opener = Mock()
            opener.open.return_value = io.BytesIO(json.dumps(payload).encode())
            with patch('app.connectors.build_opener', return_value=opener):
                page = search_json(default_connector('Wikimedia'), 'nature', 3, offset=3, return_page=True)
            self.assertEqual(len(page['items']), expected)
            self.assertFalse(page['has_more'])
            request = opener.open.call_args.args[0]
            self.assertIn('gsroffset=3', request.full_url)
            self.assertIn('AnyTube', request.get_header('User-agent'))

    def test_missing_total_is_not_misreported_as_empty(self):
        opener = Mock()
        opener.open.return_value = io.BytesIO(b'{"error":{"code":"badrequest"}}')
        with patch('app.connectors.build_opener', return_value=opener), self.assertRaises(ValueError):
            search_json(default_connector('Wikimedia'), 'nature', 3)

    def test_nrk_relative_urls_point_to_tv_not_api(self):
        response = {'hits': [{'hit': {'id': 'natur-i-endring', 'title': 'Natur i endring',
                                     'url': 'serie/natur-i-endring'}}]}
        opener = Mock()
        opener.open.return_value = io.BytesIO(json.dumps(response).encode())
        with patch('app.connectors.build_opener', return_value=opener):
            page = search_json(default_connector('NRKTV'), 'natur', 6, return_page=True)
        self.assertEqual(page['items'][0]['webpage_url'], 'https://tv.nrk.no/serie/natur-i-endring')
        self.assertFalse(page['native_page'])
        self.assertIn('maxResultsPerPage=6', opener.open.call_args.args[0].full_url)

    def test_nrk_flat_collection_locator_becomes_public_program_url(self):
        from app.worker import normalize
        self.assertEqual(normalize({'url': 'nrk:DVNA25000118'})['url'],
                         'https://tv.nrk.no/program/DVNA25000118')
        self.assertIsNone(normalize({'url': 'nrk:../../private'})['url'])

    def test_url_base_rejects_private_hosts_and_variables(self):
        for base in ('http://127.0.0.1/', 'https://{query}.example.org/', 'https://example.org/{query}'):
            with self.subTest(base=base), self.assertRaises(ValueError):
                Connector.model_validate({**default_connector('NRKTV'), 'result_base_url': base})

    def test_remote_result_cannot_use_base_to_hide_private_url(self):
        response = {'hits': [{'hit': {'id': 'one', 'title': 'Invalid', 'url': '//127.0.0.1/private'}}]}
        opener = Mock()
        opener.open.return_value = io.BytesIO(json.dumps(response).encode())
        with patch('app.connectors.build_opener', return_value=opener), self.assertRaises(ValueError):
            search_json(default_connector('NRKTV'), 'natur', 3)
