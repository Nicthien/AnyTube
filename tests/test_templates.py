import unittest
import io
from unittest.mock import patch
from yt_dlp.extractor import gen_extractor_classes
from app.catalog import catalog, search_prefixes
from app.connectors import Connector, default_connector, search_json
from app.worker import run


class TemplateTests(unittest.TestCase):
    def test_every_catalog_entry_has_a_valid_consistent_template(self):
        classes = list(gen_extractor_classes())
        ids = {cls.ie_key() for cls in classes}
        for entry in catalog():
            with self.subTest(source=entry['id']):
                config = Connector.model_validate(default_connector(entry['id']))
                self.assertIn(config.extractor, ids)
                self.assertEqual(entry['search'], config.kind != 'url')
                if config.kind == 'ytdlp':
                    for pattern in (config.search_url, config.home_url, config.home_views_url, config.home_recent_url, config.home_trending_url):
                        if pattern:
                            target = pattern.format(query='nature', limit=3)
                            self.assertTrue(any(c.ie_key() != 'Generic' and c.suitable(target) for c in classes), target)
        for key in search_prefixes():
            self.assertTrue(next(e for e in catalog() if e['id'] == key)['search'])

    def test_url_search_and_home_use_the_configured_template_and_limit(self):
        config = default_connector('YoutubeMusicSearchURL')
        with patch('app.worker.YoutubeDL') as downloader:
            downloader.return_value.__enter__.return_value.extract_info.return_value = {'entries': []}
            run({'mode': 'search', 'connector': config, 'query': 'chat & été', 'limit': 3})
            target = downloader.return_value.__enter__.return_value.extract_info.call_args.args[0]
            self.assertIn('chat%20%26%20%C3%A9t%C3%A9', target)
            self.assertEqual(downloader.call_args.args[0]['playlistend'], 3)
            config['home_url'] = 'https://www.youtube.com/results?search_query={query}&sp=CAMSAhAB'
            run({'mode': 'search', 'connector': config, 'query': 'nature', 'limit': 10, 'home': True})
            self.assertIn('sp=CAMSAhAB', downloader.return_value.__enter__.return_value.extract_info.call_args.args[0])

    def test_ytdlp_templates_reject_private_urls_and_unknown_variables(self):
        for pattern in ('http://127.0.0.1/?q={query}', 'https://{query}.example.org/', 'https://example.org/?q={unknown}'):
            with self.subTest(pattern=pattern), self.assertRaises(ValueError):
                Connector(kind='ytdlp', search_url=pattern)

    def test_archive_thumbnail_and_missing_optional_metadata(self):
        with patch('app.connectors.build_opener') as opener:
            opener.return_value.open.return_value = io.BytesIO(b'{"response":{"docs":[{"identifier":"id / test","title":"Film"}]}}')
            items = search_json(default_connector('ArchiveOrg'), 'nature', 2)
            self.assertEqual(items[0]['thumbnail'], 'https://archive.org/services/img/id%20%2F%20test')
            self.assertEqual(items[0]['webpage_url'], 'https://archive.org/details/id%20%2F%20test')
            self.assertIsNone(items[0]['view_count'])
