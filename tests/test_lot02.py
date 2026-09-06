"""Deterministic contracts for the reviewed batch 02 templates. No network is used here."""
import io
import json
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlsplit, parse_qs

from app.connectors import Connector, default_connector, neutralize_query, search_json
from app.failures import classify, SourceFailure
from app.pagination import capabilities, search_config
from app.worker import run

LOT_02 = ['Rokfin', 'RokfinSearch', 'Soundcloud', 'SoundcloudSearch', 'Vimeo', 'VrSquareSearch',
          'YahooSearch', 'Youtube', 'YoutubeMusicSearchURL', 'YoutubeSearch', 'YoutubeSearchURL']


def engine_http_error(status):
    from yt_dlp.networking.exceptions import HTTPError as EngineHTTPError
    response = Mock()
    response.status, response.reason, response.headers = status, 'Error', {}
    return EngineHTTPError(response)


class BatchTemplateTests(unittest.TestCase):
    def test_every_batch_template_is_a_valid_search_connector(self):
        for template_id in LOT_02:
            with self.subTest(template=template_id):
                config = Connector.model_validate(default_connector(template_id))
                self.assertNotEqual(config.kind, 'url')
                self.assertTrue(config.extractor)

    def test_the_reader_query_is_neutralised_only_where_the_template_asks_for_it(self):
        self.assertEqual(default_connector('ArchiveOrg')['query_escape'], 'plain')
        self.assertEqual(default_connector('Dailymotion')['query_escape'], 'none')
        for raw, expected in [(') OR mediatype:audio AND (', 'or mediatype audio and'),
                              ('C++ (tutorial)', 'C tutorial'),
                              ('1920s: silent film', '1920s silent film'),
                              ('()', 'video'),
                              ('café été', 'café été'),
                              ('ANDROID', 'ANDROID')]:
            with self.subTest(query=raw):
                self.assertEqual(neutralize_query(raw, 'plain'), expected)
                self.assertEqual(neutralize_query(raw, 'none'), raw)

    def test_the_neutralised_query_is_what_reaches_the_provider(self):
        opener = Mock()
        opener.open.return_value = io.BytesIO(b'{"response":{"docs":[]}}')
        with patch('app.connectors.build_opener', return_value=opener):
            search_json(default_connector('ArchiveOrg'), 'nature )', 2)
        target = opener.open.call_args.args[0].full_url
        self.assertIn('nature', target)
        self.assertNotIn('%29', target)

    def test_prx_uses_the_cms_api_so_a_vault_token_can_be_attached(self):
        for template_id, path, page in [('PRXStory', '/api/v1/stories/search', 'stories'),
                                        ('PRXSeriesSearch', '/api/v1/series/search', 'series')]:
            with self.subTest(template=template_id):
                config = default_connector(template_id)
                self.assertEqual(config['kind'], 'json')
                parts = urlsplit(config['search_url'])
                self.assertEqual((parts.hostname, parts.path), ('cms.prx.org', path))
                self.assertEqual(config['video_url'], 'https://beta.prx.org/' + page + '/{id}')
                self.assertEqual(config['results_path'], '/_embedded/prx:items')
                self.assertEqual(config['pagination']['mode'], 'page')

    def test_prx_maps_the_hal_payload_documented_by_the_installed_extractor(self):
        payload = json.dumps({'_embedded': {'prx:items': [{
            'id': 247843, 'title': 'Climat', 'description': 'Un sujet', 'duration': 1800,
            'releasedAt': '2026-01-02T00:00:00Z',
            '_embedded': {'prx:image': {'_links': {'enclosure': {'href': 'https://example.org/i.jpg'}}},
                          'prx:account': {'name': 'PRX'}}}]}}).encode()
        opener = Mock()
        opener.open.return_value = io.BytesIO(payload)
        with patch('app.connectors.build_opener', return_value=opener):
            items = search_json(default_connector('PRXStory'), 'climat', 2)
        self.assertEqual(items[0]['webpage_url'], 'https://beta.prx.org/stories/247843')
        self.assertEqual(items[0]['thumbnail'], 'https://example.org/i.jpg')
        self.assertEqual(items[0]['uploader'], 'PRX')
        self.assertEqual(items[0]['duration'], 1800)

    def test_missing_credentials_are_reported_as_an_account_need_not_an_outage(self):
        opener = Mock()
        from urllib.error import HTTPError
        opener.open.side_effect = HTTPError('https://cms.prx.org/api/v1/stories/search', 401, 'no', {}, None)
        with patch('app.connectors.build_opener', return_value=opener):
            with self.assertRaises(HTTPError) as raised:
                search_json(default_connector('PRXStory'), 'climat', 2)
        self.assertEqual(classify(raised.exception).code, 'authentication_required')

    def test_youtube_offers_only_the_ranking_that_changes_the_ordering(self):
        for template_id in ('Youtube', 'YoutubeSearch', 'YoutubeSearchURL'):
            with self.subTest(template=template_id):
                config = default_connector(template_id)
                self.assertEqual(capabilities(config)['search_rankings'], ['default', 'views'])
                ranked = search_config(config, 'views', 'any', 0)
                self.assertEqual(parse_qs(urlsplit(ranked['search_url']).query)['sp'], ['CAMSAhAB'])
        music = default_connector('YoutubeMusicSearchURL')
        self.assertEqual(capabilities(music)['search_rankings'], ['default'])
        self.assertEqual(music['home_kind'], 'feed')

    def test_vimeo_declares_its_documented_sorts_and_still_needs_a_token(self):
        config = default_connector('Vimeo')
        self.assertEqual(capabilities(config)['search_rankings'], ['default', 'views', 'recent'])
        for ranking, sort in (('views', 'plays'), ('recent', 'date')):
            with self.subTest(ranking=ranking):
                ranked = search_config(config, ranking, 'any', 0)
                self.assertEqual(parse_qs(urlsplit(ranked['search_url']).query)['sort'], [sort])
        self.assertEqual(config['extractor'], 'Vimeo')

    def test_no_template_can_present_a_search_as_a_platform_feed(self):
        """The label is derived, not declared: a home URL carrying {query} is a search."""
        from app.catalog import catalog
        for entry in catalog():
            if not entry['search']:
                continue
            config = default_connector(entry['id'])
            home_urls = [config[key] for key in ('home_url', 'home_trending_url',
                                                 'home_views_url', 'home_recent_url') if config[key]]
            if any('{query}' in url for url in home_urls):
                with self.subTest(template=entry['id']):
                    self.assertEqual(config['home_kind'], 'search')
        self.assertEqual(default_connector('Vimeo')['home_kind'], 'search')
        self.assertEqual(default_connector('Dailymotion')['home_kind'], 'feed')

    def test_an_existing_source_that_declared_a_feed_is_corrected_not_refused(self):
        stored = {**default_connector('Vimeo'), 'home_kind': 'feed'}
        self.assertEqual(Connector.model_validate(stored).home_kind, 'search')

    def test_vr_square_home_query_matches_the_catalogue_it_searches(self):
        self.assertEqual(default_connector('VrSquareSearch')['home_query'], 'VR')

    def test_a_listing_refused_entry_by_entry_is_not_reported_as_empty(self):
        from yt_dlp.utils import DownloadError, ExtractorError
        refusal = ExtractorError('VR SQUARE app-only videos are not supported')
        config = default_connector('VrSquareSearch')

        class Listing:
            def __init__(self, opts):
                self.flat = opts.get('extract_flat')

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extract_info(self, url, download=False, **kwargs):
                if self.flat:
                    return {'entries': [{'url': 'https://livr.jp/contents/P1', '_type': 'url'},
                                        {'url': 'https://livr.jp/contents/P2', '_type': 'url'}]}
                raise DownloadError('refused', exc_info=(type(refusal), refusal, None))

        with patch('app.worker.YoutubeDL', Listing):
            with self.assertRaises(SourceFailure) as raised:
                run({'mode': 'search', 'connector': config, 'query': 'VR', 'limit': 2})
        self.assertEqual(raised.exception.code, 'unsupported_media')

    def test_an_app_only_medium_is_not_confused_with_an_outage(self):
        from yt_dlp.utils import ExtractorError
        self.assertEqual(classify(ExtractorError('app-only videos are not supported')).code,
                         'unsupported_media')
        self.assertEqual(classify(ExtractorError('boom', cause=engine_http_error(500))).code,
                         'temporarily_unavailable')


if __name__ == '__main__':
    unittest.main()
