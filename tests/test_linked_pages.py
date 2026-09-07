import io
import json
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from app.connectors import Connector, search_json


class LinkedPageTests(unittest.TestCase):
    def config(self):
        return Connector(kind='json', search_url='https://example.com/search?q={query}', results_path='/data',
            pagination={'mode':'page','page_url_path':'/next','initial_results_path':'/items'}).model_dump()

    def test_discovers_endpoint_and_requests_correct_page(self):
        opener = Mock(); opener.open.side_effect = [io.BytesIO(json.dumps({
            'items':[1], 'next':'https://example.com/zone/new-id?q=test&page=1'}).encode()),
            io.BytesIO(json.dumps({'data':[{'title':'Third page','url':'https://example.com/video'}]}).encode())]
        with patch('app.connectors.build_opener', return_value=opener):
            result = search_json(self.config(), 'test', 3, offset=6, return_page=True)
        target = urlsplit(opener.open.call_args.args[0].full_url)
        self.assertEqual(target.path, '/zone/new-id')
        self.assertEqual(parse_qs(target.query)['page'], ['3'])
        self.assertEqual(result['items'][0]['title'], 'Third page')

    def test_empty_initial_list_and_private_link(self):
        for data, refused in [({'items':[]},False), ({'items':[1],'next':'http://127.0.0.1/private'},True)]:
            opener = Mock(); opener.open.return_value = io.BytesIO(json.dumps(data).encode())
            with patch('app.connectors.build_opener', return_value=opener):
                if refused:
                    with self.assertRaises(ValueError): search_json(self.config(), 'test', 3)
                else:
                    self.assertEqual(search_json(self.config(), 'test', 3), [])
            self.assertEqual(opener.open.call_count, 1)
