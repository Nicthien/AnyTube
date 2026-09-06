import re
import unittest
import tempfile
from unittest.mock import patch
from pathlib import Path

from support import TestClient
from app.main import app


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.env = patch.dict('os.environ', {'ANYTUBE_DATA': self.folder.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.folder.cleanup()

    def test_service_and_installed_catalog(self):
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/health').json()['status'], 'ok')
            result = client.get('/api/sources?q=youtube').json()
            self.assertGreater(result['total'], 0)
            self.assertTrue(all('youtube' in item['name'].lower() for item in result['items']))
            self.assertEqual(client.get('/api/sources?q=not-a-real-extractor-xyz').json()['items'], [])
            self.assertEqual(client.get('/').status_code, 200)

    def test_no_native_dialogs(self):
        # Conservative guard: also rejects member/bracket access and aliasing.
        forbidden = re.compile(r'\b(?:alert|confirm|prompt)\b')
        for path in Path('app').rglob('*'):
            if path.suffix in {'.js', '.jsx', '.ts', '.tsx', '.html'}:
                self.assertIsNone(forbidden.search(path.read_text(encoding='utf-8')), str(path))
