import io
import json
import unittest
from unittest.mock import Mock, patch

from app.connectors import Connector, search_json


class ThumbnailSubstitutionTests(unittest.TestCase):
    def test_declared_size_replaces_marker_without_changing_other_fields(self):
        config = Connector(kind='json', search_url='https://example.com/search?q={query}', results_path='',
                           thumbnail_substitutions={'__SIZE__':'480x270'})
        opener = Mock(); opener.open.return_value = io.BytesIO(json.dumps([{
            'title':'Nature', 'url':'https://example.com/video',
            'thumbnail':'https://example.com/image/__SIZE__?type=TEXT'}]).encode())
        with patch('app.connectors.build_opener', return_value=opener):
            item = search_json(config.model_dump(), 'nature', 3)[0]
        self.assertEqual(item['thumbnail'], 'https://example.com/image/480x270?type=TEXT')
        self.assertEqual(item['title'], 'Nature')

    def test_empty_marker_is_refused(self):
        with self.assertRaises(ValueError):
            Connector(thumbnail_substitutions={'':'large'})
