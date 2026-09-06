import tempfile
import unittest
from unittest.mock import patch
from support import TestClient
from app.main import app
from app.connectors import default_connector
from app.verification import evidence, record


class VerificationTests(unittest.TestCase):
    def test_config_and_engine_changes_invalidate_evidence(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'ANYTUBE_DATA': folder}), TestClient(app):
            config = default_connector('Dailymotion')
            record(config, 'chat', 'verified', 3)
            record(config, 'nature', 'empty')
            self.assertEqual(len(evidence(config)), 2)
            self.assertFalse(evidence({**config, 'home_query': 'different'}))
            with patch('app.verification.engine_version', return_value='next-version'):
                self.assertFalse(evidence(config))

    def test_template_diff_and_failure_evidence(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'ANYTUBE_DATA': folder}), TestClient(app) as client:
            headers = {'X-AnyTube': '1'}
            config = default_connector('Dailymotion')
            config['home_query'] = 'ma préférence'
            client.patch('/api/sources/Dailymotion', json={'connector': config}, headers=headers).raise_for_status()
            delta = client.get('/api/sources/Dailymotion/template-diff').json()
            self.assertEqual(delta['differences'][0]['field'], 'home_query')
            with patch('app.main.run_worker', side_effect=RuntimeError('Indisponible')):
                response = client.post('/api/connectors/test', json={'connector': config, 'query': 'chat'}, headers=headers)
                self.assertEqual(response.status_code, 400)
            self.assertEqual(evidence(config)[0]['status'], 'temporarily_unavailable')

    def test_failed_source_preserves_other_results_and_retry_cursor(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'ANYTUBE_DATA': folder}), TestClient(app) as client:
            async def worker(payload):
                if payload['source'] == 'Youtube':
                    raise RuntimeError('Temporary failure')
                return {'items': [{'url': 'https://example.org/one', 'title': 'One'}]}
            with patch('app.main.run_worker', side_effect=worker):
                result = client.post('/api/search', json={'query': 'nature'}, headers={'X-AnyTube':'1'}).json()
            self.assertEqual(len(result['items']), 1)
            self.assertEqual(len(result['errors']), 1)
            self.assertIn('Youtube', result['next_cursors'])
