"""One template, many self-hosted instances. No network is used here."""
import os
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from support import TestClient
from app.catalog import catalog, playback_supported
from app.connectors import Connector, default_connector, instance_host
from app.main import app

HEADERS = {'X-AnyTube': '1'}
HOME_KEYS = ('search_url', 'search_views_url', 'search_recent_url',
             'home_url', 'home_trending_url', 'home_views_url', 'home_recent_url')


class InstanceHostTests(unittest.TestCase):
    def test_a_bare_domain_a_url_and_a_default_are_all_accepted(self):
        self.assertEqual(instance_host('tilvids.com'), 'tilvids.com')
        self.assertEqual(instance_host('https://Video.Blender.ORG'), 'video.blender.org')
        self.assertEqual(instance_host('', 'framatube.org'), 'framatube.org')
        self.assertEqual(instance_host('   ', 'framatube.org'), 'framatube.org')

    def test_the_host_can_never_reach_a_private_or_disguised_address(self):
        for value in ('http://127.0.0.1', 'localhost', 'machine.local', 'https://10.0.0.4',
                      'https://user:secret@example.org', 'https://example.org:8443',
                      'https://example.org/api/v1', 'https://example.org?q=1', 'ftp://example.org'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                instance_host(value)


class InstanceTemplateTests(unittest.TestCase):
    def test_the_chosen_host_is_fixed_in_every_url_of_the_connector(self):
        config = default_connector('PeerTube', 'tilvids.com')
        for key in HOME_KEYS:
            with self.subTest(field=key):
                self.assertEqual(urlsplit(config[key]).hostname, 'tilvids.com')
        Connector.model_validate(config)
        self.assertEqual(urlsplit(default_connector('PeerTube')['search_url']).hostname, 'framatube.org')

    def test_a_query_can_never_choose_the_host(self):
        config = default_connector('PeerTube', 'tilvids.com')
        for key in HOME_KEYS:
            with self.subTest(field=key):
                self.assertNotIn('{', urlsplit(config[key]).netloc)
        with self.assertRaises((ValueError, Exception)):
            Connector.model_validate({**config, 'search_url': 'https://{query}.example.org/api?q={query}'})

    def test_the_catalogue_announces_which_templates_have_instances(self):
        entries = {item['id']: item for item in catalog()}
        self.assertEqual(entries['PeerTube']['instance_software'], 'PeerTube')
        self.assertEqual(entries['PeerTube']['default_instance'], 'framatube.org')
        self.assertNotIn('instance_software', entries['Dailymotion'])

    def test_playback_support_is_reported_per_instance_not_assumed(self):
        self.assertTrue(playback_supported('PeerTube', 'framatube.org'))
        self.assertTrue(playback_supported('PeerTube', 'tilvids.com'))
        self.assertFalse(playback_supported('PeerTube', 'instance-inconnue.example'))
        self.assertIsNone(playback_supported('Dailymotion', 'example.org'))


class InstanceRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'ANYTUBE_DATA': self.temp.name})
        self.env.start()
        self.client = TestClient(app).__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.env.stop()
        self.temp.cleanup()

    def test_several_instances_of_one_template_live_side_by_side(self):
        first = self.client.post('/api/sources', json={'id': 'PeerTube', 'instance': 'tilvids.com'},
                                 headers=HEADERS)
        second = self.client.post('/api/sources', json={'id': 'PeerTube', 'instance': 'video.blender.org'},
                                  headers=HEADERS)
        plain = self.client.post('/api/sources', json={'id': 'PeerTube'}, headers=HEADERS)
        self.assertEqual([first.status_code, second.status_code, plain.status_code], [201, 201, 201])
        created = [first.json(), second.json(), plain.json()]
        self.assertEqual(len({item['id'] for item in created}), 3)
        self.assertEqual(first.json()['name'], 'PeerTube · tilvids.com')
        self.assertEqual(first.json()['playback_extractor'], 'installed')
        self.assertEqual(urlsplit(second.json()['connector']['search_url']).hostname, 'video.blender.org')
        self.assertEqual(urlsplit(plain.json()['connector']['search_url']).hostname, 'framatube.org')

    def test_an_instance_unknown_to_the_extractor_is_added_but_announced(self):
        created = self.client.post('/api/sources', json={'id': 'PeerTube', 'instance': 'instance-inconnue.example'},
                                   headers=HEADERS)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()['playback_extractor'], 'missing')

    def test_a_refused_host_never_becomes_a_source(self):
        for value in ('127.0.0.1', 'localhost', 'https://example.org/api'):
            with self.subTest(value=value):
                response = self.client.post('/api/sources', json={'id': 'PeerTube', 'instance': value},
                                            headers=HEADERS)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post('/api/sources', json={'id': 'Dailymotion', 'instance': 'x.example'},
                                          headers=HEADERS).status_code, 400)
        self.assertEqual(len(self.client.get('/api/sources').json()['items']), 2)

    def test_the_template_preview_answers_for_a_chosen_instance(self):
        preview = self.client.get('/api/templates/PeerTube?instance=tilvids.com').json()
        self.assertEqual(preview['instance'], 'tilvids.com')
        self.assertEqual(preview['playback_extractor'], 'installed')
        self.assertEqual(urlsplit(preview['connector']['search_url']).hostname, 'tilvids.com')
        self.assertEqual(self.client.get('/api/templates/PeerTube').json()['instance'], 'framatube.org')
        self.assertEqual(self.client.get('/api/templates/Dailymotion').json()['playback_extractor'], None)

    def test_an_instance_source_still_compares_against_its_template(self):
        created = self.client.post('/api/sources', json={'id': 'PeerTube', 'instance': 'tilvids.com'},
                                   headers=HEADERS).json()
        delta = self.client.get(f'/api/sources/{created["id"]}/template-diff').json()
        changed = {item['field'] for item in delta['differences']}
        self.assertIn('search_url', changed)
        self.assertEqual(delta['id'], 'PeerTube')


if __name__ == '__main__':
    unittest.main()
