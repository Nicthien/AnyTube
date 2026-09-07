"""Deterministic contracts for the reviewed batch 01 templates. No network is used here."""
import io
import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.parse import urlsplit, parse_qs

from pydantic import ValidationError
from support import TestClient
from app.connectors import Connector, default_connector, search_json
from app.failures import classify, SourceFailure
from app.main import app
from app.pagination import capabilities, search_config
from app.worker import run

HEADERS = {'X-AnyTube': '1'}

LOT_01 = ['ArchiveOrg', 'BiliBili', 'BiliBiliSearch', 'Dailymotion', 'DailymotionSearch',
          'GameJolt', 'GameJoltSearch', 'GoogleSearch', 'MailRuMusicSearch', 'Niconico',
          'NicovideoSearch', 'NicovideoSearchDate', 'NicovideoSearchURL', 'PRXSeries',
          'PRXSeriesSearch', 'PRXStoriesSearch', 'PRXStory', 'PeerTube', 'PeerTubePlaylist',
          'RedGifsSearch']


def engine_http_error(status, headers=None):
    from yt_dlp.networking.exceptions import HTTPError as EngineHTTPError
    response = Mock()
    response.status = status
    response.reason = 'Error'
    response.headers = headers or {}
    return EngineHTTPError(response)


class FailureClassificationTests(unittest.TestCase):
    def test_engine_http_errors_are_classified_like_urllib_ones(self):
        from yt_dlp.utils import ExtractorError, DownloadError
        wrapped = ExtractorError('Unable to download JSON metadata', cause=engine_http_error(401))
        self.assertEqual(classify(wrapped).code, 'authentication_required')
        self.assertEqual(classify(DownloadError('boom', exc_info=(type(wrapped), wrapped, None))).code,
                         'authentication_required')
        limited = classify(ExtractorError('slow down', cause=engine_http_error(429, {'Retry-After': '120'})))
        self.assertEqual((limited.code, limited.retry_after), ('rate_limited', 120))
        self.assertEqual(classify(HTTPError('https://example.org', 401, 'no', {}, None)).code,
                         'authentication_required')

    def test_an_anti_crawler_gate_is_reported_as_a_quota_not_an_outage(self):
        from yt_dlp.utils import ExtractorError
        gated = classify(ExtractorError('Unable to download JSON metadata', cause=engine_http_error(412)))
        self.assertEqual((gated.code, gated.retry_after), ('rate_limited', 60))

    def test_forbidden_alone_is_not_an_account_problem(self):
        from yt_dlp.utils import ExtractorError
        self.assertEqual(classify(ExtractorError('nope', cause=engine_http_error(403))).code,
                         'temporarily_unavailable')
        explicit = ExtractorError('This video is only available for registered users',
                                  cause=engine_http_error(403))
        self.assertEqual(classify(explicit).code, 'authentication_required')

    def test_known_failures_keep_their_own_code(self):
        self.assertEqual(classify(SourceFailure('drm_protected')).code, 'drm_protected')
        self.assertEqual(classify(TimeoutError()).code, 'timeout')
        self.assertEqual(classify(ValueError('other')).code, 'temporarily_unavailable')

    def test_nrk_explicit_regional_refusal_survives_download_wrapper(self):
        from yt_dlp.utils import ExtractorError, DownloadError
        regional = ExtractorError('NRK said: Ikke tilgjengelig utenfor Norge', expected=True)
        wrapped = DownloadError('download failed', exc_info=(type(regional), regional, None))
        self.assertEqual(classify(wrapped).code, 'geo_restricted')
        self.assertEqual(classify(ExtractorError('NRK said: Ikke tilgjengelig')).code,
                         'temporarily_unavailable')


