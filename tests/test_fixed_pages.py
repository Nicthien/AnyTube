import io
import json
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from app.connectors import Connector, search_json


class FixedPageTests(unittest.TestCase):
    def test_bracketed_page_parameter_is_encoded_and_preserves_query(self):
        config = Connector(kind='json', search_url='https://example.com/api?q={query}',
                           results_path='', pagination={'mode': 'page', 'parameter': 'page[number]'})
        opener = Mock()
        opener.open.return_value = io.BytesIO(b'[]')
        with patch('app.connectors.build_opener', return_value=opener):
            search_json(config.model_dump(), 'science & art', 3, offset=3)
        query = parse_qs(urlsplit(opener.open.call_args.args[0].full_url).query)
        self.assertEqual(query['page[number]'], ['2'])
        self.assertEqual(query['q'], ['science & art'])

    def test_zero_based_provider_keeps_first_page_and_crossing_window(self):
        config = Connector(kind='json', search_url='https://example.com/api?q={query}',
                           results_path='', pagination={'mode': 'page', 'fixed_page_size': 24,
                                                       'first_page': 0, 'parameter': 'pageNumber'})
        entries = [{'title': str(n), 'url': f'https://example.com/video/{n}'} for n in range(50)]
        calls = []
        def respond(request, **kwargs):
            page = int(parse_qs(urlsplit(request.full_url).query)['pageNumber'][0])
            calls.append(page)
            return io.BytesIO(json.dumps(entries[page*24:(page+1)*24]).encode())
        opener = Mock(); opener.open.side_effect = respond
        with patch('app.connectors.build_opener', return_value=opener):
            first = search_json(config.model_dump(), 'test', 3)
            crossing = search_json(config.model_dump(), 'test', 4, offset=22)
        self.assertEqual([x['title'] for x in first], ['0', '1', '2'])
        self.assertEqual([x['title'] for x in crossing], ['22', '23', '24', '25'])
        self.assertEqual(calls, [0, 0, 1])

    def test_windows_cross_provider_boundaries_without_skips(self):
        config = Connector(kind='json', search_url='https://example.com/api?q={query}',
                           results_path='', pagination={'mode': 'page', 'fixed_page_size': 40})
        entries = [{'id': n, 'title': str(n), 'url': f'https://example.com/video/{n}'} for n in range(85)]
        calls = []
        def respond(request, **kwargs):
            page = int(parse_qs(urlsplit(request.full_url).query)['page'][0])
            calls.append(page)
            return io.BytesIO(json.dumps(entries[(page-1)*40:page*40]).encode())
        opener = Mock(); opener.open.side_effect = respond
        with patch('app.connectors.build_opener', return_value=opener):
            result = search_json(config.model_dump(), 'test', 8, offset=38, return_page=True)
            self.assertEqual([x['title'] for x in result['items']], list(map(str, range(38, 46))))
            self.assertEqual(calls, [1, 2])
            self.assertTrue(result['has_more'])
            calls.clear()
            result = search_json(config.model_dump(), 'test', 8, offset=80, return_page=True)
            self.assertEqual([x['title'] for x in result['items']], list(map(str, range(80, 85))))
            self.assertEqual(calls, [3])
            self.assertFalse(result['has_more'])

    def test_remaining_items_inside_short_final_provider_page(self):
        config = Connector(kind='json', search_url='https://example.com/api?q={query}', results_path='',
                           pagination={'mode':'page', 'fixed_page_size':40})
        opener = Mock(); opener.open.return_value = io.BytesIO(json.dumps([
            {'title':str(n), 'url':f'https://example.com/{n}'} for n in range(5)]).encode())
        with patch('app.connectors.build_opener', return_value=opener):
            result = search_json(config.model_dump(), 'test', 3, return_page=True)
        self.assertEqual(len(result['items']), 3)
        self.assertTrue(result['has_more'])
