import unittest
from unittest.mock import Mock

from app.microsoft import AnyTubeMicrosoftLearnPlaylistIE
from app.worker import normalize


class MicrosoftCollectionTests(unittest.TestCase):
    def test_metadata_and_pagination_without_episode_requests(self):
        extractor = AnyTubeMicrosoftLearnPlaylistIE()
        extractor._download_json = Mock(side_effect=[
            {'count': 2, 'results': [{'url': '/shows/python/strings/', 'title': 'Strings',
                'entry_id': 'one', 'duration_in_milliseconds': 280000,
                'upload_date': '2019-09-17T13:06:38.254Z', 'image_url': 'https://example.com/image.jpg'}]},
            {'count': 2, 'results': [{'url': '/shows/python/numbers/', 'title': 'Numbers'}]},
        ])
        entries = list(extractor._entries('https://learn.microsoft.com/api/example', 'python'))
        first = normalize(entries[0])
        self.assertEqual(first['title'], 'Strings')
        self.assertEqual(first['duration'], 280)
        self.assertEqual(first['published'], '2019-09-17')
        self.assertEqual(first['url'], 'https://learn.microsoft.com/en-us/shows/python/strings/')
        self.assertEqual(first['id'], 'one')
        self.assertEqual(extractor._download_json.call_count, 2)
        self.assertEqual(extractor._download_json.call_args.kwargs['query']['$skip'], 1)

    def test_external_paths_are_not_accepted(self):
        extractor = AnyTubeMicrosoftLearnPlaylistIE()
        extractor._download_json = Mock(return_value={'count': 2, 'results': [
            {'url': '//other.example/video'}, {'url': 'https://other.example/video'}]})
        self.assertEqual(list(extractor._entries('https://learn.microsoft.com/api/example', 'python')), [])