class BatchTemplateTests(unittest.TestCase):
    def test_every_batch_template_is_a_valid_search_connector(self):
        for template_id in LOT_01:
            with self.subTest(template=template_id):
                config = Connector.model_validate(default_connector(template_id))
                self.assertNotEqual(config.kind, 'url')
                self.assertTrue(config.extractor)

    def test_niconico_uses_the_official_snapshot_api_with_offset_pagination(self):
        config = default_connector('Niconico')
        self.assertEqual(config['kind'], 'json')
        self.assertEqual(urlsplit(config['search_url']).hostname, 'snapshot.search.nicovideo.jp')
        self.assertEqual((config['pagination']['mode'], config['pagination']['parameter']), ('offset', '_offset'))
        self.assertEqual(config['video_url'], 'https://www.nicovideo.jp/watch/{id}')
        self.assertEqual(default_connector('NicovideoSearchDate')['search_url'][-len('-startTime'):], '-startTime')
        payload = json.dumps({'data': [{'contentId': 'sm9', 'title': 'Titre', 'viewCounter': 12,
                                        'lengthSeconds': 30, 'thumbnailUrl': 'https://example.org/i.jpg'}]}).encode()
        opener = Mock()
        opener.open.return_value = io.BytesIO(payload)
        with patch('app.connectors.build_opener', return_value=opener):
            items = search_json(config, 'chat & été', 3)
        target = opener.open.call_args.args[0].full_url
        self.assertIn('chat%20%26%20%C3%A9t%C3%A9', target)
        self.assertEqual(items[0]['webpage_url'], 'https://www.nicovideo.jp/watch/sm9')
        self.assertEqual(items[0]['duration'], 30)

    def test_blank_template_parameters_survive_native_pagination(self):
        """The Niconico home listing is an empty q; dropping it makes the API answer 400."""
        config = default_connector('Niconico')
        opener = Mock()
        opener.open.return_value = io.BytesIO(b'{"data":[]}')
        with patch('app.connectors.build_opener', return_value=opener):
            search_json(config, 'vidéos', 3, home=True, offset=3, return_page=True)
        query = parse_qs(urlsplit(opener.open.call_args.args[0].full_url).query, keep_blank_values=True)
        self.assertEqual(query['q'], [''])
        self.assertEqual(query['_offset'], ['3'])
        self.assertEqual(query['_limit'], ['3'])

    def test_declarative_search_rankings_replace_the_search_url(self):
        config = default_connector('ArchiveOrg')
        self.assertEqual(capabilities(config)['search_rankings'], ['default', 'views', 'recent', 'trending'])
        for ranking in ('views', 'recent', 'trending'):
            with self.subTest(ranking=ranking):
                ranked = search_config(config, ranking, 'any', 0)
                self.assertEqual(ranked['search_url'], config[f'search_{ranking}_url'])
                self.assertIn('{query}', ranked['search_url'])
        self.assertEqual(search_config(config, 'default', 'any', 0)['search_url'], config['search_url'])

    def test_dailymotion_filters_and_youtube_fallback_are_unchanged(self):
        config = default_connector('Dailymotion')
        ranked = search_config(config, 'views', 'short', 7)
        query = parse_qs(urlsplit(ranked['search_url']).query)
        self.assertEqual(query['sort'], ['visited'])
        self.assertEqual(query['shorter_than'], ['4'])
        self.assertIn('created_after', query)
        self.assertIn('{limit}', ranked['search_url'])
        youtube = search_config(default_connector('Youtube'), 'views', 'any', 0)
        self.assertIn('sp=CAMSAhAB', youtube['search_url'])

    def test_saved_sources_without_the_new_fields_keep_their_capabilities(self):
        legacy = {key: value for key, value in default_connector('Dailymotion').items()
                  if not key.startswith('search_') or key == 'search_url'}
        legacy.pop('home_kind', None)
        legacy.pop('item_url', None)
        current = capabilities(default_connector('Dailymotion'))
        self.assertEqual(capabilities(legacy)['search_rankings'], current['search_rankings'])
        self.assertEqual(capabilities(legacy)['home_rankings'], current['home_rankings'])

    def test_item_url_rebuilds_listing_entries_that_share_the_search_page(self):
        config = default_connector('MailRuMusicSearch')
        self.assertEqual(config['item_url'], 'https://my.mail.ru/music/songs/track-{id}')
        entries = [{'id': 'a b/1', 'title': 'Piste 1', 'webpage_url': 'https://my.mail.ru/music/search/nature'},
                   {'id': 'ff02', 'title': 'Piste 2', 'webpage_url': 'https://my.mail.ru/music/search/nature'}]
        with patch('app.worker.YoutubeDL') as downloader:
            downloader.return_value.__enter__.return_value.extract_info.return_value = {'entries': entries}
            result = run({'mode': 'search', 'connector': config, 'query': 'nature', 'limit': 2})
        self.assertEqual([item['url'] for item in result['items']],
                         ['https://my.mail.ru/music/songs/track-a%20b%2F1',
                          'https://my.mail.ru/music/songs/track-ff02'])
        self.assertTrue(downloader.call_args.args[0]['ignore_no_formats_error'])

    def test_item_url_is_validated_and_limited_to_ytdlp_connectors(self):
        base = default_connector('MailRuMusicSearch')
        for value in ('http://127.0.0.1/{id}', 'https://{id}.example.org/', 'https://example.org/{unknown}'):
            with self.subTest(value=value), self.assertRaises((ValueError, ValidationError)):
                Connector.model_validate({**base, 'item_url': value})
        with self.assertRaises((ValueError, ValidationError)):
            Connector.model_validate({**default_connector('Dailymotion'), 'item_url': 'https://example.org/{id}'})

    def test_listing_modes_tolerate_entries_without_playable_formats(self):
        """GameJolt search returns community posts; a post without media must not lose the page."""
        config = default_connector('GameJoltSearch')
        with patch('app.worker.YoutubeDL') as downloader:
            downloader.return_value.__enter__.return_value.extract_info.return_value = {'entries': []}
            run({'mode': 'search', 'connector': config, 'query': 'pixel', 'limit': 3})
            self.assertTrue(downloader.call_args.args[0]['ignore_no_formats_error'])
            downloader.return_value.__enter__.return_value.extract_info.return_value = {'_type': 'playlist', 'entries': []}
            run({'mode': 'collection', 'url': 'https://gamejolt.com/@someone', 'connector': config, 'limit': 3})
            self.assertTrue(downloader.call_args.args[0]['ignore_no_formats_error'])

    def test_media_preparation_still_refuses_sources_without_formats(self):
        config = default_connector('GameJoltSearch')
        with patch('app.worker.YoutubeDL') as downloader:
            downloader.return_value.__enter__.return_value.extract_info.return_value = {'formats': []}
            with tempfile.TemporaryDirectory() as folder, self.assertRaises(Exception):
                run({'mode': 'media', 'url': 'https://gamejolt.com/p/abcdefgh', 'folder': folder,
                     'connector': config})
            self.assertNotIn('ignore_no_formats_error', downloader.call_args.args[0])


class HomeLabelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'ANYTUBE_DATA': self.temp.name})
        self.env.start()
        self.client = TestClient(app).__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.env.stop()
        self.temp.cleanup()

    def home(self, source_id, ranking='default'):
        async def worker(payload):
            return {'items': [{'title': 'ok', 'url': 'https://example.org/v'}]}
        with patch('app.main.run_worker', side_effect=worker):
            return self.client.get(f'/api/home/{source_id}?ranking={ranking}').json()

    def test_a_search_standing_in_for_a_home_feed_is_named_as_such(self):
        result = self.home('Youtube')
        self.assertEqual(result['feed_kind'], 'search')
        self.assertEqual(result['label'], 'Recherche : vidéos')
        views = self.home('Youtube', 'views')
        self.assertEqual(views['feed_kind'], 'search')
        self.assertIn('recherche : vidéos', views['label'])

    def test_a_real_platform_feed_is_not_announced_as_a_search(self):
        self.client.post('/api/sources', json={'id': 'Niconico'}, headers=HEADERS)
        for ranking in ('default', 'views', 'recent'):
            with self.subTest(ranking=ranking):
                result = self.home('Niconico', ranking)
                self.assertEqual(result['feed_kind'], 'feed')
                self.assertNotIn('recherche', result['label'].casefold())

    def test_a_search_backed_home_url_is_labelled_as_a_search(self):
        config = default_connector('Dailymotion')
        config['home_kind'] = 'search'
        self.client.patch('/api/sources/Dailymotion', json={'connector': config}, headers=HEADERS)
        result = self.home('Dailymotion')
        self.assertEqual(result['feed_kind'], 'search')
        self.assertIn('Recherche utilisée comme accueil', result['label'])


class SearchRankingRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'ANYTUBE_DATA': self.temp.name})
        self.env.start()
        self.client = TestClient(app).__enter__()
        self.client.post('/api/sources', json={'id': 'ArchiveOrg'}, headers=HEADERS)
        for source_id in ('Youtube', 'Dailymotion'):
            self.client.patch(f'/api/sources/{source_id}', json={'enabled': False}, headers=HEADERS)

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.env.stop()
        self.temp.cleanup()

    def search(self, **body):
        seen = {}

        async def worker(payload):
            seen['payload'] = payload
            return {'items': [{'title': 'ok', 'url': 'https://example.org/v'}], 'native_page': True,
                    'has_more': True}
        with patch('app.main.run_worker', side_effect=worker):
            response = self.client.post('/api/search', json={'query': 'nature', **body}, headers=HEADERS)
        return response, seen.get('payload')

    def test_a_declared_ranking_reaches_the_worker_and_paginates_natively(self):
        response, payload = self.search(ranking='trending', limit=2)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload['connector']['search_url'],
                         default_connector('ArchiveOrg')['search_trending_url'])
        self.assertEqual(payload['page_size'], 2)
        self.assertIn('ArchiveOrg', response.json()['next_cursors'])

    def test_native_pagination_stops_at_the_documented_provider_window(self):
        self.client.post('/api/sources', json={'id': 'Niconico'}, headers=HEADERS)
        self.client.patch('/api/sources/ArchiveOrg', json={'enabled': False}, headers=HEADERS)
        from app.pagination import encode
        from app.verification import revision
        from app.store import saved_sources
        source = next(s for s in saved_sources() if s['id'] == 'Niconico')
        self.assertEqual(capabilities(source['connector'])['max_results'], 1600)
        context = ['Niconico', revision(source['connector']), 'nature', 'default', 'any', 0, 2]
        beyond = self.search(limit=2, cursors={'Niconico': encode(1600, context)})[0].json()
        self.assertEqual(beyond['items'], [])
        self.assertEqual(beyond['next_cursors'], {})

    def test_an_undeclared_ranking_or_filter_is_refused_rather_than_ignored(self):
        for body in ({'ranking': 'views', 'sources': ['ArchiveOrg']},):
            self.assertEqual(self.search(**body)[0].status_code, 200)
        self.client.post('/api/sources', json={'id': 'BiliBili'}, headers=HEADERS)
        response, _ = self.search(ranking='trending')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.search(duration='short')[0].status_code, 400)


if __name__ == '__main__':
    unittest.main()
