import unittest
from unittest.mock import patch

from app.worker import run


class ArteCollectionTests(unittest.TestCase):
    def test_flat_collection_keeps_metadata_without_episode_extraction(self):
        payload = {'programs':[{'title':'Canada','videos':[{
            'kind':'SHOW', 'url':'https://www.arte.tv/fr/videos/112214-001-A/canada/',
            'programId':'112214-001-A', 'title':'Canada', 'subtitle':'Le Québec boréal',
            'durationSeconds':2589, 'firstBroadcastDate':'2024-10-07T14:33:29Z',
            'mainImage':{'url':'https://example.com/image.jpg'}, 'shortDescription':'Forêts'}]}]}
        with patch('yt_dlp.extractor.common.InfoExtractor._download_json', return_value=payload) as fetch:
            result = run({'mode':'collection','url':'https://www.arte.tv/fr/videos/RC-025777/canada/', 'limit':3})
        item = result['items'][0]
        self.assertEqual(item['title'], 'Canada — Le Québec boréal')
        self.assertEqual(item['id'], '112214-001-A')
        self.assertEqual(item['published'], '2024-10-07')
        self.assertEqual(item['duration'], 2589)
        self.assertEqual(item['thumbnail'], 'https://example.com/image.jpg')
        self.assertEqual(fetch.call_count, 1)
