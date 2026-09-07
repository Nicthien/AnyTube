import unittest
from scripts.scaffold_connector import scaffold


class ScaffoldTests(unittest.TestCase):
    def test_infers_nested_nrk_response_without_copying_data(self):
        data = {'hits': [{'hit': {'id': 'one', 'title': 'A private sample title', 'url': 'serie/one',
                                 'token': 'do-not-copy'}}]}
        config = scaffold(data, 'NRKTV', 'https://psapi.nrk.no/search?q={query}', base_url='https://tv.nrk.no/')
        self.assertEqual(config['results_path'], '/hits')
        self.assertEqual(config['mapping']['url'], '/hit/url')
        self.assertNotIn('do-not-copy', str(config))
        self.assertNotIn('A private sample title', str(config))

    def test_multiple_lists_require_explicit_selection(self):
        row = {'title': 'Video', 'url': 'https://example.org/video'}
        with self.assertRaises(ValueError):
            scaffold({'videos': [row], 'suggestions': [row]}, 'Wikimedia', 'https://example.org/search?q={query}')

    def test_malformed_later_rows_do_not_produce_valid_mapping(self):
        with self.assertRaises(ValueError):
            scaffold({'data': [{'title': 'Video', 'url': 'https://example.org/video'}, {'title': 1}]},
                     'Wikimedia', 'https://example.org/search?q={query}')

    def test_access_key_in_endpoint_is_refused(self):
        with self.assertRaises(ValueError):
            scaffold({}, 'Wikimedia', 'https://example.org/search?q={query}&api_key=secret')
