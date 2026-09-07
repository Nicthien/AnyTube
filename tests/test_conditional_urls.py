import io
import json
import unittest
from unittest.mock import Mock, patch

from app.connectors import Connector, default_connector, search_json


class ConditionalUrlTests(unittest.TestCase):
    def test_both_url_branches_are_validated_before_any_request(self):
        for field in ('video_url', 'video_url_false'):
            config = default_connector('OpenRec')
            config[field] = 'http://127.0.0.1/private/{id}'
            with self.subTest(field=field), self.assertRaises(ValueError):
                Connector.model_validate(config)

    def test_openrec_routes_each_type_and_escapes_ids(self):
        config = default_connector('OpenRec')
        opener = Mock(); opener.open.return_value = io.BytesIO(json.dumps([
            {'id':'one', 'title':'Replay', 'is_live':True},
            {'id':'two/three', 'title':'Video', 'is_live':False},
        ]).encode())
        with patch('app.connectors.build_opener', return_value=opener):
            items = search_json(config, 'test', 3)
        self.assertEqual(items[0]['webpage_url'], 'https://www.mellow-fan.com/live/one')
        self.assertEqual(items[1]['webpage_url'], 'https://www.mellow-fan.com/movie/two%2Fthree')

    def test_missing_or_string_boolean_is_not_guessed(self):
        for flag in (None, 'false', 0):
            opener = Mock(); opener.open.return_value = io.BytesIO(json.dumps([
                {'id':'one', 'title':'Video', 'is_live':flag}]).encode())
            with patch('app.connectors.build_opener', return_value=opener):
                with self.assertRaisesRegex(ValueError, 'booléen'):
                    search_json(default_connector('OpenRec'), 'test', 3)
